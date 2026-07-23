"""
核心检测逻辑 - 自动找到目标列并逐行判断是否为指定元素类型
支持：主题域分类、主题域分组、主题域、业务对象、逻辑实体、业务属性
"""
import json
import re
import pandas as pd
from pathlib import Path
from llm import chat
from rules import build_batch_prompt, build_check_prompt, ELEMENT_TYPES


def find_target_column(df: pd.DataFrame) -> tuple[str, list[str]]:
    """
    自动识别包含待检测事物的列。
    """
    keywords = [
        "业务对象唯一标识", "业务对象名称", "业务对象编码",
        "逻辑实体名称", "逻辑实体唯一标识",
        "属性名称", "属性唯一标识",
        "主题域名称", "主题域分类", "主题域分组",
        "对象名称", "对象名", "唯一标识",
        "业务对象", "名称", "实体", "单据", "事物"
    ]
    for col in df.columns:
        col_str = str(col).strip()
        for kw in keywords:
            if kw in col_str:
                values = df[col].dropna().astype(str).str.strip().tolist()
                values = [v for v in values if v and v != "nan" and len(v) > 1]
                if values:
                    return col_str, values

    # 启发式
    candidates = []
    for col in df.columns:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        sample = series.head(20)
        str_sample = sample.astype(str)

        numeric_count = str_sample.apply(lambda x: x.replace(".", "").replace("-", "").isdigit()).sum()
        if numeric_count > len(str_sample) * 0.7:
            continue

        date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')
        date_count = str_sample.apply(lambda x: bool(date_pattern.match(str(x)))).sum()
        if date_count > len(str_sample) * 0.5:
            continue

        avg_len = str_sample.apply(len).mean()
        if avg_len > 80:
            continue

        values = series.astype(str).str.strip().tolist()
        values = [v for v in values if v and v != "nan" and len(v) > 1]
        if len(values) >= 2:
            candidates.append((str(col), values, avg_len))

    if candidates:
        candidates.sort(key=lambda x: (x[2], -len(x[1])))
        best = candidates[0]
        return best[0], best[1]

    col = str(df.columns[0])
    values = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
    values = [v for v in values if v and v != "nan" and len(v) > 1]
    return col, values


def check_items_batch(items: list[str], element_type: str = "业务对象", batch_size: int = 10) -> list[dict]:
    """批量调用 LLM 判断"""
    all_results = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        numbered = "\n".join(f"{j+1}. {item}" for j, item in enumerate(batch))

        prompt = build_batch_prompt(element_type, numbered)
        if not prompt:
            for item in batch:
                all_results.append({"item": item, "is_bo": None, "confidence": "low", "reason": f"未知元素类型: {element_type}"})
            continue

        messages = [
            {"role": "system", "content": f"你是数据治理专家，严格按JSON格式输出结果。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response = chat(messages, temperature=0.1)
            parsed = parse_llm_response(response, batch)
            all_results.extend(parsed)
        except Exception as e:
            for item in batch:
                all_results.append({"item": item, "is_bo": None, "confidence": "low", "reason": f"AI分析出错: {str(e)}"})

    return all_results


def parse_llm_response(response: str, items: list[str]) -> list[dict]:
    """解析 LLM 返回的 JSON 结果"""
    json_match = re.search(r'\{[\s\S]*"results"[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            results = data.get("results", [])
            if len(results) == len(items):
                return results
            elif len(results) > 0:
                result_map = {r["item"]: r for r in results}
                return [
                    result_map.get(item, {"item": item, "is_bo": None, "confidence": "low", "reason": "未返回该项结果"})
                    for item in items
                ]
        except json.JSONDecodeError:
            pass

    results = []
    for item in items:
        results.append({"item": item, "is_bo": None, "confidence": "low", "reason": "无法自动解析，请人工判断"})
    return results


def check_single_item(item: str, element_type: str = "业务对象") -> list[dict]:
    """构建单个事物详细判断的消息列表"""
    prompt = build_check_prompt(element_type)
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"请判断「{item}」是否是{element_type}？"}
    ]


def process_excel(file_path: str, element_type: str = "业务对象") -> dict:
    """处理上传的 Excel 文件（支持多 Sheet），跨所有子表自动找到目标列"""
    path = Path(file_path)
    if not path.exists():
        return {"error": "文件不存在"}

    try:
        all_sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        return {"error": f"读取Excel失败: {str(e)}"}

    if not all_sheets:
        return {"error": "Excel文件为空"}

    # 根据元素类型确定搜索关键词
    type_keywords = {
        "主题域分类": ["主题域分类", "分类名称"],
        "主题域分组": ["主题域分组", "分组名称"],
        "主题域": ["主题域名称", "主题域"],
        "业务对象": ["业务对象唯一标识", "业务对象名称", "业务对象编码", "业务对象"],
        "逻辑实体": ["逻辑实体名称", "逻辑实体唯一标识", "逻辑实体编码", "逻辑实体"],
        "业务属性": ["属性名称", "属性唯一标识", "属性编码", "业务属性"],
    }
    search_keywords = type_keywords.get(element_type, ["名称", "唯一标识"])
    # 通用关键词兜底
    search_keywords += ["唯一标识", "对象名称", "对象名", "名称", "实体", "单据", "事物"]
    # 去重
    search_keywords = list(dict.fromkeys(search_keywords))

    best_sheet = None
    best_col = None
    best_values = []
    best_keyword = None

    sheets_info = []
    for sheet_name, df in all_sheets.items():
        if df.empty:
            continue
        col_names = [str(c).strip() for c in df.columns]
        sheets_info.append({"sheet": sheet_name, "columns": col_names, "rows": len(df)})

        for kw in search_keywords:
            for col in df.columns:
                col_str = str(col).strip()
                if kw in col_str:
                    values = df[col].dropna().astype(str).str.strip().tolist()
                    values = [v for v in values if v and v != "nan" and len(v) > 1]
                    if values and len(values) > len(best_values):
                        best_sheet = sheet_name
                        best_col = col_str
                        best_values = values
                        best_keyword = kw
                    break
            if best_values:
                break
        if best_keyword and best_keyword in search_keywords[:3]:
            break

    if not best_values:
        for sheet_name, df in all_sheets.items():
            if df.empty:
                continue
            col, values = find_target_column(df)
            if len(values) > len(best_values):
                best_sheet = sheet_name
                best_col = col
                best_values = values

    if not best_values:
        return {"error": "所有子表中均未找到有效的目标列数据"}

    unique_values = list(dict.fromkeys(best_values))
    results = check_items_batch(unique_values, element_type=element_type)

    bo_count = sum(1 for r in results if r.get("is_bo") is True)
    not_bo_count = sum(1 for r in results if r.get("is_bo") is False)
    unknown_count = sum(1 for r in results if r.get("is_bo") is None)

    return {
        "total_rows": len(best_values),
        "unique_items": len(unique_values),
        "target_column": best_col,
        "target_sheet": best_sheet,
        "matched_keyword": best_keyword,
        "element_type": element_type,
        "total_sheets": len(all_sheets),
        "sheets_info": sheets_info,
        "results": results,
        "summary": {"is_bo": bo_count, "not_bo": not_bo_count, "unknown": unknown_count}
    }

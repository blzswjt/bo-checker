"""
核心检测逻辑 - 自动找到目标列并逐行判断是否为业务对象
"""
import json
import re
import pandas as pd
from pathlib import Path
from llm import chat
from rules import BATCH_CHECK_PROMPT, CHECK_PROMPT


def find_target_column(df: pd.DataFrame) -> tuple[str, list[str]]:
    """
    自动识别包含待检测事物的列。
    策略：
    1. 优先找列名包含"业务对象"、"名称"、"对象"等关键词的列
    2. 否则找非数值、非日期、文本内容较短且有意义的那一列
    返回 (列名, 该列所有非空值列表)
    """
    # 关键词优先匹配
    keywords = ["业务对象", "对象名称", "对象名", "名称", "实体", "单据", "事物"]
    for col in df.columns:
        col_str = str(col).strip()
        for kw in keywords:
            if kw in col_str:
                values = df[col].dropna().astype(str).str.strip().tolist()
                values = [v for v in values if v and v != "nan" and len(v) > 1]
                if values:
                    return col_str, values

    # 启发式：找文本列（非纯数字、非日期），且值较短（像名称而非描述）
    candidates = []
    for col in df.columns:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        sample = series.head(20)
        str_sample = sample.astype(str)

        # 排除纯数字列
        numeric_count = str_sample.apply(lambda x: x.replace(".", "").replace("-", "").isdigit()).sum()
        if numeric_count > len(str_sample) * 0.7:
            continue

        # 排除日期列
        date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')
        date_count = str_sample.apply(lambda x: bool(date_pattern.match(str(x)))).sum()
        if date_count > len(str_sample) * 0.5:
            continue

        # 排除太长的描述列（平均长度>50字的可能是描述）
        avg_len = str_sample.apply(len).mean()
        if avg_len > 80:
            continue

        # 计算有效值数量
        values = series.astype(str).str.strip().tolist()
        values = [v for v in values if v and v != "nan" and len(v) > 1]
        if len(values) >= 2:
            candidates.append((str(col), values, avg_len))

    if candidates:
        # 优先选平均长度较短（更像名称）且行数较多的列
        candidates.sort(key=lambda x: (x[2], -len(x[1])))
        best = candidates[0]
        return best[0], best[1]

    # 兜底：返回第一列
    col = str(df.columns[0])
    values = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
    values = [v for v in values if v and v != "nan" and len(v) > 1]
    return col, values


def check_items_batch(items: list[str], batch_size: int = 10) -> list[dict]:
    """
    批量调用 LLM 判断是否为业务对象。
    每批 batch_size 个，返回结构化结果。
    """
    all_results = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        numbered = "\n".join(f"{j+1}. {item}" for j, item in enumerate(batch))

        prompt = BATCH_CHECK_PROMPT.format(items=numbered)
        messages = [
            {"role": "system", "content": "你是数据治理专家，严格按JSON格式输出结果。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response = chat(messages, temperature=0.1)
            parsed = parse_llm_response(response, batch)
            all_results.extend(parsed)
        except Exception as e:
            # 解析失败时，逐个标记为无法确定
            for item in batch:
                all_results.append({
                    "item": item,
                    "is_bo": None,
                    "confidence": "low",
                    "reason": f"AI分析出错: {str(e)}"
                })

    return all_results


def parse_llm_response(response: str, items: list[str]) -> list[dict]:
    """解析 LLM 返回的 JSON 结果"""
    # 尝试提取 JSON
    json_match = re.search(r'\{[\s\S]*"results"[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            results = data.get("results", [])
            # 校验结果数量，不足时补齐
            if len(results) == len(items):
                return results
            elif len(results) > 0:
                # 按 item 名匹配
                result_map = {r["item"]: r for r in results}
                return [
                    result_map.get(item, {"item": item, "is_bo": None, "confidence": "low", "reason": "未返回该项结果"})
                    for item in items
                ]
        except json.JSONDecodeError:
            pass

    # JSON 解析失败，逐行文本解析
    results = []
    for item in items:
        # 在文本中找该项的判断
        if "是业务对象" in response and item in response:
            # 尝试简单匹配
            is_bo = "不是业务对象" not in response.split(item)[-1][:100] if item in response else None
            results.append({
                "item": item,
                "is_bo": is_bo if is_bo is not None else None,
                "confidence": "low",
                "reason": "自动解析，建议人工复核"
            })
        else:
            results.append({
                "item": item,
                "is_bo": None,
                "confidence": "low",
                "reason": "无法自动解析，请人工判断"
            })
    return results


def check_single_item(item: str) -> dict:
    """对单个事物进行详细判断（流式场景）"""
    messages = [
        {"role": "system", "content": CHECK_PROMPT},
        {"role": "user", "content": f"请判断「{item}」是否是业务对象？"}
    ]
    return messages


def process_excel(file_path: str) -> dict:
    """
    处理上传的 Excel 文件，返回完整分析结果。
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": "文件不存在"}

    # 读取 Excel
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        return {"error": f"读取Excel失败: {str(e)}"}

    if df.empty:
        return {"error": "表格为空"}

    # 获取所有列信息
    columns_info = []
    for col in df.columns:
        series = df[col].dropna()
        sample = series.head(5).astype(str).tolist()
        columns_info.append({
            "name": str(col),
            "count": len(series),
            "samples": sample
        })

    # 自动找目标列
    target_col, values = find_target_column(df)

    if not values:
        return {"error": f"列「{target_col}」中没有找到有效数据"}

    # 去重
    unique_values = list(dict.fromkeys(values))  # 保持顺序去重

    # 批量检测
    results = check_items_batch(unique_values)

    # 统计
    bo_count = sum(1 for r in results if r.get("is_bo") is True)
    not_bo_count = sum(1 for r in results if r.get("is_bo") is False)
    unknown_count = sum(1 for r in results if r.get("is_bo") is None)

    return {
        "total_rows": len(values),
        "unique_items": len(unique_values),
        "target_column": target_col,
        "all_columns": columns_info,
        "results": results,
        "summary": {
            "is_bo": bo_count,
            "not_bo": not_bo_count,
            "unknown": unknown_count
        }
    }

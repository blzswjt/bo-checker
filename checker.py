"""
核心检测逻辑
- parse_excel_file: 解析Excel结构（所有子表、列、样本数据）
- find_target_column: 自动识别目标列（关键词+启发式）
- check_items_stream: SSE流式逐批识别（生成器）
- check_single_item: 单个事物识别消息构建
"""
import json
import re
import pandas as pd
from pathlib import Path
from llm import chat, chat_stream, get_model_display_name
from rules import build_batch_prompt, build_check_prompt, ELEMENT_TYPES, recommend_element_type
import kb


def find_target_column(df: pd.DataFrame) -> tuple[str, list[str]]:
    """自动识别包含待检测事物的列"""
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


def parse_excel_file(file_path: str) -> dict:
    """
    解析Excel文件结构，返回所有子表、列信息和AI推荐列。
    不执行识别，只做结构解析。
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": "文件不存在"}

    try:
        all_sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        return {"error": f"读取Excel失败: {str(e)}"}

    if not all_sheets:
        return {"error": "Excel文件为空"}

    sheets = []
    ai_sheet = None
    ai_column = None
    ai_keyword = None

    # 通用关键词用于AI推荐
    all_keywords = [
        "业务对象唯一标识", "业务对象名称", "业务对象编码",
        "逻辑实体名称", "逻辑实体唯一标识",
        "属性名称", "属性唯一标识",
        "主题域名称", "主题域分类", "主题域分组",
        "唯一标识", "名称",
    ]

    for sheet_name, df in all_sheets.items():
        if df.empty:
            continue

        columns = []
        for col in df.columns:
            col_str = str(col).strip()
            series = df[col].dropna()
            values = series.astype(str).str.strip().tolist()
            values = [v for v in values if v and v != "nan"]
            sample = values[:5] if values else []

            columns.append({
                "name": col_str,
                "rows": len(series),
                "sample": sample,
                "unique_count": len(set(values)),
                "recommended_type": recommend_element_type(col_str),
            })

        sheets.append({
            "name": sheet_name,
            "rows": len(df),
            "columns": columns,
        })

        # AI推荐：在所有子表中找最佳匹配列
        for kw in all_keywords:
            for col_info in columns:
                if kw in col_info["name"] and col_info["rows"] > 0:
                    if ai_column is None or len(col_info["sample"]) > 0:
                        ai_sheet = sheet_name
                        ai_column = col_info["name"]
                        ai_keyword = kw
                    break
            if ai_column and ai_keyword in all_keywords[:3]:
                break
        if ai_column and ai_keyword in all_keywords[:3]:
            break

    return {
        "total_sheets": len(all_sheets),
        "sheets": sheets,
        "ai_recommendation": {
            "sheet": ai_sheet,
            "column": ai_column,
            "keyword": ai_keyword,
        }
    }


def extract_column_values(file_path: str, sheet_name: str, column_name: str) -> list[str]:
    """从Excel中提取指定子表指定列的所有非空值（去重）"""
    all_sheets = pd.read_excel(file_path, sheet_name=None)
    df = all_sheets.get(sheet_name)
    if df is None or df.empty:
        return []

    if column_name not in df.columns:
        # 尝试模糊匹配
        for col in df.columns:
            if str(col).strip() == column_name:
                column_name = col
                break

    series = df[column_name].dropna()
    values = series.astype(str).str.strip().tolist()
    values = [v for v in values if v and v != "nan" and len(v) > 1]
    return list(dict.fromkeys(values))  # 去重保序


def check_items_stream(items: list[str], element_type: str = "业务对象", batch_size: int = 5, model_id: str = None):
    """
    生成器：逐批调用LLM判断，yield SSE事件。
    集成知识库示例，结果包含逐条规则分析(rules_check)。
    """
    total = len(items)
    model_name = get_model_display_name(model_id)
    yield {"type": "start", "total": total, "element_type": element_type, "model_id": model_id, "model_name": model_name}

    # 获取知识库示例
    kb_examples = kb.get_examples(element_type)

    all_results = []

    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        numbered = "\n".join(f"{j+1}. {item}" for j, item in enumerate(batch))

        prompt = build_batch_prompt(element_type, numbered, kb_examples=kb_examples)
        if not prompt:
            for j, item in enumerate(batch):
                result = {"item": item, "is_bo": None, "confidence": "low", "reason": f"未知元素类型: {element_type}", "rules_check": []}
                all_results.append(result)
                yield {"type": "result", "index": i + j, **result}
            yield {"type": "progress", "current": min(i + len(batch), total), "total": total}
            continue

        messages = [
            {"role": "system", "content": "你是数据治理专家，严格按JSON格式输出结果，必须包含rules_check逐条规则分析。"},
            {"role": "user", "content": prompt}
        ]

        try:
            # 流式调用：实时推送思考过程
            batch_idx = i // batch_size
            yield {"type": "thinking_start", "batch_index": batch_idx}
            full_response = ""
            for token in chat_stream(messages, temperature=0.1, model_id=model_id):
                full_response += token
                yield {"type": "thinking", "batch_index": batch_idx, "token": token}
            yield {"type": "thinking_end", "batch_index": batch_idx}

            # 解析完整响应
            parsed = parse_llm_response(full_response, batch)

            for j, result in enumerate(parsed):
                all_results.append(result)
                yield {
                    "type": "result",
                    "index": i + j,
                    "item": result.get("item", batch[j]),
                    "is_bo": result.get("is_bo"),
                    "confidence": result.get("confidence", "low"),
                    "reason": result.get("reason", ""),
                    "rules_check": result.get("rules_check", []),
                }
        except Exception as e:
            for j, item in enumerate(batch):
                result = {"item": item, "is_bo": None, "confidence": "low", "reason": f"AI分析出错: {str(e)}", "rules_check": []}
                all_results.append(result)
                yield {"type": "result", "index": i + j, **result}

        yield {"type": "progress", "current": min(i + len(batch), total), "total": total}

    bo_count = sum(1 for r in all_results if r.get("is_bo") is True)
    not_bo_count = sum(1 for r in all_results if r.get("is_bo") is False)
    unknown_count = sum(1 for r in all_results if r.get("is_bo") is None)

    yield {
        "type": "done",
        "summary": {"is_bo": bo_count, "not_bo": not_bo_count, "unknown": unknown_count, "total": total}
    }


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
                result_map = {r.get("item", ""): r for r in results}
                return [
                    result_map.get(item, {"item": item, "is_bo": None, "confidence": "low", "reason": "未返回该项结果"})
                    for item in items
                ]
        except json.JSONDecodeError:
            pass

    return [{"item": item, "is_bo": None, "confidence": "low", "reason": "无法自动解析，请人工判断"} for item in items]


def check_single_item(item: str, element_type: str = "业务对象") -> list[dict]:
    """构建单个事物详细判断的消息列表"""
    prompt = build_check_prompt(element_type)
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"请判断「{item}」是否是{element_type}？"}
    ]

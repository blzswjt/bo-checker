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


def _parse_streaming_conclusions(text: str, batch: list[str]):
    """从思考文本中实时提取已完成的结论，返回 (item_index, result_dict) 列表"""
    results = []
    for line in text.split('\n'):
        line_s = line.strip()
        # 跳过JSON块内的行
        if line_s.startswith('```') or line_s.startswith('{') or line_s.startswith('"results"'):
            continue
        # 检测新事物开始: 支持多种格式
        # - **1. 事物名** / 1. 事物名 / ### 1. 事物名 / #### 1. 事物名
        # - **### 1. 事物名** / #### 1. 事物名（含####） 等混合格式
        m = re.match(r'(?:#+\s*)?(?:\*+\s*)?(\d+)[.\uff0e\u3001]\s*(.+?)(?:\s*\*+)?$', line_s)
        if m:
            num = int(m.group(1))
            name = m.group(2).strip().rstrip('*').strip()
            if 1 <= num <= len(batch):
                results.append({'idx': num - 1, 'name': name, 'conclusion': None})
            continue
        # 检测结论行: 支持多种格式
        # - 结论：是 / - **结论：** 是 / 结论：是 / **结论：** 是
        m = re.match(r'[-\-\*]*\s*\**\s*结论\**\s*[：:]\s*(.*)', line_s)
        if m and results and results[-1]['conclusion'] is None:
            conclusion_text = m.group(1).strip().lstrip('*').strip()
            if '不是' in conclusion_text or '否' in conclusion_text:
                is_bo = False
                confidence = 'high'
            elif '是' in conclusion_text:
                is_bo = True
                confidence = 'high'
            else:
                is_bo = None
                confidence = 'medium'
            results[-1]['conclusion'] = {
                'is_bo': is_bo,
                'confidence': confidence,
                'reason': conclusion_text[:80],
            }
    return results


# 正则：检测规则判断行  ✓ 【规则名】理由  或  ✗ 【规则名】理由
_RULE_CHECK_RE = re.compile(r'[✓✗]\s*【(.+?)】\s*(.*)')
# 正则：检测事物标题 - 支持 #, **, 数字+点/顿号 等各种格式
_ITEM_HEADER_RE = re.compile(r'(?:#+\s*)?(?:\*+\s*)?(\d+)[.\uff0e\u3001]\s*(.+?)(?:\s*\*+)?$')


def _detect_streaming_rule_checks(text: str, batch: list[str], last_pos: int, emitted: dict):
    """从流式文本中实时检测规则判断行，返回新检测到的规则检查列表
    emitted: {item_idx: set(rule_names)} 已发射的规则集合，会就地更新
    简单可靠方案：每次扫描全文，通过emitted去重，性能开销可忽略
    """
    new_checks = []
    current_item_idx = -1

    for line in text.split('\n'):
        line_s = line.strip()

        # 检测事物标题
        m = _ITEM_HEADER_RE.match(line_s)
        if m:
            num = int(m.group(1))
            if 1 <= num <= len(batch):
                current_item_idx = num - 1
            continue

        # 检测规则判断行
        if current_item_idx >= 0:
            m = _RULE_CHECK_RE.search(line_s)
            if m:
                rule_name = m.group(1).strip()
                reason = m.group(2).strip()
                pass_check = '✓' in line_s[:line_s.find('【')]
                if current_item_idx not in emitted:
                    emitted[current_item_idx] = set()
                if rule_name not in emitted[current_item_idx]:
                    emitted[current_item_idx].add(rule_name)
                    new_checks.append({
                        'item_idx': current_item_idx,
                        'item_name': batch[current_item_idx],
                        'rule': rule_name,
                        'pass': pass_check,
                        'reason': reason[:100],
                    })

    return new_checks


def check_items_stream(items: list[str], element_type: str = "业务对象", batch_size: int = 5, model_id: str = None):
    """
    生成器：逐批调用LLM判断，yield SSE事件。
    集成知识库示例，结果包含逐条规则分析(rules_check)。
    支持实时逐条输出：思考完一个事物的结论后立即显示结果。
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
            {"role": "system", "content": "你是数据治理专家。请先用自然语言对每个事物进行分析思考，然后再输出JSON结果。"},
            {"role": "user", "content": prompt}
        ]

        try:
            # 流式调用：实时推送思考过程 + 实时逐条检测结果
            batch_idx = i // batch_size
            yield {"type": "thinking_start", "batch_index": batch_idx}
            full_response = ""
            json_started = False
            emitted_indices = set()  # 已经通过思考解析发射的结果索引
            _last_parse_len = 0  # 上次解析到的位置，避免重复解析
            _rule_check_emitted = {}  # {item_idx: set(rule_names)} 已发射的规则检查
            _rule_check_last_pos = 0  # 规则检查解析位置

            for token in chat_stream(messages, temperature=0.1, model_id=model_id):
                full_response += token
                # 检测JSON块开始，停止推送思考token
                if not json_started:
                    if '```json' in full_response or (full_response.count('{') > 0 and '"results"' in full_response):
                        json_started = True
                    else:
                        yield {"type": "thinking", "batch_index": batch_idx, "token": token}

                    # 实时检测规则判断行，立即发射逐条规则更新
                    if '\n' in full_response[_rule_check_last_pos:]:
                        _rule_check_last_pos = len(full_response)
                        checks = _detect_streaming_rule_checks(
                            full_response, batch, max(0, _rule_check_last_pos - 2000),
                            _rule_check_emitted
                        )
                        for ck in checks:
                            yield {
                                "type": "rule_check",
                                "batch_index": batch_idx,
                                "item_index": i + ck['item_idx'],
                                "item_name": ck['item_name'],
                                "rule": ck['rule'],
                                "pass": ck['pass'],
                                "reason": ck['reason'],
                            }

                    # 实时检测已完成的结论，立即发射结果
                    # 优化：只在有新完整行时才重新解析，避免O(n²)重解析
                    last_nl = full_response.rfind('\n')
                    if last_nl > _last_parse_len:
                        _last_parse_len = last_nl
                        conclusions = _parse_streaming_conclusions(full_response, batch)
                        for c in conclusions:
                            if c['conclusion'] and c['idx'] not in emitted_indices:
                                emitted_indices.add(c['idx'])
                                con = c['conclusion']
                                item_name = batch[c['idx']]
                                result = {
                                    "item": item_name,
                                    "is_bo": con['is_bo'],
                                    "confidence": con['confidence'],
                                    "reason": con['reason'],
                                    "rules_check": [],
                                }
                                all_results.append(result)
                                yield {"type": "result", "index": i + c['idx'], **result}

            yield {"type": "thinking_end", "batch_index": batch_idx}

            # 解析完整JSON响应，补充rules_check详情
            parsed = parse_llm_response(full_response, batch)

            for j, result in enumerate(parsed):
                item_name = result.get("item", batch[j])
                full_result = {
                    "item": item_name,
                    "is_bo": result.get("is_bo"),
                    "confidence": result.get("confidence", "low"),
                    "reason": result.get("reason", ""),
                    "rules_check": result.get("rules_check", []),
                }
                if j in emitted_indices:
                    # 已通过思考发射过，发送更新事件补充rules_check
                    # 更新all_results中的记录
                    for ar in all_results:
                        if ar.get('item') == item_name:
                            ar.update(full_result)
                            break
                    yield {"type": "result_update", "index": i + j, **full_result}
                else:
                    # 未发射过，正常发射
                    all_results.append(full_result)
                    yield {"type": "result", "index": i + j, **full_result}

        except Exception as e:
            for j, item in enumerate(batch):
                if j not in emitted_indices:
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
    """解析 LLM 返回的结果，从混合文本中提取JSON"""
    # 优先从 ```json 代码块中提取
    json_block = re.search(r'```json\s*(\{[\s\S]*?"results"[\s\S]*?\})\s*```', response)
    if json_block:
        try:
            data = json.loads(json_block.group(1))
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

    # 回退：从全文中提取JSON
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

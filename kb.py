"""
知识库管理模块
- 存储用户手动确认/纠正的识别结果
- 提供已知正例和反例供 LLM 参考
- 支持增删改查，持久化到 JSON 文件
"""
import json
from pathlib import Path
from datetime import datetime

KB_PATH = Path(__file__).parent / "knowledge.json"

DEFAULT_KB = {
    "confirmed_examples": {},
    "corrections": [],
    "custom_rules": {}
}


def load() -> dict:
    """加载知识库"""
    if KB_PATH.exists():
        try:
            with open(KB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {**DEFAULT_KB, "confirmed_examples": {}, "corrections": [], "custom_rules": {}}


def save(kb: dict):
    """保存知识库到文件"""
    with open(KB_PATH, 'w', encoding='utf-8') as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)


def add_example(element_type: str, item: str, is_match: bool, reason: str = ""):
    """添加一个已确认的示例到知识库"""
    kb = load()
    if element_type not in kb["confirmed_examples"]:
        kb["confirmed_examples"][element_type] = []

    examples = kb["confirmed_examples"][element_type]

    # 如果已存在同名项，更新它
    for ex in examples:
        if ex["item"] == item:
            ex["is_match"] = is_match
            ex["reason"] = reason
            ex["timestamp"] = datetime.now().isoformat()
            save(kb)
            return

    examples.append({
        "item": item,
        "is_match": is_match,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })
    save(kb)


def remove_example(element_type: str, item: str):
    """从知识库中删除一个示例"""
    kb = load()
    if element_type in kb["confirmed_examples"]:
        kb["confirmed_examples"][element_type] = [
            ex for ex in kb["confirmed_examples"][element_type]
            if ex["item"] != item
        ]
        save(kb)


def add_correction(item: str, element_type: str,
                   original_result: bool, corrected_result: bool,
                   reason: str = ""):
    """记录一次用户纠正"""
    kb = load()
    kb["corrections"].append({
        "item": item,
        "element_type": element_type,
        "original": original_result,
        "corrected": corrected_result,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })
    # 同时把纠正结果加入已确认示例
    add_example(element_type, item, corrected_result, reason)


def get_examples(element_type: str, max_per_side: int = 8) -> dict:
    """
    获取指定元素类型的已知正例和反例，供 LLM Prompt 使用。
    返回 {"positive": [...], "negative": [...]}
    """
    kb = load()
    examples = kb["confirmed_examples"].get(element_type, [])

    positive = [ex for ex in examples if ex.get("is_match") is True]
    negative = [ex for ex in examples if ex.get("is_match") is False]

    # 取最近的（按timestamp倒序）
    positive.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    negative.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {
        "positive": positive[:max_per_side],
        "negative": negative[:max_per_side]
    }


def get_all() -> dict:
    """获取完整知识库（供前端展示和编辑）"""
    return load()


def update_all(kb_data: dict):
    """整体替换知识库（供前端编辑器保存）"""
    save(kb_data)

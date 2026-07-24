"""
LLM 客户端封装 - 支持多模型切换
支持: 火山引擎方舟(豆包) / OpenAI兼容接口(通义千问)
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

# 模型配置列表
MODELS = [
    {
        "id": "doubao-turbo",
        "name": "豆包 Turbo (快速)",
        "provider": "ark",
        "model": os.getenv("DOUBAO_TURBO_MODEL", "Doubao-Seed-2.1-turbo"),
        "base_url": os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "api_key": os.getenv("DOUBAO_API_KEY", ""),
    },
    {
        "id": "doubao",
        "name": "豆包 Evolving (推理)",
        "provider": "ark",
        "model": os.getenv("DOUBAO_MODEL", "doubao-seed-evolving"),
        "base_url": os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "api_key": os.getenv("DOUBAO_API_KEY", ""),
    },
    {
        "id": "qwen",
        "name": "通义千问 (Qwen)",
        "provider": "openai",
        "model": os.getenv("QWEN_MODEL", "qwen-plus-latest"),
        "base_url": os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": os.getenv("QWEN_API_KEY", ""),
    },
]

# 缓存客户端
_clients = {}
_default_model_id = os.getenv("DEFAULT_MODEL", "doubao-turbo")


def get_available_models() -> list[dict]:
    """返回可用的模型列表（仅含已配置API Key的）"""
    available = []
    for m in MODELS:
        if m["api_key"]:
            available.append({
                "id": m["id"],
                "name": m["name"],
                "model": m["model"],
            })
    # 如果没有配置任何key，返回全部（开发环境可能用.env）
    if not available:
        return [{"id": m["id"], "name": m["name"], "model": m["model"]} for m in MODELS]
    return available


def get_default_model_id() -> str:
    return _default_model_id


def _get_model_config(model_id: str) -> dict:
    """根据model_id获取模型配置"""
    for m in MODELS:
        if m["id"] == model_id:
            return m
    # 默认第一个
    return MODELS[0]


def _get_client(model_id: str):
    """获取或创建对应模型的客户端"""
    if model_id not in _clients:
        cfg = _get_model_config(model_id)
        if cfg["provider"] == "ark":
            try:
                from volcenginesdkarkruntime import Ark
                _clients[model_id] = Ark(
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"],
                )
            except (ImportError, AttributeError):
                # 回退到 openai SDK（同样兼容 Ark API）
                from openai import OpenAI
                _clients[model_id] = OpenAI(
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"],
                )
        else:
            from openai import OpenAI
            _clients[model_id] = OpenAI(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
            )
    return _clients[model_id]


def chat(messages: list[dict], temperature: float = 0.3, model_id: str = None, timeout: int = 90) -> str:
    """同步调用 LLM，返回完整文本。超时默认90秒"""
    mid = model_id or _default_model_id
    cfg = _get_model_config(mid)
    client = _get_client(mid)
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=temperature,
        timeout=timeout,
    )
    return response.choices[0].message.content


def chat_stream(messages: list[dict], temperature: float = 0.3, model_id: str = None):
    """流式调用 LLM，逐步 yield 文本片段"""
    mid = model_id or _default_model_id
    cfg = _get_model_config(mid)
    client = _get_client(mid)
    stream = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content

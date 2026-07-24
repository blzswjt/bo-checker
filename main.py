"""
FastAPI 主入口 - 数据建模识别智能体
支持：主题域分类、主题域分组、主题域、业务对象、逻辑实体、业务属性
"""
import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from llm import chat_stream, get_available_models, get_default_model_id
from rules import ELEMENT_TYPES, ELEMENT_RULES, get_all_rules_text, get_rule_detail
from checker import parse_excel_file, extract_column_values, check_items_stream, check_single_item
import kb

app = FastAPI(title="数据建模识别智能体", version="4.0.0")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>页面未找到</h1>")


@app.get("/api/models")
async def get_models():
    """返回可用模型列表"""
    return {"models": get_available_models(), "default": get_default_model_id()}


@app.get("/api/element-types")
async def get_element_types():
    # 返回元素类型列表及每种类型的识别规则名
    rule_names = {}
    for etype, rules in ELEMENT_RULES.items():
        all_rule_names = []
        for r in rules.get("identification", []):
            all_rule_names.append(r["rule"])
        for r in rules.get("naming", []):
            all_rule_names.append(r["rule"])
        for r in rules.get("definition", []):
            all_rule_names.append(r["rule"])
        rule_names[etype] = all_rule_names
    return {"types": ELEMENT_TYPES, "rule_names": rule_names}


@app.post("/api/parse-excel")
async def parse_excel(file: UploadFile = File(...)):
    """上传并解析Excel，返回所有子表和列信息（不执行识别）"""
    if not file.filename.endswith((".xlsx", ".xls")):
        return JSONResponse({"error": "请上传 .xlsx 或 .xls 格式文件"}, status_code=400)

    file_id = str(uuid.uuid4())[:8]
    save_name = f"{file_id}_{file.filename}"
    save_path = UPLOAD_DIR / save_name
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    result = parse_excel_file(str(save_path))
    if "error" in result:
        return result

    result["file_id"] = file_id
    result["file_name"] = file.filename
    result["file_path"] = save_name
    return result


class CheckRequest(BaseModel):
    items: list[str]
    element_type: str = "业务对象"
    batch_size: int = 5
    model_id: Optional[str] = None


@app.post("/api/check-items")
async def check_items(req: CheckRequest):
    """SSE流式逐批识别，实时推送进度和结果"""
    if req.element_type not in ELEMENT_TYPES:
        return JSONResponse({"error": f"不支持的元素类型: {req.element_type}"}, status_code=400)

    def event_stream():
        for event in check_items_stream(req.items, req.element_type, req.batch_size, model_id=req.model_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class SingleCheckRequest(BaseModel):
    item: str
    element_type: str = "业务对象"
    model_id: Optional[str] = None


@app.post("/api/check-single")
async def check_single(req: SingleCheckRequest):
    """流式判断单个事物"""
    if req.element_type not in ELEMENT_TYPES:
        return JSONResponse({"error": f"不支持的元素类型: {req.element_type}"}, status_code=400)

    messages = check_single_item(req.item, element_type=req.element_type)

    def generate():
        for chunk in chat_stream(messages, temperature=0.2, model_id=req.model_id):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/column-values")
async def get_column_values(file_path: str, sheet: str, column: str):
    """获取指定文件中指定子表指定列的所有非空唯一值"""
    full_path = UPLOAD_DIR / file_path
    if not full_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    values = extract_column_values(str(full_path), sheet, column)
    return {"values": values, "count": len(values)}


@app.get("/api/rules")
async def get_rules():
    return {"rules": get_all_rules_text()}


# ============================================================
# 知识库管理
# ============================================================

class CorrectionRequest(BaseModel):
    item: str
    element_type: str
    original_result: Optional[bool] = None
    corrected_result: bool
    reason: str = ""


@app.post("/api/correct")
async def submit_correction(req: CorrectionRequest):
    """提交纠正并加入知识库"""
    kb.add_correction(req.item, req.element_type, req.original_result, req.corrected_result, req.reason)
    return {"ok": True}


class ExampleRequest(BaseModel):
    element_type: str
    item: str
    is_match: bool
    reason: str = ""


@app.post("/api/kb/add-example")
async def add_kb_example(req: ExampleRequest):
    """添加知识库示例"""
    kb.add_example(req.element_type, req.item, req.is_match, req.reason)
    return {"ok": True}


@app.delete("/api/kb/remove-example")
async def remove_kb_example(element_type: str, item: str):
    """删除知识库示例"""
    kb.remove_example(element_type, item)
    return {"ok": True}


@app.get("/api/kb")
async def get_knowledge_base():
    """获取完整知识库"""
    return kb.get_all()


@app.put("/api/kb")
async def update_knowledge_base(data: dict):
    """整体更新知识库"""
    kb.update_all(data)
    return {"ok": True}


# ============================================================
# 答疑智能体
# ============================================================

class QAChatRequest(BaseModel):
    item: str
    element_type: str
    rule: str
    pass_status: bool
    reason: str = ""
    question: str
    history: list[dict] = []  # [{role:'user',content:'...'}, {role:'assistant',content:'...'}]
    model_id: Optional[str] = None


@app.post("/api/qa-chat")
async def qa_chat(req: QAChatRequest):
    """答疑智能体：解释规则判断原因，支持多轮对话"""
    rule_detail = get_rule_detail(req.element_type, req.rule)
    pass_text = "通过（✓）" if req.pass_status else "不通过（✗）"

    system_prompt = (
        f"你是数据建模答疑专家。用户正在分析「{req.item}」是否为{req.element_type}。\n"
        f"\n{rule_detail}\n"
        f"\nAI分析结论：该规则{pass_text}\n"
        f"分析理由：{req.reason or '无详细理由'}\n\n"
        "请根据以上信息回答用户的疑问。如果用户不理解为什么通过或不通过，请详细解释。"
        "回答要简洁明了，用通俗易懂的语言。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in req.history[-6:]:  # 最多保留最近6条历史
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": req.question})

    def generate():
        for chunk in chat_stream(messages, temperature=0.3, model_id=req.model_id):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class QASaveRequest(BaseModel):
    item: str
    element_type: str
    rule: str
    pass_status: bool
    question: str
    answer: str


@app.post("/api/qa-save")
async def qa_save(req: QASaveRequest):
    """将答疑内容存入知识库"""
    reason = f"答疑：{req.question} → {req.answer[:200]}"
    kb.add_example(req.element_type, req.item, req.pass_status, reason)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    import sys
    print("=" * 50)
    print(f"Python: {sys.version}")
    print(f"工作目录: {os.getcwd()}")
    print(f"PORT: {os.getenv('PORT', '未设置')}")
    print(f"DOUBAO_API_KEY: {'已配置' if os.getenv('DOUBAO_API_KEY') else '未配置'}")
    print(f"QWEN_API_KEY: {'已配置' if os.getenv('QWEN_API_KEY') else '未配置'}")
    print(f"DEFAULT_MODEL: {os.getenv('DEFAULT_MODEL', 'doubao')}")
    # 检查关键依赖
    for pkg in ['volcenginesdkarkruntime', 'openai', 'fastapi', 'uvicorn', 'pandas', 'openpyxl']:
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} 未安装")
    print("=" * 50)
    port = int(os.getenv("PORT", 8005))
    print(f"启动服务: http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)

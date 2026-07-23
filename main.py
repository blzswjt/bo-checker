"""
FastAPI 主入口 - 数据建模识别智能体
支持：主题域分类、主题域分组、主题域、业务对象、逻辑实体、业务属性
"""
import os
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from llm import chat_stream
from rules import ELEMENT_TYPES, get_all_rules_text
from checker import process_excel, check_single_item

app = FastAPI(title="数据建模识别智能体", version="2.0.0")

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 上传目录
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ============================================================
# 页面
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>页面未找到</h1>")


# ============================================================
# 获取支持的元素类型列表
# ============================================================

@app.get("/api/element-types")
async def get_element_types():
    """返回所有支持的元素类型"""
    return {"types": ELEMENT_TYPES}


# ============================================================
# 上传 Excel 批量识别
# ============================================================

@app.post("/api/check-excel")
async def check_excel(
    file: UploadFile = File(...),
    element_type: str = Form(default="业务对象")
):
    """上传 Excel 文件，自动找到目标列并逐行识别"""
    if not file.filename.endswith((".xlsx", ".xls")):
        return JSONResponse({"error": "请上传 .xlsx 或 .xls 格式文件"}, status_code=400)

    if element_type not in ELEMENT_TYPES:
        return JSONResponse({"error": f"不支持的元素类型: {element_type}，可选: {ELEMENT_TYPES}"}, status_code=400)

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    result = process_excel(str(save_path), element_type=element_type)
    return result


# ============================================================
# 单个事物识别（流式）
# ============================================================

class SingleCheckRequest(BaseModel):
    item: str
    element_type: str = "业务对象"


@app.post("/api/check-single")
async def check_single(req: SingleCheckRequest):
    """流式判断单个事物是否为指定元素类型"""
    if req.element_type not in ELEMENT_TYPES:
        return JSONResponse({"error": f"不支持的元素类型: {req.element_type}"}, status_code=400)

    messages = check_single_item(req.item, element_type=req.element_type)

    def generate():
        for chunk in chat_stream(messages, temperature=0.2):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
# 规则查看
# ============================================================

@app.get("/api/rules")
async def get_rules():
    """返回所有元素类型的识别规则和命名规则"""
    return {"rules": get_all_rules_text()}


if __name__ == "__main__":
    import uvicorn
    import sys

    # 启动诊断
    print("=" * 50)
    print(f"Python: {sys.version}")
    print(f"工作目录: {os.getcwd()}")
    print(f"PORT 环境变量: {os.getenv('PORT', '未设置')}")
    print(f"LLM_API_KEY: {'已配置' if os.getenv('LLM_API_KEY') else '未配置'}")
    print(f"LLM_BASE_URL: {os.getenv('LLM_BASE_URL', '未设置')}")
    print(f"文件列表: {os.listdir('.')}")
    print("=" * 50)

    port = int(os.getenv("PORT", 8005))
    print(f"启动服务: http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)

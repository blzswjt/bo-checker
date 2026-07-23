"""
FastAPI 主入口 - 业务对象识别智能体
"""
import os
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from llm import chat_stream
from rules import CHECK_PROMPT, IDENTIFICATION_RULES, NAMING_RULES
from checker import process_excel, check_single_item, find_target_column

app = FastAPI(title="业务对象识别智能体", version="1.0.0")

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
# 上传 Excel 批量识别
# ============================================================

@app.post("/api/check-excel")
async def check_excel(file: UploadFile = File(...)):
    """上传 Excel 文件，自动找到目标列并逐行识别"""
    if not file.filename.endswith((".xlsx", ".xls")):
        return JSONResponse({"error": "请上传 .xlsx 或 .xls 格式文件"}, status_code=400)

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    result = process_excel(str(save_path))
    return result


# ============================================================
# 单个事物识别（流式）
# ============================================================

class SingleCheckRequest(BaseModel):
    item: str


@app.post("/api/check-single")
async def check_single(req: SingleCheckRequest):
    """流式判断单个事物是否为业务对象"""
    messages = check_single_item(req.item)

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
    """返回业务对象识别规则和命名规则"""
    return {
        "identification_rules": IDENTIFICATION_RULES,
        "naming_rules": NAMING_RULES
    }


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

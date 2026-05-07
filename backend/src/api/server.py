import os
import uuid
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# 导入我们已经写好的逻辑
from src.graph import build_graph
from src.scripts.ingest_knowledge import process_and_ingest_pdf

app = FastAPI(title="AI 教研大脑 API")

# 1. 配置跨域，允许前端 Vue 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 挂载 outputs 目录为静态文件，方便前端直接下载生成的 PDF
# 使用绝对路径确保正确映射
outputs_dir = Path(__file__).parent.parent.parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)

# 添加自定义 PDF 下载路由，正确设置 Content-Disposition 头
@app.get("/outputs/{filename}")
async def download_pdf(filename: str):
    """直接下载 PDF，设置正确的 Content-Disposition 头以支持自定义文件名"""
    file_path = outputs_dir / filename
    
    if not file_path.exists():
        return {"error": "文件不存在"}
    
    # 使用 FileResponse，浏览器会识别 Content-Disposition 并下载
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/pdf"
    )

# 初始化状态机大脑
agent_app = build_graph()

# ==========================================
# 接口 1：流式对话与出题 (SSE)
# ==========================================
@app.post("/chat")
async def chat_endpoint(
    prompt: str = Form(...), 
    reference_file: UploadFile = File(None)
):
    file_path = None
    mime_type = None
    
    # 接收前端的附件（图片或参考 PDF）
    if reference_file:
        ext = reference_file.filename.split(".")[-1]
        file_path = f"uploads/temp_{uuid.uuid4().hex}.{ext}"
        mime_type = reference_file.content_type
        
        # 确保目录存在
        os.makedirs("uploads", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(await reference_file.read())

    async def event_generator():
        test_input = {
            "raw_prompt": prompt, 
            "reference_file_path": file_path,
            "reference_mime_type": mime_type
        }
        
        try:
            # 记录最终的 PDF 路径，默认为空
            final_student_url = ""
            final_teacher_url = ""
            display_title = "试卷"
            download_name_student = "学生卷.pdf"
            download_name_teacher = "解析卷.pdf"

            async for output in agent_app.astream(test_input, stream_mode="updates"):
                for node_name, state_update in output.items():
                    if state_update is None:
                        state_update = {}
                        
                    event_data = {
                        "node": node_name,
                        "status": "running",
                        "details": state_update.get("review_feedback", "") or f"节点 {node_name} 正在处理..."
                    }
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # 【核心修改 3】：实时拦截编译节点传出来的最终文件下载链接
                    if node_name == "compile":
                        final_student_url = state_update.get("final_student_pdf_url", "")
                        final_teacher_url = state_update.get("final_teacher_pdf_url", "")
                        display_title = state_update.get("display_title", "试卷")
                        download_name_student = state_update.get("download_name_student", "学生卷.pdf")
                        download_name_teacher = state_update.get("download_name_teacher", "解析卷.pdf")
                        # 【调试】打印拦截到的数据
                        print(f"\n[DEBUG] Compile 节点返回的数据:")
                        print(f"  final_student_url = {final_student_url}")
                        print(f"  final_teacher_url = {final_teacher_url}")
                        print(f"  display_title = {display_title}")
                        print(f"  download_name_student = {download_name_student}")
                        print(f"  download_name_teacher = {download_name_teacher}")
            
            # 【核心修改 4】：直接用上面拦截到的确切链接推送给前端，彻底抛弃 glob.glob
            final_data = {
                            "node": "finish",
                            "status": "done",
                            "details": "全部处理完成！",
                            "pdf_student": final_student_url,
                            "pdf_teacher": final_teacher_url,
                            "download_name_student": download_name_student,
                            "download_name_teacher": download_name_teacher
                        }
            print(f"\n[DEBUG] 发送给前端的最终数据: {final_data}")
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
            
        finally:
            # 任务结束后，清理临时文件
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==========================================
# 接口 2：高精度知识库入库 (MinerU API)
# ==========================================
@app.post("/upload_knowledge")
async def upload_kb(file: UploadFile = File(...)):
    os.makedirs("uploads", exist_ok=True)
    file_path = f"uploads/{file.filename}"
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # 异步触发 MinerU 解析和 ChromaDB 入库，不阻塞前端响应
    asyncio.create_task(asyncio.to_thread(process_and_ingest_pdf, file.filename))
    
    return {"code": 0, "msg": "文件已接收，后台 MinerU 正在高精度解析并入库..."}

# 启动命令: uvicorn src.api.server:app --reload --port 8000
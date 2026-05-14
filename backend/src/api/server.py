import os
import uuid
import json
import asyncio
import threading
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.graph import build_graph
from src.scripts.ingest_knowledge import process_and_ingest_pdf
from src.tools.rag_search import vector_store

app = FastAPI(title="AI 教研大脑 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

outputs_dir = Path(__file__).parent.parent.parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)

# Serve knowledge-base images extracted from PDFs
kb_images_dir = Path(__file__).parent.parent.parent / "assets" / "images"
kb_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets/images", StaticFiles(directory=str(kb_images_dir)), name="kb_images")


@app.get("/outputs/{filename}")
async def download_pdf(filename: str):
    file_path = outputs_dir / filename
    if not file_path.exists():
        return {"error": "文件不存在"}
    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")


agent_app = build_graph()


# ==========================================
# 接口 1：流式对话与出题 (SSE)
# ==========================================
@app.post("/chat")
async def chat_endpoint(
    prompt: str = Form(...),
    reference_file: UploadFile = File(None),
):
    file_path = None
    mime_type = None

    if reference_file:
        ext = reference_file.filename.split(".")[-1]
        file_path = f"uploads/temp_{uuid.uuid4().hex}.{ext}"
        mime_type = reference_file.content_type
        os.makedirs("uploads", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(await reference_file.read())

    async def event_generator():
        test_input = {
            "raw_prompt": prompt,
            "reference_file_path": file_path,
            "reference_mime_type": mime_type,
        }
        try:
            final_student_url = ""
            final_teacher_url = ""
            download_name_student = "学生卷.pdf"
            download_name_teacher = "解析卷.pdf"

            async for output in agent_app.astream(test_input, stream_mode="updates"):
                for node_name, state_update in output.items():
                    if state_update is None:
                        state_update = {}
                    event_data = {
                        "node": node_name,
                        "status": "running",
                        "details": state_update.get("review_feedback", "") or f"节点 {node_name} 正在处理...",
                    }
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    if node_name == "compile":
                        final_student_url = state_update.get("final_student_pdf_url", "")
                        final_teacher_url = state_update.get("final_teacher_pdf_url", "")
                        download_name_student = state_update.get("download_name_student", "学生卷.pdf")
                        download_name_teacher = state_update.get("download_name_teacher", "解析卷.pdf")

            final_data = {
                "node": "finish",
                "status": "done",
                "details": "全部处理完成！",
                "pdf_student": final_student_url,
                "pdf_teacher": final_teacher_url,
                "download_name_student": download_name_student,
                "download_name_teacher": download_name_teacher,
            }
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==========================================
# 接口 2：知识库入库 (SSE 实时进度流)
# ==========================================
@app.post("/upload_knowledge")
async def upload_kb_stream(file: UploadFile = File(...)):
    """SSE stream: upload → MinerU parse → per-question split → embed."""
    file_bytes = await file.read()
    filename = file.filename

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_event(event: dict):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run_ingest():
        try:
            process_and_ingest_pdf(filename, file_bytes, on_event)
        except Exception as e:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"stage": "error", "msg": str(e)}
            )

    threading.Thread(target=run_ingest, daemon=True).start()

    async def generator():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("stage") in ("done", "error"):
                break

    return StreamingResponse(generator(), media_type="text/event-stream")


# ==========================================
# 接口 3：知识库文档列表
# ==========================================
@app.get("/knowledge/documents")
async def list_knowledge_documents():
    """Return all ingested source files with their question counts."""
    try:
        result = vector_store._collection.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []

        groups: dict = defaultdict(lambda: {"question_count": 0, "created_at": 0})
        for meta in metadatas:
            if not meta:
                continue
            sf = meta.get("source_file", "未知来源")
            groups[sf]["question_count"] += 1
            ts = meta.get("created_at", 0)
            if ts > groups[sf]["created_at"]:
                groups[sf]["created_at"] = ts

        docs = [
            {"source_file": sf, "question_count": v["question_count"], "created_at": v["created_at"]}
            for sf, v in sorted(groups.items(), key=lambda x: x[1]["created_at"], reverse=True)
        ]
        return {"code": 0, "data": docs}
    except Exception as e:
        return {"code": 1, "msg": str(e), "data": []}


# ==========================================
# 接口 4：删除知识库来源
# ==========================================
@app.delete("/knowledge/documents/{source_file:path}")
async def delete_knowledge_document(source_file: str):
    """Delete all vectors and associated images for a source file."""
    try:
        result = vector_store._collection.get(
            where={"source_file": source_file},
            include=["metadatas"],
        )
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []

        # 收集该文件所有题目引用的图片 URL
        img_urls_to_check: set[str] = set()
        for meta in metadatas:
            try:
                urls = json.loads(meta.get("image_urls", "[]"))
                img_urls_to_check.update(urls)
            except Exception:
                pass

        if ids:
            vector_store.delete(ids=ids)

        # 删除向量后，查出其他文档还在引用哪些图片，避免误删共享图片
        deleted_imgs = 0
        if img_urls_to_check:
            remaining = vector_store._collection.get(include=["metadatas"])
            still_referenced: set[str] = set()
            for meta in (remaining.get("metadatas") or []):
                try:
                    still_referenced.update(json.loads(meta.get("image_urls", "[]")))
                except Exception:
                    pass

            images_dir = Path(__file__).parent.parent.parent / "assets" / "images"
            for url in img_urls_to_check:
                if url in still_referenced:
                    continue
                img_path = images_dir / Path(url).name
                if img_path.exists():
                    img_path.unlink()
                    deleted_imgs += 1

        return {"code": 0, "msg": f"已删除 {len(ids)} 条向量，{deleted_imgs} 张图片"}
    except Exception as e:
        return {"code": 1, "msg": str(e)}

# 启动命令: uvicorn src.api.server:app --reload --port 8000

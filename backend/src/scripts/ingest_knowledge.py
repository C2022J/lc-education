# src/scripts/ingest_knowledge.py
import os
import shutil
from src.tools.mineru_parser import submit_pdf_to_mineru, poll_mineru_result
from langchain_core.documents import Document
from src.tools.rag_search import vector_store  # 复用我们之前的本地向量库

UPLOAD_DIR = "uploads"
ARCHIVE_DIR = "archived_pdfs"


def process_and_ingest_pdf(pdf_filename: str):
    """
    处理单个 PDF：API解析 -> 获取 MD -> 存入 ChromaDB -> 归档 PDF
    """
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)

    try:
        # 1. 调用云端 API 解析
        batch_id = submit_pdf_to_mineru(pdf_path)
        markdown_content = poll_mineru_result(batch_id)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：显示解析后的内容 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print(f"\n{'─'*80}")
        print(f"[Debug] MinerU 解析结果详情")
        print(f"{'─'*80}")
        print(f"📝 Markdown 总长度: {len(markdown_content)} 字符")
        
        # 提取图片链接
        import re as regex
        img_links = regex.findall(r'!\[.*?\]\((.*?)\)', markdown_content)
        print(f"📸 包含的图片链接总数: {len(img_links)}")
        if img_links:
            print(f"   图片链接列表:")
            for i, link in enumerate(img_links, 1):
                print(f"   [{i}] {link}")
        
        # 显示内容预览
        preview = markdown_content[:300] + "..." if len(markdown_content) > 300 else markdown_content
        print(f"📄 内容预览:")
        print(f"   {preview}")
        print()

        # 2. 直接将解析好的 Markdown 存入本地知识库
        print(f"🧠 正在将解析结果向量化并存入 ChromaDB...")
        metadata = {"source_file": pdf_filename}
        doc = Document(page_content=markdown_content, metadata=metadata)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：存储前的数据检查 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print(f"[Debug] 存储到 ChromaDB 前的数据:")
        print(f"   Document page_content 长度: {len(doc.page_content)} 字符")
        print(f"   Document metadata: {doc.metadata}")
        
        vector_store.add_documents(documents=[doc])
        print(f"✅ 文档已存入 ChromaDB")

        # 3. 归档源文件
        if not os.path.exists(ARCHIVE_DIR):
            os.makedirs(ARCHIVE_DIR)
        shutil.move(pdf_path, os.path.join(ARCHIVE_DIR, pdf_filename))
        print(f"📦 文件 {pdf_filename} 处理完毕并已归档！\n")

    except Exception as e:
        print(f"❌ 处理 {pdf_filename} 失败: {e}")


if __name__ == "__main__":
    for f in os.listdir(UPLOAD_DIR):
        if f.lower().endswith(".pdf"):
            process_and_ingest_pdf(f)
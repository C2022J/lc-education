# src/tools/rag_search.py
import asyncio
from typing import List
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder

from src.config.settings import settings

# 全局复用模型，避免每次调用重复加载进显存
print("🧠 正在预热本地 Embedding 和 Reranker 模型...")
embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_PATH)
reranker = CrossEncoder(settings.RERANKER_MODEL_PATH, device="cuda")

# 链接本地向量库
vector_store = Chroma(
    collection_name="math_books",
    embedding_function=embeddings,
    persist_directory=settings.CHROMA_DB_DIR
)


async def execute_rag_search(query: str, top_k: int = 2) -> List[str]:
    """
    执行 RAG 初筛 + Rerank 重排
    这个函数现在被包装成了异步，以便后续和 Web Search 并发执行。
    """
    print(f"📚 [RAG Search] 本地库正在检索: '{query}'")

    # 异步执行耗时 I/O 操作
    def _search_and_rerank():
        # 1. 向量粗筛 (召回更多结果交给 Reranker)
        initial_k = top_k * 3
        results = vector_store.similarity_search_with_relevance_scores(query, k=initial_k)

        if not results:
            print(f"    ⚠️ [RAG] 本地库无相关内容")
            return []

        print(f"    📊 [RAG] 向量粗筛返回 {len(results)} 条候选 (初始 K={initial_k})")

        # 2. Reranker 精排 (交叉编码器，打分更准)
        pairs = [[query, res[0].page_content] for res in results]
        scores = reranker.predict(pairs)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：打印重排前后的信息 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print(f"    🎯 [RAG] Reranker 重排开始...")
        for idx, (res, score) in enumerate(zip(results, scores), 1):
            doc_content = res[0].page_content
            content_preview = doc_content[:100] + "..." if len(doc_content) > 100 else doc_content
            print(f"       [{idx}] 相关度得分: {score:.4f}")
            print(f"            内容长度: {len(doc_content)} 字符")
            print(f"            预览: {content_preview}")
            
            # 检查是否包含图片链接
            import re as regex
            img_links = regex.findall(r'!\[.*?\]\((.*?)\)', doc_content)
            if img_links:
                print(f"            📸 包含 {len(img_links)} 个图片链接:")
                for img_idx, img_link in enumerate(img_links, 1):
                    print(f"               - {img_link}")

        # 3. 排序并截取
        reranked_results = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：打印最终返回的结果 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print(f"    🏆 [RAG] 精排后返回前 {top_k} 条高优内容:")
        final_docs = [res[0][0].page_content for res in reranked_results[:top_k]]
        for idx, doc in enumerate(final_docs, 1):
            doc_preview = doc[:150] + "..." if len(doc) > 150 else doc
            print(f"       [{idx}] 长度 {len(doc)} 字符")
            print(f"            {doc_preview}")

        return final_docs

    # 交给线程池跑，防止阻塞 asyncio 主事件循环
    final_docs = await asyncio.to_thread(_search_and_rerank)

    print(f"✅ [RAG Search] 本地命中 {len(final_docs)} 段高优内容。")
    return final_docs
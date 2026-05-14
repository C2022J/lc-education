# src/nodes/retriever.py
import asyncio
from typing import Dict, Any

from src.schemas.graph_state import SelectionState
from src.tools.rag_search import execute_rag_search


async def retrieve_candidates_node(state: SelectionState) -> Dict[str, Any]:
    """
    Node 2: 并发双路检索 (Map 阶段)
    同时请求本地教材库和公网题库，榨干 I/O 性能。
    """
    print("\n" + "=" * 50)
    print("⏳ [Node 2] 正在启动高并发引擎搜集题源...")

    req = state.get("requirement")
    if not req:
        raise ValueError("缺少选题要求，无法检索！")

    topic = req["topic"]
    constraints = req["constraints"]
    count = req["count"]

    # 给 RAG 使用的合并搜索词
    search_query = f"{topic} {constraints}"

    tasks = [execute_rag_search(query=search_query, top_k=count * 3)]
    results = await asyncio.gather(*tasks)

    # 合并所有的“生肉”材料 (扁平化 list of lists)
    all_candidates = []
    for res_list in results:
        all_candidates.extend(res_list)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：打印合并后的原始素材 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "─" * 80)
    print("[Node 2] 并发检索完成，汇总原始素材内容")
    print("─" * 80)
    print(f"📊 总共聚合 {len(all_candidates)} 条原始素材\n")
    
    import re as regex
    for idx, candidate in enumerate(all_candidates, 1):
        print(f"┌─ 【原始素材 {idx}】" + "─" * (60 - len(f"【原始素材 {idx}】")))
        print(f"   总长度: {len(candidate)} 字符")
        
        # 提取图片链接
        img_links = regex.findall(r'!\[.*?\]\((.*?)\)', candidate)
        print(f"   包含图片数: {len(img_links)}")
        if img_links:
            print(f"   图片链接列表:")
            for img_idx, img_link in enumerate(img_links, 1):
                print(f"      [{img_idx}] {img_link}")

        # 完整内容
        print(f"   ── 完整内容 ──")
        print(candidate)
        print(f"   ── 内容结束 ──")
        print(f"└─")
        print()

    print("─" * 80)
    print(f"✅ [Node 2] 并发检索完成，共聚合 {len(all_candidates)} 条原始素材交由大模型审阅。")
    print("=" * 50 + "\n")

    return {"raw_candidates": all_candidates}
# src/tools/web_search.py
from langchain_tavily import TavilySearch
from typing import List
from src.config.settings import settings


def execute_web_search(topic: str, constraints: str, count: int) -> List[str]:
    """
    使用 Tavily 进行公网搜题。
    根据 Node 1 解析出的教研要求，动态构建搜索词。
    """
    print("🌐 [Web Search] 启动外部网页检索...")

    tavily_tool = TavilySearch(
        tavily_api_key=settings.TAVILY_API_KEY,
        max_results=count,
        topic="general",
        search_depth="advanced",
    )

    search_query = f"{topic} {constraints} 高考题 模拟题"

    try:
        # 直接拿到底层返回的字典数据
        results_data = tavily_tool.invoke({"query": search_query})

        # 极简提取逻辑：直接从字典中取出 results 列表，并提取每个 item 的 content
        candidates = []
        if isinstance(results_data, dict) and "results" in results_data:
            for item in results_data["results"]:
                if isinstance(item, dict) and "content" in item:
                    candidates.append(item["content"])

        print(f"✅ [Web Search] 找到 {len(candidates)} 条可能的网络题源。")
        return candidates

    except Exception as e:
        print(f"❌ [Web Search] 外部搜索失败: {e}")
        return []
# src/graph.py
from langgraph.graph import StateGraph, START, END
import asyncio
from src.schemas.graph_state import SelectionState
from src.nodes.parser import parse_teacher_intent
from src.nodes.retriever import retrieve_candidates_node
from src.nodes.reviewer import review_and_select_node
from src.nodes.compiler import compile_pdf_node

def should_retry(state: SelectionState) -> str:
    """
    路由函数：根据质检结果决定下一步是重试还是编译。
    加入重试次数限制，防止无限循环。
    """
    feedback = state.get("review_feedback", "")
    retry_count = state.get("retry_count", 0)
    max_retries = 3  # 最多重试 3 次
    
    if feedback == "SUCCESS":
        print(f"✅ [路由系统] 质检通过，准备进行编译...")
        return "compile"
    
    # 【必须要有这一层拦截！】
    if "FATAL_ERROR" in feedback:
        print(f"🛑 [系统熔断] 检测到底层或 API 致命错误，已切断循环！({feedback})")
        return "compile" 
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 重试次数限制 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if retry_count >= max_retries:
        print(f"⚠️ [路由系统] 已达到最大重试次数 ({max_retries})，强制进入编译阶段...")
        print(f"   原因: {feedback}")
        return "compile"
    
    if feedback:
        new_retry_count = retry_count + 1
        print(f"⚠️ [路由系统] 质检不合格 ({feedback})")
        print(f"   重试次数: {new_retry_count}/{max_retries}，退回并发检索阶段重做...")
        # 更新状态中的重试计数
        state["retry_count"] = new_retry_count
        return "retrieve"
    
    return "compile"


def build_graph():
    """
    构建并返回企业级状态机图。
    """
    workflow = StateGraph(SelectionState)

    # 1. 注册所有的车间 (Nodes)
    workflow.add_node("parse", parse_teacher_intent)
    workflow.add_node("retrieve", retrieve_candidates_node)
    workflow.add_node("review", review_and_select_node)
    workflow.add_node("compile", compile_pdf_node)

    # 2. 规划流水线传送带 (Edges)
    workflow.add_edge(START, "parse")  # 起点走到意图解析
    workflow.add_edge("parse", "retrieve")  # 解析完毕去高并发检索
    workflow.add_edge("retrieve", "review")  # 检索完给老教师质检

    # 3. 核心机制：质检重试循环 (Conditional Edges)
    workflow.add_conditional_edges(
        "review",
        should_retry,  # 调用路由函数
        {
            "retrieve": "retrieve",  # 如果不合格，退回查资料
            "compile": "compile"  # 如果合格，去车间排版打印
        }
    )

    workflow.add_edge("compile", END)  # 打印完毕，项目结束

    # 编译成可执行的 application
    return workflow.compile()


# 如果直接运行此文件，做一个端到端的测试
if __name__ == "__main__":
    app = build_graph()

    # 模拟前端传来的老师话语
    test_input = {
        "raw_prompt": "帮我找高中数学考点必须是三角函数部分的求参数 w 的取值范围相关的题目，最好是高考真题。"
    }


    # 定义一个异步主函数来运行
    async def run_test():
        print("🚀 正在启动 AI 教研助教核心总线...\n")
        # ⚠️ 注意这里：使用了 astream，并且加了 await
        async for output in app.astream(test_input, stream_mode="updates"):
            for node_name, state_update in output.items():
                # 我们只在最外层监听节点切换，具体日志在 Node 内部打印
                pass

        print("\n🎉 端到端流程测试完毕！")


    # 使用 asyncio 启动
    asyncio.run(run_test())
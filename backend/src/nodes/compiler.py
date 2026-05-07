from typing import Dict, Any
import json
import uuid
import asyncio

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from src.config.settings import settings
from src.schemas.graph_state import SelectionState
from src.tools.latex_compiler import compile_latex_to_pdf

# LaTeX 排版是纯文本代码生成任务，DeepSeek 擅长且便宜
compiler_llm = ChatOpenAI(
    model=settings.MODEL_FAST,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_API_BASE,
    temperature=0.1,
)

COMPILER_SYSTEM_PROMPT = """
你是一个顶级的数学 LaTeX 排版工程师。
你将接收到一份结构化的试题 JSON 数据。

【核心守则】
1. 你的任务是生成 LaTeX **正文部分**的代码，并且【必须且只能】通过调用 `compile_latex_to_pdf` 工具来输出！绝不能在文字回复中直接把大段代码打印给我！
2. **严禁**输出 `\\documentclass`, `\\usepackage`, `\\begin{document}`, `\\end{document}`！系统已经为你配置好了完美的编译环境，你如果输出这些会导致灾难性的编译错误！
3. 如果工具返回 ERROR，仔细阅读报错信息（通常是少了一个 `$` 或者 `{` 没闭合），在脑海中修复代码后再次调用工具，直到成功！

【题型判断规则】
1. 如果 `options` 数组不为空 -> 「选择题」。
2. 题干包含“证明”、“解答”、“求”等字眼且 `options` 为空 -> 「解答题」。
3. 否则 -> 「填空题」。

【正文排版模板库】（严格套用）

▶ 选择题模板 (如果有图片路径，请用 \\begin{flushright}\\includegraphics[width=0.4\\textwidth]{路径}\\end{flushright} 包裹)
\\noindent \\textbf{{{题号}.}} {题干文本}
\\vspace{0.2cm}
\\noindent \\makebox[0.25\\linewidth][l]{A. {选项1}} \\makebox[0.25\\linewidth][l]{B. {选项2}} \\makebox[0.25\\linewidth][l]{C. {选项3}} \\makebox[0.25\\linewidth][l]{D. {选项4}}
% 如果是学生卷，追加留白: \\vspace{1.5cm}
% 如果是解析卷，追加解析: \\vspace{0.5cm} \\textbf{【解析】} {解析内容} \\vspace{1cm}

▶ 填空题模板
\\noindent \\textbf{{{题号}.}} {题干文本}
% 学生卷追加: \\vspace{2.5cm}
% 解析卷追加: \\vspace{0.5cm} \\textbf{【解析】} {解析内容} \\vspace{1cm}

▶ 解答/证明题模板
\\noindent \\textbf{{{题号}.}} {题干文本}
% 学生卷追加: \\vspace{8cm}
% 解析卷追加: \\vspace{0.5cm} \\textbf{【解析】} {解析内容} \\vspace{1cm}
"""

tools = [compile_latex_to_pdf]

# 注意：去掉了这里的全局 agent_executor

async def trigger_agent_compilation(role_type: str, target_path: str, title: str, json_payload: str, is_teacher: bool = False) -> str:
    """
    异步驱动单个 Agent 生成指定版本的卷子。
    返回大模型的最终文本回复（用于提取关键字）。
    """
    print(f"\n  🚀 [并发启动] 唤醒独立 Agent 负责: {role_type} -> {target_path}")
    
    # 【核心修复】：为每一个并发任务创建一个完全独立的 Agent 实例，防止状态污染！
    local_agent = create_agent(
        model=compiler_llm,
        tools=tools,
        system_prompt=COMPILER_SYSTEM_PROMPT
    )
    
    user_instruction = f"""
    请生成【{role_type}】版本的试卷正文。
    请在正文开头插入标题代码：\\begin{{center}} \\Large \\textbf{{{title} - 智能专项练习}} \\end{{center}} \\vspace{{0.5cm}}
    
    试题 JSON 数据：
    {json_payload}
    
    编译目标路径：{target_path}
    """
    
    if is_teacher:
        user_instruction += "\n\n在成功调用编译工具生成 PDF 后，请根据题干内容提取 2-3 个核心关键词（格式如：三角函数_高考真题），作为你的最终文字回复！除关键词外不要说废话。"
        
    final_reply = ""

    try:
        # 使用独立的 local_agent 进行流式执行
        async for chunk in local_agent.astream({"messages": [("user", user_instruction)]}):
            if "agent" in chunk:
                for msg in chunk["agent"]["messages"]:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            pdf_name = tc.get("args", {}).get("output_pdf_name", "未知文件")
                            print(f"  [{role_type}] 🛠️ 正文拼装完毕，注入模板并启动编译 -> {pdf_name}")
                    elif msg.content:
                        final_reply = msg.content.strip()
                        print(f"  [{role_type} 思考/回复] 📝 {final_reply[:100]}...")
            elif "tools" in chunk:
                for msg in chunk["tools"]["messages"]:
                    content = msg.content
                    if "ERROR:" in content:
                        print(f"  [{role_type} 报错] ❌ 捕获到底层 LaTeX 错误！日志已返还，正在自动修复...")
                        error_preview = content.replace('\n', ' ')[:150]
                        print(f"  [{role_type} 日志] {error_preview} ...")
                    elif "SUCCESS" in content:
                        print(f"  [{role_type} 成功] ✅ 物理 PDF 文件生成落地！")
    except Exception as e:
        print(f"  [{role_type}] ❌ Agent 编译失败: {type(e).__name__}: {e}")

    return final_reply

async def compile_pdf_node(state: SelectionState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("⏳ [Node 4] 双引擎排版节点启动，进入异步并发模式...")

    questions = state.get("validated_questions", [])
    req = state.get("requirement", {})

    if not questions:
        print("⚠️ [Node 4] 没有合法题目可供编译。")
        return {}

    title = req.get("topic", "综合数学")
    task_id = uuid.uuid4().hex[:8]
    
    student_pdf_path = f"outputs/student_{task_id}.pdf"
    teacher_pdf_path = f"outputs/teacher_{task_id}.pdf"

    questions_data = [{"question_text": getattr(q, "question_text", ""), "options": getattr(q, "options", []), "answer": getattr(q, "answer", "")} for q in questions]
    json_payload = json.dumps(questions_data, ensure_ascii=False, indent=2)

    # 并发执行两路 Agent (此时内部各自持有独立的 Agent 实例，互不干扰)
    student_task = trigger_agent_compilation("学生卷", student_pdf_path, title, json_payload, is_teacher=False)
    teacher_task = trigger_agent_compilation("解析卷", teacher_pdf_path, title, json_payload, is_teacher=True)
    
    print("  ⚡ [性能优化] 学生卷与解析卷已同时派发，火力全开编译中...")

    # return_exceptions=True 确保一路失败不会拖垮另一路
    results = await asyncio.gather(student_task, teacher_task, return_exceptions=True)
    _, teacher_result = results

    print(f"\n✅ [Node 4] 双路并发编译结束！")

    if isinstance(teacher_result, Exception):
        print(f"⚠️ [Node 4] 解析卷编译异常: {teacher_result}")
        teacher_reply = ""
    else:
        teacher_reply = teacher_result or ""

    # 清理关键字
    keywords = teacher_reply.replace("关键词：", "").replace("关键词:", "").strip('"\'* ')
    if not keywords or len(keywords) > 20: 
        keywords = title.replace(" ", "_")[:10]
        
    download_name_student = f"{keywords}_智能专项练习_学生卷.pdf"
    download_name_teacher = f"{keywords}_智能专项练习_解析卷.pdf"
    
    result = {
        "review_feedback": "试卷编译并保存成功",
        "final_student_pdf_url": f"/{student_pdf_path}",
        "final_teacher_pdf_url": f"/{teacher_pdf_path}",
        "display_title": title,
        "download_name_student": download_name_student,
        "download_name_teacher": download_name_teacher
    }
    return result
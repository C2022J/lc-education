# src/schemas/graph_state.py
from typing import TypedDict, List, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from .math_problem import QuestionItem


class TeacherRequirement(TypedDict):
    """提取出的老师的结构化需求"""
    topic: str  # 比如：三角函数
    constraints: str  # 比如：必须包含 w 的取值范围
    count: int  # 需要几道题


class SelectionState(TypedDict):
    """
    Agentic RAG 的流转筐。
    """
    # LangGraph 规范：累加的消息历史
    messages: Annotated[List[BaseMessage], add_messages]

    # 老师的原始文字输入
    raw_prompt: str

    # 【新增】支持多模态参考文件。这里我们只存路径，具体解析由 Node 1 去做
    reference_file_path: Optional[str]
    reference_mime_type: Optional[str]  # 告诉模型这是 'image/jpeg' 还是 'application/pdf'

    # 解析后的老师需求 (Node 1 负责填入)
    requirement: TeacherRequirement | None

    # RAG 或 Web 工具检索回来的“生肉”数据 (Node 2 负责填入)
    raw_candidates: List[str]

    # 经过 LLM-as-a-Judge 质检合格的“熟肉”数据 (Node 3 负责填入)
    validated_questions: List[QuestionItem]

    # 质检阶段的报错反馈，用于驱动大模型重试 (Node 3 填写，Node 2 响应)
    review_feedback: str | None

    # 编译阶段的 PDF 下载链接 (Node 4 负责填入)
    final_student_pdf_url: Optional[str]
    final_teacher_pdf_url: Optional[str]
    display_title: Optional[str]
    download_name_student: Optional[str]
    download_name_teacher: Optional[str]
# src/schemas/math_problem.py
from pydantic import BaseModel, Field
from typing import List

class QuestionItem(BaseModel):
    """
    单道题目结构，这是最终交给你的“教师版”。
    包含特定的答案隔断，方便你在前端或后续用代码直接切分出“学生版”。
    """
    question_text: str = Field(description="题干内容，必须使用严格的 LaTeX 语法")
    options: List[str] | None = Field(default=None, description="如果是选择题，提供选项列表；非选择题为空")
    # 特殊标识符，用于你的业务逻辑分离
    answer: str = Field(description="详细的答案与解析。必须以【答案】作为开头")

class FinalOutput(BaseModel):
    """
    最终交付给老师的数据结构。
    我们要强制 DeepSeek (使用 JSON Object 模式) 输出这个结构。
    """
    report: str = Field(description="给老师的简短教研报告，说明为什么选这几道题")
    questions: List[QuestionItem] = Field(description="符合要求的高质量题目列表")
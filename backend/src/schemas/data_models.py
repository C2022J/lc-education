# src/schemas/data_models.py
from pydantic import BaseModel, Field
from typing import List

class ValidatedQuestion(BaseModel):
    """单道题目的标准结构"""
    question_text: str = Field(description="完整的题目内容")
    options: List[str] = Field(default_factory=list, description="如果是选择题提供选项数组，解答题则是空列表 []")
    answer: str = Field(description="详细的解答过程或答案")
    source: str = Field(default="", description="题目来源标识（如：2023年全国卷）")

class ReviewResult(BaseModel):
    """Node 3 质检节点输出的整体格式"""
    feedback: str = Field(description="整体审核报告（说明剔除原因和入选理由）")
    selected_questions: List[ValidatedQuestion] = Field(description="最终筛选出的高质量题目列表")
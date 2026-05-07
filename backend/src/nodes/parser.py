# src/nodes/parser.py
from typing import Dict, Any, List
import json
import base64
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import settings
from src.schemas.graph_state import SelectionState

# ==========================================
# 1. 严格定义输出的 JSON Schema (按照官方要求)
# ==========================================
class IntentRequirement(BaseModel):
    topic: str = Field(description="核心知识点，例如：立体几何、空间向量、三角函数等。")
    constraints: str = Field(description="对考点、解法、难度的详细补充要求。如果用户传了图片或PDF，务必在这里描述你从文件中分析出的题型特点。")
    count: int = Field(description="需求数量", default=3)

# 多模态客户端（有附件时使用）
client = genai.Client(api_key=settings.GEMINI_API_KEY)

# 纯文本意图解析客户端（无附件时使用，更快更便宜）
deepseek_llm = ChatOpenAI(
    model=settings.MODEL_FAST,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_API_BASE,
    temperature=0.0,
)

INTENT_SYSTEM_PROMPT = """
你是一位顶尖的数学教研主任。
你现在的任务是仔细听取老师的需求。如果老师提供了一份参考文件（一张题目截图，或一份试卷），请展现你强大的多模态视觉理解能力，深入分析参考文件中的题型、难度、考点偏好。

结合老师的文本需求和参考文件内容，提取出用于系统下一步检索的核心约束。
"""

def parse_teacher_intent(state: SelectionState) -> Dict[str, Any]:
    print("\n" + "="*50)
    print(f"⏳ [Node 1] 正在分析老师的出题意图: '{state.get('raw_prompt')}'")
    
    raw_prompt = state.get("raw_prompt", "")
    ref_file_path = state.get("reference_file_path")
    ref_mime_type = state.get("reference_mime_type")

    # ==========================================
    # 2. 构建多模态内容列表 (Contents)
    # ==========================================
    contents = []
    
    # 挂载参考文件
    if ref_file_path:
        print(f"👁️ [Node 1] 检测到参考文件载入，启动原生视觉/文档解析: {ref_file_path}")
        try:
            # 官方推荐的做法：读取本地文件作为 Inline Data
            with open(ref_file_path, 'rb') as f:
                file_bytes = f.read()
                
            contents.append(
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=ref_mime_type or "image/jpeg"
                )
            )
            contents.append("【重要指令】请深入分析前面提供的参考文件，并提取出它所代表的数学考点、题型结构与难度层级。")
        except Exception as e:
            print(f"❌ [Node 1] 文件读取失败: {e}")
            
    # 挂载文本指令
    contents.append(f"【老师要求】:\n{raw_prompt}")

    # ==========================================
    # 3. 调用生成
    # ==========================================
    try:
        if ref_file_path:
            # 有附件 → 必须用 Gemini 多模态
            print(f"🔮 [Node 1] 检测到附件，调用 Gemini Vision ({settings.MODEL_VISION})")
            response = client.models.generate_content(
                model=settings.MODEL_VISION,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=INTENT_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=IntentRequirement.model_json_schema()
                )
            )
            req_obj = IntentRequirement.model_validate_json(response.text)
        else:
            # 纯文字 → 用 DeepSeek，更快更省钱
            print(f"⚡ [Node 1] 纯文本请求，调用 DeepSeek ({settings.MODEL_FAST})")
            schema_hint = json.dumps(IntentRequirement.model_json_schema(), ensure_ascii=False)
            ds_response = deepseek_llm.invoke([
                SystemMessage(content=INTENT_SYSTEM_PROMPT + f"\n\n请严格按照以下 JSON Schema 输出：{schema_hint}"),
                HumanMessage(content=f"【老师要求】:\n{raw_prompt}")
            ])
            raw_json = ds_response.content.strip().lstrip("```json").rstrip("```").strip()
            req_obj = IntentRequirement.model_validate_json(raw_json)

        req_dict = req_obj.model_dump()
        print(f"✅ [Node 1] 意图解析完成！核心约束抓取: {req_dict['constraints']}")
        print("="*50 + "\n")
        return {"requirement": req_dict}

    except Exception as e:
        print(f"❌ [Node 1] 意图解析报错: {e}")
        return {"requirement": {"topic": "综合数学", "constraints": raw_prompt, "count": 3}}
# src/nodes/reviewer_old.py
import json
import base64
import re
import os
from typing import Dict, Any, List
from pathlib import Path

# 引入 LangChain 的 Google Gemini 专属支持
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import settings
from src.schemas.graph_state import SelectionState
from src.schemas.data_models import ReviewResult

# 1. 轻量级初筛模型：使用高并发、极速的 Gemini Flash
fast_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # 免费层额度高，速度极快
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.5
)

# 2. 严苛精审与多模态模型：使用你在 config 里配置的 VISION 模型 (如 gemini-3-flash-preview)
reasoner_llm = ChatGoogleGenerativeAI(
    model=settings.MODEL_VISION, 
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.1
)

REVIEWER_SYSTEM_PROMPT = """
你是一位严苛且极具视觉敏锐度的高中数学教研组长。你的任务是审核候选题目，并挑选出完全符合要求的高质量题目。

【绝对禁忌与图形排雷规则】（触犯任意一条直接淘汰该题）：
1. 缺失残损：如果题目正文中出现了“如图所示”、“右图”、“图1”等强烈依赖图形的字眼，但候选素材中【没有】提供对应的图片链接，必须无情淘汰！绝对不能让学生做缺图的残次题。
2. 考点偏离：不符合用户要求的核心考点。
3. 难度超纲或没有详细解答过程。

【排版保留规则】：
如果候选素材包含图片（如 `![描述](url)`），请你务必将其原封不动地保留在 `question_text` 或 `answer` 的恰当位置中。

你必须严格输出 JSON 格式，结构如下：
{
  "feedback": "整体审核报告（明确说明你淘汰了哪些缺图的题目，入选了哪些高质量题目）",
  "selected_questions": [
    {
      "question_text": "完整的题目内容（包含必须的图片链接）",
      "options": ["A", "B", "C", "D"], // 如果是解答题，这里可以为空列表 []
      "answer": "详细的解答过程（包含必须的辅助线说明或图片）",
      "source": "题目来源标识"
    }
  ]
}
"""

def quick_filter_candidates(candidates: List[str], req: Dict) -> List[str]:
    """快速初筛：用便宜快的模型剔除明显无关的废料"""
    print("\n" + "╔" + "═" * 78 + "╗")
    print("║ [Node 3.1] 快速初筛阶段：启用 Gemini 多模态漏斗过滤                              ║")
    print("╚" + "═" * 78 + "╝")
    
    topic = req.get("topic", "")
    count = req.get("count", 3)
    max_keep = max(count * 2, 5)
    
    print(f"  📊 输入初筛的候选题目总数: {len(candidates)}")
    print(f"  🎯 目标知识点: {topic}")
    print(f"  📍 最多保留数量: {max_keep}\n")
    
    if len(candidates) <= max_keep:
        print(f"  ℹ️ 候选题目数 ≤ 阈值({max_keep})，跳过初筛，直接返回全部")
        return candidates
    
    # 只取一部分文本，防止上下文爆炸
    candidates_summary = "\n\n".join([f"[题 {i+1}] {c[:350]}..." for i, c in enumerate(candidates[:20])])
    
    filter_prompt = f"""
    目标知识点：{topic}
    请快速扫视以下候选题目摘要。哪些题目【粗看】是相关的？
    {candidates_summary}
    只输出相关题目的编号数字，用逗号分隔（例如：1,3,4,6）。不要输出任何其他废话！
    """
    
    print("  📝 [初筛 Step 1] 构建初筛提示词...")
    print(f"     提示词长度: {len(filter_prompt)} 字符")
    print(f"     包含的题目摘要数: {min(20, len(candidates))}\n")
    
    try:
        print("  🚀 [初筛 Step 2] 调用 Gemini Flash 初筛模型...")
        response = fast_llm.invoke([
            SystemMessage(content="你是极速质检员，立刻输出编号。"),
            HumanMessage(content=filter_prompt)
        ])
        
        raw_response = response.content.strip()
        print(f"  ✅ [初筛 Step 3] 模型原始返回: '{raw_response}'")
        
        # 粗暴解析编号
        indices = [int(x.strip()) - 1 for x in raw_response.split(",") if x.strip().isdigit()]
        print(f"  🔍 [初筛 Step 4] 解析出的题目索引: {[i+1 for i in indices]}")
        
        filtered = [candidates[i] for i in indices if i < len(candidates) and i >= 0]
        
        if filtered:
            print(f"  ✅ [初筛 Step 5] 降维打击成功：{len(candidates)} → {len(filtered)} 条")
            return filtered[:max_keep]
    except Exception as e:
        print(f"  ⚠️ [初筛异常] {type(e).__name__}: {e}")
        print(f"     启用保守策略，返回前 {max_keep} 条\n")
    
    return candidates[:max_keep]


def review_and_select_node(state: SelectionState) -> Dict[str, Any]:
    print("\n" + "="*50)
    print(f"⏳ [Node 3] 质检教研组长上线，开始严苛审题与图形排雷 (启用 {settings.MODEL_VISION})...")

    req = state.get("requirement", {})
    raw_candidates = state.get("raw_candidates", [])

    if not raw_candidates:
        print("❌ [Node 3] 弹药库为空，退回！")
        return {"review_feedback": "未找到任何素材，退回查资料", "validated_questions": []}

    # === 前置漏斗粗筛 (Fast 模型) ===
    filtered_candidates = quick_filter_candidates(raw_candidates, req)

    # === 精筛与多模态组装 (Vision 模型) ===
    candidates_text = "\n\n".join([f"[素材 {i + 1}] {c}" for i, c in enumerate(filtered_candidates)])
    
    user_prompt = f"""
    【出题要求】
    知识点：{req.get('topic')}
    约束条件：{req.get('constraints')}
    需要题量：{req.get('count', 3)} 道

    【已过滤的精选素材】
    {candidates_text}

    请执行严苛审核。务必检查“如图”等字眼是否与实际图片链接匹配，缺图题坚决不要！如果挑不够数量，有几道写几道，并生成标准 JSON。
    """

    # 1. 提取所有形如 ![xxx](url) 中的 url
    img_urls = re.findall(r'!\[.*?\]\((.*?)\)', candidates_text)
    img_urls = list(set(img_urls)) # 去重
    
    messages_content = [{"type": "text", "text": user_prompt}]
    base_dir = Path(__file__).parent.parent.parent.resolve()
    
    if img_urls:
        print(f"  👁️ [多模态视觉] 在 RAG 题库中检测到 {len(img_urls)} 个图像锚点！")
        print(f"  🔄 正在将本地物理资产转化为 Base64 视觉阵列...")

    # 2. 将本地图片转换为大模型可见的 Base64 矩阵
    for url in img_urls:
        if url.startswith("assets/images/"):
            local_path = base_dir / url
            if local_path.exists():
                with open(local_path, "rb") as img_file:
                    b64_data = base64.b64encode(img_file.read()).decode("utf-8")
                    messages_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}
                    })
                print(f"    📸 成功加载并编码图像: {local_path.name}")
            else:
                print(f"    ⚠️ 警告: 找不到本地物理图像 {local_path}")
        
        elif url.startswith("http"):
            # 如果是外网公开 URL（如网络检索回来的），直接发给大模型
            messages_content.append({"type": "image_url", "image_url": {"url": url}})
            print(f"    🌐 加载公网图像链接: {url}")

    # 3. 投喂给多模态大模型
    try:
        response = reasoner_llm.invoke([
            SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
            HumanMessage(content=messages_content) 
        ])
        
        # 【核心修复：多模态内容提取防爆盾】
        raw_content = response.content
        
        # 1. 检查是否为多模态特有的 List 结构
        if isinstance(raw_content, list):
            print("  [DEBUG] 检测到模型返回了多块混合(List)结构，正在拼接...")
            # 遍历列表，提取所有的纯文本块并拼接起来
            raw_text = "".join([
                block.get("text", "") 
                for block in raw_content 
                if isinstance(block, dict) and "text" in block
            ])
        else:
            # 2. 如果是正常的单个字符串，直接用
            raw_text = str(raw_content)

        # 拿到纯净的字符串后，再放心大胆地执行清洗
        raw_text = raw_text.strip()
        
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()

        # 原生 JSON 解析
        result_dict = json.loads(raw_text)
        
        # 重新引入 Pydantic 校验护城河
        review_obj = ReviewResult(**result_dict)
        
        validated_q = review_obj.selected_questions
        feedback = review_obj.feedback

        if len(validated_q) < req.get('count', 3) * 0.5:
            print(f"⚠️ [Node 3] 质检不通过：{feedback}")
            return {"review_feedback": f"质量太差或缺图严重：{feedback}", "validated_questions": []}

        print(f"✅ [Node 3] 质检通过！最终报告：{feedback}")
        print("="*50 + "\n")
        return {
            "review_feedback": "SUCCESS", 
            "validated_questions": validated_q,
            "raw_candidates": [] 
        }

    except json.JSONDecodeError as e:
        print(f"❌ [Node 3] JSON 解析失败! 返回内容: {raw_text[:200]}...")
        # 普通的格式错误，允许它退回重试
        return {"review_feedback": f"JSON解析失败: {e}", "validated_questions": []}

    except Exception as e:
        # 如果是其他的致命错误（比如 429 额度爆了），打上 FATAL_ERROR 标签，触发上层的熔断机制
        print(f"❌ [Node 3] 视觉大模型崩溃或校验致命失败: {e}")
        return {"review_feedback": f"FATAL_ERROR: 解析或校验失败: {e}", "validated_questions": []}
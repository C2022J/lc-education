# src/nodes/reviewer.py
import json
import base64
import re
from typing import Dict, Any, List
from pathlib import Path

# 引入 LangChain 的 Google Gemini 专属支持
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import settings
from src.schemas.graph_state import SelectionState
from src.schemas.data_models import ReviewResult

# 1. 轻量级初筛模型：DeepSeek-chat，纯文本分类任务，比 Gemini Flash 便宜
fast_llm = ChatOpenAI(
    model=settings.MODEL_FAST,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_API_BASE,
    temperature=0.0,
)

# 2. 严苛精审与多模态模型：保留 Gemini Vision，负责图文核对与 OCR 纠错
reasoner_llm = ChatGoogleGenerativeAI(
    model=settings.MODEL_VISION,
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.1,
    max_output_tokens=8192,
)

REVIEWER_SYSTEM_PROMPT = """
你是一位严苛的高中数学教研组长，兼任顶级多模态试题校对员。
你的任务是审核候选题目，利用你看到的图片（如果有）对题目文本进行核对与修复，并挑选出完全符合要求的高质量题目。

【图片链接说明——必须理解】
候选素材的文本中，凡是出现 ![说明文字](/assets/images/xxx.jpg) 这种 Markdown 格式的内容，就代表该题目已经附有配图，图片已提供。你收到的附加图片（Base64 编码）就是这些题目配图的实体。题目文本里有 `![...](...)` 标记 = 图片已提供，不得以缺图为由淘汰。

【图片链接必须放在 question_text 字段——极其重要】
- 学生版试卷只展示 `question_text` 字段，绝不展示 `answer` 字段
- 因此，原文题干中出现的图片链接（![...](...)），必须原样保留在输出的 `question_text` 字段中，位置与原文一致
- 如果解析过程中也需要引用同一张图片，可以在 `answer` 字段中额外包含该链接，但这是可选的
- 禁止把图片链接从 `question_text` 移走或只放在 `answer` 中

【核心工作机制：图文核对与自我修复】
1. 视觉纠错：当你同时收到文本和对应的图片时，请仔细对比。如果发现文本中存在 OCR 识别错误（例如字母混淆、垂直符号识别错、角标遗漏等），请依据你看到的真实图片，直接在输出的 `question_text` 或 `answer` 中进行修正！
2. 锚点锁死：题目或解答中包含的 Markdown 图片链接（例如：`![说明](/assets/images/xxx.jpg)`），是极其重要的物理锚点。你在输出修复后的文本时，必须【一字不差】地将这些图片链接保留在原本的位置，绝对不允许修改、缩写或删除！

【绝对禁忌与淘汰规则】（触犯任意一条直接淘汰该题）：
1. 严重残损与缺图：如果题目正文中出现了”如图所示”、”右图”、”图1”等强烈依赖图形的字眼，且素材文本中完全没有任何 `![...](...)` 格式的图片标记，才算缺图，必须淘汰。只要文本中有 `![...](...)` 标记，即视为已提供图片，不得淘汰。
2. 考点偏离：不符合用户要求的核心考点。
3. 难度超纲或没有详细解答过程。

【JSON 输出格式规范——严格遵守】
- 所有字符串字段中，换行统一用 \\n 表示，不得在字符串内部出现真实换行
- 字符串值内部不得包含未转义的英文双引号（”），必须写成 \\”
- LaTeX 数学公式中的反斜杠（如 \\frac、\\left、\\right 等）在 JSON 字符串里必须写成双反斜杠（\\\\frac、\\\\left、\\\\right）
- 图片链接 ![说明](/assets/images/xxx.jpg) 中的斜杠不用额外转义，保持原样即可

你必须严格输出 JSON 格式，结构如下：
{
  “feedback”: “整体审核与校对报告（明确说明你淘汰了哪些题，保留了哪些题。如果对保留的题目进行了 OCR 纠错，请简要说明修复了什么错误）”,
  “selected_questions”: [
    {
      “question_text”: “校对并修复后的完整题目内容（必须包含原始的图片链接，图片链接必须在此字段）”,
      “options”: [“A”, “B”, “C”, “D”],
      “answer”: “校对并修复后的完整解答过程”,
      “source”: “题目来源标识”
    }
  ]
}
"""

def quick_filter_candidates(candidates: List[str], req: Dict) -> List[str]:
    """
    快速初筛:用便宜快的模型剔除明显无关的废料
    """

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


async def review_and_select_node(state: SelectionState) -> Dict[str, Any]:
    print("\n" + "╔" + "═" * 78 + "╗")
    print(f"║ [Node 3] 质检教研组长上线，启用 {settings.MODEL_VISION.ljust(44)} ║"[:81])
    print("╚" + "═" * 78 + "╝")

    req = state.get("requirement", {})
    raw_candidates = state.get("raw_candidates", [])

    if not raw_candidates:
        print("❌ [Node 3] 弹药库为空，退回！")
        return {"review_feedback": "未找到任何素材，退回查资料", "validated_questions": []}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ RAG搜索结果 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "─" * 80)
    print("[3.0] RAG 搜索原始结果完整内容")
    print("─" * 80)
    print(f"📊 总共检索到 {len(raw_candidates)} 条原始素材\n")
    for idx, candidate in enumerate(raw_candidates, 1):
        print(f"┌─ 【素材 {idx}】" + "─" * (70 - len(f"【素材 {idx}】")))
        # 限制单条输出长度，但提示完整长度
        preview_len = min(500, len(candidate))
        print(candidate[:preview_len])
        if len(candidate) > preview_len:
            print(f"\n   ... (省略 {len(candidate) - preview_len} 字符，总长 {len(candidate)} 字符)")
        print(f"└─ [长度: {len(candidate)} 字符]")
        print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 前置漏斗粗筛 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "╔" + "═" * 78 + "╗")
    print("║ [3.1] 前置漏斗粗筛 (Fast 模型)                                           ║")
    print("╚" + "═" * 78 + "╝")
    filtered_candidates = quick_filter_candidates(raw_candidates, req)
    print(f"\n✅ [3.1 完成] 粗筛后保留 {len(filtered_candidates)} 条素材")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 分组：有图 vs 无图 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "─" * 80)
    print("[3.2] 候选素材分组（有图单独调用 / 无图批量调用）")
    print("─" * 80)
    base_dir = Path(__file__).parent.parent.parent.resolve()

    with_img  = [c for c in filtered_candidates if re.search(r'!\[.*?\]\(', c)]
    without_img = [c for c in filtered_candidates if not re.search(r'!\[.*?\]\(', c)]
    print(f"  📸 含图题目: {len(with_img)} 道（每道单独调用）")
    print(f"  📄 纯文字题目: {len(without_img)} 道（批量调用）\n")

    all_validated: list = []
    all_feedback: list  = []

    # ── 工具函数 ─────────────────────────────────────────────────────────────────
    def _load_images(text: str) -> list:
        """从题目文本中提取图片 URL 并转为 Base64 image_url 块，不限数量。"""
        urls = re.findall(r'!\[.*?\]\(([^)]+)\)', text)
        blocks = []
        for url in urls:
            if url.startswith("http"):
                blocks.append({"type": "image_url", "image_url": {"url": url}})
                print(f"    🌐 公网图片: {url}")
                continue
            img_filename = Path(url).name
            local_path = base_dir / "assets" / "images" / img_filename
            if local_path.exists():
                b64 = base64.b64encode(local_path.read_bytes()).decode()
                blocks.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
                print(f"    ✅ 已加载: {img_filename} ({local_path.stat().st_size} 字节)")
            else:
                print(f"    ❌ 文件不存在: {local_path}")
        return blocks

    def _build_prompt(candidates_text: str, req: dict) -> str:
        return f"""
    【出题要求】
    知识点：{req.get('topic')}
    约束条件：{req.get('constraints')}
    需要题量：{req.get('count', 3)} 道

    【候选素材】
    {candidates_text}

    请严苛审核，生成标准 JSON。有几道合格写几道，不够数量不要凑数。
    """

    def _parse_response(raw_content) -> tuple[list, str]:
        """解析模型返回，返回 (selected_questions, feedback)。失败返回 ([], 错误信息)。"""
        if isinstance(raw_content, list):
            raw_text = "".join(b.get("text", "") for b in raw_content if isinstance(b, dict) and "text" in b)
        else:
            raw_text = str(raw_content)

        raw_text = raw_text.strip()

        # 剥掉 markdown 代码块
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        # 去掉末尾的 ``` 及多余空白
        raw_text = re.sub(r'```\s*$', '', raw_text).strip()

        # 修复未双转义的 LaTeX 反斜杠（保留合法 JSON 转义符 \n \t \f \b \u \"  \\ \/）
        fixed = re.sub(r'(?<!\\)\\(?!["\\/bfntu])', r'\\\\', raw_text)

        print(f"    [模型原始返回（前400字符）] {repr(fixed[:400])}")

        # ── 尝试 1：直接解析 ────────────────────────────────────────────────────
        try:
            result_dict = json.loads(fixed, strict=False)
            review_obj = ReviewResult(**result_dict)
            print(f"    ✅ 解析成功（直接解析）")
            return review_obj.selected_questions, review_obj.feedback
        except Exception as e1:
            print(f"    ⚠️ 尝试1 失败: {e1}")

        # ── 尝试 2：截取最外层 {{ }} 块后再解析（应对前后多余文字） ────────────
        try:
            start = fixed.index('{')
            end = fixed.rindex('}')
            trimmed = fixed[start:end + 1]
            result_dict = json.loads(trimmed, strict=False)
            review_obj = ReviewResult(**result_dict)
            print(f"    ✅ 解析成功（边界截取）")
            return review_obj.selected_questions, review_obj.feedback
        except Exception as e2:
            print(f"    ⚠️ 尝试2 失败: {e2}")

        # ── 尝试 3：正则提取 selected_questions 列表 ────────────────────────────
        try:
            arr_match = re.search(r'"selected_questions"\s*:\s*(\[.*?\])\s*[,}]', fixed, re.DOTALL)
            fb_match  = re.search(r'"feedback"\s*:\s*"((?:[^"\\]|\\.)*)"', fixed)
            if arr_match:
                questions_raw = json.loads(arr_match.group(1), strict=False)
                feedback_raw  = fb_match.group(1) if fb_match else "（反馈提取失败）"
                result_dict   = {"feedback": feedback_raw, "selected_questions": questions_raw}
                review_obj    = ReviewResult(**result_dict)
                print(f"    ✅ 解析成功（正则提取）")
                return review_obj.selected_questions, review_obj.feedback
        except Exception as e3:
            print(f"    ⚠️ 尝试3 失败: {e3}")

        print(f"    ❌ 全部解析方式均失败，返回空列表")
        print(f"    [完整原始内容]\n{fixed}")
        return [], f"JSON解析失败: {e1}"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 有图题目：并行调用 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("╔" + "═" * 78 + "╗")
    print(f"║ [3.3] 含图题目并行审核（{len(with_img)} 道同时发出）{'':44}║"[:81])
    print("╚" + "═" * 78 + "╝")

    def _review_single(idx: int, candidate: str):
        """同步函数，在线程池里跑，供 asyncio.to_thread 调用。"""
        print(f"\n  ── 【含图题目 {idx}/{len(with_img)}】 ──")
        print(f"  题目内容:\n{candidate}\n")
        img_blocks = _load_images(candidate)
        print(f"  图片块数量: {len(img_blocks)}")
        prompt = _build_prompt(f"[素材 1] {candidate}", req)
        messages_content = [{"type": "text", "text": prompt}] + img_blocks
        print(f"  ⏳ 调用 {settings.MODEL_VISION}...")
        response = reasoner_llm.invoke([
            SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
            HumanMessage(content=messages_content)
        ])
        questions, feedback = _parse_response(response.content)
        print(f"  ✅ [{idx}] 审核完成，通过: {len(questions)} 道，反馈: {feedback[:80]}")
        return questions, feedback

    try:
        import asyncio as _asyncio
        tasks = [_asyncio.to_thread(_review_single, i + 1, c) for i, c in enumerate(with_img)]
        results = await _asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                print(f"  ❌ 某道含图题目审核失败: {r}")
            else:
                questions, feedback = r
                all_validated.extend(questions)
                all_feedback.append(feedback)
    except Exception as e:
        print(f"  ❌ 含图题目并行审核异常: {e}")
        import traceback; traceback.print_exc()
        return {"review_feedback": f"FATAL_ERROR: {e}", "validated_questions": []}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 无图题目：批量调用 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if without_img:
        print("\n" + "╔" + "═" * 78 + "╗")
        print("║ [3.4] 纯文字题目批量审核                                                  ║")
        print("╚" + "═" * 78 + "╝")
        candidates_text = "\n\n".join([f"[素材 {i+1}] {c}" for i, c in enumerate(without_img)])
        prompt = _build_prompt(candidates_text, req)
        print(f"  题目数: {len(without_img)}，提示词长度: {len(prompt)} 字符")
        print(f"  ── 完整提示词 ──\n{prompt}\n  ── 结束 ──")
        try:
            print(f"  ⏳ 调用 {settings.MODEL_VISION}...")
            response = await _asyncio.to_thread(
                reasoner_llm.invoke,
                [SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
                 HumanMessage(content=[{"type": "text", "text": prompt}])]
            )
            questions, feedback = _parse_response(response.content)
            print(f"  ✅ 批量审核完成，通过: {len(questions)} 道，反馈: {feedback[:80]}")
            all_validated.extend(questions)
            all_feedback.append(feedback)
        except Exception as e:
            print(f"  ❌ 纯文字题目审核异常: {e}")
            import traceback; traceback.print_exc()
            return {"review_feedback": f"FATAL_ERROR: {e}", "validated_questions": []}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 汇总结果 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    combined_feedback = " | ".join(all_feedback)
    print("\n" + "─" * 80)
    print("[3.5] 质检汇总")
    print("─" * 80)
    print(f"📊 最终挑选题目数: {len(all_validated)} / {req.get('count', 3)} 道")
    print(f"📝 质检报告: {combined_feedback}\n")

    if len(all_validated) < req.get('count', 3) * 0.5:
        print(f"⚠️ [3.5] 质检不通过：题目数不足")
        return {"review_feedback": f"质量太差或缺图严重：{combined_feedback}", "validated_questions": []}

    print(f"✅ [3.5] 质检通过！最终返回 {len(all_validated)} 道题目")
    print("╔" + "═" * 78 + "╗")
    print("║ [Node 3] 质检完成                                                       ║")
    print("╚" + "═" * 78 + "╝\n")

    return {
        "review_feedback": "SUCCESS",
        "validated_questions": all_validated,
        "raw_candidates": []
    }


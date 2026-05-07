# src/nodes/reviewer.py
import json
import base64
import re
import os
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
    temperature=0.1
)

REVIEWER_SYSTEM_PROMPT = """
你是一位严苛的高中数学教研组长，兼任顶级多模态试题校对员。
你的任务是审核候选题目，利用你看到的图片（如果有）对题目文本进行核对与修复，并挑选出完全符合要求的高质量题目。

【核心工作机制：图文核对与自我修复】
1. 视觉纠错：当你同时收到文本和对应的图片时，请仔细对比。如果发现文本中存在 OCR 识别错误（例如字母混淆、垂直符号识别错、角标遗漏等），请依据你看到的真实图片，直接在输出的 `question_text` 或 `answer` 中进行修正！
2. 锚点锁死：题目或解答中包含的 Markdown 图片链接（例如：`![说明](assets/images/xxx.jpg)`），是极其重要的物理锚点。你在输出修复后的文本时，必须【一字不差】地将这些图片链接保留在原本的位置，绝对不允许修改、缩写或删除！

【绝对禁忌与淘汰规则】（触犯任意一条直接淘汰该题）：
1. 严重残损与缺图：如果题目正文中出现了“如图所示”、“右图”、“图1”等强烈依赖图形的字眼，但候选素材中【没有】提供对应的图片链接，必须无情淘汰！绝对不能让学生做缺图的残次题。
2. 考点偏离：不符合用户要求的核心考点。
3. 难度超纲或没有详细解答过程。

你必须严格输出 JSON 格式，结构如下：
{
  "feedback": "整体审核与校对报告（明确说明你淘汰了哪些题，保留了哪些题。如果对保留的题目进行了 OCR 纠错，请简要说明修复了什么错误）",
  "selected_questions": [
    {
      "question_text": "校对并修复后的完整题目内容（必须包含原始的图片链接）",
      "options": ["A", "B", "C", "D"], // 如果是解答题，这里可以为空列表 []
      "answer": "校对并修复后的完整解答过程（必须包含原始的图片链接）",
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 组装精筛文本 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "─" * 80)
    print("[3.2] 组装精筛用的候选素材文本")
    print("─" * 80)
    candidates_text = "\n\n".join([f"[素材 {i + 1}] {c}" for i, c in enumerate(filtered_candidates)])
    print(f"📝 已过滤的素材总长度: {len(candidates_text)} 字符")
    print(f"📝 包含素材数: {len(filtered_candidates)}\n")
    
    user_prompt = f"""
    【出题要求】
    知识点：{req.get('topic')}
    约束条件：{req.get('constraints')}
    需要题量：{req.get('count', 3)} 道

    【已过滤的精选素材】
    {candidates_text}

    请执行严苛审核。务必检查"如图"等字眼是否与实际图片链接匹配，缺图题坚决不要！如果挑不够数量，有几道写几道，并生成标准 JSON。
    """
    
    print(f"❓ 出题要求:")
    print(f"   知识点: {req.get('topic')}")
    print(f"   约束条件: {req.get('constraints')}")
    print(f"   需要题量: {req.get('count', 3)} 道")
    print(f"   用户提示词总长度: {len(user_prompt)} 字符\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 图像提取与编码 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─" * 80)
    print("[3.3] 图像提取与 Base64 编码")
    print("─" * 80)
    
    # 0. 首先分析候选素材中的所有图片链接
    print("\n  [3.3.0] 分析候选素材中的图片链接")
    print(f"  📝 候选素材文本总长度: {len(candidates_text)} 字符")
    
    # 1. 提取所有形如 ![xxx](url) 中的 url
    img_urls = re.findall(r'!\[.*?\]\((.*?)\)', candidates_text)
    print(f"  📍 正则匹配到的图像锚点总数: {len(img_urls)}")
    print(f"  📌 说明: '图像锚点'是指在候选素材中形如 ![描述](url) 的图片引用标记")
    print(f"  ⚠️  注意: 如果有重复 URL，下面会去重")
    
    print(f"\n  📸 所有图像 URL (去重前):")
    for i, url in enumerate(img_urls, 1):
        print(f"     [{i}] {url}")
    
    img_urls = list(set(img_urls))  # 去重

    # 限制最多发送的图片数量，避免 token 爆炸
    MAX_IMAGES = 5
    if len(img_urls) > MAX_IMAGES:
        print(f"  ⚠️ 图片数量 {len(img_urls)} 超过上限 {MAX_IMAGES}，截断至前 {MAX_IMAGES} 张")
        img_urls = img_urls[:MAX_IMAGES]

    print(f"\n  ✂️ 去重后的图像 URL:")
    for i, url in enumerate(img_urls, 1):
        print(f"     [{i}] {url}")
    
    print()
    
    messages_content = [{"type": "text", "text": user_prompt}]
    base_dir = Path(__file__).parent.parent.parent.resolve()
    
    # 2. 将本地图片转换为大模型可见的 Base64 矩阵
    local_images_loaded = 0
    web_images_loaded = 0
    failed_images = []
    
    for url_idx, url in enumerate(img_urls, 1):
        print(f"  处理图像 [{url_idx}/{len(img_urls)}]: {url}")
        
        # 支持三种路径格式：images/xxx, assets/images/xxx, 完整http URL
        if url.startswith("assets/images/"):
            local_path = base_dir / url
            path_format = "assets/images/ 格式"
        elif url.startswith("images/"):
            # 如果是 images/xxx 格式，补全为 assets/images/xxx
            local_path = base_dir / "assets" / url
            path_format = "images/ 格式 (已补全为 assets/images/)"
        elif url.startswith("http"):
            path_format = "http URL"
            local_path = None
        else:
            path_format = "未知格式"
            local_path = None
        
        print(f"    📂 路径格式: {path_format}")
        
        if local_path is not None:
            print(f"    📂 本地路径: {local_path}")
            print(f"    ✔️ 路径存在: {local_path.exists()}")
            
            if local_path.exists():
                with open(local_path, "rb") as img_file:
                    img_bytes = img_file.read()
                    b64_data = base64.b64encode(img_bytes).decode("utf-8")
                    
                    messages_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}
                    })
                    
                    print(f"    ✅ 成功加载并编码: {local_path.name}")
                    print(f"       原始大小: {len(img_bytes)} 字节")
                    print(f"       Base64大小: {len(b64_data)} 字符")
                    print(f"       Base64 前50字符: {b64_data[:50]}...")
                    print(f"       Base64 末50字符: ...{b64_data[-50:]}")
                    local_images_loaded += 1
            else:
                print(f"    ❌ 错误: 本地图像文件不存在！")
                failed_images.append(url)
        
        elif url.startswith("http"):
            messages_content.append({"type": "image_url", "image_url": {"url": url}})
            print(f"    ✅ 加载公网图像链接")
            web_images_loaded += 1
        else:
            print(f"    ❓ 未知的 URL 格式，跳过")
            failed_images.append(url)
        
        print()
    
    print(f"📊 [3.3 统计]")
    print(f"   本地图像成功加载: {local_images_loaded}")
    print(f"   公网图像成功加载: {web_images_loaded}")
    print(f"   加载失败数: {len(failed_images)}")
    if failed_images:
        print(f"   失败的 URL:")
        for url in failed_images:
            print(f"      - {url}")
    print(f"   消息内容块总数: {len(messages_content)} (包含 1 个文本块 + {local_images_loaded + web_images_loaded} 个图像块)\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 最终消息内容预览 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─" * 80)
    print("[3.4] 最终投喂给多模态大模型的消息内容")
    print("─" * 80)
    print(f"📦 messages_content 结构 (共 {len(messages_content)} 块):")
    for i, block in enumerate(messages_content):
        if block["type"] == "text":
            print(f"\n   [块 {i+1}] 文本块")
            print(f"      长度: {len(block['text'])} 字符")
            print(f"      预览: {block['text'][:200]}...")
        elif block["type"] == "image_url":
            url = block["image_url"]["url"]
            if url.startswith("data:image/jpeg;base64,"):
                b64_part = url[len("data:image/jpeg;base64,"):]
                print(f"\n   [块 {i+1}] Base64 图像")
                print(f"      Base64 长度: {len(b64_part)} 字符")
                print(f"      预览: {b64_part[:50]}...{b64_part[-30:]}")
            else:
                print(f"\n   [块 {i+1}] 网络图像链接")
                print(f"      URL: {url}")
    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调用多模态大模型 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("╔" + "═" * 78 + "╗")
    print("║ [3.5] 调用多模态大模型进行精筛与质检                                      ║")
    print("╚" + "═" * 78 + "╝")
    print(f"🚀 调用模型: {settings.MODEL_VISION}")
    print(f"🌡️  温度参数: 0.1 (确定性高)\n")

    # 3. 投喂给多模态大模型
    try:
        print("⏳ [3.5.1] 发送请求到大模型...\n")
        response = reasoner_llm.invoke([
            SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
            HumanMessage(content=messages_content) 
        ])
        
        print("✅ [3.5.2] 收到大模型回复\n")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 处理大模型返回 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─" * 80)
        print("[3.6] 处理大模型返回内容")
        print("─" * 80)
        
        raw_content = response.content
        print(f"📦 原始返回类型: {type(raw_content).__name__}")
        print(f"   是否为 List 结构: {isinstance(raw_content, list)}\n")

        # 1. 检查是否为多模态特有的 List 结构
        if isinstance(raw_content, list):
            print("  [3.6.1] 检测到 List 结构，逐块打印内容:")
            for block_idx, block in enumerate(raw_content):
                print(f"\n    ├─ [块 {block_idx}] 类型: {type(block).__name__}")
                if isinstance(block, dict):
                    print(f"    │  键: {list(block.keys())}")
                    if "text" in block:
                        text_content = block["text"]
                        print(f"    │  文本长度: {len(text_content)} 字符")
                        print(f"    │  内容预览: {text_content[:100]}...")
                else:
                    print(f"    │  内容: {str(block)[:100]}...")
            
            # 拼接所有文本块
            print("\n  [3.6.2] 拼接所有文本块...")
            raw_text = "".join([
                block.get("text", "") 
                for block in raw_content 
                if isinstance(block, dict) and "text" in block
            ])
            print(f"  ✅ 拼接完成，总长度: {len(raw_text)} 字符")
        else:
            # 2. 如果是正常的单个字符串，直接用
            raw_text = str(raw_content)
            print(f"  [3.6.1] 直接使用字符串返回，长度: {len(raw_text)} 字符")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 清洗与解析 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n─" * 80)
        print("[3.7] 清洗与 JSON 解析")
        print("─" * 80)
        
        print(f"\n  [3.7.1] 原始返回内容 (前 300 字符):")
        print(f"  {repr(raw_text[:300])}\n")
        
        # 去除首尾空格
        raw_text = raw_text.strip()
        print(f"  [3.7.2] 去除首尾空格后长度: {len(raw_text)} 字符")
        
        # 处理 markdown 代码块
        if raw_text.startswith("```json"):
            print(f"  [3.7.3] 检测到 ```json 代码块，正在移除...")
            raw_text = raw_text[7:-3].strip()
            print(f"         处理后长度: {len(raw_text)} 字符")
        elif raw_text.startswith("```"):
            print(f"  [3.7.3] 检测到 ``` 代码块，正在移除...")
            raw_text = raw_text[3:-3].strip()
            print(f"         处理后长度: {len(raw_text)} 字符")
        else:
            print(f"  [3.7.3] 无代码块包装")

        # ==================== 👇 核心修改在这里 👇 ====================
        print(f"  [3.7.3.5] 执行 LaTeX 公式反斜杠双重转义防御...")
        # 匹配那些后面没有跟着合法 JSON 转义符 (", \, /, b, f, n, r, t, u) 的单反斜杠，将其替换为双反斜杠
        raw_text = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', raw_text)
        # =============================================================
        #        
        print(f"\n  [3.7.4] 清洗后的 JSON 内容预览 (前 500 字符):")
        print(f"  {raw_text[:500]}\n")
        
        # 原生 JSON 解析
        print(f"  [3.7.5] 执行 JSON 解析...")
        result_dict = json.loads(raw_text, strict=False)
        print(f"  ✅ JSON 解析成功！")
        print(f"     顶级键: {list(result_dict.keys())}")
        if "feedback" in result_dict:
            print(f"     反馈内容长度: {len(result_dict['feedback'])} 字符")
            print(f"     反馈内容预览: {result_dict['feedback'][:200]}...")
        if "selected_questions" in result_dict:
            print(f"     挑选题目数: {len(result_dict['selected_questions'])} 道\n")
        
        # Pydantic 校验
        print(f"  [3.7.6] 执行 Pydantic 数据校验...")
        review_obj = ReviewResult(**result_dict)
        print(f"  ✅ 数据校验通过！\n")
        
        validated_q = review_obj.selected_questions
        feedback = review_obj.feedback

        print("─" * 80)
        print("[3.8] 质检结果")
        print("─" * 80)
        print(f"📊 最终挑选题目数: {len(validated_q)} / {req.get('count', 3)} 道")
        print(f"📝 质检报告:\n{feedback}\n")

        if len(validated_q) < req.get('count', 3) * 0.5:
            print(f"⚠️ [3.8] 质检不通过：题目数不足")
            return {"review_feedback": f"质量太差或缺图严重：{feedback}", "validated_questions": []}

        print(f"✅ [3.8] 质检通过！最终返回 {len(validated_q)} 道题目")
        print("╔" + "═" * 78 + "╗")
        print("║ [Node 3] 质检完成                                                       ║")
        print("╚" + "═" * 78 + "╝\n")
        
        return {
            "review_feedback": "SUCCESS", 
            "validated_questions": validated_q,
            "raw_candidates": [] 
        }

    except json.JSONDecodeError as e:
        print(f"❌ [3.7] JSON 解析失败!")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   错误信息: {e}")
        print(f"   错误位置: 第 {e.lineno} 行, 第 {e.colno} 列")
        print(f"   返回内容长度: {len(raw_text)} 字符")
        print(f"   返回内容 (前 500 字符):\n{raw_text[:500]}\n")
        
        # 普通的格式错误，允许它退回重试
        return {"review_feedback": f"JSON解析失败: {e}", "validated_questions": []}

    except Exception as e:
        # 如果是其他的致命错误（比如 429 额度爆了），打上 FATAL_ERROR 标签，触发上层的熔断机制
        print(f"❌ [3.9] 视觉大模型崩溃或校验致命失败!")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   错误信息: {e}")
        import traceback
        print(f"   完整堆栈:\n{traceback.format_exc()}\n")
        
        return {"review_feedback": f"FATAL_ERROR: 解析或校验失败: {e}", "validated_questions": []}

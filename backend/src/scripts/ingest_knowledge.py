# src/scripts/ingest_knowledge.py
import re
import json
import time
import zipfile
import io
import requests
from pathlib import Path
from typing import Callable, Optional
from langchain_core.documents import Document
from src.tools.rag_search import vector_store
from src.config.settings import settings

MINERU_AGENT_BASE = "https://mineru.net/api/v1/agent"
MINERU_PRECISION_BASE = "https://mineru.net/api/v4"

# Filesystem-safe id for a source file  (replaces anything not alphanumeric/dash/dot)
def _source_id(filename: str) -> str:
    return re.sub(r'[^\w\-\.]', '_', filename)


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def process_and_ingest_pdf(
    pdf_filename: str,
    file_bytes: bytes,
    on_event: Optional[Callable] = None,
):
    """Full pipeline: MinerU parse → image persist → LLM split → embed."""

    def emit(event: dict):
        if on_event:
            on_event(event)

    try:
        file_size_mb = len(file_bytes) / (1024 * 1024)
        use_precision = bool(settings.MINERU_API_TOKEN)

        if not use_precision and file_size_mb > 10:
            raise Exception(
                f"文件大小 {file_size_mb:.1f} MB 超出 Agent API 限制（10 MB）。"
                "请在 .env 中配置 MINERU_API_TOKEN 以使用精准解析 API。"
            )

        # ── Step 1: MinerU parse ──────────────────────────────────────────────
        if use_precision:
            markdown, images_data = _parse_precision(pdf_filename, file_bytes, emit)
        else:
            markdown, images_data = _parse_agent(pdf_filename, file_bytes, emit)

        # ── Step 2: Save images, rewrite URLs ────────────────────────────────
        emit({"stage": "images", "msg": "处理图片资源...", "progress": 0.82})
        sid = _source_id(pdf_filename)
        markdown, saved_img_paths = _save_images_and_rewrite(markdown, images_data, sid)

        # ── Step 3: LLM-based question splitting ─────────────────────────────
        emit({"stage": "splitting", "msg": "调用 DeepSeek 识别题目边界...", "progress": 0.86})
        questions = _split_questions_with_llm(markdown)

        if not questions:
            # Fallback: store whole document
            print("[LLM切分] 回退：整个文档作为一条记录入库")
            questions = [{"title": "全文", "content": markdown.strip()}]

        # ── Step 3.5: 清理未被任何题目引用的废图 ─────────────────────────────
        all_referenced_urls = set()
        for q in questions:
            for url in _extract_image_urls(q.get("content", "")):
                all_referenced_urls.add(Path(url).name)
        orphaned = [p for p in saved_img_paths if p.name not in all_referenced_urls]
        for p in orphaned:
            try:
                p.unlink()
            except Exception:
                pass
        if orphaned:
            print(f"[图片清理] 删除 {len(orphaned)} 张废图（不属于任何题目）")

        # ── Step 4: Build Documents ───────────────────────────────────────────
        q_count = len(questions)
        emit({"stage": "embedding", "msg": f"向量化 {q_count} 道题目...", "progress": 0.93})

        ts = int(time.time())
        docs = []
        for i, q in enumerate(questions):
            content = q.get("content", "").strip()
            if not content:
                continue
            image_urls = _extract_image_urls(content)
            docs.append(Document(
                page_content=content,
                metadata={
                    "source_file": pdf_filename,
                    "question_title": q.get("title", f"题目{i+1}"),
                    "question_number": i + 1,
                    "image_urls": json.dumps(image_urls, ensure_ascii=False),
                    "has_images": len(image_urls) > 0,
                    "created_at": ts,
                },
            ))

        # ── Step 5: Deduplication ─────────────────────────────────────────────
        emit({"stage": "dedup", "msg": "去重检测，比对已有题库...", "progress": 0.96})
        clean_docs, skipped_count, dup_titles = _dedup_documents(docs)

        if clean_docs:
            vector_store.add_documents(documents=clean_docs)

            # ── 打印入库内容全文，便于核查图文对应关系 ──────────────────────────
            print("\n" + "=" * 70)
            print(f"[入库详情] 共写入 {len(clean_docs)} 道题目，以下为完整内容：")
            print("=" * 70)
            for i, doc in enumerate(clean_docs, 1):
                meta = doc.metadata
                content = doc.page_content
                img_urls_in_text = re.findall(r'!\[.*?\]\(([^)]+)\)', content)
                print(f"\n┌─ 【题目 {i}/{len(clean_docs)}】 {meta.get('question_title', '?')}")
                print(f"│  来源文件  : {meta.get('source_file', '?')}")
                print(f"│  内容长度  : {len(content)} 字符")
                print(f"│  元数据图片: {meta.get('image_urls', '[]')}")
                print(f"│  正文图片数: {len(img_urls_in_text)}")
                for j, url in enumerate(img_urls_in_text, 1):
                    img_path = Path(__file__).parent.parent.parent / "assets" / "images" / Path(url).name
                    exists = img_path.exists()
                    print(f"│     [{j}] {url}  →  文件存在: {exists}")
                print(f"│  ── 完整正文 ──")
                for line in content.splitlines():
                    print(f"│  {line}")
                print(f"└─ 结束")
            print("=" * 70 + "\n")

        emit({
            "stage": "done",
            "msg": "入库成功",
            "question_count": len(clean_docs),
            "skipped_count": skipped_count,
            "duplicate_titles": dup_titles[:10],
            "progress": 1.0,
        })

    except Exception as e:
        emit({"stage": "error", "msg": str(e)})
        raise


# ══════════════════════════════════════════════════════════════════════════════
# MinerU parsers
# ══════════════════════════════════════════════════════════════════════════════

def _parse_agent(filename: str, file_bytes: bytes, emit: Callable):
    """MinerU Agent API — no token, ≤10 MB.  Returns (markdown, {})."""

    emit({"stage": "submit", "msg": "提交至 MinerU 解析引擎...", "progress": 0.08})

    res = requests.post(
        f"{MINERU_AGENT_BASE}/parse/file",
        json={"file_name": filename, "language": "ch",
              "enable_table": True, "enable_formula": True, "is_ocr": False},
        timeout=30,
    )
    if res.status_code != 200 or res.json().get("code") != 0:
        raise Exception(f"提交解析任务失败: {res.text[:200]}")

    task_id = res.json()["data"]["task_id"]
    file_url = res.json()["data"]["file_url"]

    emit({"stage": "uploading", "msg": "上传文件至云端...", "progress": 0.18})
    put_res = requests.put(file_url, data=file_bytes, timeout=120)
    if put_res.status_code not in (200, 201):
        raise Exception(f"文件上传失败: HTTP {put_res.status_code}")

    start = time.time()
    last_state = None
    while time.time() - start < 300:
        poll = requests.get(f"{MINERU_AGENT_BASE}/parse/{task_id}", timeout=15)
        data = poll.json().get("data", {})
        state = data.get("state")

        if state == "done":
            emit({"stage": "downloading", "msg": "正在下载解析结果...", "progress": 0.78})
            md_res = requests.get(data["markdown_url"], timeout=30)
            return md_res.text, {}

        if state == "failed":
            raise Exception(f"MinerU 解析失败: {data.get('err_msg', '未知错误')}")

        if state != last_state:
            elapsed = int(time.time() - start)
            labels = {
                "waiting-file": "等待文件上传确认...",
                "pending": "排队中，等待解析资源...",
                "running": "MinerU 轻量解析中...",
                "uploading": "下载远程文件中...",
            }
            progress = min(0.22 + elapsed / 240, 0.76)
            emit({"stage": "parsing", "msg": labels.get(state, "处理中..."), "progress": progress})
            last_state = state

        time.sleep(3)

    raise Exception("解析超时（5 分钟），请检查 MinerU 服务状态")


def _parse_precision(filename: str, file_bytes: bytes, emit: Callable):
    """MinerU Precision API — requires token, supports large files.
    Returns (markdown, {image_name: bytes})."""

    headers_auth = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.MINERU_API_TOKEN}",
    }

    emit({"stage": "submit", "msg": "申请精准解析上传通道...", "progress": 0.08})
    res = requests.post(
        f"{MINERU_PRECISION_BASE}/file-urls/batch",
        headers=headers_auth,
        json={"files": [{"name": filename}], "model_version": "vlm",
              "enable_formula": True, "enable_table": True},
        timeout=30,
    )
    if res.status_code != 200 or res.json().get("code") != 0:
        raise Exception(f"申请上传链接失败: {res.text[:200]}")

    batch_id = res.json()["data"]["batch_id"]
    upload_url = res.json()["data"]["file_urls"][0]

    emit({"stage": "uploading", "msg": "上传文件至精准解析引擎...", "progress": 0.18})
    put_res = requests.put(upload_url, data=file_bytes, timeout=180)
    if put_res.status_code != 200:
        raise Exception(f"文件上传失败: HTTP {put_res.status_code}")

    poll_headers = {"Authorization": f"Bearer {settings.MINERU_API_TOKEN}"}
    start = time.time()
    while time.time() - start < 600:
        poll = requests.get(
            f"{MINERU_PRECISION_BASE}/extract-results/batch/{batch_id}",
            headers=poll_headers, timeout=15,
        )
        result = poll.json()
        if result.get("code") != 0:
            raise Exception(f"轮询失败: {result.get('msg')}")

        info = result["data"]["extract_result"][0]
        state = info["state"]

        if state == "done":
            emit({"stage": "downloading", "msg": "下载结构化数据包...", "progress": 0.78})
            zip_res = requests.get(info["full_zip_url"], timeout=60)

            markdown = ""
            images_data = {}

            with zipfile.ZipFile(io.BytesIO(zip_res.content)) as z:
                names = z.namelist()
                # Find full markdown
                md_name = next((n for n in names if n.endswith('.md') and 'full' in n), None)
                if not md_name:
                    md_name = next((n for n in names if n.endswith('.md')), None)
                if md_name:
                    markdown = z.read(md_name).decode('utf-8')

                # Extract all images
                for name in names:
                    if name.startswith('images/') or name.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        img_name = Path(name).name
                        if img_name:
                            images_data[img_name] = z.read(name)

            print(f"[Precision API] Markdown {len(markdown)} 字, 图片 {len(images_data)} 张")
            return markdown, images_data

        if state == "failed":
            raise Exception(f"精准解析失败: {info.get('err_msg')}")

        if state == "running":
            prog = info.get("extract_progress", {})
            extracted = prog.get("extracted_pages", 0)
            total = max(prog.get("total_pages", 1), 1)
            progress = 0.22 + (extracted / total) * 0.54
            emit({
                "stage": "parsing",
                "msg": f"VLM 精准解析中... {extracted}/{total} 页",
                "progress": progress,
                "pages": f"{extracted}/{total}",
            })
        else:
            elapsed = int(time.time() - start)
            emit({"stage": "parsing", "msg": f"排队中 ({elapsed}s)...", "progress": 0.22})

        time.sleep(5)

    raise Exception("精准解析超时（10 分钟）")


# ══════════════════════════════════════════════════════════════════════════════
# Image handling
# ══════════════════════════════════════════════════════════════════════════════

def _save_images_and_rewrite(markdown: str, images_data: dict, source_id: str) -> tuple:
    """Persist images to assets/images/ (flat) and rewrite markdown URLs.
    Returns (new_markdown, saved_paths) where saved_paths is the set of Path
    objects written in this call — used by the caller to clean up orphaned files.
    """
    images_dir = Path(__file__).parent.parent.parent / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: set = set()

    # Save images extracted from ZIP (Precision API)
    for img_name, img_bytes in images_data.items():
        safe_name = Path(img_name).name
        if safe_name:
            p = images_dir / safe_name
            p.write_bytes(img_bytes)
            saved_paths.add(p)

    saved = [0]
    failed = [0]

    def rewrite(m):
        alt, src = m.group(1), m.group(2)

        if src.startswith('http'):
            # CDN URL (Agent API or external) — download locally
            try:
                raw_name = src.split('/')[-1].split('?')[0]
                img_name = raw_name if ('.' in raw_name) else f"img_{saved[0]}.png"
                target = images_dir / img_name
                if not target.exists():
                    r = requests.get(src, timeout=30)
                    r.raise_for_status()
                    target.write_bytes(r.content)
                saved_paths.add(target)
                saved[0] += 1
                return f'![{alt}](/assets/images/{img_name})'
            except Exception as e:
                failed[0] += 1
                print(f"  ⚠️ 图片下载失败 {src}: {e}")
                return m.group(0)

        else:
            # Local relative path like images/xxx.png
            img_name = Path(src).name
            p = images_dir / img_name
            if p.exists():
                saved_paths.add(p)
                saved[0] += 1
                return f'![{alt}](/assets/images/{img_name})'
            else:
                failed[0] += 1
                print(f"  ⚠️ 图片文件不存在: {img_name}")
                return m.group(0)

    new_md = re.sub(r'!\[(.*?)\]\(([^)]+)\)', rewrite, markdown)
    print(f"[图片处理] 改写 {saved[0]} 张图片 URL，失败 {failed[0]} 张，共记录 {len(saved_paths)} 个文件路径")
    return new_md, saved_paths


def _extract_image_urls(content: str) -> list:
    """Return all /assets/images/... URLs found in a chunk."""
    return re.findall(r'!\[.*?\]\((/assets/images/[^)]+)\)', content)


# ══════════════════════════════════════════════════════════════════════════════
# Deduplication
# ══════════════════════════════════════════════════════════════════════════════

_DEDUP_HIGH = 0.95   # above → definitely duplicate, skip
_DEDUP_LOW  = 0.82   # between → ask LLM to confirm


def _dedup_documents(docs: list) -> tuple:
    """Compare each doc against existing vectors; return (clean, skipped_count, dup_titles)."""
    clean = []
    skipped = 0
    dup_titles = []

    for doc in docs:
        content = doc.page_content
        title = doc.metadata.get("question_title", "?")
        try:
            hits = vector_store.similarity_search_with_relevance_scores(content, k=1)
        except Exception as e:
            print(f"  [去重] 查询异常: {e}，保留该题")
            clean.append(doc)
            continue

        if not hits:
            clean.append(doc)
            continue

        best_doc, score = hits[0]

        if score >= _DEDUP_HIGH:
            print(f"  [去重] 跳过「{title}」(相似度 {score:.3f}，高度重复)")
            skipped += 1
            dup_titles.append(title)
        elif score >= _DEDUP_LOW:
            if _confirm_duplicate_with_llm(content, best_doc.page_content):
                print(f"  [去重] LLM 确认跳过「{title}」(相似度 {score:.3f})")
                skipped += 1
                dup_titles.append(title)
            else:
                print(f"  [去重] LLM 判断不同，保留「{title}」")
                clean.append(doc)
        else:
            clean.append(doc)

    print(f"[去重] 保留 {len(clean)} 道，跳过 {skipped} 道重复")
    return clean, skipped, dup_titles


def _confirm_duplicate_with_llm(content_a: str, content_b: str) -> bool:
    """Ask DeepSeek whether two question texts represent the same math problem."""
    prompt = (
        "请判断以下两段文字是否描述的是同一道数学题目（考查内容和知识点完全相同，"
        "仅存在微小的格式、题号或措辞差异均算相同）。\n\n"
        f"【文本 A】\n{content_a[:800]}\n\n"
        f"【文本 B】\n{content_b[:800]}\n\n"
        "只输出一个词：相同 或 不同"
    )
    try:
        raw = _call_deepseek(prompt)
        return "相同" in raw
    except Exception as e:
        print(f"  [去重 LLM] 判断失败: {e}，保守处理（视为不同）")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# LLM question splitting
# ══════════════════════════════════════════════════════════════════════════════

_LLM_SYSTEM = (
    "你是一名数学教材解析专家，擅长识别教辅材料中的各类题目。"
    "只输出合法的 JSON 数组，不包含任何其他文字。"
)

_LLM_PROMPT = """以下是从数学教辅 PDF 中提取的 Markdown 内容（含 LaTeX 公式，可能含图片链接）。
请识别其中所有独立的题目单元，输出 JSON 数组。

识别范围（包括但不限于）：
- 例题 1、例2、例题三…
- 变式训练、变式、变式题
- 随堂练习、课堂练习
- 基础训练、提高训练、综合练习、拓展练习
- 第 X 题、习题 X、练习 X
- 数字序号题（1. 2. 3.）

每个题目单元包含：题目本身 + 所有小问 (1)(2)(3) + 解析/答案/提示（如有）。
纯章节标题、知识点介绍、公式推导（无需作答的内容）不算题目，忽略。

【图片链接规则——严格执行】
- 原文中图片链接格式为：![说明文字](/assets/images/文件名.jpg)
- 图片属于哪道题，就必须出现在该题的 content 字段中，位置与原文一致
- 禁止删除、修改、合并或遗漏任何图片链接
- 若一道题有多张图片，全部保留

输出格式（严格 JSON 数组，key 固定为 title 和 content）：
[
  {"title": "例1", "content": "题干文字 ![说明](/assets/images/xxx.jpg) 解析文字"},
  {"title": "变式训练1", "content": "…"}
]

Markdown 内容：
"""


def _call_deepseek(prompt: str) -> str:
    """Call DeepSeek chat completion (OpenAI-compatible REST)."""
    resp = requests.post(
        f"{settings.DEEPSEEK_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.MODEL_FAST,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 8000,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _parse_llm_json(raw: str) -> list:
    """Extract and parse JSON array from LLM response, tolerating markdown fences."""
    # Strip ```json ... ``` fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        raise ValueError("LLM 响应中未找到 JSON 数组")
    return json.loads(match.group())


def _split_questions_with_llm(markdown: str) -> list:
    """Use DeepSeek to identify question boundaries in markdown.

    For long documents (>12 000 chars) the markdown is split on ## headers
    first, then each section is processed individually.
    Returns list of {title, content}.
    """
    MAX_CHARS = 12000

    if len(markdown) <= MAX_CHARS:
        segments = [markdown]
    else:
        # Split on ## / ### headers as natural section boundaries
        raw_segs = re.split(r'(?m)^(?=#{1,3}\s)', markdown)
        segments = []
        buf = ""
        for seg in raw_segs:
            if len(buf) + len(seg) <= MAX_CHARS:
                buf += seg
            else:
                if buf.strip():
                    segments.append(buf)
                buf = seg
        if buf.strip():
            segments.append(buf)
        print(f"[LLM切分] 长文档，拆成 {len(segments)} 段分别处理")

    all_questions = []
    for idx, seg in enumerate(segments):
        if not seg.strip():
            continue
        print(f"[LLM切分] 处理第 {idx+1}/{len(segments)} 段（{len(seg)} 字）...")
        try:
            raw = _call_deepseek(_LLM_PROMPT + seg)
            questions = _parse_llm_json(raw)

            print(f"  → 识别到 {len(questions)} 道题目：")
            for q in questions:
                img_count = len(_extract_image_urls(q.get("content", "")))
                img_tag = f" [🖼×{img_count}]" if img_count else ""
                print(f"     · {q.get('title', '?')}  ({len(q.get('content',''))} 字){img_tag}")

            all_questions.extend(questions)
        except Exception as e:
            print(f"  ⚠️ 第 {idx+1} 段 LLM 解析失败: {e}")

    print(f"[LLM切分] 全部段落合计识别题目: {len(all_questions)} 道")
    return all_questions

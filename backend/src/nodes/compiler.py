# src/nodes/compiler.py
"""
Python-based exam paper renderer + LaTeX compiler.
Deterministic layout: no LLM for formatting — only for keyword extraction.
"""
import re
import uuid
import asyncio
import subprocess
from pathlib import Path
from collections import defaultdict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import settings
from src.schemas.graph_state import SelectionState
from src.tools.latex_compiler import PREAMBLE_A4, PREAMBLE_EXAM

compiler_llm = ChatOpenAI(
    model=settings.MODEL_FAST,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_API_BASE,
    temperature=0.0,
)

BASE_DIR = Path(__file__).parent.parent.parent.resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Text pre-processing
# ══════════════════════════════════════════════════════════════════════════════

def _strip_label(text: str) -> str:
    """Remove original KB labels and leading question numbers from text."""
    # Strip 【...】 at the very start: 【例2】, 【变式训练1】, 【随堂练习1】 etc.
    text = re.sub(r'^\s*【[^】]{1,30}】\s*', '', text)
    # Strip leading number+delimiter like "6. " or "（3）" or "3、" or "5.（..."
    # \s* (not \s+) so the pattern matches even when no space follows the delimiter
    text = re.sub(r'^\s*[\(（]?\d{1,3}[\)）\.、]\s*', '', text)
    return text.strip()


_UNICODE_SUBS = [
    ('★', r'$\star$'),
    ('☆', r'$\star$'),
    ('●', r'$\bullet$'),
    ('○', r'（\hspace{0.5cm}）'),   # fill-in blank circle — \hspace works in text mode
    ('△', r'$\triangle$'),
    ('∘', r'$\circ$'),
    ('•', r'\textbullet{}'),
    ('…', r'\ldots{}'),
    ('·', r'\ensuremath{\cdot}'),  # \ensuremath works in both text and math mode
]

def _fix_unicode(text: str) -> str:
    """Replace unsupported Unicode characters with LaTeX equivalents."""
    for char, sub in _UNICODE_SUBS:
        text = text.replace(char, sub)
    return text


def _md_to_latex(text: str) -> str:
    """Convert minimal Markdown markup to LaTeX equivalents."""
    # Bold **text** → \textbf{text}
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    # Normalize fill-in blanks: 4+ underscores (raw or escaped) → \underline
    text = re.sub(r'(?:\\_){3,}', r'\\underline{\\hspace{3cm}}', text)
    text = re.sub(r'_{4,}', r'\\underline{\\hspace{3cm}}', text)
    # Widen answer slot: （）→ （\hspace{1.5em}） so students have room to write
    text = text.replace('（）', r'（\hspace{1.5em}）')
    return text


def _process_images(text: str) -> str:
    """Rewrite Markdown image links to \\includegraphics, right-aligned after all text.

    All image links are stripped from their inline positions and collected;
    they are then appended as a right-aligned block after the full text so the
    question stem always reads complete before any figure appears.
    """
    collected: list[str] = []

    def replace_img(m):
        alt = m.group(1)
        url = m.group(2)
        print(f'  [IMG] 发现图片 alt={repr(alt)}  url={repr(url)}')
        img_filename = Path(url).name
        abs_path = BASE_DIR / 'assets' / 'images' / img_filename
        exists = abs_path.exists()
        print(f'  [IMG] 映射到: {abs_path}  文件存在: {exists}')
        if exists:
            latex_path = str(abs_path).replace('\\', '/')
            collected.append(
                '\\begin{flushright}'
                f'\\includegraphics[width=0.30\\textwidth]{{{latex_path}}}'
                '\\end{flushright}'
            )
        else:
            print(f'  [IMG] ⚠️ 文件不存在，跳过')
        return ''  # 从行内位置移除，统一追加到末尾

    clean_text = re.sub(r'!\[(.*?)\]\(([^)]+)\)', replace_img, text).strip()

    if collected:
        img_block = '\n\n' + '\n'.join(collected)
        return clean_text + img_block
    return clean_text


def _clean(text: str) -> str:
    """Full cleaning pipeline: strip labels → unicode → markdown → images."""
    text = _strip_label(text)
    text = _fix_unicode(text)
    text = _md_to_latex(text)
    text = _process_images(text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
# Question type detection
# ══════════════════════════════════════════════════════════════════════════════

def _detect_type(question_text: str, options) -> str:
    if options:
        if '多选' in question_text or '多项' in question_text:
            return '多选'
        return '单选'
    if re.search(r'_{2,}|＿{2,}|____', question_text):
        return '填空'
    return '解答'


# ══════════════════════════════════════════════════════════════════════════════
# Option layout (adaptive: 4 / 2 / 1 per row)
# ══════════════════════════════════════════════════════════════════════════════

def _est_width(opt: str) -> int:
    """Estimate rendered character width for option layout decisions."""
    # Unwrap $math$ — keep the math content for length estimation
    s = re.sub(r'\$([^$]+)\$', r'\1', opt)
    # \frac{a}{b} → ab (fraction height ≠ width)
    s = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1\2', s)
    # Other \cmd{content} → content
    s = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', s)
    # Bare \cmd → nothing
    s = re.sub(r'\\[a-zA-Z]+', '', s)
    # Strip braces, superscripts, subscripts
    s = re.sub(r'[\{\}\^_]', '', s)
    return len(s)


def _option_lines(options: list) -> str:
    if not options:
        return ''
    labels = ['A', 'B', 'C', 'D', 'E']
    # Strip any existing A./B./C./D. label already present in the option text
    cleaned = [re.sub(r'^[A-Ea-e][.、]\s*', '', opt) for opt in options]
    max_w = max(_est_width(opt) for opt in cleaned)

    if max_w <= 10:
        cols, box = 4, '0.24'
    elif max_w <= 22:
        cols, box = 2, '0.48'
    else:
        cols, box = 1, '0.97'

    items = [f'{labels[i]}. {cleaned[i]}' for i in range(min(len(cleaned), 4))]
    rows = []
    for i in range(0, len(items), cols):
        chunk = items[i:i + cols]
        cells = ' '.join(f'\\makebox[{box}\\linewidth][l]{{{c}}}' for c in chunk)
        rows.append(f'\\noindent {cells}')
    return '\n'.join(rows)


# ══════════════════════════════════════════════════════════════════════════════
# LaTeX body renderer
# ══════════════════════════════════════════════════════════════════════════════

TYPE_ORDER = ['单选', '多选', '填空', '解答']
TYPE_HEADERS = {
    '单选': '一、单选题',
    '多选': '二、多选题',
    '填空': '三、填空题',
    '解答': '四、解答题',
}
STUDENT_SPACE = {'单选': '1.0cm', '多选': '1.0cm', '填空': '2.5cm', '解答': '8cm'}


def render_exam_body(questions, title: str, is_teacher: bool) -> str:
    """Render the full LaTeX body for student or teacher version."""
    groups = defaultdict(list)
    for q in questions:
        qt = _detect_type(
            getattr(q, 'question_text', ''),
            getattr(q, 'options', None) or [],
        )
        groups[qt].append(q)

    lines = [
        f'\\begin{{center}} \\Large \\textbf{{{title} --- 智能专项练习}} \\end{{center}}',
        '\\vspace{0.6cm}',
        '',
    ]

    global_num = 1
    for qt in TYPE_ORDER:
        if qt not in groups:
            continue

        header = TYPE_HEADERS[qt]
        lines += [
            '\\vspace{0.4cm}',
            f'\\noindent{{\\large\\textbf{{{header}}}}}',
            '\\vspace{0.25cm}',
            '',
        ]

        for q in groups[qt]:
            q_text = _clean(getattr(q, 'question_text', ''))
            opts = getattr(q, 'options', None) or []
            answer = getattr(q, 'answer', '')

            # Question stem
            lines.append(f'\\noindent \\textbf{{{global_num}.}} {q_text}')

            # Options (choice questions) — blank line ends the paragraph so
            # options always start on a new line rather than trailing the stem.
            if opts:
                lines.append('')   # \n\n = paragraph break in LaTeX
                lines.append(_option_lines(opts))

            # Student blank / teacher solution
            if is_teacher:
                answer_tex = _clean(answer)
                lines += [
                    '\\vspace{0.3cm}',
                    f'\\noindent\\textbf{{【解析】}} {answer_tex}',
                    '\\vspace{0.8cm}',
                    '',
                ]
            else:
                space = STUDENT_SPACE.get(qt, '3cm')
                if qt in ('单选', '多选'):
                    lines += ['\\vspace{0.4cm}', '']
                else:
                    lines += [f'\\vspace{{{space}}}', '']

            global_num += 1

    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# LLM polishing (validates & fixes LaTeX before compilation)
# ══════════════════════════════════════════════════════════════════════════════

_POLISH_PROMPT = """\
你是 LaTeX 数学排版修复专家。你将收到一段试卷的 LaTeX 正文代码，请检查并修复以下问题，使其能被 xelatex 正确编译：

【必须修复】
1. \\left / \\right 配对：确保每个 $...$ 块内 \\left 与 \\right 数量对应，修复孤立的 \\left 或 \\right
2. $ 配对：确保所有数学模式 $...$ 正确闭合
3. 填空横线：将 \\underline{\\hspace{3cm}} 正确保留；若发现裸露的 ____ 替换为 \\underline{\\hspace{3cm}}
4. 确认已无 ★ ☆ ● ○ 等 Unicode 字符

【严格禁止】
- 不得修改题目数学内容、公式含义、答案数值
- 不得修改 \\noindent、\\textbf、\\vspace、\\makebox 等结构命令
- 不得添加 \\documentclass、\\begin{document} 等导言区内容
- 不得重新排版或重写题目

直接输出修复后的 LaTeX 正文代码，不要有任何解释、注释或代码块标记（不要加 ```latex）。\
"""


def _polish_latex_sync(body: str) -> str:
    """Ask the LLM to validate and fix the LaTeX body (synchronous, runs in thread)."""
    try:
        resp = compiler_llm.invoke([
            SystemMessage(content=_POLISH_PROMPT),
            HumanMessage(content=body),
        ])
        result = resp.content.strip()
        # Strip markdown fences if the LLM adds them despite instructions
        result = re.sub(r'^```(?:latex|tex)?\s*', '', result, flags=re.MULTILINE)
        result = re.sub(r'\s*```\s*$', '', result, flags=re.MULTILINE)
        return result.strip() or body          # fall back to original if empty
    except Exception as e:
        print(f'  ⚠️ LLM 精修失败: {e}，使用 Python 渲染原稿')
        return body


# ══════════════════════════════════════════════════════════════════════════════
# LaTeX compilation
# ══════════════════════════════════════════════════════════════════════════════

def _compile_sync(body: str, pdf_name: str, preamble: str) -> bool:
    """Write and compile a .tex file to PDF (blocking, runs in thread)."""
    outputs_dir = BASE_DIR / 'outputs'
    outputs_dir.mkdir(parents=True, exist_ok=True)

    tex_name = pdf_name.replace('.pdf', '.tex')
    tex_path = outputs_dir / Path(tex_name).name
    pdf_path = outputs_dir / Path(pdf_name).name

    full_tex = preamble + '\n' + body + '\n\\end{document}\n'
    tex_path.write_text(full_tex, encoding='utf-8')

    try:
        subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-halt-on-error',
             f'-output-directory={outputs_dir}', str(tex_path)],
            check=True, capture_output=True, text=True, encoding='utf-8',
        )
        print(f'  ✅ PDF 生成: {pdf_path.name}')
        return True
    except subprocess.CalledProcessError as e:
        print(f'  ❌ LaTeX 编译失败:\n{e.stdout[-800:]}')
        return False


def _extract_keywords_sync(questions, topic: str) -> str:
    """Synchronous keyword extraction via LLM (runs in thread)."""
    try:
        sample = ' '.join(
            getattr(q, 'question_text', '')[:80] for q in questions[:3]
        )
        resp = compiler_llm.invoke([
            SystemMessage(content='你是关键词提取助手，直接输出2-3个关键词用下划线连接，无需其他文字。例如：三角函数_诱导公式'),
            HumanMessage(content=f'知识点：{topic}\n题目摘要：{sample}'),
        ])
        kw = resp.content.strip().replace(' ', '_')
        kw = re.sub(r'[关键词：:\s]+', '', kw)
        return kw if kw and len(kw) <= 20 else topic.replace(' ', '_')[:10]
    except Exception:
        return topic.replace(' ', '_')[:10]


# ══════════════════════════════════════════════════════════════════════════════
# Node entry point
# ══════════════════════════════════════════════════════════════════════════════

async def compile_pdf_node(state: SelectionState) -> dict:
    print('\n' + '=' * 50)
    print('⏳ [Node 4] Python 排版引擎启动...')

    questions = state.get('validated_questions', [])
    req = state.get('requirement', {})

    if not questions:
        print('⚠️ [Node 4] 没有合法题目可供编译。')
        return {}

    title = req.get('topic', '综合数学')
    task_id = uuid.uuid4().hex[:8]
    student_name = f'student_{task_id}.pdf'
    teacher_name = f'teacher_{task_id}.pdf'

    # Phase 1: Python renders structure (label stripping, grouping, option layout)
    student_body = render_exam_body(questions, title, is_teacher=False)
    teacher_body = render_exam_body(questions, title, is_teacher=True)
    print(f'  📝 Python 排版完成：学生卷 {len(student_body)} 字符，解析卷 {len(teacher_body)} 字符')

    # Phase 2: LLM polishing — fix \left/\right, $ balance, Unicode (concurrent)
    print('  🔧 LLM 精修中...')
    student_polished, teacher_polished = await asyncio.gather(
        asyncio.to_thread(_polish_latex_sync, student_body),
        asyncio.to_thread(_polish_latex_sync, teacher_body),
    )
    print(f'  ✅ 精修完成：学生卷 {len(student_polished)} 字符，解析卷 {len(teacher_polished)} 字符')

    # Phase 3: Compile both PDFs + extract keywords concurrently
    ok_s, ok_t, keywords = await asyncio.gather(
        asyncio.to_thread(_compile_sync, student_polished, student_name, PREAMBLE_A4),
        asyncio.to_thread(_compile_sync, teacher_polished, teacher_name, PREAMBLE_A4),
        asyncio.to_thread(_extract_keywords_sync, questions, title),
    )

    print(f'✅ [Node 4] 编译完成！学生卷: {"✓" if ok_s else "✗"}  解析卷: {"✓" if ok_t else "✗"}  关键词: {keywords}')

    return {
        'review_feedback': '试卷编译并保存成功',
        'final_student_pdf_url': f'/outputs/{student_name}',
        'final_teacher_pdf_url': f'/outputs/{teacher_name}',
        'display_title': title,
        'download_name_student': f'{keywords}_智能专项练习_学生卷.pdf',
        'download_name_teacher': f'{keywords}_智能专项练习_解析卷.pdf',
    }

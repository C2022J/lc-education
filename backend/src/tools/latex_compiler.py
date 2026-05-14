import subprocess
import os
from pathlib import Path
from langchain_core.tools import tool

# ── A4 paper (standard) ──────────────────────────────────────────────────────
PREAMBLE_A4 = r"""\documentclass[12pt,a4paper]{ctexart}
\usepackage{geometry}
\geometry{top=2.5cm,bottom=2.5cm,left=3cm,right=3cm}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{enumitem}
\everymath{\displaystyle}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.2em}
\begin{document}
"""

# ── 试卷纸 (8K exam paper, 26×36.85 cm) ─────────────────────────────────────
PREAMBLE_EXAM = r"""\documentclass[11pt]{ctexart}
\usepackage{geometry}
\geometry{paperwidth=26cm,paperheight=36.85cm,top=2cm,bottom=2cm,left=2.5cm,right=2.5cm}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{enumitem}
\everymath{\displaystyle}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.15em}
\begin{document}
"""

# Legacy alias kept for the tool below
LATEX_PREAMBLE = PREAMBLE_A4

LATEX_POSTAMBLE = r"""
\end{document}
"""

@tool
def compile_latex_to_pdf(body_content: str, output_pdf_name: str) -> str:
    r"""
    使用此工具将 LaTeX 正文内容编译为 PDF。
    参数 body_content: 纯 LaTeX 正文内容（绝对不要包含 \documentclass, \usepackage, \begin{document} 等导言区代码！系统会自动包裹模板）。
    参数 output_pdf_name: 输出的 PDF 文件名。
    """
    base_dir = Path(__file__).parent.parent.parent.resolve()
    safe_filename = Path(output_pdf_name).name
    temp_tex_name = safe_filename.replace(".pdf", ".tex")
    
    outputs_dir = base_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True) 
    
    final_pdf_path = outputs_dir / safe_filename
    final_tex_path = outputs_dir / temp_tex_name

    # 【核心防御机制】：将大模型生成的正文，嵌入到绝对安全的预设模板中
    full_latex = LATEX_PREAMBLE + body_content + LATEX_POSTAMBLE

    with open(final_tex_path, "w", encoding="utf-8") as f:
        f.write(full_latex)

    # 放弃 Pandoc，直接使用原生 xelatex 编译，杜绝转义 Bug
    # -interaction=nonstopmode 确保遇到错误时不会卡死等待输入
    xelatex_cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={outputs_dir}",
        str(final_tex_path)
    ]

    try:
        subprocess.run(xelatex_cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        return f"SUCCESS: 编译成功！PDF 已生成至 {final_pdf_path}"
    except subprocess.CalledProcessError as e:
        # 将标准输出中的报错片段返回给大模型
        return f"ERROR: 编译失败。错误日志:\n{e.stdout}\n请仔细检查公式是否闭合，修复 body_content 后再次调用本工具。"
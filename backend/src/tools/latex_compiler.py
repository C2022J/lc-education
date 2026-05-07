import subprocess
import os
from pathlib import Path
from langchain_core.tools import tool

# 预设的 LaTeX 导言区（包含了所有必须的数学、排版宏包，大模型不需要管这些）
LATEX_PREAMBLE = r"""\documentclass[12pt,a4paper]{ctexart}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{enumitem}
\everymath{\displaystyle}
\setlength{\parindent}{0pt}

\begin{document}
"""

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
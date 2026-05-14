# LC Education 项目说明

## 项目结构

```
lc-education/
  backend/    FastAPI + LangGraph 后端（Python）
  frontend/   Vue 3 + Vite + Tailwind CSS 前端
```

## 技术栈

- **后端**：FastAPI、LangGraph、ChromaDB、DeepSeek API、xelatex
- **前端**：Vue 3（Composition API）、Vite、Tailwind CSS v4、vue-router、lucide-vue-next

---

## LaTeX 排版规范（compiler.py）

### Unicode 替换规则

| 字符 | 正确替换 | 错误写法（禁止） |
|------|---------|----------------|
| `·`（中间点，出处引用） | `\ensuremath{\cdot}` | `\cdot{}`（文本模式下报 Missing $） |
| `○`（填空圆圈） | `\hspace{0.5cm}` 包裹 | `\;`（数学模式专用） |
| `★ ☆` | `$\star$` | 直接输出 Unicode |

`\ensuremath{...}` 在文本模式和数学模式下均有效，凡需要在任意上下文中使用数学符号必须用它，而非裸露的 `\cmd{}`。

### 选择题选项排版

选项必须**另起一行**，不能紧跟在题干末尾。实现方式：在题干行后追加空字符串 `''`，与下一行 join 后产生 `\n\n`（LaTeX 段落分隔符）。

```python
# 正确
lines.append(f'\\noindent \\textbf{{{n}.}} {q_text}')
if opts:
    lines.append('')          # 空行 → LaTeX 段落断开 → 选项另起一行
    lines.append(_option_lines(opts))

# 错误
if opts:
    lines.append('\\vspace{0.25cm}')   # vspace 不结束段落，选项仍在同行
    lines.append(_option_lines(opts))
```

### 答题括号间距

选择题答题括号 `（）` 需要有填写空间，替换为 `（\hspace{1.5em}）`。在 `_md_to_latex()` 中处理：

```python
text = text.replace('（）', r'（\hspace{1.5em}）')
```

---

## reviewer.py JSON 解析正则规范

```python
# 只将 \r 开头的 LaTeX 命令（\right 等）补全为双反斜杠
# 保留 JSON 合法转义符：\n \t \f \b \u
raw_text = re.sub(r'(?<!\\)\\(?!["\\/bfntu])', r'\\\\', raw_text)
```

**不要**把 `r`（即 `\right`）加入排除列表；**不要**把 `n`、`f`、`b`、`t` 从排除列表移除（会导致 JSON 换行符被双重转义，写入 `.tex` 文件后变成 `\n` 未定义命令）。

---

## 去重检测阈值

- `_DEDUP_HIGH = 0.95`：直接跳过
- `_DEDUP_LOW = 0.82`：调用 LLM 二次确认

---

## 图片路径规范

知识库图片统一存放于 `backend/static/kb_images/<filename>`，URL 格式为 `/kb_images/<filename>`，**不使用**含源文件名的子目录（避免中文路径问题）。

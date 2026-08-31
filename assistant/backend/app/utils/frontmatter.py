"""共享 YAML frontmatter 解析逻辑，供 orchestrator、skills API 和 update_soul 工具使用。"""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 ``---`` 标记之间的类 YAML frontmatter。

    返回 ``(fields_dict, body_text)``。如果没有 frontmatter 块，
    返回的 dict 为空，*body_text* 为原始字符串。
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[3:end].strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    body = text[end + 3:].strip()
    return fields, body


def build_frontmatter_block(fields: dict[str, str]) -> str:
    """根据解析出的字段重建 YAML frontmatter 块。

    返回适合写回文件的 ``"---\\n<key: val>\\n---\\n"`` 字符串。
    """
    if not fields:
        return "---\n---\n"
    lines = ["---"]
    for key, val in fields.items():
        lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n"

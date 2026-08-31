"""更新 AI 助手的人格设定文件（SOUL.md）。

当用户请求个性化更改时触发，例如名称、语气、风格、身份、工作方式、行为规则或约束。
"""

import logging
import os
import time
from pathlib import Path

from app.schemas.message import ToolResult
from app.utils.frontmatter import build_frontmatter_block, parse_frontmatter

logger = logging.getLogger(__name__)

# SOUL.md 路径（与 orchestrator 相同：从 app/ 向上 4 级）
_SOUL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "SOUL.md"

# 章节标题映射（英文键 -> 中文二级标题）
_SECTION_HEADER: dict[str, str] = {
    "identity": "## 身份",
    "behavior": "## 行为准则",
    "style": "## 交互风格",
    "constraints": "## 约束",
}

TOOL_DEFINITION = {
    "name": "update_soul",
    "description": (
        "更新 AI 助手的个性设定文件 (SOUL.md)。"
        "当用户提出个性化需求时使用此工具，例如：更改称呼、调整语气风格、"
        "修改行为准则、更新身份设定、改变工作方式等。"
        "可以更新特定章节（身份、行为准则、交互风格、约束）或替换完整正文。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "enum": ["identity", "behavior", "style", "constraints"],
                "description": (
                    "要更新的章节。identity=身份, behavior=行为准则, "
                    "style=交互风格, constraints=约束。"
                    "不指定此参数则替换整个正文内容（保留 YAML frontmatter）。"
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "更新后的内容。如果指定了 section，仅替换该章节的内容"
                    "（不含章节标题本身）；如果不指定 section，则替换整个正文。"
                ),
            },
        },
        "required": ["content"],
    },
}


def _update_section(body: str, header: str, new_content: str) -> str:
    target = header + "\n"
    idx = body.find(target)
    if idx == -1:
        appendix = f"\n\n{header}\n{new_content.strip()}"
        return body.rstrip() + appendix

    content_start = idx + len(target)
    rest = body[content_start:]
    next_h2 = rest.find("\n## ")
    if next_h2 == -1:
        before = body[:content_start]
        return before + new_content.strip()
    else:
        before = body[:content_start]
        after = rest[next_h2:]
        return before + new_content.strip() + after


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


async def execute(content: str, section: str | None = None, **kwargs) -> ToolResult:
    t0 = time.monotonic()

    if section is not None and section not in _SECTION_HEADER:
        valid = ", ".join(_SECTION_HEADER.keys())
        msg = f"[错误] 无效的章节名称 '{section}'。可选值: {valid}"
        return ToolResult(
            state={"status": "invalid_section", "input": {"section": section},
                   "output": None, "error": f"无效的章节名称 '{section}'",
                   "summary": f"无效的章节名称: {section}"},
            metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                      "truncated": False, "approval_required": False,
                      "approval_granted": None, "provider": "builtin",
                      "extra": {"frontmatter_preserved": False}},
            content=msg,
        )

    # 读取当前文件
    try:
        if _SOUL_PATH.exists():
            current_text = _SOUL_PATH.read_text(encoding="utf-8")
            file_size_before = _SOUL_PATH.stat().st_size
            created_new = False
        else:
            logger.warning("SOUL.md not found at %s, creating new file", _SOUL_PATH)
            current_text = ""
            file_size_before = 0
            created_new = True
    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Failed to read SOUL.md")
        msg = f"[错误] 无法读取 SOUL.md: {e}"
        return ToolResult(
            state={"status": "read_error", "input": {"section": section},
                   "output": None, "error": str(e), "summary": "无法读取 SOUL.md"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"frontmatter_preserved": False,
                                "file_size_before": file_size_before,
                                "file_size_after": 0}},
            content=msg,
        )

    # 解析 frontmatter 和正文
    frontmatter, body = parse_frontmatter(current_text)
    previous_content_length = len(body)

    # 应用修改
    if section is not None:
        header = _SECTION_HEADER[section]
        new_body = _update_section(body, header, content)
        desc = f"已更新「{header[3:]}」章节 ({len(content)} 字符)"
    else:
        new_body = content.strip()
        desc = f"已替换完整正文 ({len(content)} 字符)"

    # 重新组装并写入
    fm_block = build_frontmatter_block(frontmatter)
    full_text = fm_block + "\n" + new_body + "\n"

    try:
        _SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(_SOUL_PATH, full_text)
        file_size_after = len(full_text.encode("utf-8"))
        dur_ms = (time.monotonic() - t0) * 1000
        logger.info("SOUL.md updated: section=%s, chars=%d", section, len(content))
        msg = f"[成功] {desc}。更改将在下一次对话中生效。"
        return ToolResult(
            state={
                "status": "success",
                "input": {"section": section},
                "output": {
                    "content_length": len(content),
                    "previous_content_length": previous_content_length,
                    "created_new_file": created_new,
                    "soul_path": str(_SOUL_PATH),
                },
                "summary": desc,
            },
            metadata={
                "duration_ms": round(dur_ms, 1),
                "truncated": False,
                "approval_required": False,
                "approval_granted": None,
                "provider": "builtin",
                "extra": {
                    "frontmatter_preserved": bool(frontmatter),
                    "file_size_before": file_size_before,
                    "file_size_after": file_size_after,
                },
            },
            content=msg,
        )
    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Failed to write SOUL.md")
        msg = f"[错误] 无法写入 SOUL.md: {e}"
        return ToolResult(
            state={"status": "write_error", "input": {"section": section},
                   "output": None, "error": str(e),
                   "summary": "无法写入 SOUL.md"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"frontmatter_preserved": bool(frontmatter),
                                "file_size_before": file_size_before,
                                "file_size_after": 0}},
            content=msg,
        )

"""压缩会话上下文：摘要旧消息，保留最近消息。

由用户或 LLM 触发。摘要前会先把完整转录写入磁盘。
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import settings
from app.providers.llm.base import LLMMessage
from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "transcripts"

TOOL_DEFINITION = {
    "name": "compact",
    "description": (
        "压缩对话上下文以节省 token。将较早的对话做摘要，保留最近几轮完整内容。"
        "当你觉得上下文过长或信息密度下降时可以调用此工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keep_recent": {
                "type": "integer",
                "description": "保留最近 N 轮对话完整内容，默认为 3",
                "default": 3,
            },
        },
    },
}


async def execute(keep_recent: int = 3, **kwargs) -> ToolResult:
    """压缩会话上下文。

    这个工具比较特殊：它需要访问 Worker 内部的 messages 列表。
    通过普通工具管线调用时，会尽力调用 LLM 进行摘要压缩。

    如果 WorkerRuntime 注入了 ``worker_context``，它会直接修改内存中的消息列表。
    """
    t0 = time.monotonic()
    worker_ctx = kwargs.get("worker_context")
    conversation_id = kwargs.get("_conversation_id")

    try:
        if worker_ctx is None:
            return ToolResult(
                state={"status": "error", "input": {"keep_recent": keep_recent},
                       "output": None, "error": "compact 工具只能在 Worker 上下文中使用",
                       "summary": "compact 需要 Worker 上下文"},
                metadata={"duration_ms": 0, "truncated": False,
                          "approval_required": False, "approval_granted": None,
                          "provider": "builtin", "extra": {}},
                content="[compact 只能在对话上下文中使用]",
            )

        messages = worker_ctx.get("messages", [])
        llm = worker_ctx.get("llm")
        if not messages or not llm:
            return ToolResult(
                state={"status": "error", "input": {"keep_recent": keep_recent},
                       "output": None, "error": "缺少 messages 或 llm 上下文",
                       "summary": "compact 上下文不完整"},
                metadata={"duration_ms": 0, "truncated": False,
                          "approval_required": False, "approval_granted": None,
                          "provider": "builtin", "extra": {}},
                content="[compact 上下文不完整]",
            )

        # 1. 将完整转录保存到磁盘
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = str(conversation_id or "unknown")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        transcript_path = TRANSCRIPTS_DIR / f"{safe_id}_{ts}.json"
        transcript_data = [
            {"role": _role(m), "content": _content(m)}
            for m in messages
        ]
        transcript_path.write_text(
            json.dumps(transcript_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Saved transcript to %s", transcript_path)

        # 应用保留策略：只保留最近 N 个转录文件
        _apply_transcript_retention()

        # 2. 分离系统提示词、旧消息和最近消息
        # 这里把“轮次”定义为 user-assistant 交换
        system_msg = messages[0] if messages and _role(messages[0]) == "system" else None
        rest = messages[1:] if system_msg else messages

        # 找到最后 N 条用户消息，用于确定切分点
        user_indices = [i for i, m in enumerate(rest) if _role(m) == "user"]
        if len(user_indices) <= keep_recent:
            return ToolResult(
                state={"status": "success", "input": {"keep_recent": keep_recent},
                       "output": {"compacted_before": 0, "transcript_path": str(transcript_path)},
                       "summary": f"对话轮次不足 {keep_recent} 轮，无需压缩"},
                metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                          "truncated": False, "approval_required": False,
                          "approval_granted": None, "provider": "builtin",
                          "extra": {"transcript_path": str(transcript_path)}},
                content="对话轮次不足，无需压缩。",
            )

        cutoff_idx = user_indices[-keep_recent]
        old_msgs = rest[:cutoff_idx]
        recent_msgs = rest[cutoff_idx:]

        if not old_msgs:
            return ToolResult(
                state={"status": "success", "input": {"keep_recent": keep_recent},
                       "output": {"compacted_before": 0},
                       "summary": "没有需要压缩的旧消息"},
                metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                          "truncated": False, "approval_required": False,
                          "approval_granted": None, "provider": "builtin",
                          "extra": {}},
                content="没有需要压缩的旧消息。",
            )

        # 3. 让 LLM 摘要旧消息
        old_text = "\n".join(
            f"[{_role(m)}]: {_content(m)[:500]}"
            for m in old_msgs
        )
        summary_messages = [
            LLMMessage(
                role="system",
                content="你是一个精准的对话摘要器。请用 200-300 字概括以下对话的关键内容、用户意图和重要结论。",
            ),
            LLMMessage(role="user", content=f"请摘要以下对话：\n\n{old_text}"),
        ]
        summary, _ = await llm.chat(
            messages=summary_messages, temperature=0.3, max_tokens=500,
        )
        summary = summary.strip()[:1000]

        # 4. 持久化压缩日志
        if conversation_id:
            try:
                from app.database import session_scope as _session_scope
                from app.models.compression_log import CompressionLog
                with _session_scope() as db:
                    db.add(CompressionLog(
                        conversation_id=int(conversation_id),
                        summary_text=summary,
                        transcript_path=str(transcript_path),
                    ))
            except Exception:
                logger.exception("Failed to write compression_log")

        # 5. 重建消息列表
        new_messages = []
        if system_msg:
            new_messages.append(system_msg)
        new_messages.append(
            _make_msg("user", f"[对话摘要 — 之前的内容已被压缩]\n{summary}")
        )
        new_messages.append(
            _make_msg("assistant", "好的，我已了解之前的对话内容。请继续。")
        )
        new_messages.extend(recent_msgs)
        worker_ctx["messages"] = new_messages

        dur_ms = (time.monotonic() - t0) * 1000
        logger.info("Compacted %d messages → %d messages (summary: %d chars)",
                    len(messages), len(new_messages), len(summary))

        return ToolResult(
            state={
                "status": "success",
                "input": {"keep_recent": keep_recent},
                "output": {
                    "compacted_before": len(old_msgs),
                    "remaining": len(new_messages),
                    "summary": summary[:300],
                    "transcript_path": str(transcript_path),
                },
                "summary": f"已压缩 {len(old_msgs)} 条消息为摘要，保留最近 {keep_recent} 轮",
            },
            metadata={
                "duration_ms": round(dur_ms, 1),
                "truncated": False,
                "approval_required": False,
                "approval_granted": None,
                "provider": "builtin",
                "extra": {"transcript_path": str(transcript_path)},
            },
            content=f"[成功] 对话已压缩。保存完整记录到 {transcript_path.name}。\n\n摘要:\n{summary}",
        )

    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("compact failed")
        return ToolResult(
            state={"status": "error", "input": {"keep_recent": keep_recent},
                   "output": None, "error": str(e),
                   "summary": f"压缩失败: {e}"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin", "extra": {}},
            content=f"[错误] 对话压缩失败: {e}",
        )


def _role(m: LLMMessage) -> str:
    return getattr(m, "role", "?")


def _content(m: LLMMessage) -> str:
    return getattr(m, "content", "")


def _make_msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)


def _apply_transcript_retention() -> None:
    """删除超过保留上限的旧转录文件。

    只保留最近的 ``COMPACT_TRANSCRIPT_RETENTION`` 个文件（在 settings 中配置），
    更旧的文件会被删除。
    """
    max_keep = settings.compact_transcript_retention
    try:
        transcripts = sorted(
            TRANSCRIPTS_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in transcripts[max_keep:]:
            old_file.unlink(missing_ok=True)
            logger.info("Retention: deleted old transcript %s", old_file.name)
    except Exception:
        logger.exception("Failed to apply transcript retention policy")

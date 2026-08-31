"""记忆提取器：从会话历史中推断用户偏好。

本模块提供：
- ``extract_preferences``：用于格式化偏好提取 LLM prompt 的**纯函数**
  （无副作用，便于 mock）。
- ``run``：**异步入口点**，负责编排数据库访问、LLM 调用和推断候选项持久化。

设计说明：
- LLM 调用可通过 ``llm_provider`` 参数注入，便于在单元测试中使用 mock。
- ``run()`` 会打开自己的数据库会话（独立于调用方），因此可以安全地作为
  fire-and-forget 的 ``asyncio.create_task`` 启动。
- 失败只记录日志，不会传播回调用方。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.providers.llm.base import BaseLLMProvider, LLMMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 传入提取器 prompt 的最近消息数量。
_RECENT_MESSAGES_WINDOW = 20

_SYSTEM_PROMPT = """\
You are a preference extraction assistant. Given a conversation between a user \
and an AI assistant, identify any user preferences, habits, or personal facts \
that were explicitly stated or strongly implied.

Output a JSON array of objects. Each object must have exactly these keys:
- "title": a short label for the preference (e.g. "Preferred language")
- "content": a concise description of the preference value
- "confidence": a float between 0.0 and 1.0 indicating how confident you are

Rules:
- Only include preferences that are clearly supported by the conversation.
- Do NOT include trivial or one-off requests (e.g. "translate this sentence").
- If no meaningful preferences can be extracted, return an empty array: []
- Output ONLY the JSON array, no markdown fences, no explanation.
"""


# ---------------------------------------------------------------------------
# 纯函数：格式化 LLM prompt（无副作用）
# ---------------------------------------------------------------------------


def extract_preferences(
    messages: list[dict],
    existing_profile: list[dict],
) -> list[LLMMessage]:
    """构建用于偏好提取的 LLM 消息列表。

    这是一个**纯函数**，没有副作用；它只把输入数据转换成适合 LLM 调用的
    prompt 结构。

    参数
    ----------
    messages : list[dict]
        最近会话消息。每个 dict 至少应包含 ``msg_type``（``"user"`` 或
        ``"assistant"``）和 ``msg_json``（其中包含 ``parts`` 或 ``content`` 字段）。
    existing_profile : list[dict]
        已知 profile 记忆（用于避免重复）。每个 dict 应包含 ``title`` 和
        ``content``。

    返回
    -------
    list[LLMMessage]
        可直接发送给 LLM provider 的 LLMMessage 对象列表。
    """
    # 构建人类可读的会话转录
    transcript_lines: list[str] = []
    for msg in messages:
        msg_type = msg.get("msg_type", "unknown")
        msg_json = msg.get("msg_json", {})

        # 从 parts 提取文本内容；没有时回退到 content 字段
        parts = msg_json.get("parts", [])
        text_parts = [
            p.get("text", "") for p in parts
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        content = " ".join(text_parts).strip()
        if not content:
            content = msg_json.get("content", "")

        if content:
            role_label = "User" if msg_type == "user" else "Assistant"
            transcript_lines.append(f"{role_label}: {content}")

    transcript = "\n".join(transcript_lines)

    # 构建已有 profile 摘要，帮助 LLM 避免重复
    profile_summary = ""
    if existing_profile:
        profile_lines = [
            f"- {p.get('title', '?')}: {p.get('content', '?')}"
            for p in existing_profile
        ]
        profile_summary = (
            "\n\nAlready known preferences (do NOT repeat these):\n"
            + "\n".join(profile_lines)
        )

    user_content = (
        f"Conversation transcript:\n{transcript}"
        f"{profile_summary}"
        f"\n\nExtract new user preferences from the conversation above."
    )

    return [
        LLMMessage(role="system", content=_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# 异步入口点：编排数据库、LLM 和持久化
# ---------------------------------------------------------------------------


async def run(
    conversation_id: int,
    llm_provider: BaseLLMProvider | None = None,
) -> list[dict[str, Any]]:
    """从会话中提取用户偏好，并持久化候选项。

    此函数会打开自己的数据库会话（独立于调用方），设计上用于通过
    ``asyncio.create_task`` 以 fire-and-forget 方式调用。

    参数
    ----------
    conversation_id : int
        要分析的会话。
    llm_provider : BaseLLMProvider | None
        可选的 LLM provider 实例。如果为 ``None``，会通过默认工厂创建。
        测试时可传入 mock/stub。

    返回
    -------
    list[dict[str, Any]]
        已写入数据库的候选偏好 dict 列表。每个 dict 包含
        ``title``、``content``、``confidence``。
    """
    from app.database import session_scope
    from app.memory.manager import MemoryManager
    from app.providers.factory import create_llm_provider
    from app.repositories.conversation_repo import ConversationRepository

    provider = llm_provider or create_llm_provider()

    with session_scope() as db:
        conv_repo = ConversationRepository(db)
        memory_mgr = MemoryManager(db)

        # 加载会话中的最近消息
        recent_messages = conv_repo.find_messages(
            conversation_id,
            limit=_RECENT_MESSAGES_WINDOW,
            order="desc",
        )
        # 反转为时间正序
        recent_messages = list(reversed(recent_messages))

        if not recent_messages:
            logger.debug(
                "extractor.run: no messages in conversation %d, skipping",
                conversation_id,
            )
            return []

        # 将 ORM Message 对象转换为纯函数使用的 dict
        messages_data = [
            {"msg_type": m.msg_type, "msg_json": m.msg_json or {}}
            for m in recent_messages
        ]

        # 加载已有 profile 记忆以避免重复
        existing_profile_records = memory_mgr.list_profiles(limit=50)
        existing_profile = [
            {"title": r.title, "content": r.content}
            for r in existing_profile_records
        ]

        # 构建 LLM prompt（纯函数）
        llm_messages = extract_preferences(messages_data, existing_profile)

        # 调用 LLM
        response_text, _usage = await provider.chat(llm_messages)

        # 解析响应：期望得到 JSON 数组
        candidates = _parse_candidates(response_text)

        if not candidates:
            logger.debug(
                "extractor.run: no candidates extracted for conversation %d",
                conversation_id,
            )
            return []

        # 以 inferred=True 写入候选项
        written: list[dict[str, Any]] = []
        for candidate in candidates:
            title = candidate.get("title", "").strip()
            content = candidate.get("content", "").strip()
            confidence = candidate.get("confidence", 0.5)

            if not title or not content:
                continue

            # 将 confidence 限制在 [0.0, 1.0]
            confidence = max(0.0, min(1.0, float(confidence)))

            memory_mgr.add_profile(
                scope="global",
                title=title,
                content=content,
                source_type="conversation",
                source_ref=str(conversation_id),
                inferred=True,
                confidence=confidence,
            )

            # 直接在记录上设置 source_conversation_id。
            # add_profile() 方法尚未暴露这个字段，因此更新最后插入的记录。
            from app.models.memory_record import MemoryRecord
            last_record = (
                db.query(MemoryRecord)
                .order_by(MemoryRecord.id.desc())
                .first()
            )
            if last_record:
                last_record.source_conversation_id = conversation_id
                db.flush()

            written.append({
                "title": title,
                "content": content,
                "confidence": confidence,
            })

        logger.info(
            "extractor.run: wrote %d inferred candidates for conversation %d",
            len(written),
            conversation_id,
        )
        return written


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _parse_candidates(response_text: str) -> list[dict[str, Any]]:
    """将 LLM 响应解析为候选 dict 列表。

    处理常见的 LLM 小毛病，例如 JSON 外包裹 markdown 代码块。
    """
    text = response_text.strip()

    # 如果存在 markdown 代码围栏则剥离
    if text.startswith("```"):
        lines = text.split("\n")
        # 移除第一行（```json 或 ```）和最后一行（```）
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("extractor: failed to parse LLM response as JSON: %s", text[:200])
        return []

    if not isinstance(parsed, list):
        logger.warning("extractor: LLM response is not a JSON array")
        return []

    # 校验每个候选项是否包含必需字段
    valid: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if "title" in item and "content" in item:
            valid.append(item)

    return valid

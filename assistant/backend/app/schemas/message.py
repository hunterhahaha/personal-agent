"""UI/SSE 传输层的新消息数据结构。

它们与内部 LLMMessage dataclass（用于 LLM API 通信）以及数据库 Message ORM
模型（用于持久化）共存。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── 共享基础结构 ──────────────────────────────────────────────


class TimeRecord(BaseModel):
    start: int  # Unix 毫秒时间戳
    end: int  # Unix 毫秒时间戳


class TokenUsage(BaseModel):
    total: int
    input: int
    output: int
    reasoning: int
    cache: dict[str, int] = Field(default_factory=dict)


# ── assistant 消息片段 ────────────────────────────────────────


class TextPart(BaseModel):
    type: Literal["text", "reasoning"]
    text: str
    time: TimeRecord | None = None
    id: str
    sessionID: str
    messageID: str


class ToolPart(BaseModel):
    type: Literal["toolcall"] = "toolcall"
    tool: str
    callID: str
    state: dict[str, Any]  # 状态结构：{status, input, output, title?, time?}
    metadata: dict[str, Any]  # 工具专属诊断信息
    id: str
    sessionID: str
    messageID: str


# ── assistant 消息信封 ─────────────────────────────────────


class AssistantBaseMsg(BaseModel):
    parentID: str
    role: str
    mode: str
    agent: str
    variant: str
    path: dict[str, str] = Field(default_factory=dict)
    cost: float = 0.0
    token: TokenUsage = Field(default_factory=lambda: TokenUsage(total=0, input=0, output=0, reasoning=0))
    modelID: str
    providerID: str
    time: TimeRecord
    finish: str
    id: str
    sessionID: str


class AssistantMsg(BaseModel):
    message: AssistantBaseMsg
    parts: list[TextPart | ToolPart]


# ── user 消息信封 ──────────────────────────────────────────


class UserBaseMsg(BaseModel):
    role: str
    time: TimeRecord
    agent: str
    modelID: str
    providerID: str
    variant: str
    id: str
    sessionID: str


class UserMsg(BaseModel):
    message: UserBaseMsg
    part: list[TextPart]  # FilePart 是占位设计，尚未实现


# ── ToolResult：工具 execute() 的内部返回值 ─────────


from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """每个工具的 execute() 都返回这个对象。Worker 会拆解它：
    - content → 作为工具结果消息发给 LLM（文本表示）
    - state + metadata → 通过 event_callback 发给 SSE / 前端
    """

    state: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    content: str = ""  # 提供给 LLM 上下文的文本摘要

    def __str__(self) -> str:
        return self.content

    @property
    def status(self) -> str:
        return self.state.get("status", "unknown")


# ── 便捷重导出 ──────────────────────────────────────

__all__ = [
    "TimeRecord",
    "TokenUsage",
    "TextPart",
    "ToolPart",
    "AssistantBaseMsg",
    "AssistantMsg",
    "UserBaseMsg",
    "UserMsg",
    "ToolResult",
]

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New Chat"
    source: str = "chat"
    workspace_root: str | None = None


class ConversationUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    id: int
    title: str
    source: str = "chat"
    session_id: str | None = None
    workspace_root: str | None = None
    turn_count: int = 0
    successful_turn_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """数据库中的消息行：在 ``msg_json`` 中携带完整的 UserMsg 或 AssistantMsg，
    并包含数据库层面的元数据（id、时间戳）。"""

    id: int
    conversation_id: int
    msg_type: str  # 角色取值："user" | "assistant"
    turn_index: int | None = None
    msg_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    message: str
    model_id: Optional[str] = None
    workspace_root: Optional[str] = None

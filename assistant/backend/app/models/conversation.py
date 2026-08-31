"""Conversation 模型：用户聊天会话。"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conversation(Base):
    """顶层聊天会话。

    将一系列消息（见 ``Message``）组织在同一个标题下。
    从 ``Base`` 继承标准的 ``id``、``created_at`` 和 ``updated_at`` 列。
    """

    __tablename__ = "conversations"

    title: Mapped[str] = mapped_column(String, default="New Chat", nullable=False)
    source: Mapped[str] = mapped_column(String, default="chat", nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)
    workspace_root: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

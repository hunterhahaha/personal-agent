"""Message 模型：以 JSON 保存完整的 ``UserMsg`` 或 ``AssistantMsg``。"""

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )
    msg_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # 角色取值："user" | "assistant"
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    msg_json: Mapped[dict] = mapped_column(JSON, nullable=False)

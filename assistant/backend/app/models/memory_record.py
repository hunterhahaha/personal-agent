"""MemoryRecord 模型：从历史交互中持久化下来的知识。"""

from sqlalchemy import Boolean, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 记忆类（需要重写）

class MemoryRecord(Base):
    """从交互中提取或推断出的长期记忆单元。

    记录可以表示事实、偏好、会话摘要或学到的模式。每条记录都有类型
    （``memory_type``）和作用域（``scope``），也可以通过 ``source_type`` /
    ``source_ref`` 可选地关联回来源。
    """

    __tablename__ = "memory_records"

    memory_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    inferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

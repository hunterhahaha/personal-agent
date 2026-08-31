"""PromptTemplate 模型：带版本的 system/user/task 提示词。"""

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 提示词模板类（草稿部分需要重写）
class PromptTemplate(Base):
    """带版本的可复用提示词模板。

    模板可以有不同类型（``system``、``user``、``task``），并会被 skills 和 agent 模板引用，
    用于组合最终发送给 LLM 的系统提示词。
    """

    __tablename__ = "prompt_templates"

    prompt_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="system", nullable=False)
    version: Mapped[str] = mapped_column(String, default="1.0", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    draft_content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    version_history: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

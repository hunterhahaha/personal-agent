"""Task 模型：定时或按需 LLM 执行定义。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Task(Base):
    """可调度的任务，用于向 LLM 发送提示词。

    任务可以是重复任务（cron_expr），也可以是一次性任务（run_at）。
    """

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cron_expr: Mapped[str | None] = mapped_column(String, nullable=True)
    run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

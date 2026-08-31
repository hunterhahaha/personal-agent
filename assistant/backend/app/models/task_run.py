"""TaskRun 模型：单次任务执行尝试的记录。"""

from datetime import datetime

from sqlalchemy import Integer, JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 任务结果类（需要重写）
class TaskRun(Base):
    """单次任务调用的执行记录。

    捕获完整生命周期：执行何时开始和结束、是否成功，以及过程中产生的日志或错误。
    """

    __tablename__ = "task_runs"

    task_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

"""待审批工具调用请求的持久化存储。

将内存中的 ``_pending_approvals`` 字典迁移到数据库表，使审批状态能够跨进程重启保留，
并能在多个 worker 之间工作。

该表使用字符串 UUID ``request_id`` 作为唯一主键，不使用自增 ``id``；
这一模式与 ``ToolResultRecord`` 相同。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _PendingApprovalBase(DeclarativeBase):
    pass


class PendingApproval(_PendingApprovalBase):
    """一条等待用户决策的工具调用审批请求。

    生命周期：pending → approved | denied | expired
    """

    __tablename__ = "pending_approvals"

    request_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    tool_name: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    args_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expire_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_pending_approvals_conv_status", "conversation_id", "status"),
    )

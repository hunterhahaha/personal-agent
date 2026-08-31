"""被 micro-compacted 的工具调用结果的持久化存储。

该表通过 database.py 中的原始 SQL（迁移）创建。这个模型只用于 ORM 查询访问，
并使用专用 base，避免 ``Base`` 的自增 ``id`` 列与作为唯一主键的 ``callID`` 冲突。
"""

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _ToolResultBase(DeclarativeBase):
    pass


class ToolResultRecord(_ToolResultBase):
    __tablename__ = "tool_results"

    callID: Mapped[str] = mapped_column(
        String(128), primary_key=True, nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    full_output: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

"""上下文压缩事件的审计日志。

该表通过 database.py 中的原始 SQL（迁移）创建。这个模型只用于 ORM 查询访问，
并使用专用 base，避免自增 ``id`` 列与 ``Base`` 冲突。
"""

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _CompressionBase(DeclarativeBase):
    pass

# 上下文压日志缩类

class CompressionLog(_CompressionBase):
    __tablename__ = "compression_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_path: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

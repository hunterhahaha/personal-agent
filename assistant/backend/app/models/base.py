"""SQLAlchemy 基础配置和共享模型字段。"""

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config.settings import settings

# ---------------------------------------------------------------------------
# 引擎和会话工厂
# ---------------------------------------------------------------------------

# 设置允许跨线程访问数据库
_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# 声明式基类
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """所有 ORM 模型的抽象基类。

    每个子类都会获得一个代理整数主键（``id``）和两个必填时间戳
    （``created_at``、``updated_at``）。
    """

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# 依赖辅助函数（兼容 FastAPI）
# ---------------------------------------------------------------------------

def get_db() -> Generator:
    """产出一个 SQLAlchemy 会话，并确保使用后关闭。

    用作 FastAPI 依赖::

        from fastapi import Depends
        from sqlalchemy.orm import Session

        @app.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

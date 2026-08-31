"""数据库引擎、会话和结构初始化辅助函数。"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.base import engine, Base
from app.models import base as _base_module
from app.models.compression_log import _CompressionBase
from app.models.pending_approval import _PendingApprovalBase
from app.models.tool_result import _ToolResultBase


# ---------------------------------------------------------------------------
# session_scope — 可复用的数据库会话上下文管理器
# ---------------------------------------------------------------------------

@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """为一组数据库操作提供事务作用域。

    用法::

        from app.database import session_scope

        with session_scope() as db:
            repo = SomeRepository(db)
            repo.do_something()

    正常退出时会自动提交会话；发生异常时会回滚。
    无论如何，退出代码块时都会关闭会话。

    这个辅助函数替代代码库中分散的
    ``SessionLocal() + try/finally close`` 模式。

    注意：SessionLocal 会在调用时解析，而不是导入时解析。
    这样测试 fixture 可以 patch ``app.models.base.SessionLocal``，
    并让这里自动使用被替换后的工厂。
    """
    db = _base_module.SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """按当前 ORM 模型创建运行时需要的表。"""
    Base.metadata.create_all(bind=engine)
    _ToolResultBase.metadata.create_all(bind=engine)
    _CompressionBase.metadata.create_all(bind=engine)
    _PendingApprovalBase.metadata.create_all(bind=engine)
    _ensure_workspace_root_column()
    _ensure_turn_count_column()
    _ensure_successful_turn_count_column()
    _ensure_message_turn_index_column()


def _ensure_workspace_root_column() -> None:
    """为已有 SQLite 数据库补齐 conversations.workspace_root。"""
    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("conversations")}
    if "workspace_root" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN workspace_root VARCHAR(1024)"))


def _ensure_successful_turn_count_column() -> None:
    """为已有 SQLite 数据库补齐 conversations.successful_turn_count。"""
    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("conversations")}
    if "successful_turn_count" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE conversations ADD COLUMN successful_turn_count INTEGER NOT NULL DEFAULT 0")
        )


def _ensure_turn_count_column() -> None:
    """为已有 SQLite 数据库补齐 conversations.turn_count。"""
    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("conversations")}
    if "turn_count" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 0"))


def _ensure_message_turn_index_column() -> None:
    """为已有 SQLite 数据库补齐 messages.turn_index。"""
    inspector = inspect(engine)
    if "messages" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("messages")}
    if "turn_index" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE messages ADD COLUMN turn_index INTEGER"))

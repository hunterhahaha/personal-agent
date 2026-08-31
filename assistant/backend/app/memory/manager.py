"""Profile-only memory management.

The database keeps a ``memory_type`` column as a future extension point, but the
current application layer only accepts and returns ``profile`` records.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.memory_record import MemoryRecord
from app.repositories import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PROFILE_MEMORY_TYPE = "profile"
VALID_MEMORY_TYPES = frozenset({PROFILE_MEMORY_TYPE})


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------

class MemoryManager:
    """管理 AI 助手的 profile 记忆。

    参数
    ----------
    db : Session
        绑定到数据库的 SQLAlchemy ORM 会话。
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = MemoryRepository(db)

    # ------------------------------------------------------------------
    # 持久化记忆记录的核心 CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        memory_type: str,
        scope: str,
        title: str,
        content: str,
        source_type: str | None = None,
        source_ref: str | None = None,
        inferred: bool = False,
        confidence: float | None = None,
        tags: list[str] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> MemoryResponse:
        """创建一条新的持久化记忆记录。

        参数
        ----------
        memory_type : str
            当前只允许 ``"profile"``。数据库字段保留为未来扩展点。
        scope : str
            记忆的命名空间或归属者，例如用户 id、会话 id 或 agent 名称。
        title : str
            记录的人类可读短标题。
        content : str
            记忆正文，例如事实、日志、偏好等。
        source_type : str | None
            产生该记忆的来源类别，例如 ``"conversation"``、``"web_search"``、``"file"``。
        source_ref : str | None
            来源类别内部的标识符，例如会话 UUID、URL 或文件路径。
        inferred : bool
            为 ``True`` 时表示该记录由系统推断得出，而不是用户明确陈述。
        confidence : float | None
            推断记录的置信度分数（0.0 -- 1.0）。
        tags : list[str] | None
            用于过滤的可选标签列表。
        metadata_json : dict[str, Any] | None
            任意键值元数据。

        返回
        -------
        MemoryResponse
            新创建记录对应的 Pydantic 模型。

        抛出
        ------
        ValueError
            当 *memory_type* 不是 ``"profile"`` 时抛出。
        """
        if memory_type not in VALID_MEMORY_TYPES:
            msg = (
                f"Invalid memory type: {memory_type!r}. "
                f"Must be one of {sorted(VALID_MEMORY_TYPES)}"
            )
            logger.warning(msg)
            raise ValueError(msg)

        if not scope or not scope.strip():
            logger.warning("add() called with empty or whitespace-only scope")
            raise ValueError("scope must be a non-empty string")

        if not title or not title.strip():
            logger.warning("add() called with empty or whitespace-only title")
            raise ValueError("title must be a non-empty string")

        schema = MemoryCreate(
            memory_id=str(uuid_mod.uuid4()),
            memory_type=memory_type,
            scope=scope.strip(),
            title=title.strip(),
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            inferred=inferred,
            confidence=confidence,
            tags=tags or [],
            metadata_json=metadata_json or {},
        )

        try:
            record = self.repo.create(schema)
            logger.info(
                "Created %s memory [%s] in scope %r",
                memory_type,
                record.memory_id,
                scope,
            )
            return MemoryResponse.model_validate(record)
        except Exception:
            logger.exception("Failed to create %s memory record", memory_type)
            raise

    def get_by_id(self, record_id: int) -> MemoryResponse | None:
        """按自增主键获取单条记录。

        参数
        ----------
        record_id : int
            整数 ``id`` 列的值。

        返回
        -------
        MemoryResponse | None
        """
        record = self.repo.find_by_id(record_id)
        if record is None:
            return None
        if record.memory_type != PROFILE_MEMORY_TYPE:
            return None
        return MemoryResponse.model_validate(record)

    def get_by_memory_id(self, memory_id: str) -> MemoryResponse | None:
        """按 UUID ``memory_id`` 获取单条记录。

        参数
        ----------
        memory_id : str
            创建时分配的唯一字符串标识符。

        返回
        -------
        MemoryResponse | None
        """
        record = self.repo.find_by_memory_id(memory_id)
        if record is None:
            return None
        if record.memory_type != PROFILE_MEMORY_TYPE:
            return None
        return MemoryResponse.model_validate(record)

    def get_by_type(
        self,
        memory_type: str,
        scope: str | None = None,
        limit: int = 20,
        inferred: bool | None = None,
    ) -> list[MemoryResponse]:
        """返回指定记忆类型的记录，最新记录在前。

        参数
        ----------
        memory_type : str
            当前只允许 ``"profile"``。
        scope : str | None
            如果提供，则只返回该作用域内的结果。
        limit : int
            最多返回的记录数（默认 20）。
        inferred : bool | None
            如果提供，则只返回对应推断状态的记录。

        返回
        -------
        list[MemoryResponse]
        """
        if memory_type not in VALID_MEMORY_TYPES:
            msg = (
                f"Invalid memory type: {memory_type!r}. "
                f"Must be one of {sorted(VALID_MEMORY_TYPES)}"
            )
            logger.warning(msg)
            raise ValueError(msg)

        records = self.repo.find_by_type(
            memory_type,
            scope or "",
            limit,
            inferred=inferred,
        )
        return [MemoryResponse.model_validate(r) for r in records]

    def list_profiles(
        self,
        scope: str | None = None,
        limit: int = 20,
        inferred: bool | None = None,
    ) -> list[MemoryResponse]:
        """返回 profile 记忆，最新记录在前。"""
        return self.get_by_type(
            PROFILE_MEMORY_TYPE,
            scope=scope,
            limit=limit,
            inferred=inferred,
        )

    def get_by_scope(
        self,
        scope: str,
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """返回属于某个作用域的记录，最新记录在前。

        参数
        ----------
        scope : str
            用于过滤的命名空间。
        limit : int
            最多返回的记录数（默认 50）。

        返回
        -------
        list[MemoryResponse]
        """
        records = (
            self.db.query(MemoryRecord)
            .filter(
                MemoryRecord.memory_type == PROFILE_MEMORY_TYPE,
                MemoryRecord.scope == scope,
            )
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [MemoryResponse.model_validate(r) for r in records]

    def search_by_tags(
        self,
        tags: list[str],
        memory_type: str | None = None,
        scope: str | None = None,
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """返回包含给定所有标签的记录。

        这里执行客户端侧过滤。对于大型数据集，应考虑增加专用数据库查询。

        参数
        ----------
        tags : list[str]
            必须全部存在的标签。
        memory_type : str | None
            可选的类型过滤条件。
        scope : str | None
            可选的作用域过滤条件。
        limit : int
            最多返回的记录数（默认 50）。

        返回
        -------
        list[MemoryResponse]
        """
        query = self.db.query(MemoryRecord)

        filters: list[Any] = []
        if memory_type is not None and memory_type not in VALID_MEMORY_TYPES:
            msg = (
                f"Invalid memory type: {memory_type!r}. "
                f"Must be one of {sorted(VALID_MEMORY_TYPES)}"
            )
            logger.warning(msg)
            raise ValueError(msg)
        filters.append(MemoryRecord.memory_type == PROFILE_MEMORY_TYPE)
        if memory_type is not None:
            filters.append(MemoryRecord.memory_type == memory_type)
        if scope is not None:
            filters.append(MemoryRecord.scope == scope)

        if filters:
            query = query.filter(and_(*filters))

        records = (
            query.order_by(MemoryRecord.created_at.desc()).limit(limit).all()
        )

        tag_set = set(tags)
        matched = [
            r for r in records if tag_set.issubset(set(r.tags or []))
        ]
        return [MemoryResponse.model_validate(r) for r in matched]

    def search(
        self,
        query_str: str,
        memory_type: str | None = None,
        scope: str | None = None,
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """在 ``title`` 和 ``content`` 字段上执行简单文本搜索。

        使用大小写不敏感的 ``LIKE`` 模式匹配。生产环境面对更大数据集时，
        可考虑全文搜索或外部搜索索引。

        参数
        ----------
        query_str : str
            要搜索的子字符串。
        memory_type : str | None
            可选的类型过滤条件。
        scope : str | None
            可选的作用域过滤条件。
        limit : int
            最多返回的记录数（默认 50）。

        返回
        -------
        list[MemoryResponse]
        """
        pattern = f"%{query_str}%"
        filters: list[Any] = [
            MemoryRecord.title.ilike(pattern)
            | MemoryRecord.content.ilike(pattern),
        ]
        if memory_type is not None and memory_type not in VALID_MEMORY_TYPES:
            msg = (
                f"Invalid memory type: {memory_type!r}. "
                f"Must be one of {sorted(VALID_MEMORY_TYPES)}"
            )
            logger.warning(msg)
            raise ValueError(msg)
        filters.append(MemoryRecord.memory_type == PROFILE_MEMORY_TYPE)
        if memory_type is not None:
            filters.append(MemoryRecord.memory_type == memory_type)
        if scope is not None:
            filters.append(MemoryRecord.scope == scope)

        records = (
            self.db.query(MemoryRecord)
            .filter(and_(*filters))
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [MemoryResponse.model_validate(r) for r in records]

    def update(
        self,
        record_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        source_type: str | None = None,
        source_ref: str | None = None,
        inferred: bool | None = None,
        confidence: float | None = None,
        tags: list[str] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> MemoryResponse | None:
        """更新已有记忆记录的字段。

        只会应用值不是 ``None`` 的关键字参数。若要显式将字段设为 ``None``，
        应使用哨兵值 :py:obj:`_UNSET`（目前尚未暴露；当前 ``None`` 表示“不修改”）。

        参数
        ----------
        record_id : int
            要更新记录的自增主键。
        title : str | None
        content : str | None
        source_type : str | None
        source_ref : str | None
        inferred : bool | None
        confidence : float | None
        tags : list[str] | None
        metadata_json : dict[str, Any] | None

        返回
        -------
        MemoryResponse | None
            更新后的记录；未找到时返回 ``None``。
        """
        record = self.repo.find_by_id(record_id)
        if record is None:
            logger.warning("update() -- record id=%d not found", record_id)
            return None
        if record.memory_type != PROFILE_MEMORY_TYPE:
            logger.warning("update() -- record id=%d is not a profile memory", record_id)
            return None

        changed = False
        if title is not None:
            record.title = title
            changed = True
        if content is not None:
            record.content = content
            changed = True
        if source_type is not None:
            record.source_type = source_type
            changed = True
        if source_ref is not None:
            record.source_ref = source_ref
            changed = True
        if inferred is not None:
            record.inferred = inferred
            changed = True
        if confidence is not None:
            record.confidence = confidence
            changed = True
        if tags is not None:
            record.tags = tags
            changed = True
        if metadata_json is not None:
            record.metadata_json = metadata_json
            changed = True

        if not changed:
            logger.debug("update() -- no fields to update for id=%d", record_id)
            return MemoryResponse.model_validate(record)

        try:
            self.db.commit()
            self.db.refresh(record)
            logger.info("Updated memory record id=%d", record_id)
            return MemoryResponse.model_validate(record)
        except Exception:
            logger.exception("Failed to update memory record id=%d", record_id)
            self.db.rollback()
            raise

    def delete(self, record_id: int) -> bool:
        """按自增主键删除一条记忆记录。

        参数
        ----------
        record_id : int
            要删除记录的主键。

        返回
        -------
        bool
            记录被删除时返回 ``True``；记录不存在时返回 ``False``。
        """
        record = self.repo.find_by_id(record_id)
        if record is None:
            logger.warning("delete() -- record id=%d not found", record_id)
            return False
        if record.memory_type != PROFILE_MEMORY_TYPE:
            logger.warning("delete() -- record id=%d is not a profile memory", record_id)
            return False

        deleted = self.repo.delete(record_id)
        if deleted:
            logger.info("Deleted memory record id=%d", record_id)
        return deleted

    # ------------------------------------------------------------------
    # profile 记忆入口
    # ------------------------------------------------------------------

    def add_profile(
        self,
        scope: str,
        title: str,
        content: str,
        **kwargs: Any,
    ) -> MemoryResponse:
        """添加 profile 记忆（用户偏好、特征等）。"""
        return self.add(PROFILE_MEMORY_TYPE, scope, title, content, **kwargs)

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def add_many(
        self,
        records: list[dict[str, Any]],
    ) -> list[MemoryResponse]:
        """在单个事务中创建多条记忆记录。

        参数
        ----------
        records : list[dict[str, Any]]
            每个 dict 至少必须包含 ``scope``、``title`` 和 ``content``。
            ``memory_type`` 可省略；提供时必须是 ``"profile"``。
            :meth:`add` 接受的其他键都是可选项。

        返回
        -------
        list[MemoryResponse]

        抛出
        ------
        ValueError
            当任意记录缺少必需字段或记忆类型无效时抛出。
        """
        schemas: list[MemoryCreate] = []
        for i, rec in enumerate(records):
            mtype = rec.get("memory_type", PROFILE_MEMORY_TYPE)
            if mtype not in VALID_MEMORY_TYPES:
                msg = (
                    f"Record index {i} has invalid memory_type: {mtype!r}. "
                    f"Must be one of {sorted(VALID_MEMORY_TYPES)}"
                )
                raise ValueError(msg)
            if not rec.get("scope", "").strip():
                raise ValueError(f"Record index {i} has empty scope")
            if not rec.get("title", "").strip():
                raise ValueError(f"Record index {i} has empty title")

            schemas.append(
                MemoryCreate(
                    memory_id=str(uuid_mod.uuid4()),
                    memory_type=mtype,
                    scope=rec["scope"].strip(),
                    title=rec["title"].strip(),
                    content=rec.get("content", ""),
                    source_type=rec.get("source_type"),
                    source_ref=rec.get("source_ref"),
                    inferred=rec.get("inferred", False),
                    confidence=rec.get("confidence"),
                    tags=rec.get("tags", []),
                    metadata_json=rec.get("metadata_json", {}),
                )
            )

        results: list[MemoryResponse] = []
        try:
            for schema in schemas:
                record = self.repo.create(schema)
                results.append(MemoryResponse.model_validate(record))
            logger.info("Bulk-created %d memory records", len(results))
        except Exception:
            logger.exception("Bulk memory creation failed, rolling back")
            self.db.rollback()
            raise

        return results

    # ------------------------------------------------------------------
    # 推断记忆管理
    # ------------------------------------------------------------------

    def get_inferred(
        self,
        scope: str | None = None,
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """返回推断（未确认）记忆记录，最新记录在前。

        参数
        ----------
        scope : str | None
            如果提供，则只返回该作用域内的结果。
        limit : int
            最多返回的记录数（默认 50）。

        返回
        -------
        list[MemoryResponse]
        """
        query = self.db.query(MemoryRecord).filter(
            MemoryRecord.memory_type == PROFILE_MEMORY_TYPE,
            MemoryRecord.inferred == True,  # noqa: E712
        )
        if scope is not None:
            query = query.filter(MemoryRecord.scope == scope)

        records = (
            query.order_by(MemoryRecord.created_at.desc()).limit(limit).all()
        )
        return [MemoryResponse.model_validate(r) for r in records]

    def get_confirmed(
        self,
        scope: str | None = None,
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """返回已确认（非推断）记忆记录，最新记录在前。

        参数
        ----------
        scope : str | None
            如果提供，则只返回该作用域内的结果。
        limit : int
            最多返回的记录数（默认 50）。

        返回
        -------
        list[MemoryResponse]
        """
        query = self.db.query(MemoryRecord).filter(
            MemoryRecord.memory_type == PROFILE_MEMORY_TYPE,
            MemoryRecord.inferred == False,  # noqa: E712
        )
        if scope is not None:
            query = query.filter(MemoryRecord.scope == scope)

        records = (
            query.order_by(MemoryRecord.created_at.desc()).limit(limit).all()
        )
        return [MemoryResponse.model_validate(r) for r in records]

    def confirm(self, record_id: int) -> MemoryResponse | None:
        """确认一条推断记忆记录（设置 inferred=False）。

        参数
        ----------
        record_id : int
            要确认记录的自增主键。

        返回
        -------
        MemoryResponse | None
            更新后的记录；未找到时返回 ``None``。
        """
        record = self.repo.find_by_id(record_id)
        if record is None:
            logger.warning("confirm() -- record id=%d not found", record_id)
            return None
        if record.memory_type != PROFILE_MEMORY_TYPE:
            logger.warning("confirm() -- record id=%d is not a profile memory", record_id)
            return None

        record.inferred = False
        try:
            self.db.commit()
            self.db.refresh(record)
            logger.info("Confirmed inferred memory record id=%d", record_id)
            return MemoryResponse.model_validate(record)
        except Exception:
            logger.exception("Failed to confirm memory record id=%d", record_id)
            self.db.rollback()
            raise

    def reject(self, record_id: int) -> bool:
        """拒绝并删除一条推断记忆记录。

        参数
        ----------
        record_id : int
            要拒绝记录的自增主键。

        返回
        -------
        bool
            记录被删除时返回 ``True``；未找到时返回 ``False``。
        """
        record = self.repo.find_by_id(record_id)
        if record is None:
            logger.warning("reject() -- record id=%d not found", record_id)
            return False
        if record.memory_type != PROFILE_MEMORY_TYPE:
            logger.warning("reject() -- record id=%d is not a profile memory", record_id)
            return False

        if not record.inferred:
            logger.warning(
                "reject() -- record id=%d is not inferred, skipping", record_id
            )
            return False

        try:
            self.db.delete(record)
            self.db.commit()
            logger.info("Rejected (deleted) inferred memory record id=%d", record_id)
            return True
        except Exception:
            logger.exception("Failed to reject memory record id=%d", record_id)
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def get_stats(
        self,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """返回已存储记忆的聚合统计信息。

        参数
        ----------
        scope : str | None
            如果提供，则统计信息限定在该命名空间内。

        返回
        -------
        dict[str, Any]
            包含 ``total``、``by_type`` 和 ``latest_record`` 的字典。
        """
        query = self.db.query(MemoryRecord).filter(
            MemoryRecord.memory_type == PROFILE_MEMORY_TYPE
        )
        if scope is not None:
            query = query.filter(MemoryRecord.scope == scope)

        total = query.count()

        latest = (
            query.order_by(MemoryRecord.created_at.desc()).first()
        )

        return {
            "total": total,
            "by_type": {PROFILE_MEMORY_TYPE: total},
            "latest_record": (
                MemoryResponse.model_validate(latest) if latest else None
            ),
        }

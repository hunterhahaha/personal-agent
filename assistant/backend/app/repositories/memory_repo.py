from typing import Any

from sqlalchemy.orm import Session

from app.models.memory_record import MemoryRecord
from app.repositories.base import BaseRepository


class MemoryRepository(BaseRepository):
    model = MemoryRecord

    def __init__(self, db: Session):
        super().__init__(db)

    def find_by_type(
        self,
        memory_type: str,
        scope: str = "",
        limit: int = 50,
        inferred: bool | None = None,
    ) -> list:
        q = self.db.query(MemoryRecord).filter(
            MemoryRecord.memory_type == memory_type,
        )
        if scope:
            q = q.filter(MemoryRecord.scope == scope)
        if inferred is not None:
            q = q.filter(MemoryRecord.inferred == inferred)
        return (
            q.order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def find_by_scope(self, scope: str, limit: int = 50) -> list:
        return (
            self.db.query(MemoryRecord)
            .filter(MemoryRecord.scope == scope)
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def find_by_memory_id(self, memory_id: str) -> Any | None:
        return (
            self.db.query(MemoryRecord)
            .filter(MemoryRecord.memory_id == memory_id)
            .first()
        )

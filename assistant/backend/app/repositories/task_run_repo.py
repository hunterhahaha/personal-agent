"""TaskRun 记录的 repository。"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.task_run import TaskRun
from app.repositories.base import BaseRepository


class TaskRunRepository(BaseRepository):
    model = TaskRun

    def __init__(self, db: Session):
        super().__init__(db)

    def find_latest_by_task_id(self, task_id: str) -> Optional[Any]:
        return (
            self.db.query(TaskRun)
            .filter(TaskRun.task_id == task_id)
            .order_by(TaskRun.created_at.desc())
            .first()
        )

    def create_from_task(self, task_id: str) -> TaskRun:
        run = TaskRun(
            task_id=task_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            logs=[],
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

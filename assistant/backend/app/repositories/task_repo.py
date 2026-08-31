from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository):
    model = Task

    def __init__(self, db: Session):
        super().__init__(db)

    def find_by_task_id(self, task_id: str) -> Optional[Any]:
        return self.db.query(Task).filter(Task.task_id == task_id).first()

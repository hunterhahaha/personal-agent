from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.tool import Tool
from app.repositories.base import BaseRepository


class ToolRepository(BaseRepository):
    model = Tool

    def __init__(self, db: Session):
        super().__init__(db)

    def find_by_tool_id(self, tool_id: str) -> Optional[Any]:
        return self.db.query(Tool).filter(Tool.tool_id == tool_id).first()

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.sub_agent_blueprint import SubAgentBlueprint
from app.repositories.base import BaseRepository


class SubAgentBlueprintRepository(BaseRepository):
    model = SubAgentBlueprint

    def __init__(self, db: Session):
        super().__init__(db)

    def find_by_blueprint_id(self, blueprint_id: str) -> Optional[Any]:
        return (
            self.db.query(SubAgentBlueprint)
            .filter(SubAgentBlueprint.blueprint_id == blueprint_id)
            .first()
        )

"""用于加载和查找 SubAgentBlueprint 实体的 registry。"""

from sqlalchemy.orm import Session

from app.registries.base import BaseRegistry
from app.repositories.sub_agent_blueprint_repo import SubAgentBlueprintRepository


class SubAgentBlueprintRegistry(BaseRegistry["SubAgentBlueprint"]):
    """以 blueprint_id 为键的 SubAgentBlueprint 实体内存缓存。"""

    _id_attr = "blueprint_id"

    def _get_repo(self, db: Session) -> SubAgentBlueprintRepository:
        return SubAgentBlueprintRepository(db)

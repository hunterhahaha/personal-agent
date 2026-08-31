"""用于加载和查找 PromptTemplate 实体的 registry。"""

from sqlalchemy.orm import Session

from app.registries.base import BaseRegistry
from app.repositories import PromptTemplateRepository


class PromptRegistry(BaseRegistry["PromptTemplate"]):
    """以 prompt_id 为键的 PromptTemplate 实体内存缓存。"""

    _id_attr = "prompt_id"

    def _get_repo(self, db: Session) -> PromptTemplateRepository:
        return PromptTemplateRepository(db)

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.prompt_template import PromptTemplate
from app.repositories.base import BaseRepository


class PromptTemplateRepository(BaseRepository):
    model = PromptTemplate

    def __init__(self, db: Session):
        super().__init__(db)

    def find_by_prompt_id(self, prompt_id: str) -> Optional[Any]:
        return (
            self.db.query(PromptTemplate)
            .filter(PromptTemplate.prompt_id == prompt_id)
            .first()
        )

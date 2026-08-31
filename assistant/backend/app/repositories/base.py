from typing import Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session


class BaseRepository:
    model: type = None  # 必须由子类重写

    def __init__(self, db: Session):
        self.db = db

    def find_all(self, skip: int = 0, limit: int = 100) -> list:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def find_by_id(self, id: int) -> Optional[Any]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def create(self, schema: BaseModel) -> Any:
        obj = self.model(**schema.model_dump())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, id: int, schema: BaseModel) -> Optional[Any]:
        obj = self.find_by_id(id)
        if obj is None:
            return None
        update_data = schema.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(obj, field, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, id: int) -> bool:
        obj = self.find_by_id(id)
        if obj is None:
            return False
        self.db.delete(obj)
        self.db.commit()
        return True

    def toggle_enabled(self, id: int) -> Optional[Any]:
        obj = self.find_by_id(id)
        if obj is None:
            return None
        obj.enabled = not obj.enabled
        self.db.commit()
        self.db.refresh(obj)
        return obj

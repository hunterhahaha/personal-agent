"""模型配置 repository。"""

import secrets
import string

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.model_config import ModelConfig
from app.repositories.base import BaseRepository

_UID_CHARS = string.ascii_lowercase + string.digits
_UID_LEN = 10


def _gen_uid() -> str:
    return "".join(secrets.choice(_UID_CHARS) for _ in range(_UID_LEN))


class ModelConfigRepository(BaseRepository):
    model = ModelConfig

    def __init__(self, db: Session):
        super().__init__(db)

    def create(self, schema: BaseModel) -> ModelConfig:
        """创建模型配置，并自动生成唯一 uid。"""
        while True:
            uid = _gen_uid()
            if not self.db.query(ModelConfig).filter(ModelConfig.uid == uid).first():
                break
        obj = ModelConfig(uid=uid, **schema.model_dump())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def find_by_uid(self, uid: str) -> ModelConfig | None:
        return (
            self.db.query(ModelConfig)
            .filter(ModelConfig.uid == uid)
            .first()
        )

    def get_active(self) -> ModelConfig | None:
        return (
            self.db.query(ModelConfig)
            .filter(ModelConfig.is_active == True)
            .first()
        )

    def set_active(self, record_id: int) -> ModelConfig | None:
        obj = self.find_by_id(record_id)
        if obj is None:
            return None
        self.db.query(ModelConfig).filter(
            ModelConfig.is_active == True,
            ModelConfig.id != record_id,
        ).update({"is_active": False})
        obj.is_active = True
        self.db.commit()
        self.db.refresh(obj)
        return obj

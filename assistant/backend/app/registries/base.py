"""通用基础 registry，为数据库实体提供内存缓存。"""

import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository

T = TypeVar("T")

logger = logging.getLogger(__name__)


class BaseRegistry(ABC, Generic[T]):
    """以内存缓存实体，并使用字符串标识符作为键。

    子类必须实现 ``_get_repo`` 来提供 repository，并实现 ``_entity_id`` 从每个实体中提取查找键。
    """

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    @abstractmethod
    def _get_repo(self, db: Session) -> BaseRepository:
        """返回用于加载实体的 repository。"""

    @property
    @abstractmethod
    def _id_attr(self) -> str:
        """用作 dict 键的属性名，例如 ``"tool_id"``。"""

    def load_all(self, db: Session) -> None:
        """从数据库加载所有实体到内存缓存。"""
        repo = self._get_repo(db)
        items = repo.find_all()
        self._items = {getattr(item, self._id_attr): item for item in items}
        cls_name = self.__class__.__name__
        logger.info("Loaded %d items into %s", len(self._items), cls_name)

    def get(self, item_id: str) -> T | None:
        """按标识符查找单个实体。"""
        return self._items.get(item_id)

    def get_enabled(self) -> list[T]:
        """返回所有 ``enabled`` 为 True 的实体。"""
        return [i for i in self._items.values() if i.enabled]


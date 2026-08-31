from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str | None = None


class BaseSearchProvider(ABC):
    @abstractmethod
    async def search(
        self, query: str, num_results: int = 5
    ) -> list[SearchResult]:
        """执行搜索查询并返回结果列表。"""
        ...

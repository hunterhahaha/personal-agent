"""Tavily 搜索 provider：面向 AI 优化的搜索 API。"""

import logging

import httpx

from app.providers.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilySearchProvider(BaseSearchProvider):
    """通过 Tavily API 搜索（需要 API key）。"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("TAVILY_API_KEY is required for Tavily search provider")
        self.api_key = api_key

    async def search(
        self, query: str, num_results: int = 5
    ) -> list[SearchResult]:
        """通过 Tavily API 执行网页搜索。"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    TAVILY_API_URL,
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": num_results,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            logger.error("Tavily search timed out after 30 seconds")
            raise RuntimeError("Search request timed out")
        except httpx.HTTPStatusError as e:
            logger.error("Tavily returned HTTP %s", e.response.status_code)
            raise RuntimeError(f"Search returned HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("Tavily search failed: %s", e)
            raise RuntimeError(f"Search request failed: {e}")

        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    content=item.get("raw_content"),
                )
            )

        if not results:
            logger.warning("No results from Tavily for query: %s", query)

        return results

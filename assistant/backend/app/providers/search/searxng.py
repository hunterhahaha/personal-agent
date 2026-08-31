"""SearXNG 搜索 provider：自托管元搜索引擎。"""

import logging
from urllib.parse import quote_plus

import httpx

from app.providers.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)


class SearXNGSearchProvider(BaseSearchProvider):
    """通过自托管 SearXNG 实例进行搜索。"""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or "http://localhost:8888").rstrip("/")

    async def search(
        self, query: str, num_results: int = 5
    ) -> list[SearchResult]:
        """通过 SearXNG JSON API 执行搜索。"""
        url = f"{self.base_url}/search?format=json&q={quote_plus(query)}&categories=general"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            logger.error("SearXNG request timed out after 15 seconds")
            raise RuntimeError("Search request timed out")
        except httpx.HTTPStatusError as e:
            logger.error("SearXNG returned HTTP %s", e.response.status_code)
            raise RuntimeError(f"Search returned HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("SearXNG request failed: %s", e)
            raise RuntimeError(f"Search request failed: {e}")

        results: list[SearchResult] = []
        for item in data.get("results", [])[:num_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )

        if not results:
            logger.warning("No results from SearXNG for query: %s", query)

        return results

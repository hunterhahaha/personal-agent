"""Bing 搜索 provider：国内可访问，无需 API key。"""

import logging
import re
from urllib.parse import quote_plus

import httpx

from app.providers.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)


class BingSearchProvider(BaseSearchProvider):
    """通过 Bing HTML 搜索（无需 API key）。"""

    def __init__(self, api_key: str | None = None):
        pass

    async def search(
        self, query: str, num_results: int = 5
    ) -> list[SearchResult]:
        """使用 Bing HTML 结果执行网页搜索。"""
        url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num_results}"

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                )
                response.raise_for_status()

        except httpx.TimeoutException:
            logger.error("Bing search timed out after 10 seconds")
            raise RuntimeError("Search request timed out")
        except httpx.HTTPStatusError as e:
            logger.error("Bing returned HTTP %s", e.response.status_code)
            raise RuntimeError(f"Search returned HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("Bing search failed: %s", e)
            raise RuntimeError(f"Search request failed: {e}")

        results = self._parse_results(response.text, num_results)
        if not results:
            logger.warning("No results parsed from Bing for query: %s", query)
        return results

    def _parse_results(
        self, html: str, num_results: int
    ) -> list[SearchResult]:
        """解析 Bing HTML 搜索结果。"""
        results: list[SearchResult] = []

        # 每个结果位于 class 为 b_algo 的 <li> 中
        algo_pattern = re.compile(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
            re.DOTALL,
        )
        # 标题位于 <h2><a href="..." ...>title</a></h2> 中
        h2_link_pattern = re.compile(
            r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        # 摘要位于 <p class="b_lineclamp2"> 中
        snippet_pattern = re.compile(
            r'<p[^>]*class="b_lineclamp2"[^>]*>(.*?)</p>',
            re.DOTALL,
        )

        blocks = algo_pattern.findall(html)
        for block in blocks[:num_results]:
            link_match = h2_link_pattern.search(block)
            if not link_match:
                continue
            url = link_match.group(1)
            raw_title = link_match.group(2)
            title = self._clean_text(raw_title)

            snippet = ""
            snip_match = snippet_pattern.search(block)
            if snip_match:
                snippet = self._clean_text(snip_match.group(1))

            results.append(
                SearchResult(title=title, url=url, snippet=snippet)
            )

        return results

    @staticmethod
    def _clean_text(text: str) -> str:
        """去除 HTML 标签并清理空白字符。"""
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&#39;", "'").replace("&quot;", '"')
        text = re.sub(r"\s+", " ", text).strip()
        return text

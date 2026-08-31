"""搜索网页以获取当前信息。"""

import logging
import time

from app.providers.factory import create_search_provider
from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Search the web for current information",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
}


async def execute(query: str, num_results: int = 5, **kwargs) -> ToolResult:
    t0 = time.monotonic()
    provider = create_search_provider()
    provider_name = type(provider).__name__
    try:
        results = await provider.search(query, num_results=num_results)
        items = [
            {"title": r.title, "url": r.url, "snippet": r.snippet}
            for r in results
        ]
        dur_ms = (time.monotonic() - t0) * 1000
        content = "\n\n".join(
            f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}"
            for i, r in enumerate(items)
        )
        return ToolResult(
            state={
                "status": "success",
                "input": {"query": query, "num_results": num_results},
                "output": {"results": items, "results_count": len(items)},
                "summary": f"找到 {len(items)} 条结果: '{query}'",
            },
            metadata={
                "duration_ms": round(dur_ms, 1), "truncated": False,
                "approval_required": False, "approval_granted": None,
                "provider": "builtin",
                "extra": {"provider": provider_name},
            },
            content=content or "(无搜索结果)",
        )
    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Web search failed")
        return ToolResult(
            state={
                "status": "error",
                "input": {"query": query, "num_results": num_results},
                "output": {"results": [], "results_count": 0},
                "error": str(e),
                "summary": f"搜索失败: {e}",
            },
            metadata={
                "duration_ms": round(dur_ms, 1), "truncated": False,
                "approval_required": False, "approval_granted": None,
                "provider": "builtin",
                "extra": {"provider": provider_name},
            },
            content=f"搜索失败: {e}",
        )

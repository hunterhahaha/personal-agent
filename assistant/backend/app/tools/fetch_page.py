"""抓取 URL 并返回其文本内容。"""

import logging
import time

import httpx

from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 5000

TOOL_DEFINITION = {
    "name": "fetch_page",
    "description": "Fetch a URL and return its text content (first 5000 characters)",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
        },
        "required": ["url"],
    },
}


async def execute(url: str, **kwargs) -> ToolResult:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        content = response.text[:MAX_CONTENT_LENGTH]
        truncated = len(response.text) > MAX_CONTENT_LENGTH
        dur_ms = (time.monotonic() - t0) * 1000
        text_content = (
            f"[URL: {url}]\n[Status: {response.status_code}]\n\n{content}"
            + ("\n\n[内容已截断至 5000 字符]" if truncated else "")
        )
        return ToolResult(
            state={
                "status": "success",
                "input": {"url": url},
                "output": {
                    "content": content,
                    "content_length": len(content),
                    "truncated": truncated,
                    "http_status_code": response.status_code,
                },
                "summary": f"HTTP {response.status_code}, {len(content)} chars"
                + (" (truncated)" if truncated else ""),
                "final_url": str(response.url) if str(response.url) != url else None,
            },
            metadata={
                "duration_ms": round(dur_ms, 1),
                "truncated": truncated,
                "approval_required": False, "approval_granted": None,
                "provider": "httpx",
                "extra": {
                    "content_type": response.headers.get("content-type", ""),
                    "redirect_count": len(response.history),
                },
            },
            content=text_content,
        )

    except httpx.TimeoutException:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.error("Request to %s timed out", url)
        return ToolResult(
            state={"status": "timeout", "input": {"url": url},
                   "output": None, "error": "Request timed out after 15 seconds",
                   "summary": "timeout after 15s"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "httpx", "extra": {}},
            content=f"[错误] 请求 {url} 超时（15秒）",
        )
    except httpx.HTTPStatusError as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.error("HTTP error fetching %s: %s %s", url,
                     e.response.status_code, e.response.text[:200])
        return ToolResult(
            state={"status": "error", "input": {"url": url},
                   "output": None,
                   "error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                   "summary": f"HTTP {e.response.status_code}"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "httpx", "extra": {}},
            content=f"[错误] HTTP {e.response.status_code}: {e.response.reason_phrase}",
        )
    except httpx.RequestError as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.error("Request failed for %s: %s", url, e)
        return ToolResult(
            state={"status": "error", "input": {"url": url},
                   "output": None, "error": f"Request failed: {e}",
                   "summary": "网络请求失败"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "httpx", "extra": {}},
            content=f"[错误] 请求失败: {e}",
        )
    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Unexpected error fetching %s", url)
        return ToolResult(
            state={"status": "error", "input": {"url": url},
                   "output": None, "error": str(e),
                   "summary": f"未知错误: {type(e).__name__}"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "httpx", "extra": {}},
            content=f"[错误] {e}",
        )

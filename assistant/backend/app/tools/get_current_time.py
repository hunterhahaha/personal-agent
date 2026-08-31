"""获取当前日期和时间的工具。"""
import time
from datetime import datetime

from app.schemas.message import ToolResult


async def execute(**kwargs) -> ToolResult:
    t0 = time.monotonic()
    now = datetime.now().astimezone()
    iso = now.isoformat()
    dur_ms = (time.monotonic() - t0) * 1000
    return ToolResult(
        state={
            "status": "success",
            "input": {},
            "output": {"datetime": iso, "timezone": str(now.tzinfo)},
            "summary": iso[:19],
        },
        metadata={
            "duration_ms": round(dur_ms, 1), "truncated": False,
            "approval_required": False, "approval_granted": None,
            "provider": "builtin", "extra": {},
        },
        content=iso,
    )


TOOL_DEFINITION = {
    "name": "get_current_time",
    "description": "Get the current date and time.",
    "input_schema": {"type": "object", "properties": {}},
}

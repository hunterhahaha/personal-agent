"""取回先前被 micro-compacted 的工具结果原始完整输出。"""

import logging

from app.database import session_scope
from app.repositories.tool_result_repo import ToolResultRepository
from app.schemas.message import ToolResult as ToolResultSchema

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "get_tool_result",
    "description": "获取指定工具调用 ID 的完整原始输出结果。当上下文中的工具结果被摘要替代时，使用此工具获取完整内容。",
    "input_schema": {
        "type": "object",
        "properties": {
            "call_id": {
                "type": "string",
                "description": "工具调用的 callID（以 call_ 开头）",
            },
        },
        "required": ["call_id"],
    },
}


async def execute(call_id: str, **kwargs) -> ToolResultSchema:
    try:
        with session_scope() as db:
            repo = ToolResultRepository(db)
            row = repo.get_by_call_id(call_id)
            if row:
                logger.info("Retrieved tool result for callID=%s (%d chars)", call_id, len(row.full_output))
                return ToolResultSchema(
                    state={
                        "status": "success",
                        "input": {"call_id": call_id},
                        "output": {"full_output": row.full_output, "summary": row.summary},
                        "summary": f"已获取 {row.tool} 的完整输出 ({len(row.full_output)} 字符)",
                    },
                    metadata={
                        "duration_ms": 0,
                        "truncated": False,
                        "approval_required": False,
                        "approval_granted": None,
                        "provider": "db",
                        "extra": {"tool": row.tool},
                    },
                    content=row.full_output,
                )
            msg = f"[未找到 callID={call_id} 的工具结果]"
            return ToolResultSchema(
                state={"status": "not_found", "input": {"call_id": call_id},
                       "output": None, "error": f"未找到 callID={call_id}",
                       "summary": msg},
                metadata={"duration_ms": 0, "truncated": False,
                          "approval_required": False, "approval_granted": None,
                          "provider": "db", "extra": {}},
                content=msg,
            )
    except Exception as e:
        logger.exception("get_tool_result failed for callID=%s", call_id)
        msg = f"[错误] 获取工具结果失败: {e}"
        return ToolResultSchema(
            state={"status": "error", "input": {"call_id": call_id},
                   "output": None, "error": str(e), "summary": msg},
            metadata={"duration_ms": 0, "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "db", "extra": {}},
            content=msg,
        )

"""把任务委派给由蓝图（Skill）定义的子智能体。

主 LLM 使用此工具把子任务卸载给专门构建的子智能体。
每个子智能体都有自己的 WorkerRuntime、受限工具集和专用系统提示词。
子智能体实例会在完成后销毁。
"""

import logging
import time

from app.database import session_scope
from app.repositories.sub_agent_blueprint_repo import SubAgentBlueprintRepository
from app.schemas.message import ToolResult
from app.worker.sub_agent import FAIL_BRACKET, SubAgentBlueprintSpec, run_sub_agent

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "run_sub_agent",
    "description": (
        "创建并运行一个子智能体来处理子任务。"
        "子智能体根据蓝图配置拥有自己的工具集和系统提示词，"
        "完成后自动销毁。"
        "适用于需要独立上下文或并行处理的复杂子任务。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "要使用的蓝图 ID。可以从可用蓝图目录中查看。",
            },
            "task": {
                "type": "string",
                "description": "子任务的详细描述，越具体越好。",
            },
        },
        "required": ["skill_id", "task"],
    },
}


async def execute(skill_id: str, task: str, **kwargs) -> ToolResult:
    # 提取注入的父事件回调，用于子智能体可观测性
    parent_event_callback = kwargs.pop("_parent_event_callback", None)
    parent_call_id = kwargs.pop("_parent_call_id", "")

    t0 = time.monotonic()
    try:
        with session_scope() as db:
            repo = SubAgentBlueprintRepository(db)
            bp = repo.find_by_blueprint_id(skill_id)
            if not bp:
                msg = f"[错误] 找不到蓝图 '{skill_id}'"
                return ToolResult(
                    state={"status": "not_found", "input": {"skill_id": skill_id, "task": task},
                           "output": None, "error": f"找不到蓝图 '{skill_id}'",
                           "summary": f"蓝图 '{skill_id}' 不存在", "blueprint_name": None},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"blueprint_tools": [], "llm_provider": ""}},
                    content=msg,
                )

            if not bp.enabled:
                msg = f"[错误] 蓝图 '{skill_id}' 已禁用"
                return ToolResult(
                    state={"status": "disabled", "input": {"skill_id": skill_id, "task": task},
                           "output": None, "error": f"蓝图 '{skill_id}' 已禁用",
                           "summary": f"蓝图已禁用", "blueprint_name": bp.name},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"blueprint_tools": bp.tool_ids or [],
                                        "llm_provider": ""}},
                    content=msg,
                )

            if not bp.tool_ids:
                msg = f"[错误] 蓝图 '{skill_id}' 没有配置工具"
                return ToolResult(
                    state={"status": "no_tools", "input": {"skill_id": skill_id, "task": task},
                           "output": None, "error": "蓝图没有配置工具",
                           "summary": "蓝图没有配置工具", "blueprint_name": bp.name},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"blueprint_tools": [], "llm_provider": ""}},
                    content=msg,
                )

            # 在 commit/close 前复制所有运行时字段。SQLAlchemy 会在 commit 后
            # 让 ORM 属性过期，因此异步 worker 不能接收绑定 session 的模型实例。
            bp_spec = SubAgentBlueprintSpec(
                blueprint_id=bp.blueprint_id,
                name=bp.name,
                description=bp.description,
                tool_ids=list(bp.tool_ids or []),
                prompt_template_ids=list(bp.prompt_template_ids or []),
            )
            bp_name = bp_spec.name
            bp_tool_ids = list(bp_spec.tool_ids)

        result = await run_sub_agent(
            blueprint=bp_spec,
            task=task,
            parent_event_callback=parent_event_callback,
            parent_call_id=parent_call_id,
        )
        dur_ms = (time.monotonic() - t0) * 1000
        return ToolResult(
            state={
                "status": "success",
                "input": {"skill_id": skill_id, "task": task},
                "output": {"result": result, "result_length": len(result)},
                "summary": f"子智能体 '{skill_id}' 完成，输出 {len(result)} 字符",
                "blueprint_name": bp_name,
            },
            metadata={
                "duration_ms": round(dur_ms, 1),
                "truncated": False,
                "approval_required": False,
                "approval_granted": None,
                "provider": "builtin",
                "extra": {
                    "blueprint_tools": bp_tool_ids,
                    "llm_provider": "",
                },
            },
            content=result,
        )

    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Sub-agent '%s' crashed", skill_id)
        msg = FAIL_BRACKET + str(e)
        return ToolResult(
            state={"status": "crashed", "input": {"skill_id": skill_id, "task": task},
                   "output": None, "error": str(e),
                   "summary": f"子智能体崩溃: {type(e).__name__}",
                   "blueprint_name": None},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"blueprint_tools": [], "llm_provider": ""}},
            content=msg,
        )

"""子智能体运行时：按蓝图创建并执行受限的 WorkerRuntime。"""

import logging
from dataclasses import dataclass
from typing import Callable

from app.models.sub_agent_blueprint import SubAgentBlueprint
from app.providers.llm.base import BaseLLMProvider
from app.schemas.sse_events import (
    SUB_AGENT_DONE,
    SUB_AGENT_START,
    SUB_AGENT_TOOL_CALL,
    SUB_AGENT_TOOL_RESULT,
)
from app.worker.runtime import WorkerRuntime

logger = logging.getLogger(__name__)

SUCCESS_BRACKET = ("[子智能体已完成]" + chr(10))
FAIL_BRACKET = ("[子智能体执行失败]" + chr(10))


@dataclass(frozen=True)
class SubAgentBlueprintSpec:
    """异步子智能体运行时使用的、脱离会话的蓝图数据。"""

    blueprint_id: str
    name: str
    description: str
    tool_ids: list
    prompt_template_ids: list


async def run_sub_agent(
    blueprint: SubAgentBlueprint | SubAgentBlueprintSpec,
    task: str,
    llm_provider: BaseLLMProvider | None = None,
    parent_event_callback: Callable | None = None,
    parent_call_id: str = "",
) -> str:
    """让 *blueprint* 定义的单个子智能体执行 *task*。

    子智能体只会拿到 ``blueprint.tool_ids`` 中列出的工具，以及根据
    ``blueprint.prompt_template_ids`` 引用的提示词模板构建出的系统提示词。
    WorkerRuntime 实例仅属于本次调用；调用返回后实例会被垃圾回收。

    参数：
        blueprint: 子智能体蓝图配置。
        task: 子智能体要执行的任务描述。
        llm_provider: 可选的 LLM provider 覆盖项。
        parent_event_callback: 来自父 worker 的可选回调，用于发出子智能体
            可观测性事件（sub_agent_start、sub_agent_tool_call、
            sub_agent_tool_result、sub_agent_done）。
            签名：``async def cb(event_type: str, data: dict) -> None``。
        parent_call_id: 触发本次子智能体执行的父 worker 工具调用 ID。
            前端用它追踪层级关系。

    返回：
        子智能体的回复文本，或错误消息。
    """
    system_prompt = _build_sub_system_prompt(blueprint)
    tool_ids = list(blueprint.tool_ids or [])

    # 发出 sub_agent_start 事件
    if parent_event_callback:
        await parent_event_callback(SUB_AGENT_START, {
            "parent_call_id": parent_call_id,
            "blueprint_id": blueprint.blueprint_id,
            "blueprint_name": blueprint.name or "",
            "task": task,
        })

    # 构建子回调，将 child worker 事件转换为父回调上的 sub_agent_* 事件。
    child_event_callback: Callable | None = None
    if parent_event_callback:
        async def child_event_callback(event_type: str, data: dict) -> None:
            """将 child worker 事件转换为 sub_agent_* 事件。"""
            if event_type == "tool_call":
                await parent_event_callback(SUB_AGENT_TOOL_CALL, {
                    "parent_call_id": parent_call_id,
                    "tool_name": data.get("tool_name", ""),
                    "tool_args": data.get("tool_args", {}),
                    "call_id": data.get("call_id", ""),
                })
            elif event_type == "tool_result":
                await parent_event_callback(SUB_AGENT_TOOL_RESULT, {
                    "parent_call_id": parent_call_id,
                    "tool_name": data.get("tool_name", ""),
                    "call_id": data.get("call_id", ""),
                    "result_len": data.get("result_len", 0),
                    "state": data.get("state", {}),
                    "metadata": data.get("metadata", {}),
                })
            # child worker 的其他事件（thinking、reasoning、done）不再转发；
            # 父级会单独处理 sub_agent_done。

    worker = WorkerRuntime(llm_provider=llm_provider)
    result = await worker.execute(
        system_prompt=system_prompt or "",
        task_prompt=task,
        tool_ids=tool_ids,
        event_callback=child_event_callback,
    )

    if result.get("success") and result.get("result"):
        out = result["result"]
        response_text: str = ""
        if isinstance(out, str) and out.strip():
            response_text = out
        elif isinstance(out, dict) and out.get("results"):
            response_text = str(out)

        if response_text:
            # 发出 sub_agent_done（成功）
            if parent_event_callback:
                await parent_event_callback(SUB_AGENT_DONE, {
                    "parent_call_id": parent_call_id,
                    "blueprint_id": blueprint.blueprint_id,
                    "success": True,
                    "result_len": len(response_text),
                    "error": None,
                })
            return response_text

    error = result.get("error", "子智能体未返回有效结果")
    logger.warning("Sub-agent '%s' failed: %s", blueprint.blueprint_id, error)

    # 发出 sub_agent_done（失败）
    if parent_event_callback:
        await parent_event_callback(SUB_AGENT_DONE, {
            "parent_call_id": parent_call_id,
            "blueprint_id": blueprint.blueprint_id,
            "success": False,
            "result_len": 0,
            "error": error,
        })

    return FAIL_BRACKET + error


def _build_sub_system_prompt(blueprint: SubAgentBlueprint | SubAgentBlueprintSpec) -> str:
    """根据蓝图引用的提示词组装子智能体系统提示词。"""
    from app.database import session_scope
    from app.repositories.prompt_template_repo import PromptTemplateRepository

    parts: list[str] = []
    parts.append(
        f"你是子智能体「{blueprint.name}」。{blueprint.description}"
    )
    parts.append("只使用分配给你的工具完成任务，完成后直接返回结果。")

    if blueprint.prompt_template_ids:
        try:
            with session_scope() as db:
                repo = PromptTemplateRepository(db)
                for pid in blueprint.prompt_template_ids:
                    tmpl = repo.find_by_prompt_id(pid)
                    if tmpl and tmpl.enabled and tmpl.content:
                        parts.append(tmpl.content)
        except Exception:
            logger.warning("Failed to load prompts for blueprint '%s'", blueprint.blueprint_id, exc_info=True)

    return "\n\n".join(parts)

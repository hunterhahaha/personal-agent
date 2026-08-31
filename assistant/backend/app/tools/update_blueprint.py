"""修改已有的子智能体蓝图。

主 LLM 会使用此工具微调已经接近可用的蓝图。
"""

import logging
import time

from app.database import session_scope
from app.repositories.prompt_template_repo import PromptTemplateRepository
from app.repositories.sub_agent_blueprint_repo import SubAgentBlueprintRepository
from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "update_blueprint",
    "description": (
        "修改一个现有的子智能体蓝图。当蓝图大致可用但需要调整时使用。"
        "可以修改名称、描述、工具列表、系统提示词或启用状态。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "要修改的蓝图 ID",
            },
            "name": {
                "type": "string",
                "description": "新的显示名称（可选）",
            },
            "description": {
                "type": "string",
                "description": "新的用途描述（可选）",
            },
            "tool_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的工具 ID 列表（可选）",
            },
            "system_prompt": {
                "type": "string",
                "description": "新的系统提示词（可选）",
            },
            "enabled": {
                "type": "boolean",
                "description": "启用或禁用此蓝图（可选）",
            },
        },
        "required": ["skill_id"],
    },
}


async def execute(
    skill_id: str,
    name: str | None = None,
    description: str | None = None,
    tool_ids: list[str] | None = None,
    system_prompt: str | None = None,
    enabled: bool | None = None,
    **kwargs,
) -> ToolResult:
    t0 = time.monotonic()
    try:
        with session_scope() as db:
            bp_repo = SubAgentBlueprintRepository(db)
            bp = bp_repo.find_by_blueprint_id(skill_id)
            if not bp:
                msg = f"[错误] 找不到蓝图 '{skill_id}'"
                return ToolResult(
                    state={"status": "not_found", "input": {"skill_id": skill_id},
                           "output": None, "error": f"找不到蓝图 '{skill_id}'",
                           "summary": f"找不到蓝图 '{skill_id}'"},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"system_prompt_created": False}},
                    content=msg,
                )

            changes: list[str] = []
            new_values: dict = {}

            if name is not None:
                bp.name = name
                changes.append("名称")
                new_values["name"] = name
            if description is not None:
                bp.description = description
                changes.append("描述")
                new_values["description"] = description
            if tool_ids is not None:
                bp.tool_ids = tool_ids
                changes.append(f"工具({len(tool_ids)}个)")
                new_values["tool_ids"] = tool_ids
            if enabled is not None:
                bp.enabled = enabled
                changes.append("启用状态")
                new_values["enabled"] = enabled

            sys_prompt_created = False
            if system_prompt is not None:
                prompt_repo = PromptTemplateRepository(db)
                prompt_id = f"{skill_id}_system"
                tmpl = prompt_repo.find_by_prompt_id(prompt_id)
                if tmpl:
                    tmpl.content = system_prompt
                else:
                    from app.models.prompt_template import PromptTemplate
                    db.add(
                        PromptTemplate(
                            prompt_id=prompt_id,
                            name=f"{bp.name} — 系统提示词",
                            type="system",
                            version="1.0",
                            enabled=True,
                            created_by="ai",
                            description=f"System prompt for blueprint '{skill_id}'",
                            content=system_prompt,
                        )
                    )
                    if prompt_id not in (bp.prompt_template_ids or []):
                        bp.prompt_template_ids = list(bp.prompt_template_ids or []) + [prompt_id]
                    sys_prompt_created = True
                changes.append("系统提示词")

            if not changes:
                msg = f"[提示] 蓝图 '{skill_id}' 没有需要修改的字段"
                return ToolResult(
                    state={"status": "no_changes", "input": {"skill_id": skill_id},
                           "output": {"changes": [], "new_values": {}},
                           "summary": "没有需要修改的字段"},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"system_prompt_created": False}},
                    content=msg,
                )

        dur_ms = (time.monotonic() - t0) * 1000
        logger.info("Updated blueprint '%s': %s", skill_id, ", ".join(changes))
        msg = f"[成功] 已更新蓝图 '{skill_id}'：{', '.join(changes)}"
        return ToolResult(
            state={
                "status": "updated",
                "input": {"skill_id": skill_id},
                "output": {"changes": changes, "new_values": new_values},
                "summary": f"已更新蓝图 '{skill_id}'：{', '.join(changes)}",
            },
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"system_prompt_created": sys_prompt_created}},
            content=msg,
        )

    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Failed to update blueprint '%s'", skill_id)
        msg = f"[错误] 更新蓝图失败: {e}"
        return ToolResult(
            state={"status": "error", "input": {"skill_id": skill_id},
                   "output": None, "error": str(e),
                   "summary": f"更新蓝图失败: {e}"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"system_prompt_created": False}},
            content=msg,
        )

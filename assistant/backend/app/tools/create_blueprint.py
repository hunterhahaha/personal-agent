"""创建新的子智能体蓝图（Skill + PromptTemplate）。

当没有现有蓝图适合当前任务时，主 LLM 会使用此工具。
"""

import logging
import time

from app.database import session_scope
from app.models.prompt_template import PromptTemplate
from app.models.sub_agent_blueprint import SubAgentBlueprint
from app.repositories.prompt_template_repo import PromptTemplateRepository
from app.repositories.sub_agent_blueprint_repo import SubAgentBlueprintRepository
from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "create_blueprint",
    "description": (
        "创建一个新的子智能体蓝图。当现有蓝图都不适合当前任务时使用。"
        "蓝图定义了子智能体的身份、可用工具和系统提示词。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "蓝图唯一 ID（如 'code_reviewer'），使用字母数字和下划线",
            },
            "name": {
                "type": "string",
                "description": "蓝图显示名称",
            },
            "description": {
                "type": "string",
                "description": "蓝图用途描述，帮助主智能体判断何时使用",
            },
            "tool_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "子智能体可以使用的工具 ID 列表",
            },
            "system_prompt": {
                "type": "string",
                "description": "子智能体的系统提示词，定义其身份、行为准则和工作方式",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表（可选）",
            },
        },
        "required": ["skill_id", "name", "description", "system_prompt"],
    },
}


async def execute(
    skill_id: str,
    name: str,
    description: str,
    system_prompt: str,
    tool_ids: list[str] | None = None,
    tags: list[str] | None = None,
    **kwargs,
) -> ToolResult:
    t0 = time.monotonic()
    tool_ids = tool_ids or []
    tags = tags or []

    try:
        with session_scope() as db:
            bp_repo = SubAgentBlueprintRepository(db)
            prompt_repo = PromptTemplateRepository(db)

            if bp_repo.find_by_blueprint_id(skill_id):
                msg = f"[错误] 蓝图 '{skill_id}' 已存在"
                return ToolResult(
                    state={"status": "already_exists", "input": {"skill_id": skill_id, "name": name,
                             "description": description, "tool_ids": tool_ids, "tags": tags},
                           "output": None, "error": f"蓝图 '{skill_id}' 已存在",
                           "summary": f"蓝图 '{skill_id}' 已存在，无法重复创建"},
                    metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                              "truncated": False, "approval_required": False,
                              "approval_granted": None, "provider": "builtin",
                              "extra": {"new_prompt_created": False}},
                    content=msg,
                )

            prompt_id = f"{skill_id}_system"
            new_prompt = False
            if not prompt_repo.find_by_prompt_id(prompt_id):
                db.add(
                    PromptTemplate(
                        prompt_id=prompt_id,
                        name=f"{name} — 系统提示词",
                        type="system",
                        version="1.0",
                        enabled=True,
                        created_by="ai",
                        description=f"Auto-created system prompt for blueprint '{skill_id}'",
                        content=system_prompt,
                    )
                )
                new_prompt = True

            db.add(
                SubAgentBlueprint(
                    blueprint_id=skill_id,
                    name=name,
                    description=description,
                    enabled=True,
                    tool_ids=tool_ids,
                    prompt_template_ids=[prompt_id],
                    tags=tags,
                )
            )

        dur_ms = (time.monotonic() - t0) * 1000
        logger.info("Created blueprint '%s' with %d tools", skill_id, len(tool_ids))
        msg = f"[成功] 已创建蓝图 '{skill_id}'（{name}），配置了 {len(tool_ids)} 个工具。"
        return ToolResult(
            state={
                "status": "created",
                "input": {"skill_id": skill_id, "name": name, "description": description,
                          "tool_ids": tool_ids, "tags": tags},
                "output": {"prompt_id": prompt_id, "tool_ids_count": len(tool_ids)},
                "summary": f"已创建蓝图 '{skill_id}'（{name}），{len(tool_ids)} 个工具",
            },
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"new_prompt_created": new_prompt}},
            content=msg,
        )

    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.exception("Failed to create blueprint '%s'", skill_id)
        msg = f"[错误] 创建蓝图失败: {e}"
        return ToolResult(
            state={"status": "error", "input": {"skill_id": skill_id},
                   "output": None, "error": str(e),
                   "summary": f"创建蓝图失败: {e}"},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "builtin",
                      "extra": {"new_prompt_created": False}},
            content=msg,
        )

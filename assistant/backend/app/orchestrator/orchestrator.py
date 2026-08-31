"""Orchestrator -- 协调任务执行的主智能体。"""

import logging
from pathlib import Path
from typing import Callable

from app.config.settings import HISTORY_WINDOW
from app.models.base import SessionLocal
from app.registries import PromptRegistry, SubAgentBlueprintRegistry, ToolRegistry
from app.memory.manager import MemoryManager
from app.worker.runtime import WorkerRuntime
from app.utils.workspace import normalize_workspace_root

logger = logging.getLogger(__name__)

WORKFLOW_EXCLUDED_TOOL_IDS = {"compact", "get_tool_result"}


def _log_extractor_error(future) -> None:
    """fire-and-forget 记忆提取任务的回调。

    记录提取器抛出的异常，但不向外传播。
    """
    if future.exception():
        logger.warning("Memory extractor failed: %s", future.exception())


# SOUL.md 文件路径（项目根目录下的 assistant/SOUL.md）
_SOUL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "SOUL.md"

# 默认系统提示词模板路径（与 SOUL.md 搭配，负责运行协议而非人格设定）
_DEFAULT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "prompts"
    / "system_default.md"
)

# 基于文件的 skills 目录路径
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills"


def _fallback_title(first_message: str) -> str:
    """当模型输出不可用时，构建一个确定性的标题。"""
    title = first_message.strip().splitlines()[0].strip("\"'“”‘’` ：:，,。.!！?？")
    return (title or "新会话")[:20]


def _clean_generated_title(raw_title: str, first_message: str) -> str:
    """只保留真正的短标题，拒绝类似提示词说明的模型输出。"""
    title = raw_title.strip().splitlines()[0].strip("\"'“”‘’` ：:，,。.!！?？")
    for prefix in ("标题：", "标题:", "会话标题：", "会话标题:"):
        if title.startswith(prefix):
            title = title[len(prefix):].strip("\"'“”‘’` ：:，,。.!！?？")

    bad_markers = (
        "根据用户",
        "第一句话",
        "生成一个",
        "简短标题",
        "直接输出",
        "不要任何",
        "我们根据",
        "可以是",
    )
    if (
        not title
        or len(title) > 24
        or any(marker in title for marker in bad_markers)
    ):
        return _fallback_title(first_message)
    return title[:20]


async def generate_title(
    first_message: str,
    model_id: str | None = None,
) -> str:
    """根据用户第一条消息生成短会话标题。

    使用最小 LLM 调用，不携带额外上下文，快速且简单。
    它独立于主聊天流程运行；失败时静默降级。
    """
    try:
        from app.providers.factory import create_llm_provider
        from app.providers.llm.base import LLMMessage

        # 标题生成应该便宜且不触发 reasoning。如果没有显式选择模型，
        # 通过 uid 解析数据库中的当前激活模型，避免工厂附加该模型的默认思考模式。
        title_model_id = model_id
        if title_model_id is None:
            try:
                from app.database import session_scope
                from app.repositories.model_config_repo import ModelConfigRepository

                with session_scope() as db:
                    active = ModelConfigRepository(db).get_active()
                    title_model_id = active.uid if active else None
            except Exception:
                title_model_id = None

        llm = create_llm_provider(model_id=title_model_id)
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "你只输出一个中文会话标题，不要解释，不要复述要求。"
                    "标题不超过10个汉字。"
                ),
            ),
            LLMMessage(role="user", content=first_message),
        ]
        title, _ = await llm.chat(messages=messages, temperature=0.0)
        return _clean_generated_title(title, first_message)
    except Exception:
        logger.exception("Title generation failed, using fallback")
        return _fallback_title(first_message)

from app.utils.frontmatter import parse_frontmatter


def _read_soul_md() -> str:
    """读取 SOUL.md 文件并返回正文内容。

    如果文件不存在或读取失败，返回空字符串。
    """
    if not _SOUL_PATH.exists():
        logger.warning("SOUL.md not found at %s", _SOUL_PATH)
        return ""
    try:
        text = _SOUL_PATH.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        if body:
            logger.info("Loaded SOUL.md (%d chars)", len(body))
        return body
    except Exception:
        logger.exception("Failed to read SOUL.md")
        return ""


def _read_default_system_prompt() -> str:
    """读取文件型默认系统提示词模板。"""
    if not _DEFAULT_SYSTEM_PROMPT_PATH.exists():
        logger.warning(
            "Default system prompt not found at %s",
            _DEFAULT_SYSTEM_PROMPT_PATH,
        )
        return ""
    try:
        text = _DEFAULT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        if body:
            logger.info("Loaded default system prompt (%d chars)", len(body))
        return body
    except Exception:
        logger.exception("Failed to read default system prompt")
        return ""


def _build_workspace_context(workspace_root: str | None = None) -> str:
    """返回供系统提示词使用的工作区路径摘要。"""
    current_workspace = normalize_workspace_root(workspace_root)
    return (
        "项目工作区 (Workspace):\n"
        f"- 当前会话工作区: {current_workspace}\n"
        f"- Skills 文件夹: {_SKILLS_DIR}\n"
        f"- SOUL.md: {_SOUL_PATH}\n"
        "如需查看 skill 具体内容，使用 run_terminal 工具执行 dir/type/cat 等命令"
    )


def _build_skills_context() -> str:
    """扫描基于文件的 skills，并返回上下文字符串。

    只包含已启用的 skill（没有 ``.disabled`` 标记）。
    每个 skill 格式化为 ``name: description (path: file_path)``。
    """
    if not _SKILLS_DIR.exists():
        return ""
    lines: list[str] = []
    for child in sorted(_SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        disabled = (child / ".disabled").exists()
        if disabled:
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            name = fm.get("name", "").strip()
            desc = fm.get("description", "").strip()
            if name and desc:
                lines.append(f"- {name}: {desc}（路径: skills/{child.name}）")
        except Exception:
            continue
    if not lines:
        return ""
    return "可用技能 (Skills):\n" + "\n".join(lines)


def _build_memory_context(memory: MemoryManager) -> str:
    """加载已确认的 profile 记忆，并返回格式化后的上下文字符串。"""
    parts: list[str] = []

    profile_memories = memory.list_profiles(limit=20, inferred=False)
    if profile_memories:
        lines = [f"- {m.title}: {m.content[:200]}" for m in profile_memories]
        parts.append("用户偏好与个性化设定:\n" + "\n".join(lines))

    return "\n\n".join(parts)


class Orchestrator:
    """主编排智能体。

    通过可选构造函数注入接收 registries 和 worker factory，
    便于测试；未提供时使用默认值。

    统一执行流程：
    1. 加载配置（agent 模板、提示词、工具、skills）
    2. 构建系统提示词（SOUL.md + 全局默认提示词 + 角色提示词 + skills + 记忆）
    3. 通过 WorkerRuntime 执行任务
    4. 存储结果
    5. 返回结果
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        blueprint_registry: SubAgentBlueprintRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
        worker_factory: type[WorkerRuntime] = WorkerRuntime,
    ):
        self._tool_registry = tool_registry or ToolRegistry()
        self._blueprint_registry = blueprint_registry or SubAgentBlueprintRegistry()
        self._prompt_registry = prompt_registry or PromptRegistry()
        self._worker_factory = worker_factory

    def _load_registries(self, db):
        """从数据库加载所有 registry。"""
        self._tool_registry.load_all(db)
        self._blueprint_registry.load_all(db)
        self._prompt_registry.load_all(db)

    def _build_system_prompt(
        self,
        memory: MemoryManager,
        role_prompt_id: str | None = None,
        workspace_root: str | None = None,
    ) -> str:
        """根据所有配置来源组装完整系统提示词。

        顺序：SOUL.md → 全局默认提示词 → 角色提示词 → skills 上下文 → 记忆上下文。
        """
        parts: list[str] = []

        # 1. SOUL.md — AI 人格和行为
        soul = _read_soul_md()
        if soul:
            parts.append(soul)

        # 2. 文件型全局默认提示词 — 运行协议、工具规则和安全边界
        default_template = _read_default_system_prompt()
        if default_template:
            if parts:
                parts.append("---")
            parts.append(default_template)

        # 3. registry 中的角色提示词（可选补充，不替代全局默认提示词）
        role_template_content = ""
        if role_prompt_id:
            role_prompt = self._prompt_registry.get(role_prompt_id)
            if role_prompt and role_prompt.enabled:
                role_template_content = role_prompt.content

        if role_template_content:
            if parts:
                parts.append("---")
            parts.append(role_template_content)
        elif not parts:
            parts.append("You are a helpful AI assistant.")

        # 4. 基于文件的 skills 上下文
        skills_ctx = _build_skills_context()
        if skills_ctx:
            parts.append(skills_ctx)

        # 5. 子智能体蓝图目录
        bp_ctx = self._build_blueprint_context()
        if bp_ctx:
            parts.append(bp_ctx)

        # 6. 工作区路径
        workspace_ctx = _build_workspace_context(workspace_root)
        if workspace_ctx:
            parts.append(workspace_ctx)

        # 7. 记忆上下文（profile + global）
        mem_ctx = _build_memory_context(memory)
        if mem_ctx:
            parts.append(mem_ctx)

        system_prompt = "\n\n".join(parts)
        logger.warning(
            "\033[31m[SYSTEM PROMPT READY] chars=%d\n%s\033[0m",
            len(system_prompt),
            system_prompt,
        )
        return system_prompt

    def _build_blueprint_context(self) -> str:
        """为系统提示词构建紧凑的蓝图目录 {name, function}。"""
        blueprints = [
            s for s in self._blueprint_registry.get_enabled()
            if s.tool_ids
        ]
        if not blueprints:
            return ""

        lines = [
            "## 蓝图目录",
            "可用子智能体蓝图（用 run_sub_agent 调用）：",
            "",
        ]
        for bp in blueprints:
            lines.append(f"- **{bp.name}**（{bp.blueprint_id}）: {bp.description}")

        lines.append("")
        lines.append("若无合适蓝图，可用 create_blueprint 创建或 update_blueprint 修改。")
        return "\n".join(lines)

    def _get_workflow_tool_ids(self) -> list[str]:
        """返回当前 LLM 工作流可用的已启用工具 ID。"""
        return [
            t.tool_id
            for t in self._tool_registry.get_enabled()
            if t.tool_id not in WORKFLOW_EXCLUDED_TOOL_IDS
        ]

    async def execute_scheduled_task(
        self,
        task_name: str,
        task_description: str,
    ) -> dict:
        """通过把任务描述发送给 LLM 来执行定时任务。

        使用所有已启用工具。不会创建会话记录。
        """
        db = SessionLocal()
        try:
            self._load_registries(db)
            memory = MemoryManager(db)

            # 构建系统提示词（与聊天一致）
            system_content = self._build_system_prompt(memory=memory)

            # 收集当前工作流可用的已启用工具。
            tool_ids = self._get_workflow_tool_ids()

            worker = self._worker_factory()
            result = await worker.execute(
                system_prompt=system_content,
                task_prompt=task_description,
                tool_ids=tool_ids,
            )

            return {
                "success": result.get("success", False),
                "result": result.get("result", ""),
                "logs": result.get("logs", []),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.exception("Scheduled task execution failed: %s", e)
            return {"success": False, "error": str(e), "result": "", "logs": []}
        finally:
            db.close()

    async def chat(
        self,
        message: str,
        conversation_id: int | None = None,
        context: dict | None = None,
        approval_callback: Callable | None = None,
        event_callback: Callable | None = None,
        model_id: str | None = None,
        user_msg_db_id: int | None = None,
        workspace_root: str | None = None,
    ) -> tuple[str, dict]:
        """使用 orchestrator 处理一条聊天消息。

        返回 (reply_text, token_usage)。
        """
        db = SessionLocal()
        try:
            self._load_registries(db)
            memory = MemoryManager(db)

            # 从新的 msg_json 格式加载会话历史。
            # 使用倒序 + limit 取最近 N 条消息，然后反转成时间正序。
            # exclude_id 确保当前用户消息（调用方已存储）不会在 LLM 历史上下文中重复。
            from app.repositories import ConversationRepository
            conv_repo = ConversationRepository(db)
            if conversation_id:
                history = conv_repo.find_messages(
                    conversation_id,
                    order="desc",
                    limit=HISTORY_WINDOW,
                    exclude_id=user_msg_db_id,
                )[::-1]  # 反转为时间正序
            else:
                history = []
            history_dicts: list[dict] = []
            for m in history:
                entry = {"_db_id": m.id, "msg_type": m.msg_type,
                         "msg_json": m.msg_json or {}}
                history_dicts.append(entry)

            # 获取当前工作流可用工具。
            tool_ids = self._get_workflow_tool_ids()

            # 构建系统提示词
            system_content = self._build_system_prompt(
                memory=memory,
                workspace_root=workspace_root,
            )

            # 使用模型和思考模式覆盖项创建 LLM provider
            from app.providers.factory import create_llm_provider
            llm = create_llm_provider(model_id=model_id)

            worker = self._worker_factory(llm_provider=llm)
            result = await worker.execute(
                system_prompt=system_content,
                task_prompt=message,
                tool_ids=tool_ids,
                config={"temperature": 0.7, "max_tokens": 4096},
                history_messages=history_dicts,
                approval_callback=approval_callback,
                event_callback=event_callback,
                conversation_id=conversation_id,
                workspace_root=workspace_root,
            )

            if result.get("success"):
                reply_text = result.get("result", "")
                token_usage = result.get("token_usage", {})

                if conversation_id:
                    successful_turn_count = conv_repo.increment_successful_turn_count(
                        conversation_id
                    )

                    # 每 5 个成功用户轮次后台提取一次候选记忆。
                    # 失败只记录日志，不向外传播。
                    if (
                        successful_turn_count is not None
                        and successful_turn_count % 5 == 0
                    ):
                        import asyncio
                        from app.memory.extractor import run as extract_memories

                        logger.warning(
                            "\033[31m[MEMORY EXTRACTION TRIGGERED] "
                            "conversation_id=%s successful_turn_count=%s "
                            "正在调用记忆生成\033[0m",
                            conversation_id,
                            successful_turn_count,
                        )
                        task = asyncio.create_task(extract_memories(conversation_id))
                        task.add_done_callback(_log_extractor_error)

                return reply_text, token_usage

            error_msg = result.get("error", "Unknown error")
            logger.error("Chat execution failed: %s", error_msg)
            return f"Sorry, I couldn't process that request. ({error_msg})", {}

        except Exception as e:
            logger.exception("Chat processing failed: %s", e)
            return f"Sorry, I encountered an error: {e}", {}
        finally:
            db.close()

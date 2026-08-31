"""Worker Runtime — 使用 LLM 和工具执行任务（并行执行）。"""
# 程序对于数据格式的处理部分需要重写
import asyncio
import importlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.providers.factory import create_llm_provider
from app.providers.llm.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolDefinition
from app.schemas.message import ToolResult

logger = logging.getLogger(__name__)

# 模块级工具缓存：module_id -> module
_tool_modules: dict[str, Any] = {}

ENABLE_MICRO_COMPACT = False


def _public_tool_args(tool_args: dict | None) -> dict:
    """返回可安全写入 SSE/DB 的工具参数，排除内部运行时字段。"""
    return {
        k: v
        for k, v in dict(tool_args or {}).items()
        if not str(k).startswith("_")
    }


@dataclass
class ToolEntry:
    """已加载工具的注册表条目。

    tool_id（文件名）与 TOOL_DEFINITION.name 在设计上允许不一致；registry 以 name 为唯一键
    """

    execute: Callable
    requires_approval: bool
    definition: dict
    module_path: str


def _load_tool_module(tool_id: str) -> Any:
    """从 app.tools.{tool_id} 动态导入工具模块。"""
    if tool_id not in _tool_modules:
        try:
            _tool_modules[tool_id] = importlib.import_module(
                f"app.tools.{tool_id}"
            )
        except (ImportError, ModuleNotFoundError) as e:
            logger.error("Failed to load tool module '%s': %s", tool_id, e)
            raise
    return _tool_modules[tool_id]


class WorkerRuntime:
    """通过编排 LLM 调用和工具执行来完成任务。

    单轮 LLM 迭代中的工具调用会通过 ``asyncio.gather`` **并行**执行。
    审批流程会串行化（一次只弹一个对话），但无需审批的工具不必等待其他工具。

    可传入可选的 LLM provider 以便依赖注入；
    未传入时通过 ``create_llm_provider`` 使用已配置的 provider。
    """

    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm: BaseLLMProvider = llm_provider or create_llm_provider()
        self._logs: list[str] = []
        self._log_lock: asyncio.Lock = asyncio.Lock()
        self._tool_map: dict[str, ToolEntry] = {}
        self._approval_lock: asyncio.Lock = asyncio.Lock()

    async def _log(self, message: str, *args: Any) -> None:
        """线程安全地追加日志。"""
        async with self._log_lock:
            if args:
                formatted = message % args
            else:
                formatted = message
            self._logs.append(formatted)
            logger.warning("[Worker] %s", formatted)

    async def execute(
        self,
        system_prompt: str,
        task_prompt: str,
        tool_ids: list[str],
        config: dict | None = None,
        history_messages: list[dict] | None = None,
        approval_callback: Callable | None = None,
        event_callback: Callable | None = None,
        conversation_id: int | None = None,
        workspace_root: str | None = None,
    ) -> dict:
        """使用给定提示词和工具执行任务。

        核心循环：
        1. 调用 LLM（携带工具定义）
        2. 如果 LLM 返回 ``tool_calls``，通过 ``asyncio.gather`` **并行**
           执行工具，追加结果，然后回到第 1 步
        3. 如果没有 ``tool_calls``，说明这是最终回复，直接返回
        4. 如果任一工具失败，将错误作为 tool 消息回灌给 LLM，让它决定重试
           还是放弃；只有达到 ``max_iterations`` 时才终止

        参数：
            system_prompt: 给 LLM 的系统级指令。
            task_prompt: 要完成的用户任务。
            tool_ids: 工具模块标识符列表。
            config: temperature、max_tokens 等可选覆盖项。
            history_messages: 可选的会话历史。
            approval_callback: 工具需要用户审批时调用。
                ``async def cb(tool_name: str, tool_args: dict) -> bool``。
                返回 ``True`` 表示批准；如果为 ``None``，需要审批的工具会被跳过。
            event_callback: 执行期间每个重要事件的回调。
                ``async def cb(event_type: str, data: dict) -> None``。
                事件类型包括：``thinking``、``tool_call``、``tool_result``、
                ``done``。

        返回：
            包含 success、result、logs、error 的字典。
        """
        self._logs = []
        self._tool_map = {}
        self._conv_id = conversation_id
        self._workspace_root = workspace_root
        self._token_usage: dict = {"total": 0, "input": 0, "output": 0, "reasoning": 0, "cache": {}}
        config = config or {}
        temperature = config.get("temperature", 0.7)
        max_tokens = config.get("max_tokens", 4096)

        # ------------------------------------------------------------------
        # 1. 构建工具定义和工具映射
        # ------------------------------------------------------------------
        tool_defs: list[ToolDefinition] = []
        for tid in tool_ids:
            try:
                mod = _load_tool_module(tid)
                td = mod.TOOL_DEFINITION
                tool_defs.append(
                    ToolDefinition(
                        name=td["name"],
                        description=td["description"],
                        input_schema=td.get("input_schema", {}),
                    )
                )
                # tool_id（文件名）与 TOOL_DEFINITION.name 在设计上允许不一致；
                # registry 以 name 为唯一键
                self._tool_map[td["name"]] = ToolEntry(
                    execute=mod.execute,
                    requires_approval=bool(getattr(mod, "REQUIRES_APPROVAL", False)),
                    definition=td,
                    module_path=f"app.tools.{tid}",
                )
                await self._log("Loaded tool: %s", td["name"])
            except Exception as e:
                await self._log("Skipped tool %s: %s", tid, e)

        # ------------------------------------------------------------------
        # 2. 从新的 msg_json 格式构建消息
        # ------------------------------------------------------------------
        messages = [LLMMessage(role="system", content=system_prompt)]
        for h in (history_messages or []):
            _append_history_msg(messages, h)
        messages.append(LLMMessage(role="user", content=task_prompt))
        self._messages_ref = messages  # 供 compact 工具直接修改列表

        # ------------------------------------------------------------------
        # 3. 执行：循环直到 LLM 不再请求工具
        # ------------------------------------------------------------------
        try:
            if not tool_defs:
                chat_result = await self._llm.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response, usage = _unpack_chat_result(chat_result)
                # 累加这次单次调用的 token 用量，使无工具快速路径与循环分支保持一致。
                WorkerRuntime.accumulate_token(self._token_usage, usage)

                # 发出 iteration_done，让 chat.py 能持久化这条单轮 AssistantMsg；
                # 无工具路径必须保持 N=1 不变量：恰好 1 个 iteration_done + 1 个 done。
                if event_callback:
                    iteration_parts: list[dict] = []
                    if response:
                        iteration_parts.append({
                            "type": "text",
                            "text": response,
                        })
                    await event_callback("iteration_done", {
                        "iteration": 1,
                        "parts": iteration_parts,
                        "has_tool_calls": False,
                    })
                    await event_callback("done", {"result": response})

                return {
                    "success": True,
                    "result": response,
                    "logs": self._logs,
                    "error": None,
                    "token_usage": self._token_usage,
                }

            max_iterations = 200
            for iteration in range(max_iterations):
                if event_callback:
                    await event_callback("thinking", {"iteration": iteration + 1})

                # 第 1 层 — micro_compact：静默替换过长或过旧的工具结果。
                # 放在开关后面，保留实现，但默认不改动线上工具输出。
                if ENABLE_MICRO_COMPACT:
                    await self._micro_compact(messages, iteration, conversation_id)

                chat_with_tools_result = await self._llm.chat_with_tools(
                    messages=messages,
                    tools=tool_defs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response, tool_calls, msg_dict, usage_dict = _unpack_chat_with_tools_result(
                    chat_with_tools_result
                )
                # 跨迭代累加 token 用量
                WorkerRuntime.accumulate_token(self._token_usage, usage_dict)

                # 如果存在 reasoning 内容则发出事件（例如 DeepSeek thinking）
                reasoning = msg_dict.get("reasoning_content", "")
                if reasoning and event_callback:
                    await event_callback("reasoning", {
                        "type": "reasoning",
                        "text": reasoning,
                        "id": msg_dict.get("id", ""),
                        "message_id": msg_dict.get("id", ""),
                    })

                await self._log(
                    "Iteration %d: response len=%d, tool_calls=%d",
                    iteration + 1,
                    len(response),
                    len(tool_calls),
                )

                # 保留 provider 专属的额外字段
                extra = {
                    k: v
                    for k, v in msg_dict.items()
                    if k not in ("content", "role", "tool_calls", "function_call")
                }
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response or "",
                        tool_calls=tool_calls,
                        extra_fields=extra or None,
                    )
                )

                # 没有工具调用，说明这是最终答案
                if not tool_calls:
                    await self._log(
                        "No more tool calls, returning final response (%d chars)",
                        len(response),
                    )
                    if event_callback:
                        # 为最终迭代发出 iteration_done（无 tool_calls）。
                        # 顺序：reasoning（如有）→ text（如果响应非空）。
                        iteration_parts: list[dict] = []
                        if reasoning:
                            iteration_parts.append({
                                "type": "reasoning",
                                "text": reasoning,
                            })
                        if response:
                            iteration_parts.append({
                                "type": "text",
                                "text": response,
                            })
                        await event_callback("iteration_done", {
                            "iteration": iteration + 1,
                            "parts": iteration_parts,
                            "has_tool_calls": False,
                        })
                        await event_callback("done", {"result": response})
                    return {
                        "success": True,
                        "result": response,
                        "logs": self._logs,
                        "error": None,
                        "token_usage": self._token_usage,
                    }

                # ----------------------------------------------------------
                # 并行执行工具调用
                # ----------------------------------------------------------
                futures = [
                    self._run_one_tool(tc, approval_callback, event_callback)
                    for tc in tool_calls
                ]

                results = await asyncio.gather(*futures, return_exceptions=True)

                # 按调用顺序累积本轮迭代的 toolcall parts。
                iteration_tool_parts: list[dict] = []

                for tc, result in zip(tool_calls, results):
                    tool_call_id: str = tc.get("id", "")
                    tool_name: str = tc.get("name", "")
                    tool_args: dict = _public_tool_args(tc.get("arguments", {}))

                    tool_state: dict | None = None
                    tool_metadata: dict | None = None

                    if isinstance(result, BaseException):
                        # 将错误作为 tool 消息回灌给 LLM，而不是中止整个会话。
                        msg_content = f"Error: {repr(result)}"
                        logger.error(
                            "工具 '%s' 执行异常 (回灌给 LLM): %s",
                            tool_name, result,
                        )
                        await self._log(
                            "Tool %s raised exception, feeding back to LLM: %s",
                            tool_name, result,
                        )
                        # 合成错误状态，确保 toolcall part 对 iteration_done 仍是完整结构。
                        tool_state = {
                            "status": "error",
                            "input": tool_args,
                            "output": {"error": repr(result)},
                        }
                        tool_metadata = {}
                    else:
                        content: str
                        tool_error: str | None
                        content, tool_error, tool_state, tool_metadata = result

                        if tool_error:
                            # 工具显式返回错误：作为 tool 消息回灌给 LLM，
                            # 让它决定重试还是放弃。
                            msg_content = f"Error: {tool_error}"
                            logger.warning(
                                "工具 '%s' 返回错误 (回灌给 LLM): %s",
                                tool_name, tool_error,
                            )
                            await self._log(
                                "Tool %s returned error, feeding back to LLM: %s",
                                tool_name, tool_error,
                            )
                            if tool_state is None:
                                tool_state = {
                                    "status": "error",
                                    "input": tool_args,
                                    "output": {"error": tool_error},
                                }
                                tool_metadata = tool_metadata or {}
                        else:
                            msg_content = content
                            if tool_state is None:
                                tool_state = {
                                    "status": "success",
                                    "input": tool_args,
                                    "output": {"result": content},
                                }
                                tool_metadata = tool_metadata or {}

                    # 构建 tool 消息：可能是成功内容，也可能是错误内容
                    tool_msg = LLMMessage(
                        role="tool",
                        content=msg_content,
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                    tool_msg._iteration = iteration  # 标记迭代轮次，供 micro_compact 判断老化
                    messages.append(tool_msg)

                    # 记录本轮 iteration_done 使用的 toolcall part
                    iteration_tool_parts.append({
                        "type": "toolcall",
                        "tool": tool_name,
                        "callID": tool_call_id,
                        "state": tool_state,
                        "metadata": tool_metadata or {},
                    })

                # ----------------------------------------------------------
                # 为本轮包含工具调用的迭代发出 iteration_done。
                # 顺序：reasoning（如有）→ text（如果响应非空）
                # → 按调用顺序排列的 toolcall parts（每个都填充 state.output）。
                # ----------------------------------------------------------
                if event_callback:
                    iteration_parts = []
                    if reasoning:
                        iteration_parts.append({
                            "type": "reasoning",
                            "text": reasoning,
                        })
                    if response:
                        iteration_parts.append({
                            "type": "text",
                            "text": response,
                        })
                    iteration_parts.extend(iteration_tool_parts)
                    await event_callback("iteration_done", {
                        "iteration": iteration + 1,
                        "parts": iteration_parts,
                        "has_tool_calls": True,
                    })

            await self._log("Reached max iterations (%d)", max_iterations)
            return {
                "success": True,
                "result": response,
                "logs": self._logs,
                "error": None,
                "token_usage": self._token_usage,
            }

        except Exception as e:
            logger.exception("Worker execution failed")
            return {
                "success": False,
                "result": "",
                "logs": self._logs,
                "error": str(e),
                "token_usage": self._token_usage,
            }

    # -------------------------------------------------------------------
    # 单个工具执行
    # -------------------------------------------------------------------

    async def _run_one_tool(
        self,
        tc: dict,
        approval_callback: Callable | None,
        event_callback: Callable | None,
    ) -> tuple[str, str | None, dict | None, dict | None]:
        """执行一次带审批流程的工具调用。

        返回 ``(content, error, state, metadata)``；成功时 *error* 为 ``None``。
        成功时 ``state`` / ``metadata`` 来自工具的 ``ToolResult``；错误或拒绝路径
        中它们可能是 ``None``，调用方需要在这种情况下合成最小状态。
        """
        tool_name: str = tc.get("name", "")
        tool_args: dict = _public_tool_args(tc.get("arguments", {}))
        tool_call_id: str = tc.get("id", "")

        entry = self._tool_map.get(tool_name)
        if entry is None:
            await self._log("Unknown tool: %s", tool_name)
            return ("", f"未知工具 '{tool_name}'", None, None)

        execute_fn = entry.execute
        execution_args = dict(tool_args)

        if tool_name == "run_terminal" and self._workspace_root:
            execution_args["_workspace_root"] = self._workspace_root

        # ---- 审批阶段（串行化，一次一个对话）----
        requires_approval = self._check_approval_required(tool_name)
        approved = False

        if requires_approval:
            if approval_callback is None:
                content = "[此命令需要用户审批，但当前环境不支持审批流程，已自动拒绝]"
                await self._log(
                    "Tool %s requires approval but no callback, denied", tool_name
                )
                return (content, None, None, None)

            async with self._approval_lock:
                approved = await approval_callback(tool_name, tool_args)

            if not approved:
                content = "[用户拒绝了此命令的执行]"
                await self._log("Tool %s: user denied approval", tool_name)
                return (content, None, None, None)

            await self._log("Tool %s: user approved, executing", tool_name)

        # ---- 执行阶段 ----
        if event_callback:
            await event_callback("tool_call", {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "call_id": tool_call_id,
            })

        # 为需要上下文的工具注入 worker_context（例如 compact）
        if tool_name == "compact":
            execution_args["worker_context"] = {
                "messages": self._messages_ref,
                "llm": self._llm,
            }
            execution_args["_conversation_id"] = self._conv_id

        # 为子智能体可观测性注入 parent_event_callback
        if tool_name == "run_sub_agent" and event_callback:
            execution_args["_parent_event_callback"] = event_callback
            execution_args["_parent_call_id"] = tool_call_id

        await self._log("Tool: %s(%s)", tool_name, tool_args)
        try:
            if requires_approval:
                result = await execute_fn(approved=approved, **execution_args)
            else:
                result = await execute_fn(**execution_args)

            # 如果可用，提取结构化 state/metadata
            if isinstance(result, ToolResult):
                result_str = result.content
                tool_state = result.state
                tool_metadata = result.metadata
            else:
                result_str = str(result)
                tool_state = {"status": "success", "summary": result_str[:200]}
                tool_metadata = {}
        except Exception as e:
            error_msg = f"工具 '{tool_name}' 执行失败: {e}"
            logger.error(error_msg, exc_info=True)
            return ("", error_msg, None, None)

        if event_callback:
            await event_callback("tool_result", {
                "tool_name": tool_name,
                "call_id": tool_call_id,
                "result_len": len(result_str),
                "state": tool_state,
                "metadata": tool_metadata,
            })
        await self._log("Tool %s completed", tool_name)
        return (result_str, None, tool_state, tool_metadata)

    # -------------------------------------------------------------------
    # micro_compact（第 1 层 — 静默自动压缩）
    # -------------------------------------------------------------------

    async def _micro_compact(
        self,
        messages: list[LLMMessage],
        current_iteration: int,
        conversation_id: int | None,
    ) -> None:
        """用摘要占位符静默替换过长或过旧的工具结果。

        - 文本超过 200 字符时，替换为 ``[tool_name: summary]``
        - 超过 3 轮迭代的结果，无论长度都替换
        - 已经替换过的消息不会重复处理
        """
        if not ENABLE_MICRO_COMPACT:
            return

        if conversation_id is None:
            return

        for i, msg in enumerate(messages):
            if msg.role != "tool":
                continue
            if not msg.tool_call_id:
                continue
            if _is_already_compacted(msg.content):
                continue

            content_len = len(msg.content)
            tool_name = msg.name or "tool"

            # 估算消息的迭代“年龄”
            msg_iter = getattr(msg, "_iteration", None)
            is_old = (
                msg_iter is not None
                and (current_iteration - msg_iter) > 3
            )

            if content_len > 200 or is_old:
                summary = _make_summary(msg.content)
                full_output = msg.content
                msg.content = f"[{tool_name}: {summary}]"

                # 将原始内容持久化到数据库
                try:
                    from app.database import session_scope
                    from app.repositories.tool_result_repo import ToolResultRepository
                    with session_scope() as db:
                        repo = ToolResultRepository(db)
                        repo.save(
                            call_id=msg.tool_call_id,
                            conversation_id=conversation_id,
                            tool=tool_name,
                            full_output=full_output,
                            summary=summary,
                        )
                        logger.info(
                            "micro_compact: replaced %s result (%d → %d chars, iteration %s)",
                            tool_name, content_len, len(msg.content),
                            msg_iter,
                        )
                except Exception:
                    logger.exception("micro_compact: failed to persist tool_result")

    # -------------------------------------------------------------------
    # 辅助函数
    # -------------------------------------------------------------------

    # -------------------------------------------------------------------
    # 辅助函数（模块级）
    # -------------------------------------------------------------------

    def _check_approval_required(self, tool_name: str) -> bool:
        """查询 _tool_map，检查工具是否需要用户审批。

        使用 TOOL_DEFINITION["name"] 作为查找键，而不是文件名。
        """
        entry = self._tool_map.get(tool_name)
        return entry.requires_approval if entry else False

    @staticmethod
    def accumulate_token(acc: dict, usage: dict) -> None:
        """跨 LLM 迭代累加 token 用量。

        从模块级 ``_accumulate_token`` 移到静态方法，
        便于发现和测试。
        """
        if not usage:
            return
        for k in ("total", "input", "output", "reasoning"):
            acc[k] = acc.get(k, 0) + usage.get(k, 0)
        cache = usage.get("cache", {})
        if cache:
            acc_cache = acc.get("cache", {})
            if not isinstance(acc_cache, dict):
                acc_cache = {}
                acc["cache"] = acc_cache
            for ck in ("hit", "miss"):
                acc_cache[ck] = acc_cache.get(ck, 0) + cache.get(ck, 0)


# ── 模块级辅助函数 ──────────────────────────────────────────


def _is_already_compacted(content: str) -> bool:
    """如果内容已经像 micro_compact 占位符，则返回 True。"""
    return content.startswith("[") and ": " in content and content.endswith("]")


def _make_summary(content: str) -> str:
    """从工具输出生成简短的单行摘要。"""
    text = content.replace("\n", " ").replace("\r", " ").strip()[:120]
    if len(content) > 120:
        text += "…"
    return text


def _unpack_chat_result(result: Any) -> tuple[str, dict]:
    """同时接受新的 LLMResponse 和旧版 ``(text, usage)`` 结果。"""
    if isinstance(result, LLMResponse):
        return result.text, result.usage
    response, usage = result
    return response, usage


def _unpack_chat_with_tools_result(result: Any) -> tuple[str, list[dict], dict, dict]:
    """同时接受新的 LLMResponse 和旧版 chat_with_tools 元组结果。"""
    if isinstance(result, LLMResponse):
        msg_dict = result.raw_message_dict
        tool_calls: list[dict] = []
        for tc in result.message.tool_calls:
            raw_arguments = tc.function.arguments
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": arguments,
                "raw_arguments": raw_arguments,
            })
        return result.text, tool_calls, msg_dict, result.usage
    response, tool_calls, msg_dict, usage = result
    return response, tool_calls, msg_dict, usage


def _stringify_tool_output(output: Any) -> str:
    """仅从 state.output 构建历史工具上下文。"""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False)


def _append_history_msg(messages: list[LLMMessage], entry: dict) -> None:
    """从新格式历史条目（msg_json）重建 LLMMessage。

    单条带工具调用的 ``AssistantMsg`` 会展开为多条 LLMMessage：
    一条 assistant 消息（带 tool_calls），后面跟随每个 ToolPart 对应的一条
    tool-result 消息。
    """
    msg_type = entry.get("msg_type", "")
    msg_json = entry.get("msg_json") or {}

    if msg_type == "user":
        text = _extract_text_from_parts(msg_json.get("part", []))
        messages.append(LLMMessage(role="user", content=text))

    elif msg_type == "assistant":
        parts = msg_json.get("parts", [])
        text_parts = [p for p in parts if p.get("type") in ("text", "reasoning")]
        tool_parts = [p for p in parts if p.get("type") == "toolcall"]

        # 合并 text 和 reasoning 内容
        content = "".join(p.get("text", "") for p in text_parts if p.get("type") == "text")
        reasoning = "".join(p.get("text", "") for p in text_parts if p.get("type") == "reasoning")

        # 为 assistant 消息构建 tool_calls 列表
        tool_calls: list[dict] = []
        for tp in tool_parts:
            state_input = tp.get("state", {}).get("input", {})
            tool_calls.append({
                "id": tp.get("callID", ""),
                "name": tp.get("tool", ""),
                "arguments": state_input,
                "raw_arguments": json.dumps(state_input, ensure_ascii=False),
            })

        messages.append(LLMMessage(
            role="assistant",
            content=content or "",
            tool_calls=tool_calls if tool_calls else None,
            extra_fields={"reasoning_content": reasoning} if reasoning else None,
        ))

        # 追加工具结果消息
        for tp in tool_parts:
            state = tp.get("state", {})
            output = state.get("output", {})
            output_str = _stringify_tool_output(output)
            msg = LLMMessage(
                role="tool",
                content=output_str,
                tool_call_id=tp.get("callID", ""),
                name=tp.get("tool", ""),
            )
            msg._iteration = -1  # 标记为旧消息，供 micro_compact 使用
            messages.append(msg)


def _extract_text_from_parts(parts: list[dict]) -> str:
    """从 TextPart 字典列表中提取纯文本。"""
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return "\n".join(texts) if texts else ""

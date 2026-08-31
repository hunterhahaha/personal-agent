import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config.settings import settings
from app.providers.llm.base import (
    BaseLLMProvider,
    LLMFunctionCall,
    LLMMessage,
    LLMResponse,
    LLMResponseMessage,
    LLMToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    """适用于任意 OpenAI-compatible API 的 LLM provider（OpenAI、Azure、Ollama 等）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    # ------------------------------------------------------------------
    # 内部辅助函数
    # ------------------------------------------------------------------
    # 打包所有上下文
    @staticmethod
    def _convert_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """将 LLMMessage 列表转换为 OpenAI API 消息格式。"""
        converted: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.role == "assistant" and msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc.get("raw_arguments", ""),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                # 包含 provider 专属字段（例如 DeepSeek 的 reasoning_content）
                if msg.extra_fields:
                    entry.update(msg.extra_fields)
            if msg.role == "tool" and msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            converted.append(entry)
        return converted

    # 将所有工具信息打包
    @staticmethod
    def _convert_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """将 ToolDefinition 列表转换为 OpenAI tool 格式。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    # 构建请求openai sdk的参数字典
    def _build_kwargs(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """构建 chat completion 请求通用的 kwargs 字典。

        ``chat()`` 和 ``chat_with_tools()`` 都委托到这里，
        避免重复组装 model/messages/temperature/tools。
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return kwargs

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str, dict]:
        """发送 chat completion，并返回 (response_text, usage_dict)。"""
        try:
            kwargs = self._build_kwargs(messages, tools, temperature, max_tokens)
            response = await self._client.chat.completions.create(**kwargs)
            llm_response = self._process_response(
                response,
                allow_reasoning_fallback=False,
            )
            return llm_response.text, llm_response.usage
        except Exception as e:
            logger.error("LLM chat request failed: %s", e, exc_info=True)
            raise RuntimeError(f"LLM chat request failed: {e}") from e

    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict], dict, dict]:
        """携带工具定义发送 chat completion。

        返回 (response_text, tool_calls, msg_dict, usage_dict)。
        """
        try:
            kwargs = self._build_kwargs(messages, tools, temperature, max_tokens)
            response = await self._client.chat.completions.create(**kwargs)
            llm_response = self._process_response(response)
            return (
                llm_response.text,
                _legacy_tool_calls(llm_response.message.tool_calls),
                llm_response.raw_message_dict,
                llm_response.usage,
            )
        except Exception as e:
            logger.error("LLM chat_with_tools request failed: %s", e, exc_info=True)
            raise RuntimeError(f"LLM chat_with_tools request failed: {e}") from e

    def _process_response(
        self,
        response,
        allow_reasoning_fallback: bool = True,
    ) -> LLMResponse:
        """统一处理 LLM 响应并提取通用字段。"""
        choice = response.choices[0]
        message = response.choices[0].message
        msg_dict = message.model_dump() if hasattr(message, "model_dump") else {}

        # chat() 不能把内部 reasoning 暴露为答案文本；tool-chat
        # 为现有多迭代工作流保留 fallback。
        content = message.content or ""
        if allow_reasoning_fallback and not content:
            content = msg_dict.get("reasoning_content", "") or ""

        # 标准化 tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(LLMToolCall(
                    id=tc.id,
                    function=LLMFunctionCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                ))

        extra = {
            k: v
            for k, v in msg_dict.items()
            if k not in ("content", "role", "tool_calls", "function_call")
        }
        return LLMResponse(
            id=getattr(response, "id", None),
            model=getattr(response, "model", None),
            message=LLMResponseMessage(
                role=msg_dict.get("role", "assistant"),
                content=content,
                tool_calls=tool_calls,
                extra_fields=extra,
            ),
            finish_reason=getattr(choice, "finish_reason", None),
            usage=_extract_usage(response),
            raw=response,
        )


def _legacy_tool_calls(tool_calls: list[LLMToolCall]) -> list[dict]:
    """返回历史兼容的 WorkerRuntime 工具调用 dict 结构。"""
    legacy: list[dict] = []
    for tc in tool_calls:
        raw_arguments = tc.function.arguments
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.warning(
                "LLM tool call %s returned invalid JSON arguments: %s",
                tc.id,
                raw_arguments[:200],
            )
            arguments = {}
        legacy.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": arguments,
            "raw_arguments": raw_arguments,
        })
    return legacy


def _extract_usage(response) -> dict:
    """从 OpenAI-compatible 响应中提取 token 用量，
    转换为 ``AssistantBaseMsg`` 期望的 ``TokenUsage`` 形状。"""

    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {"total": 0, "input": 0, "output": 0, "reasoning": 0, "cache": {}}

        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", 0) if details else 0

        cache_hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        cache_miss = getattr(usage, "prompt_cache_miss_tokens", 0) or 0

        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", 0) if details else 0

        return {
            "total": getattr(usage, "total_tokens", 0) or 0,
            "input": getattr(usage, "prompt_tokens", 0) or 0,
            "output": getattr(usage, "completion_tokens", 0) or 0,
            "reasoning": reasoning or 0,
            "cache": {"hit": cache_hit, "miss": cache_miss, "cached_tokens": cached_tokens},
        }
    except Exception:
        return {"total": 0, "input": 0, "output": 0, "reasoning": 0, "cache": {}}

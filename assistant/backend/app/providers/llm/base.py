from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMMessage:
    role: str  # 角色取值："system", "user", "assistant", "tool"
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict] | None = None  # DeepSeek 格式中的 assistant tool_calls
    extra_fields: dict | None = None  # provider 专属字段（reasoning_content 等）


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class LLMFunctionCall:
    """工具调用内部兼容 OpenAI 格式的 function call payload。"""

    name: str
    arguments: str


@dataclass
class LLMToolCall:
    """chat-completion provider 返回的最小通用 tool_call 结构。"""

    id: str
    function: LLMFunctionCall
    type: str = "function"

    @property
    def name(self) -> str:
        return self.function.name

    @property
    def raw_arguments(self) -> str:
        return self.function.arguments


@dataclass
class LLMRequest:
    """单次 chat-completion 调用的 provider 中立请求结构。"""

    model: str
    messages: list[LLMMessage]
    tools: list[ToolDefinition] | None = None
    tool_choice: str | dict | None = None
    stream: bool | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponseMessage:
    """provider 返回的 assistant 消息。"""

    role: str = "assistant"
    content: str | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """单次 chat-completion 调用的 provider 中立响应结构。"""

    message: LLMResponseMessage
    id: str | None = None
    model: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def text(self) -> str:
        return self.message.content or ""

    @property
    def raw_message_dict(self) -> dict[str, Any]:
        return {
            "role": self.message.role,
            "content": self.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.message.tool_calls
            ] or None,
            **self.message.extra_fields,
        }


class BaseLLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str, dict]:
        """发送 chat completion 请求。

        返回 (response_text, token_usage_dict)。
        """
        ...

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict], dict, dict]:
        """携带工具定义发送 chat completion 请求。

        返回 (response_text, tool_calls, raw_message_dict, token_usage_dict)。
        """
        ...

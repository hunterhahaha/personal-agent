"""聊天流式 API 的 SSE 事件类型定义和 payload schema。

本模块是聊天执行期间所有 Server-Sent Event 类型的唯一注册处。
每种事件都记录了 payload 形状，确保后端发送方和前端消费者共享一致契约。

事件类型分为两类：
  1. **主事件**：主 WorkerRuntime 在一次聊天轮次中发出。
  2. **子智能体事件**：子智能体代表父 worker 执行时发出，用于观察嵌套工具执行。

所有子智能体事件都携带 ``parent_call_id`` 字段，指向生成该子智能体的父 worker
工具调用，从而让前端可以渲染层级视图。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─── 主事件（由 WorkerRuntime 发出）────────────────────────────

@dataclass
class ThinkingEvent:
    """LLM 正在处理（迭代标记）。

    Payload:
        iteration: int — 当前循环迭代轮次（从 1 开始）。
    """
    event_type: str = "thinking"
    iteration: int = 0


@dataclass
class ReasoningEvent:
    """LLM 发出了 reasoning/thinking 内容（例如 DeepSeek 扩展思考）。

    Payload:
        type: "reasoning"
        text: str — reasoning 文本片段。
        id: str — provider 层消息 ID。
        message_id: str — 与 id 相同（兼容字段）。
    """
    event_type: str = "reasoning"
    type: str = "reasoning"
    text: str = ""
    id: str = ""
    message_id: str = ""


@dataclass
class ToolCallEvent:
    """一次工具执行已开始。

    Payload:
        tool_name: str — 被调用工具的名称。
        tool_args: dict — 传给工具的参数。
        call_id: str — 本次工具调用的唯一标识。
    """
    event_type: str = "tool_call"
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ToolResultEvent:
    """一次工具执行已完成。

    Payload:
        tool_name: str — 工具名称。
        call_id: str — 对应 tool_call 的 call_id。
        result_len: int — 结果内容长度。
        state: dict — 结构化工具状态。
        metadata: dict — 工具元数据。
    """
    event_type: str = "tool_result"
    tool_name: str = ""
    call_id: str = ""
    result_len: int = 0
    state: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class DoneEvent:
    """worker 已完成执行。

    Payload:
        result: str — 最终回复文本。
    """
    event_type: str = "done"
    result: str = ""


@dataclass
class ApprovalRequiredEvent:
    """工具执行前需要用户审批。

    Payload:
        request_id: str — 唯一审批请求标识。
        tool_name: str — 请求审批的工具。
        tool_args: dict — 批准后将传入的参数。
    """
    event_type: str = "approval_required"
    request_id: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)


# ─── 子智能体事件 ─────────────────────────────────────────────────────
#
# 这些事件在子智能体（通过 run_sub_agent 工具生成）执行时发出。
# 它们镜像主事件，但带有 ``sub_agent_`` 前缀，并始终包含 ``parent_call_id``
# 以便追踪层级。


@dataclass
class SubAgentStartEvent:
    """子智能体已开始执行。

    Payload:
        parent_call_id: str — 生成该子智能体的父级 tool_call ID
            （前端用它挂到正确的父工具调用下）。
        blueprint_id: str — 蓝图标识。
        blueprint_name: str — 人类可读的蓝图名称。
        task: str — 分配给子智能体的任务描述。
    """
    event_type: str = "sub_agent_start"
    parent_call_id: str = ""
    blueprint_id: str = ""
    blueprint_name: str = ""
    task: str = ""


@dataclass
class SubAgentToolCallEvent:
    """子智能体已发起工具调用。

    Payload:
        parent_call_id: str — 指向父级工具调用。
        tool_name: str — 子智能体正在调用的工具名称。
        tool_args: dict — 工具参数。
        call_id: str — 本次子智能体工具调用的唯一 ID。
    """
    event_type: str = "sub_agent_tool_call"
    parent_call_id: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    call_id: str = ""


@dataclass
class SubAgentToolResultEvent:
    """子智能体的一次工具调用已完成。

    Payload:
        parent_call_id: str — 指向父级工具调用。
        tool_name: str — 工具名称。
        call_id: str — 对应 sub_agent_tool_call 的 call_id。
        result_len: int — 结果内容长度。
        state: dict — 结构化工具状态。
        metadata: dict — 工具元数据。
    """
    event_type: str = "sub_agent_tool_result"
    parent_call_id: str = ""
    tool_name: str = ""
    call_id: str = ""
    result_len: int = 0
    state: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class SubAgentDoneEvent:
    """子智能体已完成执行。

    Payload:
        parent_call_id: str — 指向父级工具调用。
        blueprint_id: str — 蓝图标识。
        success: bool — 子智能体是否成功完成。
        result_len: int — 结果文本长度。
        error: str | None — 失败时的错误消息。
    """
    event_type: str = "sub_agent_done"
    parent_call_id: str = ""
    blueprint_id: str = ""
    success: bool = True
    result_len: int = 0
    error: str | None = None


# ─── 事件类型常量（供 emit 调用使用）─────────────────────────

SUB_AGENT_START = "sub_agent_start"
SUB_AGENT_TOOL_CALL = "sub_agent_tool_call"
SUB_AGENT_TOOL_RESULT = "sub_agent_tool_result"
SUB_AGENT_DONE = "sub_agent_done"

# 所有已知事件类型，用于校验和文档
ALL_EVENT_TYPES: list[str] = [
    "thinking",
    "reasoning",
    "tool_call",
    "tool_result",
    "done",
    "approval_required",
    SUB_AGENT_START,
    SUB_AGENT_TOOL_CALL,
    SUB_AGENT_TOOL_RESULT,
    SUB_AGENT_DONE,
]

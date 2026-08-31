"""聊天会话与消息处理的 API 路由。

消息以完整的 ``UserMsg`` / ``AssistantMsg`` JSON 信封格式存储。
"""

# 处理 sse 事件流的函数没有使用定义的 schemas，需要重新设计

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import session_scope
from app.models.base import get_db
from app.orchestrator.orchestrator import Orchestrator
from app.repositories import ConversationRepository
from app.repositories.pending_approval_repo import PendingApprovalRepository
from app.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    MessageResponse,
)
from app.tools.run_terminal import is_dangerous_command
from app.utils.workspace import command_workspace_violation, normalize_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# 内存 dict 保留作为同进程快速路径；DB 为持久化真实来源。
# 重启后内存丢失但 DB 状态仍可被 /approve 端点更新。
# 在单 worker SQLite 部署中，内存 Event 提供亚秒级响应；DB 轮询作为
# 兜底保证跨重启/多进程场景下审批状态不丢失。
_pending_approvals: dict[str, dict] = {}

# Worker 轮询 DB 审批状态的间隔（秒）。
_APPROVAL_POLL_INTERVAL: float = 1.5
# 等待审批决策的总超时时间。
_APPROVAL_TIMEOUT: float = 120.0

# 项目根目录：从 app/api/ 向上 4 级 → assistant/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_AUTO_TITLE_PLACEHOLDERS = {"", "新会话", "New Chat"}
_STREAM_EVENT_LIMIT = 500
_STREAM_RETAIN_SECONDS = 300
_conversation_streams: dict[int, dict[str, Any]] = {}


def _prune_conversation_streams() -> None:
    now = time.time()
    stale_ids = [
        conversation_id
        for conversation_id, state in _conversation_streams.items()
        if not state.get("active") and now - state.get("updated_at", now) > _STREAM_RETAIN_SECONDS
    ]
    for conversation_id in stale_ids:
        _conversation_streams.pop(conversation_id, None)


def _start_conversation_stream(conversation_id: int) -> None:
    _prune_conversation_streams()
    _conversation_streams[conversation_id] = {
        "active": True,
        "seq": 0,
        "events": deque(maxlen=_STREAM_EVENT_LIMIT),
        "subscribers": set(),
        "updated_at": time.time(),
    }


def _publish_conversation_event(conversation_id: int, event_type: str, data: dict) -> None:
    state = _conversation_streams.get(conversation_id)
    if state is None:
        _start_conversation_stream(conversation_id)
        state = _conversation_streams[conversation_id]

    state["seq"] += 1
    state["updated_at"] = time.time()
    item = {
        "seq": state["seq"],
        "event": event_type,
        "data": data,
    }
    state["events"].append(item)

    if event_type in {"done", "error"}:
        state["active"] = False

    for queue in list(state["subscribers"]):
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            state["subscribers"].discard(queue)


def _resolve_model_name(model_id: str | None) -> str:
    """从 DB 查询实际的模型名称（如 'deepseek-v4-flash'）。

    使用单个 DB 会话完成「活跃模型」和「特定模型」两种查询。
    """
    from app.repositories.model_config_repo import ModelConfigRepository

    try:
        with session_scope() as db:
            repo = ModelConfigRepository(db)
            if not model_id:
                # 查询当前活跃模型
                active = repo.get_active()
                if active:
                    return active.model_id
                return ""
            # 按 uid 或数字 id 查询
            cfg = repo.find_by_uid(model_id)
            if not cfg and model_id.isdigit():
                cfg = repo.find_by_id(int(model_id))
            if cfg:
                return cfg.model_id
    except Exception:
        pass
    return model_id or ""


class ApproveRequest(BaseModel):
    request_id: str
    approved: bool


# ── 会话 CRUD ──────────────────────────────────────────────


@router.get("/conversations", response_model=List[ConversationResponse])
def list_conversations(response: Response, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    total = repo.count_all()
    response.headers["X-Total-Count"] = str(total)
    return repo.find_all(skip=skip, limit=limit)


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    try:
        return repo.create(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    from app.models.message import Message

    repo = ConversationRepository(db)
    conv = repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    repo.delete(conversation_id)
    return None


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(conversation_id: int, data: ConversationUpdate,
                        db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    conv = repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.title = data.title
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}/messages",
            response_model=List[MessageResponse])
def list_messages(conversation_id: int, response: Response, skip: int = 0,
                  limit: int = 100, db: Session = Depends(get_db)):
    repo = ConversationRepository(db)
    conv = repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    total = repo.count_messages(conversation_id)
    response.headers["X-Total-Count"] = str(total)
    return repo.find_messages(conversation_id, skip=skip, limit=limit)


# ── SSE 辅助函数 ────────────────────────────────────────────────────


def _json_safe(value: Any) -> Any:
    """将无法 JSON 编码的值转换为安全占位值。"""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return f"<non-serializable:{type(value).__name__}>"


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_json_safe(data), ensure_ascii=False)}\n\n"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return uuid.uuid4().hex


def _should_auto_generate_title(title: str | None, existing_message_count: int) -> bool:
    """只为尚未编辑过的空会话自动生成标题。"""
    return existing_message_count == 0 and (title or "").strip() in _AUTO_TITLE_PLACEHOLDERS


# ── 聊天发送（SSE 流式） ───────────────────────────────────────


@router.post("/chat/send")
async def chat_send(request: ChatRequest, db: Session = Depends(get_db)):
    conv_repo = ConversationRepository(db)

    # ── 创建或获取会话 ──
    conversation_id = request.conversation_id
    should_generate_title = False
    if conversation_id is None:
        try:
            conv = conv_repo.create(ConversationCreate(
                title=request.message[:50],
                workspace_root=request.workspace_root,
            ))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        conversation_id = conv.id
        should_generate_title = True
    else:
        conv = conv_repo.find_by_id(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        should_generate_title = _should_auto_generate_title(
            conv.title,
            conv_repo.count_messages(conversation_id),
        )

    effective_workspace_root = normalize_workspace_root(conv.workspace_root)
    turn_index = conv_repo.reserve_turn_index(conversation_id)
    if turn_index is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if should_generate_title:
        from app.orchestrator.orchestrator import generate_title

        async def _set_title():
            """独立的标题生成任务，使用自己的 DB 会话（fire-and-forget）。

            内部使用 session_scope()，因此不依赖外层请求的会话——
            外层会话可能在协程执行时已被关闭。
            """
            title = await generate_title(
                request.message,
                model_id=request.model_id,
            )
            with session_scope() as title_db:
                title_repo = ConversationRepository(title_db)
                title_repo.update(conversation_id, ConversationUpdate(title=title))

        def _title_done_callback(fut: asyncio.Task) -> None:
            """记录 fire-and-forget 标题任务的失败信息。"""
            if fut.cancelled():
                return
            exc = fut.exception()
            if exc is not None:
                logger.exception(
                    "generate_title failed for conversation %d",
                    conversation_id,
                    exc_info=exc,
                )

        title_task = asyncio.create_task(_set_title())
        title_task.add_done_callback(_title_done_callback)

    # ── 构造并持久化用户消息 ──
    session_id = conv.session_id or f"ses_{_uuid()[:20]}"
    user_msg_id = f"msg_{_uuid()[:20]}"
    t_now = _now_ms()

    model_name = _resolve_model_name(request.model_id)

    user_msg = {
        "message": {
            "role": "user",
            "time": {"start": t_now, "end": t_now},
            "agent": "ask",
            "modelID": model_name,
            "providerID": "",
            "variant": "",
            "id": user_msg_id,
            "sessionID": session_id,
        },
        "part": [{
            "type": "text",
            "text": request.message,
            "id": f"prt_{_uuid()[:20]}",
            "sessionID": session_id,
            "messageID": user_msg_id,
        }],
    }
    _user_msg_record = conv_repo.add_message(
        conversation_id,
        "user",
        user_msg,
        turn_index=turn_index,
    )
    _user_msg_db_id: int | None = _user_msg_record.id
    _start_conversation_stream(conversation_id)

    # ── 事件生成器 ──
    async def event_generator():
        # 以下变量必须在 emit 闭包创建前初始化，顺序不可调整 ──────────
        # emit 闭包及 event_callback 读取这些变量；若在闭包定义之后才赋值，
        # 将导致 UnboundLocalError 或读到错误的初始值。
        # session_id 来自外层作用域（event_generator 的闭包），此处显式引用以
        # 表明依赖关系；不可在 emit 定义之后重新赋值。
        _session_id: str = session_id
        event_queue: asyncio.Queue = asyncio.Queue()
        t_start: int = _now_ms()
        # 每轮 iteration 落盘后的 DB message id（按轮次顺序）——
        # `done` 事件的 payload 构造时使用，task 4.3 将替换旧的 `message_id` 字段。
        iteration_msg_ids: list[int] = []
        # ─────────────────────────────────────────────────────────────────

        async def emit(event_type: str, data: dict):
            """只负责将事件入队，不构造 msg_id / prt_id 等 payload 字段。"""
            _publish_conversation_event(conversation_id, event_type, data)
            await event_queue.put((event_type, data))

        async def _on_event(event_type: str, data: dict):
            """事件预处理：构造 prt_id / messageID 等 payload 字段，再入队。

            此函数作为 event_callback 传给 Orchestrator，承担 payload 构造
            职责；emit 本身只做入队操作。
            """
            nonlocal t_start

            # ── runtime 的 "done" 事件：吞掉不转发 ──
            # runtime.execute() 在每次返回前会 emit 一次 `done` 作为内部
            # "完成" 信号（历史行为）。自 task 4.3 起，SSE 的最终 `done`
            # 事件由 event_generator 末尾统一发射，payload 含
            # {conversation_id, message_ids, token_usage}，不再由 runtime
            # 的 `{"result": reply_text}` 主导。若此处转发 runtime 的 done，
            # 会产生两条 `event: done`，前端（及测试）只会看到第一条的
            # `{"result": ...}`，拿不到 conversation_id / message_ids。
            if event_type == "done":
                return

            # ── iteration_done: 每轮 LLM 调用结束时 runtime 推送该轮完整 parts ──
            # 立即构造 AssistantMsg envelope 并落盘一条 DB 记录；然后通过 SSE
            # 将 {message_id, msg} 推给前端，前端据此追加一条独立的 assistant 块。
            # （需求 2.1 / 2.2 / 2.5）
            if event_type == "iteration_done":
                # 该轮独立的 msg_id / 时间戳
                iter_msg_id = f"msg_{_uuid()[:20]}"
                t_end = _now_ms()

                # parts：为 runtime 产出的 part 补全 id / sessionID / messageID
                iter_parts: list[dict] = []
                for p in data.get("parts", []):
                    prt_id = f"prt_{_uuid()[:20]}"
                    part = {
                        **p,
                        "id": prt_id,
                        "sessionID": _session_id,
                        "messageID": iter_msg_id,
                    }
                    iter_parts.append(part)

                workspace_path = {
                    "cwd": effective_workspace_root,
                    "root": effective_workspace_root,
                }

                iter_assistant_msg = {
                    "message": {
                        "parentID": user_msg_id,
                        "role": "assistant",
                        "mode": model_name,
                        "agent": "ask",
                        "variant": "",
                        "path": workspace_path,
                        "cost": 0.0,
                        # token usage 由最终 `done` 事件汇总；单轮记录 token 先置 0.
                        "token": {
                            "total": 0, "input": 0, "output": 0,
                            "reasoning": 0, "cache": {},
                        },
                        "modelID": request.model_id or "",
                        "providerID": "",
                        "time": {"start": t_start, "end": t_end},
                        "finish": "tool_use" if data.get("has_tool_calls") else "stop",
                        "id": iter_msg_id,
                        "sessionID": _session_id,
                    },
                    "parts": iter_parts,
                }

                # 立即落盘该轮 AssistantMsg——整轮对话每轮都有独立 DB 记录，
                # 即便后续 iteration 中断也不会丢失已产出的内容。
                msg_record = conv_repo.add_message(
                    conversation_id,
                    "assistant",
                    iter_assistant_msg,
                    turn_index=turn_index,
                )
                iteration_msg_ids.append(msg_record.id)

                # SSE 推送给前端：payload 含 message_id + 完整 msg envelope
                await emit("iteration_done", {
                    "message_id": msg_record.id,
                    "msg": iter_assistant_msg,
                })

                # 为下一轮准备独立的时间窗口起点
                t_start = _now_ms()
                return

            await emit(event_type, data)

        # 审批回调 — 持久化到 DB，同进程走内存快速路径
        async def approval_callback(tool_name: str, tool_args: dict) -> bool:
            if tool_name == "run_terminal":
                command = tool_args.get("command", "")
                cwd = tool_args.get("cwd")
                workspace_violation = command_workspace_violation(
                    command,
                    effective_workspace_root,
                    cwd if isinstance(cwd, str) else None,
                )
                if command and not is_dangerous_command(command) and not workspace_violation:
                    return True
                if workspace_violation:
                    tool_args = {
                        **tool_args,
                        "_workspace_root": effective_workspace_root,
                        "_workspace_violation": workspace_violation,
                    }

            request_id = str(uuid.uuid4())
            expire_at = datetime.now(timezone.utc) + timedelta(seconds=_APPROVAL_TIMEOUT)

            # ── 持久化到 DB（真实来源） ──
            with session_scope() as approval_db:
                approval_repo = PendingApprovalRepository(approval_db)
                approval_repo.create(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    tool_name=tool_name,
                    args_json=json.dumps(tool_args, ensure_ascii=False),
                    expire_at=expire_at,
                )

            # ── 内存快速路径（同进程优化） ──
            event = asyncio.Event()
            _pending_approvals[request_id] = {"event": event, "approved": False}

            try:
                await emit("approval_required", {
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                })

                # ── 轮询循环：同时检查内存事件和 DB 状态 ──
                # 谁先触发谁胜出。
                deadline = time.time() + _APPROVAL_TIMEOUT
                while time.time() < deadline:
                    # 快速路径：同进程内 /approve 设置的内存事件
                    if event.is_set():
                        return _pending_approvals.get(request_id, {}).get("approved", False)

                    # DB 轮询：检查 /approve 是否更新了行（覆盖重启场景）
                    with session_scope() as poll_db:
                        poll_repo = PendingApprovalRepository(poll_db)
                        row = poll_repo.get(request_id)
                        if row and row.status == "approved":
                            return True
                        if row and row.status == "denied":
                            return False
                        if row and row.status == "expired":
                            return False

                    await asyncio.sleep(_APPROVAL_POLL_INTERVAL)

                # ── 超时：在 DB 中标记为已过期 ──
                with session_scope() as expire_db:
                    expire_repo = PendingApprovalRepository(expire_db)
                    expire_repo.update_status(request_id, "expired")
                return False
            finally:
                _pending_approvals.pop(request_id, None)

        orchestrator = Orchestrator()
        reply_text = ""
        token_usage: dict = {}

        async def run_chat():
            nonlocal reply_text, token_usage
            try:
                reply_text, token_usage = await orchestrator.chat(
                    message=request.message,
                    conversation_id=conversation_id,
                    approval_callback=approval_callback,
                    event_callback=_on_event,
                    model_id=request.model_id,
                    user_msg_db_id=_user_msg_db_id,
                    workspace_root=effective_workspace_root,
                )
            except Exception as e:
                logger.exception("Chat execution error")
                await emit("error", {"message": str(e)})
            finally:
                # `done` 必须由后台聊天任务发布，不能依赖响应迭代器尾部。
                # 浏览器刷新会取消原 StreamingResponse 迭代器，但后台任务
                # 仍可能继续运行；恢复订阅者仍需要最终事件。
                await emit("done", {
                    "conversation_id": conversation_id,
                    "message_ids": iteration_msg_ids,
                    "token_usage": token_usage,
                })
                await event_queue.put(None)

        task = asyncio.create_task(run_chat())

        while True:
            item = await event_queue.get()
            if item is None:
                break
            event_type, data = item
            yield _sse_event(event_type, data)

        await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations/{conversation_id}/events")
def stream_conversation_events(
    conversation_id: int,
    after: int = 0,
    db: Session = Depends(get_db),
):
    repo = ConversationRepository(db)
    conv = repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async def event_generator():
        state = _conversation_streams.get(conversation_id)
        if state is None:
            yield _sse_event("done", {
                "conversation_id": conversation_id,
                "message_ids": [],
                "token_usage": {},
                "recovered": False,
            })
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=_STREAM_EVENT_LIMIT)
        state["subscribers"].add(queue)
        try:
            for item in list(state["events"]):
                if item["seq"] > after:
                    yield _sse_event(item["event"], item["data"])

            if not state.get("active"):
                return

            while True:
                item = await queue.get()
                yield _sse_event(item["event"], item["data"])
                if item["event"] in {"done", "error"}:
                    return
        finally:
            state["subscribers"].discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 审批端点 ───────────────────────────────────────────────


@router.post("/chat/approve")
async def chat_approve(data: ApproveRequest):
    new_status = "approved" if data.approved else "denied"

    # ── 更新 DB（权威数据源） ──
    with session_scope() as approve_db:
        approve_repo = PendingApprovalRepository(approve_db)
        row = approve_repo.get(data.request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="审批请求不存在或已过期")
        if row.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"审批请求已处理，当前状态: {row.status}",
            )
        approve_repo.update_status(data.request_id, new_status)

    # ── 快速路径：如果 Worker 仍在同进程，设置内存事件 ──
    entry = _pending_approvals.get(data.request_id)
    if entry is not None:
        entry["approved"] = data.approved
        entry["event"].set()

    return {"request_id": data.request_id, "approved": data.approved}

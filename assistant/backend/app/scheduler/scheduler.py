"""Scheduler — 集成 APScheduler 执行 cron 和一次性任务。"""

import logging
import time
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.database import session_scope
from app.repositories import TaskRepository, TaskRunRepository
from app.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _now_ms() -> int:
    """Unix 毫秒时间戳，与 api/chat.py 的约定一致。"""
    return int(time.time() * 1000)


def _short_uuid() -> str:
    return uuid.uuid4().hex[:20]


class SchedulerManager:
    """使用 APScheduler 管理定时任务。"""

    def __init__(self, orchestrator: Orchestrator | None = None):
        self.scheduler = self._new_scheduler()
        self._orchestrator = orchestrator or Orchestrator()

    def _new_scheduler(self) -> AsyncIOScheduler:
        """在 start() 时创建绑定到当前事件循环的调度器。"""
        return AsyncIOScheduler(timezone=_LOCAL_TZ)

    def start(self):
        if self.scheduler.state == STATE_RUNNING:
            logger.info("Scheduler already running")
            return
        if self.scheduler.state != STATE_STOPPED:
            self.scheduler = self._new_scheduler()
        self._load_tasks()
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        if self.scheduler.state == STATE_STOPPED:
            logger.info("Scheduler already stopped")
            return
        self.scheduler.shutdown(wait=False)
        self.scheduler = self._new_scheduler()
        logger.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # 公共调度 API（由任务 CRUD 端点调用）
    # ------------------------------------------------------------------

    def schedule_task(self, task):
        """调度或重新调度单个任务；如果旧 job 存在则先移除。"""
        try:
            self.scheduler.remove_job(task.task_id, jobstore="default")
        except Exception:
            pass  # job 可能尚不存在
        if not task.enabled:
            return
        try:
            if task.cron_expr:
                self._schedule_cron(task)
            elif task.run_at:
                now = datetime.now(timezone.utc)
                run_at = task.run_at.replace(tzinfo=timezone.utc) if task.run_at.tzinfo is None else task.run_at
                if run_at > now:
                    self._schedule_one_shot(task)
        except Exception:
            logger.warning("Failed to schedule task '%s'", task.task_id, exc_info=True)

    def unschedule_task(self, task_id: str):
        """从调度器中移除任务。"""
        try:
            self.scheduler.remove_job(task_id, jobstore="default")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 任务加载
    # ------------------------------------------------------------------

    def _load_tasks(self):
        with session_scope() as db:
            try:
                repo = TaskRepository(db)
                tasks = [t for t in repo.find_all(limit=500) if t.enabled]
                for task in tasks:
                    if task.cron_expr:
                        self._schedule_cron(task)
                    elif task.run_at:
                        # 只调度未来的一次性任务
                        now = datetime.now(timezone.utc)
                        run_at = task.run_at.replace(tzinfo=timezone.utc) if task.run_at.tzinfo is None else task.run_at
                        if run_at > now:
                            self._schedule_one_shot(task)
                logger.info("Loaded %d scheduled task(s)", len(tasks))
            except Exception as e:
                logger.exception("Failed to load scheduled tasks: %s", e)

    def _schedule_cron(self, task):
        try:
            parts = task.cron_expr.strip().split()
            if len(parts) != 5:
                logger.warning("Invalid cron expr for '%s': %s", task.task_id, task.cron_expr)
                return
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
                timezone=_LOCAL_TZ,
            )
            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task.task_id,
                name=task.name,
                replace_existing=True,
                kwargs={"task_id": task.task_id},
            )
            logger.info("Scheduled recurring '%s' with cron: %s", task.name, task.cron_expr)
        except Exception as e:
            logger.exception("Failed to schedule '%s': %s", task.task_id, e)

    def _schedule_one_shot(self, task):
        try:
            run_at = task.run_at.replace(tzinfo=timezone.utc) if task.run_at.tzinfo is None else task.run_at
            trigger = DateTrigger(run_date=run_at)
            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task.task_id,
                name=task.name,
                replace_existing=True,
                kwargs={"task_id": task.task_id},
            )
            logger.info("Scheduled one-shot '%s' at %s", task.name, run_at.isoformat())
        except Exception as e:
            logger.exception("Failed to schedule one-shot '%s': %s", task.task_id, e)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def _execute_task(self, task_id: str):
        """执行任务并记录本次运行。"""
        with session_scope() as db:
            repo = TaskRepository(db)
            task = repo.find_by_task_id(task_id)
            if not task or not task.enabled:
                return
            task_name = task.name
            task_desc = task.description
            is_recurring = task.recurring

        logger.info("Executing task: %s (%s)", task_name, task_id)

        # 创建运行记录
        with session_scope() as db:
            try:
                run_repo = TaskRunRepository(db)
                run = run_repo.create_from_task(task_id)
                run_id = run.id
            except Exception as e:
                logger.exception("Failed to create run record for '%s': %s", task_id, e)
                return

        # 执行
        result_text = ""
        try:
            result = await self._orchestrator.execute_scheduled_task(
                task_name=task_name,
                task_description=task_desc,
            )
            success = result.get("success", False)
            result_text = result.get("result", "") if success else result.get("error", "")
            self._update_run(
                run_id=run_id,
                status="completed" if success else "failed",
                result=result.get("result", ""),
                error=result.get("error"),
                logs=result.get("logs", []),
            )
            logger.info("Task '%s' completed: success=%s", task_name, success)
        except Exception as e:
            logger.exception("Task '%s' execution failed", task_name)
            result_text = str(e)
            self._update_run(run_id=run_id, status="failed", error=result_text, result=result_text)

        # 为所有任务结果创建持久化会话
        try:
            convo_id = self._create_task_conversation(task_name, result_text or "任务完成但无输出内容")
            self._set_run_conversation(run_id, convo_id)
        except Exception as e:
            logger.warning("Failed to create task conversation: %s", e)

        # 执行后禁用非重复任务
        if not is_recurring:
            self.unschedule_task(task_id)
            with session_scope() as db:
                try:
                    task = TaskRepository(db).find_by_task_id(task_id)
                    if task:
                        task.enabled = False
                        logger.info("Disabled non-recurring task '%s'", task_id)
                except Exception as e:
                    logger.warning("Failed to disable task: %s", e)

    # ------------------------------------------------------------------
    # 手动执行
    # ------------------------------------------------------------------

    async def run_task_manually(self, task_id: str) -> dict:
        with session_scope() as db:
            repo = TaskRepository(db)
            task = repo.find_by_task_id(task_id)
            if not task:
                return {"success": False, "error": f"Task '{task_id}' not found"}
            task_name = task.name
            task_desc = task.description
            is_recurring = task.recurring

        with session_scope() as db:
            run_repo = TaskRunRepository(db)
            run = run_repo.create_from_task(task_id)
            run_id = run.id

        result_text = ""
        try:
            result = await self._orchestrator.execute_scheduled_task(
                task_name=task_name,
                task_description=task_desc,
            )
            success = result.get("success", False)
            result_text = result.get("result", "") if success else result.get("error", "")
            self._update_run(
                run_id=run_id,
                status="completed" if success else "failed",
                result=result.get("result", ""),
                error=result.get("error"),
                logs=result.get("logs", []),
            )
            # 为所有结果创建会话
            try:
                convo_id = self._create_task_conversation(task_name, result_text or "任务完成但无输出内容")
                self._set_run_conversation(run_id, convo_id)
            except Exception as e:
                logger.warning("Failed to create task conversation: %s", e)
            if not is_recurring:
                self.unschedule_task(task_id)
                with session_scope() as db:
                    try:
                        t = TaskRepository(db).find_by_task_id(task_id)
                        if t:
                            t.enabled = False
                    except Exception:
                        pass
            return result
        except Exception as e:
            result_text = str(e)
            self._update_run(run_id=run_id, status="failed", error=result_text, result=result_text)
            try:
                convo_id = self._create_task_conversation(task_name, result_text)
                self._set_run_conversation(run_id, convo_id)
            except Exception as ex:
                logger.warning("Failed to create task conversation: %s", ex)
            return {"success": False, "error": result_text}

    # ------------------------------------------------------------------
    # 持久化辅助函数
    # ------------------------------------------------------------------

    def _create_task_conversation(self, task_name: str, result_text: str) -> int:
        """为任务结果创建会话，并返回会话 ID。

        通过三参数仓储签名 ``add_message(conversation_id, msg_type, msg_json)``
        写入一条符合 AssistantMsg schema（见 schemas/message.py）的 assistant 消息。
        定时任务产生的 ``result_text`` 会包装成 ``parts`` 里的 ``TextPart``；
        ``task_result=True`` 会作为 ``msg_json`` 顶层标记挂载
        （位于 AssistantMsg envelope 外），因此 ``messages`` 表仍保持
        ``msg_type`` / ``msg_json`` 两列形态。
        """
        from app.repositories import ConversationRepository
        from app.schemas import ConversationCreate

        with session_scope() as db:
            repo = ConversationRepository(db)
            conv = repo.create(ConversationCreate(title=f"[任务] {task_name}", source="task"))

            session_id = conv.session_id or f"ses_{_short_uuid()}"
            assistant_msg_id = f"msg_{_short_uuid()}"
            t_now = _now_ms()

            text_part = {
                "type": "text",
                "text": result_text,
                "id": f"prt_{_short_uuid()}",
                "sessionID": session_id,
                "messageID": assistant_msg_id,
            }

            # AssistantMsg 信封。字段语义：
            # mode=模型名，agent="ask"，variant=思考强度。定时任务没有用户可见的
            # 模型/思考模式选择，因此 mode/variant 保持空字符串，同时 agent 仍为
            # "ask"（默认 agent）。
            assistant_msg = {
                "message": {
                    "parentID": "",
                    "role": "assistant",
                    "mode": "",
                    "agent": "ask",
                    "variant": "",
                    "path": {},
                    "cost": 0.0,
                    "token": {
                        "total": 0,
                        "input": 0,
                        "output": 0,
                        "reasoning": 0,
                        "cache": {},
                    },
                    "modelID": "",
                    "providerID": "",
                    "time": {"start": t_now, "end": t_now},
                    "finish": "stop",
                    "id": assistant_msg_id,
                    "sessionID": session_id,
                },
                "parts": [text_part],
                # 调度器专属标记，位于 AssistantMsg 信封外部；
                # 下游 Pydantic 校验会忽略未知顶层字段，因此仍会接受这个 envelope。
                "task_result": True,
            }

            repo.add_message(conv.id, "assistant", assistant_msg)
            return conv.id

    def _set_run_conversation(self, run_id: int, conversation_id: int):
        with session_scope() as db:
            try:
                from app.repositories import TaskRunRepository
                run = TaskRunRepository(db).find_by_id(run_id)
                if run:
                    run.conversation_id = conversation_id
            except Exception as e:
                logger.warning("Failed to set conversation_id on run: %s", e)

    # ------------------------------------------------------------------
    # 辅助函数
    # ------------------------------------------------------------------

    def _update_run(self, run_id: int, status: str, result: str = "", error: str | None = None, logs: list[str] | None = None):
        with session_scope() as db:
            try:
                repo = TaskRunRepository(db)
                run = repo.find_by_id(run_id)
                if not run:
                    return
                run.status = status
                run.finished_at = datetime.now(timezone.utc)
                if result:
                    run.result = result[:5000]
                if error is not None:
                    run.error = error
                if logs is not None:
                    run.logs = logs
            except Exception as e:
                logger.exception("Failed to update run record '%s': %s", run_id, e)


scheduler_manager = SchedulerManager()

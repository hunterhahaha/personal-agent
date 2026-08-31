from datetime import datetime, timezone
from typing import Optional


from pydantic import BaseModel, field_serializer


class TaskCreate(BaseModel):
    task_id: str
    name: str
    description: str = ""
    enabled: bool = True
    cron_expr: Optional[str] = None
    run_at: Optional[datetime] = None
    recurring: bool = False


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    cron_expr: Optional[str] = None
    run_at: Optional[datetime] = None
    recurring: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    task_id: str
    name: str
    description: str
    enabled: bool
    cron_expr: Optional[str] = None
    run_at: Optional[datetime] = None
    recurring: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

# 为了契合 UserMsg 和 AssistantMsg ，需要重新设计
class TaskRunResponse(BaseModel):
    id: int
    task_id: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    logs: list = []
    conversation_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("started_at", "finished_at", "created_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

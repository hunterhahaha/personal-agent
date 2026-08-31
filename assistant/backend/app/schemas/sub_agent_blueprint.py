"""SubAgentBlueprint 的 Pydantic schemas。"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, field_serializer


class SubAgentBlueprintCreate(BaseModel):
    blueprint_id: str
    name: str
    description: str = ""
    enabled: bool = True
    tool_ids: list[str] = []
    prompt_template_ids: list[str] = []
    input_schema: dict = {}
    output_schema: dict = {}
    memory_policy_id: Optional[str] = None
    tags: list[str] = []


class SubAgentBlueprintUpdate(BaseModel):
    blueprint_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    tool_ids: Optional[list[str]] = None
    prompt_template_ids: Optional[list[str]] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    memory_policy_id: Optional[str] = None
    tags: Optional[list[str]] = None


class SubAgentBlueprintResponse(BaseModel):
    id: int
    blueprint_id: str
    name: str
    description: str
    enabled: bool
    tool_ids: list[str]
    prompt_template_ids: list[str]
    input_schema: dict
    output_schema: dict
    memory_policy_id: Optional[str] = None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ToolCreate(BaseModel):
    tool_id: str
    name: str
    description: str = ""
    category: str = "general"
    enabled: bool = True
    provider: str
    input_schema: dict = {}
    output_schema: dict = {}
    config: dict = {}
    tags: list[str] = []


class ToolUpdate(BaseModel):
    tool_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    config: Optional[dict] = None
    tags: Optional[list[str]] = None


class ToolResponse(BaseModel):
    id: int
    tool_id: str
    name: str
    description: str
    category: str
    enabled: bool
    provider: str
    source: str = "builtin"
    input_schema: dict
    output_schema: dict
    config: dict
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}



from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# 草稿部分的字段需要重新设计
class PromptTemplateCreate(BaseModel):
    prompt_id: str
    name: str
    type: str = "system"
    version: str = "1.0"
    enabled: bool = True
    created_by: str
    description: str = ""
    content: str = ""
    draft_content: Optional[str] = None
    metadata_json: dict = {}


class PromptTemplateUpdate(BaseModel):
    prompt_id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    version: Optional[str] = None
    enabled: Optional[bool] = None
    created_by: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    draft_content: Optional[str] = None
    metadata_json: Optional[dict] = None


class PromptTemplateResponse(BaseModel):
    id: int
    prompt_id: str
    name: str
    type: str
    version: str
    enabled: bool
    created_by: str
    description: str
    content: str
    draft_content: Optional[str] = None
    version_history: Optional[list] = None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftSaveRequest(BaseModel):
    draft_content: str


class PublishRequest(BaseModel):
    draft_content: Optional[str] = None

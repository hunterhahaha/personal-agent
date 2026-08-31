from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class MemoryCreate(BaseModel):
    memory_id: str
    memory_type: Literal["profile"]
    scope: str
    title: str
    content: str
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    inferred: bool = False
    confidence: Optional[float] = None
    tags: list[str] = []
    metadata_json: dict = {}


class MemoryResponse(BaseModel):
    id: int
    memory_id: str
    memory_type: Literal["profile"]
    scope: str
    title: str
    content: str
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    inferred: bool
    confidence: Optional[float] = None
    tags: list[str]
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

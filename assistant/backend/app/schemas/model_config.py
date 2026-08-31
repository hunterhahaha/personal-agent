"""模型配置的 Pydantic schemas。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ModelConfigCreate(BaseModel):
    model_id: str = Field(..., description="模型标识（如 deepseek-chat）")
    name: str = Field(..., description="显示名称")
    base_url: str = Field(..., description="API 地址")
    api_key: str = Field(..., description="API 密钥")


class ModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    model_id: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None

class ModelConfigResponse(BaseModel):
    id: int
    uid: str
    model_id: str
    name: str
    base_url: str
    api_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

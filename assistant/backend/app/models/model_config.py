"""模型配置：保存用户配置的 LLM 模型设置。"""

from sqlalchemy import Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

class ModelConfig(Base):
    __tablename__ = "model_configs"

    uid: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    thinking_modes: Mapped[dict] = mapped_column(JSON, default=lambda: {"options": [{"id": "high", "label": "high"}, {"id": "max", "label": "max"}], "parameter": "reasoning_effort"}, nullable=False)

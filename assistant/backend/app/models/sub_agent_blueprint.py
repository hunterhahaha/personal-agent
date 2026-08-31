"""SubAgentBlueprint 模型：专用子智能体的组装规格。"""

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 蓝图类（需要重写）
class SubAgentBlueprint(Base):
    """运行时构造子智能体所用的蓝图。

    将 tool_ids、prompt_template_ids、schemas 和记忆策略打包成可复用的子智能体组装模板。
    """

    __tablename__ = "sub_agent_blueprints"

    blueprint_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tool_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    prompt_template_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    memory_policy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

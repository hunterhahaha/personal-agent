"""用于加载和查找 Tool 实体的注册表。

每次调用 ``load_all`` 时，都会从 ``app/tools/*.py`` 自动发现工具；
新的工具文件会自动注册到数据库。
"""

import importlib
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.tool import Tool
from app.registries.base import BaseRegistry

logger = logging.getLogger(__name__)

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
_DELETED_BUILTIN_TOOL_IDS = {"get_workspace_info", "run_read", "run_write"}


def _discover_tool_definitions() -> list[dict]:
    """扫描 tools 目录，查找导出 ``TOOL_DEFINITION`` 的 Python 模块。

    返回已发现工具文件中的 ``TOOL_DEFINITION`` 字典列表。
    文件名以 ``_`` 开头的文件（例如 ``__init__``）会被跳过。
    """
    defs: list[dict] = []
    for path in sorted(_TOOLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = path.stem
        try:
            mod = importlib.import_module(f"app.tools.{module_name}")
        except Exception:
            logger.warning("Failed to import tool module %s", path.name, exc_info=True)
            continue
        td = getattr(mod, "TOOL_DEFINITION", None)
        if not td or not td.get("name"):
            logger.debug("Skipping %s: no TOOL_DEFINITION with a name", path.name)
            continue
        defs.append(td)
    return defs


def _sync_tools_to_db(db: Session) -> None:
    """将发现的工具 upsert 到数据库。

    - 新工具（按 ``tool_id`` 判断）会以 ``source='builtin'`` 插入。
    - 已存在工具会根据模块定义更新 ``name``、``description`` 和
      ``input_schema``；其他字段（``enabled``、``config``、``provider``、
      ``tags``、``category``）保持不变。
    - 数据库中存在但磁盘上缺失的内置工具会标记为 ``enabled=False``；
      已明确废弃的内置工具会从数据库删除。
    - ``source='user'`` 的工具不会被这个同步流程改动。
    """
    repo = ToolRepository(db)
    disk_tool_ids: set[str] = set()

    for td in _discover_tool_definitions():
        tool_id = td["name"]
        disk_tool_ids.add(tool_id)
        existing = repo.find_by_tool_id(tool_id)
        if existing:
            existing.name = td.get("name", existing.name)
            existing.description = td.get("description", existing.description)
            existing.input_schema = td.get("input_schema", existing.input_schema)
            existing.source = "builtin"
            # 如果之前因磁盘缺失而被禁用，则重新启用
            if not existing.enabled and existing.source == "builtin":
                existing.enabled = True
        else:
            db.add(
                Tool(
                    tool_id=tool_id,
                    name=td.get("name", tool_id),
                    description=td.get("description", ""),
                    category="general",
                    enabled=True,
                    provider="builtin",
                    source="builtin",
                    input_schema=td.get("input_schema", {}),
                    output_schema={},
                    tags=[],
                )
            )
            logger.info("Auto-registered new tool: %s", tool_id)

    # 将磁盘上缺失的内置工具标记为禁用
    all_tools = db.query(Tool).all()
    for tool in all_tools:
        if tool.source == "builtin" and tool.tool_id not in disk_tool_ids:
            if tool.tool_id in _DELETED_BUILTIN_TOOL_IDS:
                db.delete(tool)
                logger.info("Deleted removed builtin tool: %s", tool.tool_id)
                continue
            if tool.enabled:
                tool.enabled = False
                logger.info("Disabled missing builtin tool: %s", tool.tool_id)

    db.commit()


class ToolRegistry(BaseRegistry["Tool"]):
    """以 tool_id 为键的 Tool 实体内存缓存。

    覆盖 ``load_all``，先扫描文件系统中新建或更新的工具模块；
    这样只要向 ``app/tools/`` 添加文件，下次聊天调用时工具就可用。
    """

    _id_attr = "tool_id"

    def _get_repo(self, db: Session) -> "ToolRepository":
        return ToolRepository(db)

    def load_all(self, db: Session) -> None:
        _sync_tools_to_db(db)
        super().load_all(db)


# 延迟导入，避免模块级循环依赖
from app.repositories.tool_repo import ToolRepository  # noqa: E402

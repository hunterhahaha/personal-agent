"""共享实体解析辅助函数：把字符串或整数 ID 解析为数据库实体。"""

from typing import Any


def resolve_entity(repo: Any, entity_id: str) -> Any | None:
    """优先按字符串 ID 查找实体，然后回退到整数 ID。

    找到时返回实体；找不到时返回 ``None``。
    """
    # 优先尝试基于字符串的查找
    if hasattr(repo, "find_by_tool_id"):
        entity = repo.find_by_tool_id(entity_id)
    elif hasattr(repo, "find_by_task_id"):
        entity = repo.find_by_task_id(entity_id)
    else:
        entity = None

    if entity is not None:
        return entity

    # 回退到整数 ID
    try:
        return repo.find_by_id(int(entity_id))
    except (ValueError, TypeError):
        return None

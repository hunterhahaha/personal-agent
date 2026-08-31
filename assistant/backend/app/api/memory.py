"""用户画像记忆管理 API 路由。"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.memory.manager import MemoryManager

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="简短标题")
    content: str = Field(..., min_length=1, description="记忆内容")


class MemoryItem(BaseModel):
    id: int
    title: str
    content: str
    created_at: str
    inferred: Optional[bool] = None
    confidence: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


def _memory_to_item(m) -> MemoryItem:
    return MemoryItem(
        id=m.id,
        title=m.title,
        content=m.content,
        created_at=m.created_at.isoformat() + "Z" if hasattr(m, "created_at") and m.created_at else "",
        inferred=getattr(m, "inferred", None),
        confidence=getattr(m, "confidence", None),
    )


@router.get("", response_model=List[MemoryItem])
def list_memories(db: Session = Depends(get_db)):
    """返回所有 profile 类型记忆（最新在前），包含 inferred 和 confidence 字段。"""
    manager = MemoryManager(db)
    records = manager.list_profiles(limit=200)
    return [_memory_to_item(m) for m in records]


@router.post("", response_model=MemoryItem, status_code=201)
def create_memory(data: MemoryCreateRequest, db: Session = Depends(get_db)):
    """添加新的 profile 记忆。"""
    manager = MemoryManager(db)
    title = data.title.strip()
    content = data.content.strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="title 和 content 不能为空")
    record = manager.add_profile(scope="user", title=title, content=content)
    return _memory_to_item(record)


@router.patch("/{record_id}/confirm", response_model=MemoryItem)
def confirm_memory(record_id: int, db: Session = Depends(get_db)):
    """确认一条推断记忆记录（设置 inferred=False）。"""
    manager = MemoryManager(db)
    result = manager.confirm(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return _memory_to_item(result)


@router.delete("/{record_id}/reject", status_code=204)
def reject_memory(record_id: int, db: Session = Depends(get_db)):
    """拒绝并删除一条推断记忆记录。"""
    manager = MemoryManager(db)
    if not manager.reject(record_id):
        raise HTTPException(status_code=404, detail="记忆不存在或非候选记忆")
    return None


@router.delete("/{record_id}", status_code=204)
def delete_memory(record_id: int, db: Session = Depends(get_db)):
    """按记录 ID 删除记忆。"""
    manager = MemoryManager(db)
    if not manager.delete(record_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return None

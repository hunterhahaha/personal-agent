from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.repositories import ToolRepository
from app.schemas import ToolCreate, ToolUpdate, ToolResponse
from app.utils.entity_resolver import resolve_entity

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=List[ToolResponse])
def list_tools(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    repo = ToolRepository(db)
    return repo.find_all(skip, limit)


@router.get("/{tool_id}", response_model=ToolResponse)
def get_tool(tool_id: str, db: Session = Depends(get_db)):
    repo = ToolRepository(db)
    tool = resolve_entity(repo, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.post("", response_model=ToolResponse, status_code=201)
def create_tool(data: ToolCreate, db: Session = Depends(get_db)):
    repo = ToolRepository(db)
    # 检查重复的 tool_id
    if repo.find_by_tool_id(data.tool_id):
        raise HTTPException(
            status_code=409,
            detail=f"Tool with tool_id '{data.tool_id}' already exists",
        )
    return repo.create(data)


@router.put("/{tool_id}", response_model=ToolResponse)
def update_tool(tool_id: str, data: ToolUpdate, db: Session = Depends(get_db)):
    repo = ToolRepository(db)
    tool = repo.find_by_tool_id(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return repo.update(tool.id, data)


@router.post("/{tool_id}/toggle", response_model=ToolResponse)
def toggle_tool(tool_id: str, db: Session = Depends(get_db)):
    repo = ToolRepository(db)
    tool = repo.find_by_tool_id(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    result = repo.toggle_enabled(tool.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return result

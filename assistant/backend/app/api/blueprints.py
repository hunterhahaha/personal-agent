"""SubAgent Blueprint 增删改查 API 路由。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.repositories import SubAgentBlueprintRepository
from app.schemas import (
    SubAgentBlueprintCreate,
    SubAgentBlueprintUpdate,
    SubAgentBlueprintResponse,
)

router = APIRouter(prefix="/api/blueprints", tags=["blueprints"])


@router.get("", response_model=List[SubAgentBlueprintResponse])
def list_blueprints(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """返回所有子智能体蓝图。"""
    repo = SubAgentBlueprintRepository(db)
    return repo.find_all(skip=skip, limit=limit)


@router.get("/{blueprint_id}", response_model=SubAgentBlueprintResponse)
def get_blueprint(blueprint_id: str, db: Session = Depends(get_db)):
    """根据 blueprint_id 获取单个蓝图。"""
    repo = SubAgentBlueprintRepository(db)
    bp = repo.find_by_blueprint_id(blueprint_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return bp


@router.post("", response_model=SubAgentBlueprintResponse, status_code=201)
def create_blueprint(data: SubAgentBlueprintCreate, db: Session = Depends(get_db)):
    """创建新的子智能体蓝图。"""
    repo = SubAgentBlueprintRepository(db)
    existing = repo.find_by_blueprint_id(data.blueprint_id)
    if existing:
        raise HTTPException(status_code=409, detail="Blueprint with this ID already exists")
    return repo.create(data)


@router.put("/{blueprint_id}", response_model=SubAgentBlueprintResponse)
def update_blueprint(
    blueprint_id: str,
    data: SubAgentBlueprintUpdate,
    db: Session = Depends(get_db),
):
    """更新已有的子智能体蓝图。"""
    repo = SubAgentBlueprintRepository(db)
    bp = repo.find_by_blueprint_id(blueprint_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bp, field, value)
    db.commit()
    db.refresh(bp)
    return bp


@router.delete("/{blueprint_id}", status_code=204)
def delete_blueprint(blueprint_id: str, db: Session = Depends(get_db)):
    """删除子智能体蓝图。"""
    repo = SubAgentBlueprintRepository(db)
    bp = repo.find_by_blueprint_id(blueprint_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    db.delete(bp)
    db.commit()
    return None

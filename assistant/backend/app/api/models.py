"""LLM 模型配置 API 路由。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.repositories.model_config_repo import ModelConfigRepository
from app.schemas.model_config import (
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelConfigResponse,
)

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=List[ModelConfigResponse])
def list_models(db: Session = Depends(get_db)):
    """列出所有已配置模型。"""
    repo = ModelConfigRepository(db)
    return repo.find_all()


@router.post("", response_model=ModelConfigResponse, status_code=201)
def create_model(data: ModelConfigCreate, db: Session = Depends(get_db)):
    """添加新的模型配置，uid 会自动生成。"""
    repo = ModelConfigRepository(db)
    return repo.create(data)


@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: int, db: Session = Depends(get_db)):
    """删除模型配置。"""
    repo = ModelConfigRepository(db)
    if not repo.delete(model_id):
        raise HTTPException(status_code=404, detail="模型不存在")
    return None


@router.put("/{model_id}", response_model=ModelConfigResponse)
def update_model(model_id: int, data: ModelConfigUpdate, db: Session = Depends(get_db)):
    """更新模型配置。"""
    repo = ModelConfigRepository(db)
    model = repo.find_by_id(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    if data.name is not None:
        model.name = data.name
    if data.model_id is not None:
        model.model_id = data.model_id
    if data.base_url is not None:
        model.base_url = data.base_url
    if data.api_key is not None:
        model.api_key = data.api_key
    db.commit()
    db.refresh(model)
    return model


@router.post("/{model_id}/activate", response_model=ModelConfigResponse)
def activate_model(model_id: int, db: Session = Depends(get_db)):
    """将某个模型设为当前激活模型，并停用其他模型。"""
    repo = ModelConfigRepository(db)
    model = repo.set_active(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model

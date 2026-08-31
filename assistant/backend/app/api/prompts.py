"""带版本控制的提示词模板管理 API 路由。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.repositories import PromptTemplateRepository
from app.schemas import (
    DraftSaveRequest,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PublishRequest,
)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

READ_ONLY_TYPES = {"system"}


@router.get("", response_model=List[PromptTemplateResponse])
def list_prompts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    repo = PromptTemplateRepository(db)
    return repo.find_all(skip, limit)


@router.get("/{prompt_id}", response_model=PromptTemplateResponse)
def get_prompt(prompt_id: str, db: Session = Depends(get_db)):
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        try:
            prompt = repo.find_by_id(int(prompt_id))
        except ValueError:
            pass
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("", response_model=PromptTemplateResponse, status_code=201)
def create_prompt(data: PromptTemplateCreate, db: Session = Depends(get_db)):
    repo = PromptTemplateRepository(db)
    if repo.find_by_prompt_id(data.prompt_id):
        raise HTTPException(
            status_code=409,
            detail=f"Prompt with prompt_id '{data.prompt_id}' already exists",
        )
    # 检查所有提示词中的名称唯一性
    existing = repo.find_all()
    if any(p.name == data.name for p in existing):
        raise HTTPException(
            status_code=409,
            detail=f"Prompt with name '{data.name}' already exists",
        )
    return repo.create(data)


@router.put("/{prompt_id}", response_model=PromptTemplateResponse)
def update_prompt(
    prompt_id: str,
    data: PromptTemplateUpdate,
    db: Session = Depends(get_db),
):
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    # 如果正在修改名称，则检查名称唯一性
    if data.name is not None and data.name != prompt.name:
        existing = repo.find_all()
        if any(p.name == data.name and p.id != prompt.id for p in existing):
            raise HTTPException(
                status_code=409,
                detail=f"Prompt with name '{data.name}' already exists",
            )
    return repo.update(prompt.id, data)


@router.post("/{prompt_id}/toggle", response_model=PromptTemplateResponse)
def toggle_prompt(prompt_id: str, db: Session = Depends(get_db)):
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    result = repo.toggle_enabled(prompt.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


@router.post("/{prompt_id}/draft", response_model=PromptTemplateResponse)
def save_draft(
    prompt_id: str,
    data: DraftSaveRequest,
    db: Session = Depends(get_db),
):
    """保存草稿内容，不影响已发布版本。"""
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.type in READ_ONLY_TYPES:
        raise HTTPException(status_code=403, detail="System prompts are read-only")
    return repo.update(prompt.id, PromptTemplateUpdate(draft_content=data.draft_content))


@router.post("/{prompt_id}/publish", response_model=PromptTemplateResponse)
def publish_prompt(
    prompt_id: str,
    data: PublishRequest = PublishRequest(),
    db: Session = Depends(get_db),
):
    """发布新版本：当前内容进入历史，草稿变为正文，版本号递增。"""
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.type in READ_ONLY_TYPES:
        raise HTTPException(status_code=403, detail="System prompts are read-only")

    draft = data.draft_content if data.draft_content is not None else prompt.draft_content
    if not draft or not draft.strip():
        raise HTTPException(status_code=400, detail="No draft content to publish")

    # 归档当前版本
    history = list(prompt.version_history or [])
    history.insert(
        0,
        {
            "version": prompt.version,
            "content": prompt.content,
            "created_by": prompt.created_by,
            "created_at": prompt.updated_at.isoformat(),
        },
    )

    # 递增版本号（简单 semver：1.0 → 1.1 → 1.2）
    parts = prompt.version.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    new_version = f"{major}.{minor + 1}"

    prompt.content = draft
    prompt.draft_content = None
    prompt.version = new_version
    prompt.version_history = history
    db.commit()
    db.refresh(prompt)
    return prompt


@router.post("/{prompt_id}/rollback", response_model=PromptTemplateResponse)
def rollback_prompt(prompt_id: str, db: Session = Depends(get_db)):
    """回滚到上一个版本，并丢弃当前版本。"""
    repo = PromptTemplateRepository(db)
    prompt = repo.find_by_prompt_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.type in READ_ONLY_TYPES:
        raise HTTPException(status_code=403, detail="System prompts are read-only")

    history = list(prompt.version_history or [])
    if not history:
        raise HTTPException(status_code=400, detail="No previous version to rollback to")

    prev = history.pop(0)
    prompt.content = prev["content"]
    prompt.version = prev["version"]
    prompt.version_history = history
    db.commit()
    db.refresh(prompt)
    return prompt

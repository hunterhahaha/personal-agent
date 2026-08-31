"""任务管理和按需执行 API 路由。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.repositories import TaskRepository, TaskRunRepository
from app.schemas import TaskCreate, TaskUpdate, TaskResponse, TaskRunResponse
from app.scheduler import scheduler_manager
from app.utils.entity_resolver import resolve_entity

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=List[TaskResponse])
def list_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return TaskRepository(db).find_all(skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    if repo.find_by_task_id(data.task_id):
        raise HTTPException(status_code=409, detail=f"Task '{data.task_id}' already exists")
    task = repo.create(data)
    scheduler_manager.schedule_task(task)
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, data: TaskUpdate, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = repo.update(task.id, data)
    scheduler_manager.schedule_task(updated)
    return updated


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    scheduler_manager.unschedule_task(task.task_id)
    repo.delete(task.id)
    return None


@router.post("/{task_id}/toggle", response_model=TaskResponse)
def toggle_task(task_id: str, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = repo.toggle_enabled(task.id)
    scheduler_manager.schedule_task(result)
    return result


@router.post("/{task_id}/run", response_model=TaskRunResponse)
async def run_task(task_id: str, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await scheduler_manager.run_task_manually(task.task_id)

    run_repo = TaskRunRepository(db)
    latest = run_repo.find_latest_by_task_id(task.task_id)
    if not latest:
        raise HTTPException(status_code=500, detail="Task run failed to create")
    return latest


@router.get("/{task_id}/runs", response_model=List[TaskRunResponse])
def list_task_runs(task_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """返回某个任务的执行历史。"""
    repo = TaskRepository(db)
    task = resolve_entity(repo, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    run_repo = TaskRunRepository(db)
    return run_repo.find_by_task_id(task.task_id, skip=skip, limit=limit)


@router.get("/runs/history", response_model=List[TaskRunResponse])
def list_all_runs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """返回所有任务运行历史。"""
    run_repo = TaskRunRepository(db)
    return run_repo.find_all(skip=skip, limit=limit)

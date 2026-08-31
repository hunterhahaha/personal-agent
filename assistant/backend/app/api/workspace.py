"""工作区相关 API。"""

import asyncio
import logging
import tkinter as tk
from tkinter import filedialog

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.utils.workspace import validate_user_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class SelectFolderResponse(BaseModel):
    path: str | None


@router.post("/select-folder", response_model=SelectFolderResponse)
async def select_folder(request: Request):
    """打开本机原生文件夹选择窗口并返回绝对路径。"""
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="只允许本机请求选择工作区")

    try:
        selected = await asyncio.to_thread(_ask_directory)
    except Exception as exc:
        logger.exception("Failed to open native folder selector")
        raise HTTPException(
            status_code=500,
            detail=f"无法打开文件夹选择窗口: {type(exc).__name__}",
        ) from exc

    if not selected:
        return SelectFolderResponse(path=None)
    try:
        normalized = validate_user_workspace_root(selected)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SelectFolderResponse(path=normalized)


def _ask_directory() -> str | None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(parent=root, title="选择工作区")
        return selected or None
    finally:
        root.destroy()

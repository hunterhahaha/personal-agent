"""Personal AI Assistant 的 FastAPI 应用入口。"""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.database import init_db
from app.api import (
    tools,
    skills,
    blueprints,
    prompts,
    tasks,
    chat,
    memory,
    models,
    workspace,
)
from app.scheduler import scheduler_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化数据库并启动调度器。"""
    logger.info("Starting Personal AI Assistant ...")
    init_db()
    logger.info(f"Database initialized at {settings.database_url}")
    scheduler_manager.start()
    yield
    scheduler_manager.stop()
    logger.info("Shutting down Personal AI Assistant ...")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tools.router)
app.include_router(skills.router)
app.include_router(blueprints.router)
app.include_router(prompts.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(models.router)
app.include_router(workspace.router)


@app.get("/")
def root():
    return {"app": settings.app_name, "version": "1.0.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}

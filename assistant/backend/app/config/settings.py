from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Personal AI Assistant"
    debug: bool = True

    # 数据库
    database_url: str = "sqlite:///./assistant.db"

    # LLM 提供商
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"

    # 搜索
    search_provider: str = "bing"
    tavily_api_key: str = ""
    searxng_base_url: str = "http://localhost:8888"

    # 技能
    skill_source_path: str = ""

    # 历史记录
    history_window: int = 50

    # 压缩转录保留数量（最多保留的转录文件数）
    compact_transcript_retention: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# 便于其他模块导入的常量
HISTORY_WINDOW: int = settings.history_window
COMPACT_TRANSCRIPT_RETENTION: int = settings.compact_transcript_retention

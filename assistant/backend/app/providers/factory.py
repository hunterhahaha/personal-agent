"""Provider 工厂：根据配置集中创建 provider。"""

from app.config.settings import settings
from app.providers.llm.base import BaseLLMProvider
from app.providers.search.base import BaseSearchProvider


def _get_active_model_from_db() -> tuple[str, str, str] | None:
    """返回当前激活模型的 (base_url, api_key, model)。"""
    try:
        from app.database import session_scope
        from app.repositories.model_config_repo import ModelConfigRepository

        with session_scope() as db:
            repo = ModelConfigRepository(db)
            active = repo.get_active()
            if active:
                return active.base_url, active.api_key, active.model_id
            return None
    except Exception:
        return None


def create_llm_provider(model_id: str | None = None) -> BaseLLMProvider:
    """创建 LLM provider，优先使用数据库中的激活模型，而不是 .env 设置。

    参数：
        model_id: 覆盖当前激活模型；为 None 时使用数据库激活模型。
    """
    from app.providers.llm.openai_compatible import OpenAICompatibleProvider

    db_config = _get_active_model_from_db()
    if model_id:
        # 从数据库查找指定模型（按 uid 或数字 id）
        try:
            from app.database import session_scope
            from app.repositories.model_config_repo import ModelConfigRepository
            with session_scope() as db:
                repo = ModelConfigRepository(db)
                cfg = repo.find_by_uid(model_id)
                if not cfg and model_id.isdigit():
                    cfg = repo.find_by_id(int(model_id))
                if cfg:
                    return OpenAICompatibleProvider(
                        base_url=cfg.base_url,
                        api_key=cfg.api_key,
                        model=cfg.model_id,
                    )
        except Exception:
            pass

    if db_config:
        base_url, api_key, model = db_config
        return OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def create_search_provider() -> BaseSearchProvider:
    """根据当前设置创建搜索 provider。

    支持的 provider（通过 ``SEARCH_PROVIDER`` 设置）：
    - ``tavily``：Tavily AI 优化搜索（需要 TAVILY_API_KEY）
    - ``searxng``：自托管 SearXNG 实例（需要 SEARXNG_BASE_URL）
    - ``bing``：Bing HTML 搜索（默认，无需 API key）
    """
    provider_name = settings.search_provider

    if provider_name == "tavily":
        from app.providers.search.tavily import TavilySearchProvider

        return TavilySearchProvider(api_key=settings.tavily_api_key)

    if provider_name == "searxng":
        from app.providers.search.searxng import SearXNGSearchProvider

        return SearXNGSearchProvider(base_url=settings.searxng_base_url)

    # 默认：Bing（国内可访问，无需 API key）
    from app.providers.search.bing import BingSearchProvider

    return BingSearchProvider()

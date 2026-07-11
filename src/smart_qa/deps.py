"""核心依赖 — FastAPI Depends() 依赖注入

集中管理所有可注入的依赖，避免路由中直接实例化组件。

提供的依赖:
  - get_llm_client()    → ChatOpenAI (DeepSeek 兼容)
  - get_db()            → AsyncSession (在 core/database.py 中定义)
  - get_rate_limiter()  → RateLimiter 单例
  - get_security()      → SensitiveFilter 单例
  - get_agent_graph()   → 编译后的 LangGraph 图

Usage:
    from smart_qa.deps import get_rate_limiter, get_security

    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        limiter: RateLimiter = Depends(get_rate_limiter),
        security: SensitiveFilter = Depends(get_security),
    ):
        ...
"""

from functools import lru_cache

from smart_qa.config import settings
from smart_qa.security import RateLimiter, SensitiveFilter

# ═══════════════════════════════════════════
# LLM Client
# ═══════════════════════════════════════════


@lru_cache
def get_llm_client():
    """获取 LLM 客户端 (DeepSeek via OpenAI-compatible API)

    单例 + 懒加载，首次调用时初始化。
    DeepSeek API 兼容 OpenAI SDK，直接用 ChatOpenAI。
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.lightweight_model,
        temperature=0.3,
        max_tokens=2048,
        timeout=30,
    )


# ═══════════════════════════════════════════
# Security
# ═══════════════════════════════════════════


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """获取 RateLimiter 单例"""
    return RateLimiter(
        global_cap=settings.global_rate_limit,
        global_rate=settings.global_refill_rate,
        user_cap=settings.user_rate_limit,
        user_rate=settings.user_refill_rate,
        daily_budget=settings.daily_token_budget,
    )


@lru_cache
def get_security() -> SensitiveFilter:
    """获取 SensitiveFilter 单例"""
    return SensitiveFilter()


# ═══════════════════════════════════════════
# Agent Graph
# ═══════════════════════════════════════════


@lru_cache
def get_agent_graph():
    """获取编译后的 LangGraph Agent 图（全局单例，启动时编译一次）"""
    from smart_qa.agent.graph import build_graph

    llm = get_llm_client()
    return build_graph(llm_client=llm)

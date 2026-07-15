"""核心依赖访问器 — 统一通过 DI 容器管理

所有依赖优先从 smart_qa.di.container 获取（由 web.py lifespan 注册），
若容器中不存在则直接构建（兼容测试环境和 CLI 场景）。

依赖注册清单（见 web.py lifespan）:
  - "llm"              → ChatOpenAI 客户端（工厂懒加载）
  - "agent_graph"      → 编译后的 LangGraph StateGraph（工厂懒加载）
  - "rate_limiter"     → RateLimiter 实例
  - "security"         → SensitiveFilter 实例
  - "bm25"             → BM25Index 实例
  - "knowledge_graph"  → KnowledgeGraph 实例
  - "store"            → LangGraph Store 实例

Usage:
    from smart_qa.deps import get_llm_client, get_security
    from smart_qa.di import container

    # FastAPI 路由注入
    limiter: RateLimiter = Depends(get_rate_limiter)

    # 业务代码
    llm = get_llm_client()
    bm25 = container.get("bm25")
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI

from smart_qa.config import settings
from smart_qa.di import container
from smart_qa.security import RateLimiter, SensitiveFilter

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


# ═══════════════════════════════════════════
# LLM 客户端
# ═══════════════════════════════════════════


def _build_llm_client() -> ChatOpenAI:
    """直接构建 LLM 客户端（回退用）"""
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY 未配置，请设置环境变量或 .env 文件")
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.lightweight_model,
        temperature=0.3,
        max_tokens=2048,
        timeout=30,
    )


def get_llm_client() -> ChatOpenAI:
    """获取 LLM 客户端（优先容器，回退到直接构建）"""
    from smart_qa.di import container
    if container.has("llm"):
        return container.get("llm")
    return _build_llm_client()


# ═══════════════════════════════════════════
# 安全组件（优先容器，回退到直接构建）
# ═══════════════════════════════════════════


def get_rate_limiter() -> RateLimiter:
    """获取 RateLimiter（优先容器，回退到直接构建）"""
    from smart_qa.di import container
    if container.has("rate_limiter"):
        return container.get("rate_limiter")
    return RateLimiter(
        global_cap=settings.global_rate_limit,
        global_rate=settings.global_refill_rate,
        user_cap=settings.user_rate_limit,
        user_rate=settings.user_refill_rate,
        daily_budget=settings.daily_token_budget,
    )


def get_security() -> SensitiveFilter:
    """获取 SensitiveFilter（优先容器，回退到直接构建）"""
    from smart_qa.di import container
    if container.has("security"):
        return container.get("security")
    return SensitiveFilter()


# ═══════════════════════════════════════════
# Agent Graph
# ═══════════════════════════════════════════


def get_agent_graph() -> CompiledStateGraph:
    """获取编译后的 LangGraph Agent 图（优先容器，回退构建）"""
    from smart_qa.agent.graph import build_graph
    from smart_qa.di import container
    if container.has("agent_graph"):
        return container.get("agent_graph")
    return build_graph(llm_client=get_llm_client())

"""核心依赖 — FastAPI Depends() 依赖注入

集中管理所有可注入的单例依赖，避免路由中直接实例化组件。

功能概览:
  - get_llm_client()    → ChatOpenAI (DeepSeek 兼容)    [单例, 懒加载]
  - get_rate_limiter()  → RateLimiter                    [单例, 懒加载]
  - get_security()      → SensitiveFilter                [单例, 懒加载]
  - get_agent_graph()   → 编译后的 LangGraph StateGraph  [单例, 懒加载]

设计说明:
    所有工厂函数使用 @lru_cache 装饰器实现单例模式。
    首次调用时创建实例，后续返回缓存实例。
    这确保了整个应用生命周期内只有一个 LLM 客户端、一个限流器、一个安全过滤器。

Usage:
    from smart_qa.deps import get_agent_graph, get_rate_limiter, get_security

    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        limiter: RateLimiter = Depends(get_rate_limiter),
        security: SensitiveFilter = Depends(get_security),
    ):
        graph = get_agent_graph()
        ...
"""

from functools import lru_cache

from smart_qa.config import settings
from smart_qa.security import RateLimiter, SensitiveFilter


@lru_cache
def get_llm_client():
    """获取 LLM 客户端 (DeepSeek via OpenAI-compatible API)

    使用 LangChain 的 ChatOpenAI 包装器，连接兼容 OpenAI SDK 的 API（如 DeepSeek）。
    从 settings 读取 API Key、Base URL、模型名。

    单例 + 懒加载：首次调用时初始化 LLM 连接，之后复用。
    低温（temperature=0.3）确保回答一致性，max_tokens=2048 控制生成长度。

    返回值:
        langchain_openai.ChatOpenAI — 配置好的 LLM 客户端实例
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


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """获取 RateLimiter 单例

    从 settings 读取三层限流的参数（全局桶、用户桶、每日 Token 预算）。
    所有参数可运行时通过 .env 调整。

    返回值:
        RateLimiter — 配置好的三层令牌桶限流器

    参见:
        smart_qa.security.RateLimifier
    """
    return RateLimiter(
        global_cap=settings.global_rate_limit,
        global_rate=settings.global_refill_rate,
        user_cap=settings.user_rate_limit,
        user_rate=settings.user_refill_rate,
        daily_budget=settings.daily_token_budget,
    )


@lru_cache
def get_security() -> SensitiveFilter:
    """获取 SensitiveFilter 单例

    四道安全防线：
      1. AC 自动机敏感词匹配
      2. Prompt 注入检测
      3. 代码注入检测（XSS/SQL/Shell）
      4. PII 输出脱敏

    返回值:
        SensitiveFilter — 配置好的安全过滤器实例

    参见:
        smart_qa.security.SensitiveFilter
    """
    return SensitiveFilter()


@lru_cache
def get_agent_graph():
    """获取编译后的 LangGraph Agent 图（全局单例，启动时编译一次）

    构建并编译完整的 StateGraph，包括所有节点（router、scenarios、guards、memory）。
    编译后图结构不可变，可安全并发执行多个请求。

    内部流程:
        1. 获取 LLM 客户端实例
        2. 调用 build_graph(llm_client) 构建未编译的图
        3. workflow.compile(checkpointer=_memory, store=_store) 编译

    返回值:
        langgraph.graph.CompiledStateGraph — 可执行的编译态图

    注意:
        图编译后线程安全，但 _memory (MemorySaver) 和 _store (PostgresStore)
        是模块级单例，所有请求共享同一检查点和长期记忆存储。
    """
    from smart_qa.agent.graph import build_graph

    llm = get_llm_client()
    return build_graph(llm_client=llm)

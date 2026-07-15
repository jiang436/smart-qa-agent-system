"""FastAPI 入口 — 智能问答 Agent 系统"""

import json as _json
import os as _os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as _sa_text

from smart_qa.api.routes import router
from smart_qa.config import settings
from smart_qa.database.engine import close_db, init_db
from smart_qa.database.redis import close_redis, init_redis
from smart_qa.observability.logger import logger
from smart_qa.observability.metrics import setup_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        await init_redis()
        logger.info("Redis 连接成功")
    except Exception as e:
        logger.warning("Redis 不可用: {}", str(e)[:100])
    try:
        await init_db()
        logger.info("PostgreSQL 连接成功")
    except Exception as e:
        logger.warning("PostgreSQL 不可用: {}", str(e)[:100])

    # ── DI 容器注册（统一依赖管理入口）──
    try:
        from smart_qa.di import container
        from smart_qa.knowledge.knowledge_graph import KnowledgeGraph
        from smart_qa.security import RateLimiter, SensitiveFilter

        # 基础设施 — 始终可用
        container.register("knowledge_graph", KnowledgeGraph())
        container.register("rate_limiter", RateLimiter(
            global_cap=settings.global_rate_limit,
            global_rate=settings.global_refill_rate,
            user_cap=settings.user_rate_limit,
            user_rate=settings.user_refill_rate,
            daily_budget=settings.daily_token_budget,
        ))
        container.register("security", SensitiveFilter())
        logger.info("DI 容器: KnowledgeGraph / RateLimiter / SensitiveFilter 已注册")

        # LLM 客户端 — 懒加载（首次 get("llm") 时才构建）
        def _build_llm() -> Any:
            from langchain_openai import ChatOpenAI
            if not settings.llm_api_key:
                raise RuntimeError("LLM_API_KEY 未配置")
            return ChatOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.lightweight_model,
                temperature=0.3, max_tokens=2048, timeout=30,
            )
        container.register_factory("llm", _build_llm)

        # Agent 图 — 懒加载（依赖 llm，通过工厂链自动解析）
        def _build_graph() -> Any:
            from smart_qa.agent.graph import build_graph
            return build_graph(llm_client=container.get("llm"))
        container.register_factory("agent_graph", _build_graph)

        logger.info("DI 容器: LLM / AgentGraph 工厂已注册")
    except Exception as e:
        logger.warning("DI 容器初始化失败: {}", e)

    # 预加载 BM25 知识库（含 FAQ JSON，优先从磁盘加载，免每次重启重建）
    try:
        from smart_qa.knowledge.bm25 import BM25Index

        _bm25 = BM25Index()

        if _bm25.load():
            # 磁盘有缓存 → 直接使用
            pass
        else:
            # 无缓存 → 从文件构建后保存
            _docs = []
            _knowledge_dir = settings.get_knowledge_dir()
            for _root, _dirs, _files in _os.walk(_knowledge_dir):
                for _f in _files:
                    if _f.endswith(".md"):
                        with open(_os.path.join(_root, _f), encoding="utf-8") as _fh:
                            for _p in _fh.read().split("\n\n"):
                                if len(_p.strip()) > 20:
                                    _docs.append(_p.strip())
            # 加载 FAQ JSON
            for _faq_file in settings.get_faq_file_list():
                try:
                    with open(_faq_file, encoding="utf-8") as _fh:
                        _faq_data = _json.load(_fh)
                    _entries = _faq_data if isinstance(_faq_data, list) else _faq_data.get("entries", [])
                    for _entry in _entries:
                        _q = _entry.get("question", "")
                        _a = _entry.get("answer", "")
                        if _q and _a and len(_q + _a) > 30:
                            _docs.append(f"问：{_q}\n答：{_a}")
                    logger.info("FAQ 已加载 file={} entries={}", _faq_file, len(_entries))
                except Exception as _e:
                    logger.warning("FAQ 加载失败 file={} err={}", _faq_file, str(_e)[:80])

            if _docs:
                _bm25.build(_docs)
                _bm25.save()
            else:
                logger.warning("BM25 知识库为空")

        from smart_qa.rag.retrieval import set_shared_bm25

        set_shared_bm25(_bm25)
        _bm25_status = f"docs={_bm25.doc_count} built_at={_bm25.built_at_str or '未构建'}"
        logger.info("BM25 知识库已加载 {}", _bm25_status)
    except Exception as e:
        logger.warning("BM25 知识库加载失败: {}", e)

    setup_metrics(app)
    # 初始化 LangGraph Store（PostgreSQL 长期记忆）
    try:
        from langgraph.store.postgres import PostgresStore

        from smart_qa.agent.graph import set_store

        pg_dsn = settings.postgres_dsn.replace("+asyncpg", "")  # sync driver for PostgresStore
        store = PostgresStore.from_conn_string(pg_dsn)
        store.setup()  # sync setup: create tables
        set_store(store)
        logger.info("LangGraph Store 已就绪 (PostgresStore)")
    except Exception as e:
        logger.warning("LangGraph Store 不可用: {}，使用 InMemoryStore", str(e)[:80])
        from langgraph.store.memory import InMemoryStore

        set_store(InMemoryStore())

    # 预热 BM25 + 向量预计算（避免首次请求等 40s）
    try:
        from smart_qa.rag.retrieval import _load_knowledge_bm25
        _load_knowledge_bm25()
        logger.info("BM25 索引 + 向量预计算已预热")
    except Exception as e:
        logger.warning("BM25 预热失败: {}", str(e)[:80])
        from langgraph.store.memory import InMemoryStore

        set_store(InMemoryStore())

    # OTel 可观测（有 OTEL_EXPORTER_OTLP_ENDPOINT 时生效）
    try:
        from smart_qa.observability.tracer import setup_otel, setup_phoenix

        setup_otel(app=app)
        setup_phoenix()
    except Exception as e:
        logger.debug("可观测接入异常: {}", e)
    yield
    try:
        await close_redis()
    except Exception:
        pass
    try:
        await close_db()
    except Exception:
        pass


app = FastAPI(
    title="智能问答 Agent 系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    """健康检查 — 实际探测各服务连通性"""
    import asyncio

    services: dict[str, str] = {}

    # PostgreSQL 连通性检查
    try:
        from smart_qa.database.engine import _engine as pg_engine
        if pg_engine is not None:
            async with pg_engine.connect() as conn:
                await conn.execute(_sa_text("SELECT 1"))
            services["db"] = "ok"
        else:
            services["db"] = "not_initialized"
    except Exception as e:
        services["db"] = f"error: {str(e)[:80]}"

    # Redis 连通性检查（2s 超时）
    try:
        from smart_qa.database.redis import redis_client
        if redis_client is not None:
            await asyncio.wait_for(redis_client.ping(), timeout=2.0)
            services["redis"] = "ok"
        else:
            services["redis"] = "not_initialized"
    except TimeoutError:
        services["redis"] = "timeout"
    except Exception as e:
        services["redis"] = f"error: {str(e)[:80]}"

    # Milvus 连通性检查
    try:
        from pymilvus import MilvusClient

        from smart_qa.config import settings
        client = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)
        client.list_collections()  # lightweight probe
        services["milvus"] = "ok"
    except Exception as e:
        services["milvus"] = f"error: {str(e)[:80]}"

    all_ok = all(v == "ok" for v in services.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "services": services,
    }


def main():
    """CLI 入口: uv run smart-qa"""
    import uvicorn

    uvicorn.run("smart_qa.web:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.smart_qa.web:app", host=settings.host, port=settings.port, reload=True)

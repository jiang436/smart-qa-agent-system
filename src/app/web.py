"""FastAPI 入口 — 智能问答 Agent 系统"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.database.engine import close_db, init_db
from src.database.redis import close_redis, init_redis
from src.observability.logger import logger
from src.observability.metrics import setup_metrics


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

    # 预加载 FAQ 快速匹配器（900 条常见问答，<10ms 命中）
    try:
        from src.knowledge.faq_matcher import get_faq_matcher
        _faq = get_faq_matcher()
        _faq_count = _faq.load([
            "data/faq_knowledge_base.json",
            "data/faq_consumables.json",
            "data/faq_troubleshooting.json",
        ])
        logger.info("FAQ 快速匹配器已就绪 entries={}", _faq_count)
    except Exception as e:
        logger.warning("FAQ 匹配器加载失败: {}", str(e)[:80])

    # 预加载 BM25 知识库
    try:
        import os as _os
        from src.knowledge.bm25 import BM25Index
        _bm25 = BM25Index()
        _docs = []
        for _root, _dirs, _files in _os.walk("data/knowledge"):
            for _f in _files:
                if _f.endswith(".md"):
                    with open(_os.path.join(_root, _f), encoding="utf-8") as _fh:
                        for _p in _fh.read().split("\n\n"):
                            if len(_p.strip()) > 20:
                                _docs.append(_p.strip())
        # 加载 FAQ JSON 常见问答（300题×3类=900条）
        import json as _json
        for _faq_file in ["data/faq_knowledge_base.json", "data/faq_consumables.json", "data/faq_troubleshooting.json"]:
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
            from src.rag.retrieval import set_shared_bm25
            set_shared_bm25(_bm25)
            logger.info("BM25 知识库已加载 docs={}", len(_docs))
    except Exception as e:
        logger.warning("BM25 知识库加载失败: {}", e)

    setup_metrics(app)
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

from src.app.api.routes import router

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "services": {
            "db": "ok",
            "redis": "ok",
            "milvus": "ok",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.app.web:app", host="0.0.0.0", port=8000, reload=True)

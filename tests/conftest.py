"""共享 Fixtures — 用于所有测试的 Mock 对象和工具"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


# ═══════════════════════════════════════
# Milvus 可用性检查
# ═══════════════════════════════════════


def _check_milvus_available() -> bool:
    """检查 Milvus 是否可用"""
    try:
        from pymilvus import MilvusClient
        from smart_qa.config import settings

        client = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)
        client.list_collections()
        return True
    except Exception:
        return False


MILVUS_AVAILABLE = _check_milvus_available()


# ═══════════════════════════════════════
# FastAPI 测试客户端
# ═══════════════════════════════════════


@pytest.fixture
def api_client():
    """创建 FastAPI TestClient（不使用真实外部服务）"""
    from smart_qa.web import app

    return TestClient(app)


# ═══════════════════════════════════════
# Mock LLM
# ═══════════════════════════════════════


class MockLLM:
    """可配置的 Mock LLM 客户端"""

    def __init__(self, invoke_result=None, ainvoke_result=None, astream_chunks=None):
        self.invoke_result = invoke_result or "mock response"
        self.ainvoke_result = ainvoke_result or "mock async response"
        self.astream_chunks = astream_chunks or ["mock ", "streamed ", "answer"]
        self.invoke = MagicMock(return_value=_make_response(self.invoke_result))
        self.ainvoke = AsyncMock(return_value=_make_response(self.ainvoke_result))

    async def astream(self, messages):
        for chunk in self.astream_chunks:
            yield _make_response(chunk)


def _make_response(content: str):
    return type("R", (), {"content": content})()


@pytest.fixture
def mock_llm():
    return MockLLM()


# ═══════════════════════════════════════
# Mock Embedding
# ═══════════════════════════════════════


class MockEmbedding:
    """Mock Embedding 模型 — 返回确定性向量"""

    dimension: int = 512

    def encode(self, texts):
        import numpy as np

        if isinstance(texts, str):
            texts = [texts]
        return np.random.RandomState(hash(str(texts)) % (2**31)).rand(
            len(texts), 512
        ).astype(np.float32)

    def cosine_similarity(self, vec1, vec2):
        import numpy as np

        dot = np.dot(vec1, vec2)
        norm = np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-10
        return float(dot / norm)


@pytest.fixture
def mock_embedding():
    return MockEmbedding()


# ═══════════════════════════════════════
# Mock Retriever
# ═══════════════════════════════════════


class MockRetriever:
    """可配置的 Mock 检索器"""

    def __init__(self, docs=None, source="RRF_fusion", confidence="high"):
        self.docs = docs or [
            {
                "content": "边刷建议每3-6个月更换一次，刷毛缩短1/3以上时需更换。",
                "score": 0.9,
                "doc_id": 1,
                "source": "maintenance_guide.md",
            },
            {
                "content": "X30 Pro 支持全屋清扫、定时清扫、禁区设置等功能。",
                "score": 0.8,
                "doc_id": 2,
                "source": "user_manual.md",
            },
        ]
        self.source = source
        self.confidence = confidence

    def retrieve(self, query, top_k=5, mode="parallel"):
        return {
            "docs": self.docs,
            "source": self.source,
            "confidence": self.confidence,
            "total": len(self.docs),
            "note": "",
            "query_used": query,
        }

    async def retrieve_async(self, query, top_k=5, mode="parallel"):
        return self.retrieve(query, top_k, mode)

    def _rewrite_query(self, query):
        return f"rewritten: {query}"


@pytest.fixture
def mock_retriever():
    return MockRetriever()


# ═══════════════════════════════════════
# 通用测试数据
# ═══════════════════════════════════════


@pytest.fixture
def sample_docs():
    """通用测试文档列表"""
    return [
        {
            "content": "X30 Pro 扫地机器人电池过热保护，请将设备移至阴凉处",
            "score": 0.85,
            "source": "L1_semantic",
        },
        {
            "content": "如何重置扫地机器人Wi-Fi连接，长按重置键5秒",
            "score": 0.72,
            "source": "L1_semantic",
        },
        {
            "content": "边刷更换周期为3-6个月，建议定期检查磨损情况",
            "score": 0.68,
            "source": "L1_semantic",
        },
        {
            "content": "HEPA滤网建议每3-4个月更换一次，以保证过滤效果",
            "score": 0.65,
            "source": "L1_semantic",
        },
        {
            "content": "E05错误码表示电池过热，请冷却后重启设备",
            "score": 0.60,
            "source": "L1_semantic",
        },
    ]


@pytest.fixture
def sample_query() -> str:
    return "电池过热怎么处理"


# ═══════════════════════════════════════
# Chat state builder
# ═══════════════════════════════════════


def build_chat_state(
    user_msg: str = "",
    user_id: str = "test-user",
    session_id: str = "test-session",
    **extra,
) -> dict:
    """快捷构建 AgentState"""
    state = {
        "messages": [{"role": "user", "content": user_msg}] if user_msg else [],
        "user_id": user_id,
        "session_id": session_id,
        "intent": None,
        "scenario": None,
        "step": 0,
        "max_steps": 15,
        "tool_calls_history": [],
        "retrieved_docs": None,
        "final_answer": None,
        "user_profile": None,
        "short_term": None,
        "task_memory": None,
        "error": None,
        "loop_detected": False,
    }
    state.update(extra)
    return state


# ═══════════════════════════════════════
# pytest 配置钩子 — 测试结果持久化
# ═══════════════════════════════════════


_session_start_time: float = 0


def pytest_sessionstart(session):
    global _session_start_time
    import time

    _session_start_time = time.time()


def pytest_sessionfinish(session):
    """测试结束后保存结果摘要"""
    import json
    import os
    import time

    results_dir = os.path.join(os.path.dirname(__file__), "..", "test_results")
    os.makedirs(results_dir, exist_ok=True)

    duration = round(time.time() - _session_start_time, 1) if _session_start_time else 0

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": session.testscollected,
        "passed": 0,
        "failed": getattr(session, "testsfailed", 0),
        "duration_seconds": duration,
        "milvus_available": MILVUS_AVAILABLE,
    }
    report["passed"] = max(0, report["total"] - report["failed"])

    # 收集按文件统计
    item_counts = {}
    for item in session.items:
        fname = os.path.basename(item.location[0]) if hasattr(item, "location") else "unknown"
        item_counts[fname] = item_counts.get(fname, 0) + 1

    report["file_breakdown"] = item_counts

    # 写入 JSON
    report_path = os.path.join(results_dir, "test_summary.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 写入 Markdown 摘要
    md_path = os.path.join(results_dir, "TEST_REPORT.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 测试报告\n\n")
        f.write(f"**时间**: {report['timestamp']}\n\n")
        f.write(f"**总计**: {report['total']} | ✅ {report['passed']} 通过 | ❌ {report['failed']} 失败\n\n")
        f.write(f"**耗时**: {report['duration_seconds']:.1f}s\n\n")
        f.write(f"## 按文件统计\n\n")
        f.write(f"| 文件 | 测试数 |\n")
        f.write(f"|------|--------|\n")
        for fname, count in sorted(item_counts.items()):
            f.write(f"| {fname} | {count} |\n")

        if not MILVUS_AVAILABLE:
            f.write(f"\n> ⚠️ Milvus 未运行，知识库相关测试可能失败。\n")

    print(f"\n[TestResults] 报告已保存: {report_path}")
    print(f"[TestResults] Markdown: {md_path}")

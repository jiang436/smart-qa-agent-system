"""RAG Agent 增强测试 — C-RAG 循环 / 幻觉检测 / 查询重写 / 上下文压缩"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from conftest import MockLLM, MockRetriever


class MockRetrieverWithQuality:
    """可控制检索质量的 Mock 检索器"""

    def __init__(self, docs_per_round=None):
        self.docs_per_round = docs_per_round or [
            [{"content": "doc1", "score": 0.3, "doc_id": 1, "source": "test.md"}],
            [{"content": "doc2", "score": 0.6, "doc_id": 2, "source": "test.md"}],
        ]
        self.call_count = 0

    def retrieve(self, query, top_k=5, mode="parallel"):
        idx = min(self.call_count, len(self.docs_per_round) - 1)
        docs = self.docs_per_round[idx]
        return {
            "docs": docs,
            "source": "RRF_fusion",
            "confidence": "high" if idx > 0 else "low",
            "total": len(docs),
            "note": "",
            "query_used": query,
        }

    async def retrieve_async(self, query, top_k=5, mode="parallel"):
        self.call_count += 1
        return self.retrieve(query, top_k, mode)

    def _rewrite_query(self, query):
        return f"rewritten: {query}"


# ═══════════════════════════════════════
# C-RAG 检索质量评估 → 改写 → 重试
# ═══════════════════════════════════════


class TestCRAGRetrieval:
    """C-RAG: 检索 → 评估 → 修正"""

    def test_quality_check_high_score(self):
        """高 rerank_score → 质量 OK"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        docs = [{"rerank_score": 0.85}, {"score": 0.7}]
        assert agent._check_retrieval_quality("test", docs) is True

    def test_quality_check_medium_with_enough_docs(self):
        """中等分 + ≥2 文档 → OK"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        docs = [{"score": 0.35}, {"score": 0.3}]
        assert agent._check_retrieval_quality("test", docs) is True

    def test_quality_check_low_single_doc(self):
        """低分单文档 → 不足"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        docs = [{"score": 0.2}]
        assert agent._check_retrieval_quality("test", docs) is False

    def test_quality_check_empty(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        assert agent._check_retrieval_quality("test", []) is False

    def test_quality_check_bm25_score_normalized(self):
        """BM25 原始分 (>1) 被归一化到 0-1"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        docs = [{"score": 15.0}]  # BM25 原始高分
        assert agent._check_retrieval_quality("test", docs) is True

    @pytest.mark.asyncio
    async def test_crag_retry_on_low_quality(self):
        """低质量 → 改写 → 重试"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        retriever = MockRetrieverWithQuality()
        agent = RAGAgent(llm_client=MockLLM(), retriever=retriever)

        result, docs, source = await agent._crag_retrieve("test query", top_k=5, max_retries=2)

        assert result is not None
        assert isinstance(docs, list)
        assert source in ("L2_rewrite", "L4_llm", "RRF_fusion")

    @pytest.mark.asyncio
    async def test_crag_high_quality_skips_retry(self):
        """高质量直接通过，不重试"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        retriever = MockRetriever()
        agent = RAGAgent(llm_client=MockLLM(), retriever=retriever)

        result, docs, source = await agent._crag_retrieve("test", top_k=5, max_retries=2)

        assert result["confidence"] == "high"
        assert len(docs) >= 2


# ═══════════════════════════════════════
# 幻觉检测与安全降级
# ═══════════════════════════════════════


class TestHallucinationGuard:
    """幻觉检测与安全降级"""

    def test_high_risk_blocks(self):
        from smart_qa.rag.citation import HallucinationGuard
        assert HallucinationGuard.should_block({"hallucination_risk": "high"}, threshold="high") is True

    def test_medium_risk_not_blocked_by_high_threshold(self):
        from smart_qa.rag.citation import HallucinationGuard
        assert HallucinationGuard.should_block({"hallucination_risk": "medium"}, threshold="high") is False

    def test_low_risk_not_blocked(self):
        from smart_qa.rag.citation import HallucinationGuard
        assert HallucinationGuard.should_block({"hallucination_risk": "low"}, threshold="high") is False

    def test_safe_response_includes_unverified_warning(self):
        from smart_qa.rag.citation import HallucinationGuard
        answer = {
            "text": "正常回答",
            "unverified_claims": ["claim1", "claim2"],
        }
        result = HallucinationGuard.generate_safe_response(answer)
        assert "claim1" in result or "小智" in result


# ═══════════════════════════════════════
# CitationTracker 引用标注
# ═══════════════════════════════════════


class TestCitationTracker:
    """引用追踪器"""

    def test_build_cited_answer_with_docs(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        tracker.register_docs([
            {"doc_id": "1", "content": "X30 Pro 边刷每3-6个月更换一次", "source": "guide.md"},
        ])

        result = tracker.build_cited_answer("边刷怎么换", "X30 Pro 边刷每3-6个月更换一次。")
        assert "text" in result
        assert "citations" in result
        assert "hallucination_risk" in result

    def test_build_cited_answer_without_docs(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()  # 未注册任何文档
        result = tracker.build_cited_answer("test", "this is an answer")
        assert result["hallucination_risk"] == "high"

    def test_verify_document_matching_content(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        result = tracker.verify_document("X30 Pro 电池过热保护", "电池过热")
        assert "verified" in result

    def test_verify_empty_params(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        result = tracker.verify_document("", "")
        assert result["verified"] is False


# ═══════════════════════════════════════
# 查询重写（指代消解）
# ═══════════════════════════════════════


class TestQueryRewrite:
    """查询重写 — 短追问补全上下文"""

    def test_short_query_with_history_rewritten(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor

        llm = MockLLM(invoke_result="X30 Pro 边刷更换周期 多久换一次")
        agent = RAGAgent(
            llm_client=llm,
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

        state = {
            "messages": [
                {"role": "user", "content": "X30 Pro 边刷需要定期更换吗"},
                {"role": "assistant", "content": "是的，X30 Pro 边刷建议每3-6个月更换。"},
                {"role": "user", "content": "多久换一次"},
            ],
        }
        result = agent._enrich_query_with_history("多久换一次", state)
        assert len(result) > len("多久换一次")

    def test_long_query_not_rewritten(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor

        agent = RAGAgent(
            llm_client=MockLLM(),
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

        long_query = "X30 Pro 扫地机器人的边刷更换周期是多久"
        state = {"messages": [{"role": "user", "content": long_query}]}
        result = agent._enrich_query_with_history(long_query, state)
        assert result == long_query  # 长查询不变

    def test_query_without_history_not_rewritten(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor

        agent = RAGAgent(
            llm_client=MockLLM(),
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

        result = agent._enrich_query_with_history("短查询", {"messages": []})
        assert result == "短查询"  # 无历史不变


# ═══════════════════════════════════════
# 上下文压缩
# ═══════════════════════════════════════


class TestContextCompression:
    """文档上下文压缩"""

    def test_compress_short_docs_skipped(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())

        short_docs = [{"content": "short", "score": 0.5}]
        result = agent._compress_docs("test", short_docs)
        assert len(result) == 1
        assert result[0]["content"] == "short"

    def test_compress_no_llm_returns_original(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=None, retriever=MockRetriever())

        docs = [{"content": "x" * 500, "score": 0.5}]
        result = agent._compress_docs("test", docs)
        assert len(result) >= 1

    def test_compress_with_mock_llm(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent

        llm = MockLLM(invoke_result="[文档0] 相关句子\n[文档1] NONE")
        agent = RAGAgent(llm_client=llm, retriever=MockRetriever())

        docs = [
            {"content": "x" * 500, "score": 0.9},
            {"content": "y" * 500, "score": 0.3},
        ]
        result = agent._compress_docs("test", docs)
        assert len(result) >= 1  # 至少保留一个（短文档通过）

    def test_compress_empty_list(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        agent = RAGAgent(llm_client=MockLLM(), retriever=MockRetriever())
        result = agent._compress_docs("test", [])
        assert result == []

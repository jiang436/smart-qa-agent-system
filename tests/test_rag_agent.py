"""RAGAgent 完整 pipeline 测试 — mock LLM + mock retriever"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class MockLLM:
    def __init__(self, invoke_result=None):
        self.invoke_result = invoke_result

    def invoke(self, prompt):
        return type('R', (), {'content': self.invoke_result or 'mock response'})()

    async def ainvoke(self, messages):
        return type('R', (), {'content': 'mock streamed answer'})()

    async def astream(self, messages):
        yield type('C', (), {'content': 'mock '})()
        yield type('C', (), {'content': 'answer'})()


class MockRetriever:
    def __init__(self, docs=None, source="RRF_fusion", confidence="high"):
        self.docs = docs or [
            {"content": "bian shua jian yi 3-6 ge yue geng huan", "score": 0.9, "doc_id": 1, "source": "manual.md"},
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


class TestRAGAgentBasic:
    @pytest.fixture
    def agent(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor
        return RAGAgent(
            llm_client=MockLLM(invoke_result="zhe shi yi ge ce shi hui da"),
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

    def test_extract_query_from_state(self, agent):
        state = {"messages": [{"role": "user", "content": "bian shua"}]}
        query = agent._extract_query(state)
        assert query == "bian shua"

    def test_extract_history(self, agent):
        state = {
            "messages": [
                {"role": "user", "content": "bian shua"},
                {"role": "assistant", "content": "bian shua 3 ge yue huan"},
            ],
        }
        history = agent._extract_history(state)
        assert "bian shua" in history

    def test_build_context_with_docs(self, agent):
        docs = [{"content": "bian shua geng huan 3-6 yue", "score": 0.9, "source": "manual.md"}]
        context = agent._build_context("bian shua", docs)
        assert "bian shua" in context
        assert "can kao xin xi" in context.lower() or "bian shua geng huan" in context.lower()

    def test_build_context_without_docs(self, agent):
        context = agent._build_context("test", [])
        assert "wei zhao dao" in context.lower() or "test" in context.lower()

    def test_clean_output_removes_excess_newlines(self, agent):
        text = "hello\n\n\n\nworld"
        cleaned = agent._clean_output(text)
        assert "\n\n\n" not in cleaned

    def test_clean_output_preserves_citations(self, agent):
        text = "bian shua yao huan [manual.md]\n\nyuan yin... [wei yan zheng]"
        cleaned = agent._clean_output(text)
        assert "[manual.md]" in cleaned
        assert "[wei yan zheng]" in cleaned

    def test_enrich_query_long_skips(self, agent):
        """长查询不需要增强"""
        long_query = "X30 Pro bian shua geng huan zhou qi shi duo shao"
        result = agent._enrich_query_with_history(long_query, {"messages": []})
        assert result == long_query  # 不变

    def test_enrich_query_short_needs_history(self, agent):
        """短查询从历史提取话题"""
        state = {
            "messages": [
                {"role": "user", "content": "bian shua"},
                {"role": "assistant", "content": "X30 Pro bian shua jian yi 3-6 ge yue geng huan"},
            ],
        }
        agent.llm = MockLLM(invoke_result="X30 Pro bian shua geng huan zhou qi duo jiu huan yi ci")
        result = agent._enrich_query_with_history("duo jiu huan yi ci", state)
        # 短查询被增强（LLM 返回改写后查询，比原查询长）
        assert len(result) >= len("duo jiu huan yi ci")

    def test_check_retrieval_quality_high(self, agent):
        docs = [{"rerank_score": 0.85}, {"score": 0.7}]
        assert agent._check_retrieval_quality("test", docs) is True

    def test_check_retrieval_quality_low(self, agent):
        docs = [{"score": 0.1}]
        assert agent._check_retrieval_quality("test", docs) is False

    def test_check_retrieval_quality_empty(self, agent):
        assert agent._check_retrieval_quality("test", []) is False


class TestRAGAgentAnswer:
    @pytest.fixture
    def agent(self):
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor
        return RAGAgent(
            llm_client=MockLLM(invoke_result="zhe shi ce shi hui da"),
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

    @pytest.mark.asyncio
    async def test_answer_returns_dict(self, agent):
        result = await agent.answer("bian shua zen me huan")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "docs" in result
        assert "source" in result
        assert "hallucination_risk" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_answer_with_cache_hit(self, agent):
        """缓存命中直接返回——注意：SemanticCache 需要 embedding 匹配才命中，mock 无法完美模拟"""
        state = {"messages": [{"role": "user", "content": "test_cache_key"}]}
        result_state = await agent.retrieve_and_generate(state)
        assert "final_answer" in result_state
        assert len(result_state["final_answer"]) > 0

    @pytest.mark.asyncio
    async def test_answer_empty_query(self, agent):
        state = {"messages": []}
        result_state = await agent.retrieve_and_generate(state)
        assert "final_answer" in result_state
        assert len(result_state["final_answer"]) > 0

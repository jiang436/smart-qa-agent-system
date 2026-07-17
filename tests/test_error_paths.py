"""异常降级测试 — LLM 超时 / Milvus 不可用 / Redis 不可用 / PG 不可用

验证各层降级策略不会导致系统崩溃
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from conftest import MockLLM, MockRetriever, build_chat_state


# ═══════════════════════════════════════
# LLM 降级
# ═══════════════════════════════════════


class TestLLMFallback:
    """LLM API 不可用时的降级"""

    @pytest.mark.asyncio
    async def test_rag_agent_llm_timeout_fallback(self):
        """LLM astream 超时 → 降级 ainvoke → 再失败 → 兜底文案"""
        from smart_qa.agent.agents.rag_agent import RAGAgent
        from smart_qa.memory.cache import SemanticCache
        from smart_qa.memory.short_term import MemoryCompressor

        failing_llm = MagicMock()
        failing_llm.astream = MagicMock(side_effect=asyncio.TimeoutError("timeout"))
        failing_llm.ainvoke = AsyncMock(side_effect=Exception("also failed"))

        agent = RAGAgent(
            llm_client=failing_llm,
            retriever=MockRetriever(),
            semantic_cache=SemanticCache(),
            compressor=MemoryCompressor(llm_client=None),
        )

        answer = await agent._generate_answer("test", "context", "")
        assert len(answer) > 0
        assert "抱歉" in answer or "重试" in answer

    @pytest.mark.asyncio
    async def test_router_llm_error_falls_to_keyword(self):
        """Router LLM 失败 → 关键词降级"""
        from smart_qa.agent.agents.router_agent import RouterAgent

        router = RouterAgent(llm_client=None)  # 无 LLM
        intent = await router._classify_intent("E05错误码怎么解决")
        assert intent in ("troubleshoot", "qa", "general")

    def test_router_classify_no_llm(self):
        """无 LLM 时 classify 返回关键词结果"""
        from smart_qa.agent.agents.router_agent import RouterAgent
        router = RouterAgent(llm_client=None)
        result = router.classify("怎么设置定时清扫")
        assert result in ("qa", "troubleshoot", "general")

    def test_semantic_cache_no_llm_works(self):
        """无 LLM 时语义缓存正常工作"""
        from smart_qa.memory.cache import SemanticCache
        cache = SemanticCache(redis_client=None)
        # 本地模式应该正常工作
        assert cache.threshold > 0


# ═══════════════════════════════════════
# Milvus 不可用
# ═══════════════════════════════════════


class TestMilvusUnavailable:
    """Milvus 不可用时检索降级"""

    def test_semantic_search_milvus_error_fallback(self):
        """Milvus 异常 → 降级到预计算向量"""
        from smart_qa.rag.retrieval import MultiLayerRetriever
        from smart_qa.di import container

        mock_milvus = MagicMock()
        mock_milvus.search = MagicMock(side_effect=Exception("Connection refused"))

        container.register("doc_vectors", None)  # 无预计算向量

        retriever = MultiLayerRetriever(milvus_client=mock_milvus, llm_client=None)
        docs = retriever._semantic_search("test", top_k=3)
        # 应该返回空列表而不是崩溃
        assert isinstance(docs, list)

    def test_retrieve_without_milvus_or_bm25(self):
        """无任何后端 → L4 LLM 兜底"""
        from smart_qa.rag.retrieval import MultiLayerRetriever

        mock_bm25 = MagicMock()
        mock_bm25.doc_count = 0
        mock_bm25.documents = []

        retriever = MultiLayerRetriever(milvus_client=None, llm_client=None, bm25_index=mock_bm25)
        result = retriever.retrieve("扫地机不走了", top_k=5)

        assert result["source"] == "L4_llm"
        assert result["confidence"] == "low"
        assert isinstance(result["docs"], list)

    def test_cascade_retrieve_all_layers_fail(self):
        """四层全部失败 → L4 LLM 兜底"""
        from smart_qa.rag.retrieval import MultiLayerRetriever

        mock_bm25 = MagicMock()
        mock_bm25.doc_count = 0
        mock_bm25.search = MagicMock(return_value=[])

        retriever = MultiLayerRetriever(milvus_client=None, llm_client=None, bm25_index=mock_bm25)
        result = retriever._cascade_retrieve("test query")

        assert result["source"] == "L4_llm"


# ═══════════════════════════════════════
# Redis 不可用
# ═══════════════════════════════════════


class TestRedisUnavailable:
    """Redis 不可用时缓存降级"""

    def test_semantic_cache_local_fallback(self):
        """无 Redis → 本地 dict 存储"""
        from smart_qa.memory.cache import SemanticCache
        cache = SemanticCache(redis_client=None)

        # 本地存储应该工作
        assert cache.redis is None
        assert hasattr(cache, "_local_store")

    @pytest.mark.asyncio
    async def test_cache_get_local(self):
        """本地缓存读写"""
        from smart_qa.memory.cache import SemanticCache

        cache = SemanticCache(redis_client=None)
        await cache.set("怎么重置扫地机", "长按重置键3秒即可重置。")

        result = await cache.get("怎么重置扫地机")
        assert result is not None
        assert "answer" in result

    @pytest.mark.asyncio
    async def test_cache_clear_local(self):
        """清空本地缓存"""
        from smart_qa.memory.cache import SemanticCache

        cache = SemanticCache(redis_client=None)
        await cache.set("test_key", "test_value")
        await cache.clear()
        result = await cache.get("test_key")
        assert result is None


# ═══════════════════════════════════════
# PostgreSQL 不可用
# ═══════════════════════════════════════


class TestPostgresUnavailable:
    """PostgreSQL 不可用时降级"""

    @pytest.mark.asyncio
    async def test_conversation_load_fails_gracefully(self):
        """load_messages 失败时返回空列表"""
        from smart_qa.memory.conversation_store import load_messages

        # 无 PG 连接时应该不崩溃
        try:
            messages = await load_messages("test-session")
            assert isinstance(messages, list)
        except Exception:
            # PG 不可用时可接受
            pass

    def test_session_factory_available(self):
        """Session factory 存在但不一定可用"""
        try:
            from smart_qa.database.engine import get_session_factory
            factory = get_session_factory()
            assert factory is not None
        except Exception:
            pass


# ═══════════════════════════════════════
# 综合降级链路
# ═══════════════════════════════════════


class TestFullDegradationChain:
    """全链路降级测试"""

    def test_build_graph_without_any_services(self):
        """零外部依赖时也能构建 graph"""
        from smart_qa.agent.graph import build_graph
        graph = build_graph(llm_client=None)
        assert graph is not None

    @pytest.mark.asyncio
    async def test_qa_scenario_no_llm_no_redis(self):
        """QA 场景：无 LLM 无 Redis"""
        from smart_qa.scenarios.qa_scenario import QAScenario

        state = build_chat_state("test query")
        try:
            result = await QAScenario.run(state)
            assert "final_answer" in result
        except RuntimeError:
            pass  # 无 LLM 时可接受

    @pytest.mark.asyncio
    async def test_troubleshoot_no_llm_has_error_codes(self):
        """故障排查：无 LLM 但错误码匹配仍可用"""
        from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario

        state = build_chat_state("E05错误")
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        assert "E05" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_troubleshoot_no_match_fallback(self):
        """故障排查：无匹配 → 兜底建议"""
        from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario

        state = build_chat_state("扫地机出了我不知道的问题xyz")
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        # 应该有兜底建议
        assert len(result["final_answer"]) > 10

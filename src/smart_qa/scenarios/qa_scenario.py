"""知识问答场景 — 基于 RAG 的产品手册问答

文档第 2.1 节:
  用户: "扫地机器人老是卡在门槛那里怎么办？"
  -> 意图分类 -> 语义缓存查 -> RAG 检索 -> LLM 整合回答 -> 记忆写入

完整流程:
  1. 检查语义缓存 — query embedding 相似度 > 0.95 直接返回
  2. 加载 CoT RAG 提示模板
  3. 调用 RAGAgent 检索并生成回答
  4. 写入短期记忆（压缩器更新对话上下文）
  5. 写入语义缓存（下次相同问题直接命中）
  6. 返回 state，final_answer 已填充

涉及技术:
  - 四层召回兜底（语义->改写->BM25->LLM）
  - 语义缓存（高频问题直接命中）
  - 引用标注（CitationTracker）
  - 自我反思（ReflectionAgent）
  - 记忆压缩（MemoryCompressor）
"""

import time

from smart_qa.agent.agents.rag_agent import RAGAgent
from smart_qa.agent.state_utils import extract_user_query
from smart_qa.memory.cache import SemanticCache
from smart_qa.memory.short_term import MemoryCompressor
from smart_qa.observability.logger import logger


class QAScenario:
    """知识问答场景

    用法:
        result_state = await QAScenario.run(state)
    """

    _rag_agent: RAGAgent | None = None
    _semantic_cache: SemanticCache | None = None
    _compressor: MemoryCompressor | None = None

    @classmethod
    def _get_rag_agent(cls, llm_client=None) -> RAGAgent:
        """懒加载 RAGAgent 单例"""
        if cls._rag_agent is None:
            cls._rag_agent = RAGAgent(llm_client=llm_client)
        if llm_client is not None:
            cls._rag_agent.llm = llm_client
        return cls._rag_agent

    @classmethod
    def _get_cache(cls) -> SemanticCache:
        """懒加载语义缓存（带 Redis 支持）"""
        if cls._semantic_cache is None:
            from smart_qa.database.redis import RedisClient

            redis_client = RedisClient.get_client()
            cls._semantic_cache = SemanticCache(redis_client=redis_client)
        return cls._semantic_cache

    @classmethod
    def _get_compressor(cls, llm_client=None) -> MemoryCompressor:
        """懒加载记忆压缩器"""
        if cls._compressor is None:
            cls._compressor = MemoryCompressor(llm_client=llm_client, window_size=6)
        elif llm_client and cls._compressor.llm is None:
            cls._compressor.llm = llm_client
        return cls._compressor

    @staticmethod
    async def run(state: dict) -> dict:
        """执行知识问答场景

        Args:
            state: AgentState 字典

        Returns:
            更新后的 state，final_answer 已填充
        """
        start_time = time.time()

        query = QAScenario._extract_query(state)
        if not query:
            state["final_answer"] = "您好！请问有什么关于产品的问题需要帮您解答？"
            return state

        state.get("user_id", "anonymous")

        cache = QAScenario._get_cache()
        cached_answer = await cache.get(query)
        if cached_answer:
            state["final_answer"] = cached_answer
            state["retrieved_docs"] = []
            QAScenario._log_cache_hit(query)
            return state

        try:
            from smart_qa.deps import get_llm_client

            rag = QAScenario._get_rag_agent(llm_client=get_llm_client())
            state = await rag.retrieve_and_generate(state)
        except Exception as e:
            logger.error("RAG 执行异常: {}", e)
            state["final_answer"] = (
                "抱歉，查询信息时出了点小问题。\n"
                "建议您稍后重试，或者换个方式描述您的问题。\n"
                "如果还是不行，可以联系人工客服，我会尽力帮您。"
            )
            state["error"] = str(e)[:200]
            return state

        final_answer = state.get("final_answer", "")
        if not final_answer or len(final_answer) < 10:
            state["final_answer"] = (
                f"关于「{query[:30]}...」，我暂时没有找到详细的资料。\n"
                "您可以看看产品说明书，或者换个关键词试试。\n"
                "如果还需要帮助，随时告诉我，我帮您联系客服人员。"
            )

        if len(final_answer) >= 10:
            await cache.set(query, final_answer)

        elapsed = time.time() - start_time
        if elapsed > 3.0:
            logger.warning("QAScenario 慢查询 latency={:.1f}s query={}", elapsed, query[:80])

        return state

    @staticmethod
    def _extract_query(state: dict) -> str:
        return extract_user_query(state)

    @staticmethod
    def _log_cache_hit(query: str):
        """记录缓存命中"""
        logger.info("语义缓存命中 query={}", query[:80])

    @classmethod
    def configure(cls, llm_client=None, retriever=None, semantic_cache=None, compressor=None):
        """手动配置场景依赖"""
        if llm_client or retriever:
            cls._rag_agent = RAGAgent(
                llm_client=llm_client,
                retriever=retriever,
                semantic_cache=semantic_cache,
                compressor=compressor,
            )
        if semantic_cache:
            cls._semantic_cache = semantic_cache
        if compressor:
            cls._compressor = compressor

    @classmethod
    def reset(cls):
        """重置所有单例（用于测试清理）"""
        cls._rag_agent = None
        cls._semantic_cache = None
        cls._compressor = None

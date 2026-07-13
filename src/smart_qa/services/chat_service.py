"""对话服务 — 智能问答的核心业务逻辑

提取自 api/routes.py 和 scenarios/qa_scenario.py，
统一管理对话请求的完整处理链：
  安全检查 → 缓存查找 → RAG 检索 → 引用标注 → 反思 → 记忆写入
"""

import time
import uuid

from smart_qa.agent.agents.rag_agent import RAGAgent
from smart_qa.memory.cache import SemanticCache
from smart_qa.memory.short_term import MemoryCompressor
from smart_qa.models.chat_schema import ChatRequest, ChatResponse
from smart_qa.observability.logger import logger


class ChatService:
    """对话服务

    用法:
        service = ChatService(llm_client=..., retriever=...)
        response = await service.process_chat(request)
    """

    def __init__(self, llm_client=None, retriever=None, semantic_cache=None, compressor=None):
        self.rag = RAGAgent(
            llm_client=llm_client,
            retriever=retriever,
            semantic_cache=semantic_cache,
            compressor=compressor,
        )
        self.cache = semantic_cache or SemanticCache()
        self.compressor = compressor or MemoryCompressor(llm_client=llm_client)

    async def process_chat(self, request: ChatRequest) -> ChatResponse:
        """处理普通对话请求"""
        query = request.message.strip()
        if not query:
            return ChatResponse(answer="请提供您的问题。", session_id=request.session_id or str(uuid.uuid4())[:12])

        session_id = request.session_id or str(uuid.uuid4())[:12]

        # 1. 缓存查找
        cached = await self.cache.get(query)
        if cached:
            return ChatResponse(answer=cached, session_id=session_id, intent="qa")

        # 2. RAG 检索与生成
        start = time.time()
        try:
            result = await self.rag.answer(query, user_id=request.user_id)
        except Exception as e:
            return ChatResponse(
                answer=f"抱歉，处理您的问题时遇到了错误：{str(e)[:100]}",
                session_id=session_id,
            )

        elapsed = time.time() - start
        if elapsed > 3.0:
            logger.warning("慢查询 latency={:.1f}s query={}", elapsed, query[:80])

        # 3. 写入缓存
        await self.cache.set(query, result.get("answer", ""))

        return ChatResponse(
            answer=result.get("answer", "抱歉，未能找到相关信息。"),
            session_id=session_id,
            intent=result.get("source", "general"),
        )

    async def process_stream(self, request: ChatRequest):
        """处理 SSE 流式对话 — 返回初始状态供 graph.astream_events 处理"""
        return {
            "messages": [{"role": "user", "content": request.message}],
            "user_id": request.user_id,
            "session_id": request.session_id or str(uuid.uuid4())[:12],
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

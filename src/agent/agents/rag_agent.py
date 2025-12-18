"""RAG Agent — 基于检索增强生成的知识问答

核心工作流:
  1. 接收用户 query，理解真实信息需求
  2. 调用四层召回 (语义->改写->BM25->LLM) 检索知识库
  3. 对检索结果进行重排序和去重 (MMR)
  4. 组装上下文，注入 CoT prompt 模板，调用 LLM 生成回答
  5. 对回答进行引用标注和幻觉检测
  6. 自我反思检查，必要时改进回答
  7. 将结果写入语义缓存和短期记忆

技术要点:
  - MultiLayerRetriever: 四层召回的协调器
  - CitationTracker: 为回答标注知识来源
  - HallucinationGuard: 检测并拦截幻觉回答
  - ReflectionAgent: 自我反思改进回答质量
  - MemoryCompressor: 压缩对话历史并更新用户画像
"""

from typing import Any

from src.agent.agents.reflection import ReflectionAgent
from src.agent.persona import get_system_prompt
from src.agent.prompts.loader import load_cot_prompt
from src.knowledge.vector_store import get_embedding
from src.memory.cache import SemanticCache
from src.memory.short_term import MemoryCompressor, Message
from src.observability.logger import logger
from src.rag.citation import CitationTracker, HallucinationGuard
from src.rag.retrieval import MultiLayerRetriever
from src.agent.state_utils import extract_user_query


class RAGAgent:
    """RAG 知识问答 Agent

    职责: 接收用户问题 -> 检索知识 -> 生成回答 -> 质量检查 -> 返回结果

    用法:
        agent = RAGAgent(llm_client=llm, retriever=retriever)
        result = await agent.retrieve_and_generate(state)
    """

    def __init__(
        self,
        llm_client=None,
        retriever: MultiLayerRetriever | None = None,
        semantic_cache: SemanticCache | None = None,
        compressor: MemoryCompressor | None = None,
    ):
        """
        Args:
            llm_client: LangChain LLM 客户端 (ChatOpenAI 等)
            retriever: 四层检索器，不传则创建默认实例
            semantic_cache: 语义缓存，用于判断高频问题
            compressor: 记忆压缩器，用于写入短期记忆
        """
        self.llm = llm_client
        self.retriever = retriever or MultiLayerRetriever(llm_client=llm_client)
        self.cache = semantic_cache or SemanticCache()
        self.compressor = compressor or MemoryCompressor(llm_client=llm_client)
        self.citation_tracker = CitationTracker()
        self.reflection = ReflectionAgent(llm_client=llm_client, max_refine_rounds=3)
        self.embedding = get_embedding()

    async def retrieve_and_generate(self, state: dict) -> dict:
        """执行 RAG 问答流程

        这是供 LangGraph 场景节点调用的主入口。

        Args:
            state: AgentState 字典，需包含 messages 字段

        Returns:
            更新后的 state，包含:
              - retrieved_docs: 检索到的文档列表
              - final_answer: 最终回答内容
        """
        query = self._extract_query(state)
        if not query:
            state["final_answer"] = "请提供您的问题，我会尽力帮您解答。"
            return state

        # 从上一轮回答中提取话题词，注入检索查询（解决"多久洗一次"丢失上下文）
        enriched_query = self._enrich_query_with_history(query, state)

        try:
            cot_prompt = load_cot_prompt("rag")
        except FileNotFoundError:
            cot_prompt = ""

        logger.info("开始检索 query={} enriched={}", query[:40], enriched_query[:60])
        retrieval_result = self.retriever.retrieve(enriched_query, top_k=5)

        docs = retrieval_result.get("docs", [])
        retrieval_source = retrieval_result.get("source", "L4_llm")
        logger.info("检索完成 source={} hits={}", retrieval_source, len(docs))
        state["retrieved_docs"] = docs

        if docs:
            self.citation_tracker.register_docs(docs)

        history = self._extract_history(state)
        context = self._build_context(query, docs, history)

        draft_answer = await self._generate_answer(query, context, cot_prompt)

        cited_result = self.citation_tracker.build_cited_answer(query, draft_answer)

        if HallucinationGuard.should_block(cited_result, threshold="high"):
            final_answer = HallucinationGuard.generate_safe_response(cited_result)
        else:
            final_answer = cited_result.get("text", draft_answer)

        # 自我反思改进 (L4 兜底时跳过——无文档可验证，反思无意义)
        if docs and retrieval_source != "L4_llm":
            refined = await self.reflection.refine_answer(
                query=query,
                draft_answer=final_answer,
                context={"docs": docs},
            )
            final_answer = refined.get("final_answer", final_answer)
        else:
            refined = {"final_answer": final_answer, "confidence": 0.7}

        final_answer = refined.get("final_answer", final_answer)

        logger.info("写入缓存 query={}", query[:60])
        self.cache.set(query, final_answer)

        user_msg = Message(role="user", content=query)
        assistant_msg = Message(role="assistant", content=final_answer)

        existing = state.get("short_term")
        if existing and hasattr(existing, "recent_messages"):
            all_msgs = existing.recent_messages + [user_msg, assistant_msg]
        else:
            all_msgs = [user_msg, assistant_msg]

        compressed = await self.compressor.compress(all_msgs)

        state["final_answer"] = final_answer
        state["short_term"] = {
            "summary": compressed.summary,
            "recent_messages": [{"role": m.role, "content": m.content[:200]} for m in compressed.recent_messages],
        }

        if compressed.user_profile_snapshot:
            profile = state.get("user_profile") or {}
            profile.update(compressed.user_profile_snapshot)
            state["user_profile"] = profile

        return state

    def _extract_query(self, state: dict) -> str:
        return extract_user_query(state)

    def _enrich_query_with_history(self, query: str, state: dict) -> str:
        """从上一轮对话提取话题词，注入短查询，解决上下文丢失

        "多久洗一次？" → 上文聊滤网 → "滤网 清洗频率 多久洗一次"
        """
        # 如果当前查询已经足够长且具体，不需要增强
        if len(query) >= 10:
            return query

        messages = state.get("messages", [])
        if len(messages) < 2:
            return query

        # 从上一轮助手回答中提取关键词
        last_assistant = ""
        for msg in reversed(messages[:-1]):
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
            if role in ("assistant", "ai") and content:
                last_assistant = content
                break

        if not last_assistant:
            return query

        # 提取产品/耗材关键词
        topic_keywords = [
            "边刷", "主刷", "滚刷", "拖布", "抹布", "滤网", "HEPA", "hepa",
            "集尘袋", "尘袋", "清洁液", "清洗液", "银离子", "阻垢剂",
            "清洗盘", "基站", "水箱", "清水箱", "污水箱", "充电座", "充电触点",
            "驱动轮", "万向轮", "传感器", "激光雷达", "防撞条",
            "尘盒", "X30 Pro", "X30",
        ]
        found = []
        for kw in topic_keywords:
            if kw.lower() in last_assistant.lower():
                found.append(kw)

        if found:
            enriched = " ".join(found[:3]) + " " + query
            logger.info("检索查询增强 query={} -> enriched={}", query[:30], enriched[:50])
            return enriched
        return query

    def _extract_history(self, state: dict) -> str:
        """提取最近 3 轮对话历史"""
        messages = state.get("messages", [])
        if len(messages) <= 1:
            return ""
        recent = messages[-7:]
        lines = []
        for msg in recent[:-1]:
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
            if role == "user" or role == "human":
                lines.append(f"用户: {content[:100]}")
            elif role == "assistant" or role == "ai":
                lines.append(f"助手: {content[:100]}")
        return "\n".join(lines) if lines else ""

    def _build_context(self, query: str, docs: list[dict], history: str = "") -> str:
        """组装 LLM 上下文 — 不再暴露调试标记

        修复: 之前输出 [检索来源: L1_semantic] 和 [文档N] 标记，
        与 persona 要求"不要用'根据知识库'等后台术语"冲突。
        现在改为自然语气引出参考资料。
        """
        parts = []

        if docs:
            parts.append("以下是与您问题相关的参考信息：\n")
            for i, doc in enumerate(docs[:5], 1):
                content = doc.get("content", "")[:500]
                if content:
                    parts.append(f"• {content}")
        else:
            parts.append("[按常识回答]")

        if history:
            parts.append(f"\n\n对话历史：\n{history}")

        parts.append(f"\n\n用户问题：{query}")
        return "\n".join(parts)

    async def _generate_answer(self, query: str, context: str, cot_prompt: str) -> str:
        """调用 LLM 生成回答"""
        if not self.llm:
            return f"关于「{query[:30]}...」，我暂时没有找到相关的资料。您可以看看产品说明书，或者联系客服获取更多帮助。"

        system_prompt = get_system_prompt("qa")

        if cot_prompt:
            system_prompt += f"\n\n思考步骤:\n{cot_prompt}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            return self._clean_output(content)
        except Exception as e:
            logger.error("LLM 调用失败: {}", e)
            return "抱歉，处理您的问题时遇到了一点小问题，请稍后重试或联系人工客服。"

    @staticmethod
    def _clean_output(text: str) -> str:
        """过滤内部调试标记，清理输出"""
        import re
        text = re.sub(r"\[来源[：:][^\]]*\]", "", text)
        text = re.sub(r"\[无来源\]", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # -- 便捷方法: 独立使用（不依赖 LangGraph state）--

    async def answer(self, query: str, user_id: str = "anonymous") -> dict[str, Any]:
        """独立问答接口（不依赖 AgentState）

        Args:
            query: 用户问题
            user_id: 用户 ID（用于缓存）

        Returns:
            {
                "answer": str,
                "docs": list,
                "source": str,
                "hallucination_risk": str,
                "confidence": float,
            }
        """
        cached = self.cache.get(query)
        if cached:
            return {
                "answer": cached,
                "docs": [],
                "source": "cache",
                "hallucination_risk": "low",
                "confidence": 0.99,
            }

        result = self.retriever.retrieve(query, top_k=5)
        docs = result.get("docs", [])

        context = self._build_context(query, docs)
        draft = await self._generate_answer(query, context, load_cot_prompt("rag"))

        if docs:
            self.citation_tracker.register_docs(docs)
        cited = self.citation_tracker.build_cited_answer(query, draft)
        answer = cited.get("text", draft)

        refined = await self.reflection.refine_answer(query, answer, {"docs": docs} if docs else None)

        self.cache.set(query, refined["final_answer"])

        return {
            "answer": refined["final_answer"],
            "docs": docs,
            "source": result.get("source", "L4_llm"),
            "hallucination_risk": cited.get("hallucination_risk", "unknown"),
            "confidence": refined.get("confidence", 0.7),
        }

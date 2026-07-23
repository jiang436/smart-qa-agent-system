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

from smart_qa.agent.agents.reflection import ReflectionAgent
from smart_qa.agent.persona import get_system_prompt
from smart_qa.agent.prompts.loader import load_cot_prompt
from smart_qa.agent.state_utils import extract_user_query
from smart_qa.config import settings
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.memory.cache import SemanticCache
from smart_qa.memory.short_term import MemoryCompressor, Message
from smart_qa.observability.logger import logger
from smart_qa.rag.citation import CitationTracker, HallucinationGuard
from smart_qa.rag.retrieval import MultiLayerRetriever


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
        enriched_query = await self._enrich_query_with_history(query, state)

        try:
            cot_prompt = load_cot_prompt("rag")
        except FileNotFoundError:
            cot_prompt = ""

        logger.info("开始检索 query={} enriched={}", query[:40], enriched_query[:60])

        # ── C-RAG: 检索 → 评估 → 修正 ──
        retrieval_result, docs, retrieval_source = await self._crag_retrieve(
            enriched_query, top_k=settings.retrieval_top_k, max_retries=settings.retrieval_crag_max_retries
        )

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

        # L4 兜底时标注来源（无检索文档 → 基于模型自身知识）
        if retrieval_source == "L4_llm" and not final_answer.startswith("（提示："):
            final_answer = (
                "（提示：以下内容基于通用知识，知识库中暂无精确匹配的文档。）\n\n"
                + final_answer
            )

        logger.info("写入缓存 query={}", query[:60])
        citations = [
            {"doc_id": str(d.get("doc_id", i)), "source": d.get("source", ""), "matched_sentence": (d.get("content", "") or "")[:200]}
            for i, d in enumerate(docs[:5]) if d.get("content")
        ]
        await self.cache.set(query, final_answer, citations)

        user_msg = Message(role="user", content=query)
        assistant_msg = Message(role="assistant", content=final_answer)

        existing = state.get("short_term")
        if isinstance(existing, dict) and "recent_messages" in existing:
            all_msgs = [Message(role=m["role"], content=m["content"]) for m in existing["recent_messages"]]
            all_msgs += [user_msg, assistant_msg]
        elif existing and hasattr(existing, "recent_messages"):
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

    async def _enrich_query_with_history(self, query: str, state: dict) -> str:
        """参照 RAGFlow full_question: LLM 重写追问为完整独立查询"""
        if len(query) > 15:
            return query
        if not self.llm:
            return query

        messages = state.get("messages", [])
        logger.info("查询重写检查: query={} msgs={}", query[:30], len(messages))
        if len(messages) < 3:
            return query

        # 构建对话历史文本（取最近6条=3轮）
        history_lines = []
        for msg in messages[:-1]:  # 排除当前用户消息
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "user":
                history_lines.append(f"用户：{content}")
            elif role in ("assistant", "ai"):
                history_lines.append(f"助手：{content[:300]}")
        history = "\n".join(history_lines[-6:])

        try:
            prompt = (
                "根据对话历史，把用户最新问题改写为完整独立的问题，补全所有代词和省略信息。\n"
                "只输出改写后的问题，不要解释。\n\n"
                f"对话历史：\n{history}\n\n"
                f"最新问题：{query}\n"
                "改写后："
            )
            resp = await self.llm.ainvoke(prompt)
            rewritten = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if rewritten and len(rewritten) <= 100 and rewritten != query:
                logger.info("查询重写: {} -> {}", query[:30], rewritten[:80])
                return rewritten
        except Exception as e:
            logger.debug("查询重写失败: {}", e)

        return query

    async def _crag_retrieve(
        self, query: str, top_k: int = 5, max_retries: int = 2
    ) -> tuple[dict, list[dict], str]:
        """C-RAG: 检索 → 评估 → 修正循环

        核心逻辑（来自 Datawhale RAG 指南 §4.5 校正检索）:
          1. 检索文档
          2. 评估质量 — 如果文档与问题高度相关 → 直接使用
          3. 质量不足 → 查询改写 → 重新检索（最多重试 N 次）
          4. 多次重试仍差 → 标记为 L4_llm 兜底

        Returns:
            (retrieval_result, docs, source_label)
        """
        retrieval_result = await self.retriever.retrieve_async(query, top_k=top_k)
        docs = retrieval_result.get("docs", [])
        source = retrieval_result.get("source", "L4_llm")

        # 快速预判：有足够文档 + 置信度高 → 跳过评估
        if len(docs) >= 3 and retrieval_result.get("confidence") == "high":
            return retrieval_result, docs, source

        # 质量评估
        quality_ok = self._check_retrieval_quality(query, docs)

        retry = 0
        while not quality_ok and retry < max_retries:
            retry += 1
            logger.info("C-RAG: 检索质量不足, 改写重试 ({}/{})", retry, max_retries)

            # 改写查询
            if self.llm:
                rewritten = self.retriever._rewrite_query(query) if hasattr(self.retriever, "_rewrite_query") else None
            else:
                rewritten = None
            if not rewritten:
                break

            retrieval_result = await self.retriever.retrieve_async(rewritten, top_k=top_k)
            docs = retrieval_result.get("docs", [])
            source = retrieval_result.get("source", "L2_rewrite")
            quality_ok = self._check_retrieval_quality(query, docs)

        if not quality_ok:
            logger.warning("C-RAG: {} 次重试后检索质量仍不足 → 降级 LLM 自身知识", retry)
            retrieval_result["confidence"] = "low"
            retrieval_result["source"] = "L4_llm"
            retrieval_result["note"] = (retrieval_result.get("note", "") + " | C-RAG 降级 LLM 兜底").strip()

        return retrieval_result, docs, retrieval_result.get("source", source)

    def _check_retrieval_quality(self, query: str, docs: list[dict]) -> bool:
        """评估检索质量 — 文档是否与 query 相关

        判断标准:
          1. ReRank 最高分 ≥ 0.5 → 质量 OK
          2. 有 ≥ 2 条文档且最高分 ≥ 0.3 → OK
          3. 其他 → 质量不足
        """
        if not docs:
            return False

        # ReRank 分优先（0-1 归一化），原始分做参考
        top_rerank = max((d.get("rerank_score", 0) or 0) for d in docs)
        top_score = top_rerank if top_rerank > 0 else max(
            (d.get("score", 0) or 0) for d in docs
        )
        # 原始 BM25 分 (>1) 映射到 0-1 区间
        if top_score > 1:
            top_score = min(top_score / 20.0, 1.0)

        if top_score >= 0.5:
            return True
        if len(docs) >= 2 and top_score >= 0.3:
            return True

        logger.debug("C-RAG 评估: quality=low top_score={:.3f} docs={}", top_score, len(docs))
        return False

    def _compress_docs(self, query: str, docs: list[dict]) -> list[dict]:
        """上下文压缩 — 一次 LLM 调用批量压缩所有文档

        比逐篇调用快 5 倍（5 次 → 1 次 API 调用）。
        """
        if not self.llm or not docs:
            return docs

        # 短文档直接保留（提高到 400 字确保产品规格段不被压缩误删标题）
        short = [d for d in docs if len(d.get("content", "")) < 400]
        to_compress = [d for d in docs if len(d.get("content", "")) >= 400]

        if not to_compress:
            return docs

        # 构建批量 prompt
        docs_block = ""
        for i, doc in enumerate(to_compress[:5]):
            docs_block += f"[文档{i}]\n{doc.get('content', '')[:500]}\n\n"

        try:
            prompt = (
                "从以下文档中，逐篇提取与用户问题**直接相关**的句子。无关的整篇丢弃（标记 NONE）。\n"
                "保持原文不变，不要改写。\n\n"
                f"用户问题：{query}\n\n"
                f"{docs_block}"
                "输出格式（每篇一段）:\n"
                "[文档0] 相关句子\n"
                "[文档0] NONE   ← 表示这篇全都不相关\n"
                "[文档1] 相关句子\n"
                "..."
            )
            resp = self.llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)

            # 解析批量结果
            import re
            compressed = list(short)
            for i, doc in enumerate(to_compress[:5]):
                pattern = rf"\[文档{i}\]\s*(.+)"
                m = re.search(pattern, text)
                if m:
                    extracted = m.group(1).strip()
                    if "NONE" in extracted.upper():
                        logger.debug("文档丢弃 doc={}", i)
                    else:
                        new_doc = dict(doc)
                        new_doc["content"] = extracted
                        new_doc["compressed"] = True
                        compressed.append(new_doc)
                        if len(extracted) < len(doc.get("content", "")):
                            logger.debug("文档压缩 doc={} chars: {} → {}", i, len(doc.get("content", "")), len(extracted))
                else:
                    compressed.append(doc)
        except Exception as e:
            logger.debug("批量压缩失败: {}", e)
            return docs

        return compressed if compressed else docs

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
        """组装 LLM 上下文 — 知识检索 + 知识图谱 + 对话历史"""
        parts = []

        if docs:
            parts.append("以下是与您问题相关的参考信息：\n")
            for _i, doc in enumerate(docs[:5], 1):
                content = doc.get("content", "")[:500]
                if content:
                    parts.append(f"• {content}")
        else:
            parts.append("（未找到相关资料，请根据产品常识谨慎回答，不要编造技术参数）")

        # 知识图谱补充
        try:
            from smart_qa.knowledge.knowledge_graph import get_kg

            kg_context = get_kg().augment_context(query)
            if kg_context:
                parts.append(f"\n\n{kg_context}")
        except Exception:
            pass

        if history:
            parts.append(f"\n\n对话历史：\n{history}")

        parts.append(f"\n\n用户问题：{query}")
        return "\n".join(parts)

    async def _generate_answer(self, query: str, context: str, cot_prompt: str) -> str:
        """调用 LLM 流式生成回答"""
        if not self.llm:
            return (
                f"关于「{query[:30]}...」，我暂时没有找到相关的资料。您可以看看产品说明书，或者联系客服获取更多帮助。"
            )

        system_prompt = get_system_prompt("qa")
        if cot_prompt:
            system_prompt += f"\n\n思考步骤:\n{cot_prompt}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        try:
            # 真流式：astream token by token
            full_text = ""
            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    full_text += chunk.content
            return self._clean_output(full_text) if full_text else ""
        except Exception:
            # astream 失败降级 ainvoke
            try:
                response = await self.llm.ainvoke(messages)
                content = response.content if hasattr(response, "content") else str(response)
                return self._clean_output(content)
            except Exception as e2:
                logger.error("LLM 调用失败: {}", e2)
                return "抱歉，处理您的问题时遇到了一点小问题，请稍后重试或联系人工客服。"

    @staticmethod
    def _clean_output(text: str) -> str:
        """清理输出格式，保留引用标注"""
        import re

        # 保留 [来源: xxx] 和 [无来源] 标记供用户参考
        # 仅清理多余空行
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
        cached = await self.cache.get(query)
        if cached:
            return {
                "answer": cached,
                "docs": [],
                "source": "cache",
                "hallucination_risk": "low",
                "confidence": 0.99,
            }

        result = await self.retriever.retrieve_async(query, top_k=5)
        docs = result.get("docs", [])

        context = self._build_context(query, docs)
        draft = await self._generate_answer(query, context, load_cot_prompt("rag"))

        if docs:
            self.citation_tracker.register_docs(docs)
        cited = self.citation_tracker.build_cited_answer(query, draft)
        answer = cited.get("text", draft)

        refined = await self.reflection.refine_answer(query, answer, {"docs": docs} if docs else None)

        await self.cache.set(query, refined["final_answer"])

        return {
            "answer": refined["final_answer"],
            "docs": docs,
            "source": result.get("source", "L4_llm"),
            "hallucination_risk": cited.get("hallucination_risk", "unknown"),
            "confidence": refined.get("confidence", 0.7),
        }

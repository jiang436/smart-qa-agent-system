"""HyDE — Hypothetical Document Embeddings

核心思路:
  直接用 query 去搜向量库 → 语义可能不匹配
  让 LLM 先根据 query 生成一段假设答案 → 再用假设答案去搜
  → 假设答案和真实知识库的语义更接近, 召回效果更好

流程:
  query → LLM 生成假设文档 → embedding → 向量检索 (HyDE)
                                  +
  query → embedding → 向量检索 (原始)
                    ↓
              RRF 融合 → top_k

面试阐述:
  "HyDE 解决的是 query 和文档之间的 semantic gap。
   用户说'扫地机不走了', 知识库里写的是'设备停止工作的原因',
   直接搜可能匹配不到。我让 LLM 先生成一个假设答案——
   '扫地机器人可能因为电量耗尽、轮子卡住或传感器故障而停止工作'——
   再用这个假设答案去搜, 命中率明显提升。"

Usage:
    hyde = HyDERetriever(llm=llm, embedding=embed)
    docs = hyde.retrieve("扫地机不走了")
"""

from src.observability.logger import logger


class HyDERetriever:
    """HyDE 检索增强器

    生成假设文档 → embedding → 检索 → 与原始 query 结果融合
    """

    def __init__(self, llm_client=None, embedding_model=None, retriever=None):
        self.llm = llm_client
        self.embedding = embedding_model
        self.retriever = retriever  # MultiLayerRetriever

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """HyDE 检索: 假设文档 + 原始 query 两路融合

        Returns:
            融合后的文档列表
        """
        # 1. 生成假设文档
        hypothetical = self._generate_hypothetical(query)

        if not hypothetical:
            # 降级: 直接用原始 query 检索
            logger.warning("HyDE 生成失败, 降级原 query 检索")
            if self.retriever:
                result = self.retriever.retrieve(query, top_k)
                return result.get("docs", [])
            return []

        logger.info("HyDE hypothetical doc len={}", len(hypothetical))

        # 2. 假设文档 embedding 检索
        hyde_docs = self._search_with_text(hypothetical, top_k * 2)

        # 3. 原始 query 检索
        original_docs = self._search_with_text(query, top_k * 2)

        # 4. RRF 融合
        fused = self._rrf_merge(original_docs, hyde_docs, top_k)

        logger.info("HyDE result original={} hyde={} fused={}", len(original_docs), len(hyde_docs), len(fused))
        return fused

    # ── 假设文档生成 ──

    def _generate_hypothetical(self, query: str) -> str | None:
        """LLM 生成假设文档

        让 LLM 假装自己是知识库, 写一段可能回答这个问题的文档。
        这段假设文档的语义向量会"拉近"query 和真实知识库的距离。
        """
        if not self.llm:
            return None

        prompt = (
            "你是一个扫地机器人技术专家。请用一段专业文档风格的内容"
            "回答以下问题。不需要真的准确, 只需要看起来像知识库里会有的文字。\n\n"
            f"问题: {query}\n\n"
            "假设文档:"
        )
        try:
            response = self.llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            return text.strip()[:500]
        except Exception as e:
            logger.warning("HyDE 生成失败: {}", e)
            return None

    # ── 检索辅助 ──

    def _search_with_text(self, text: str, top_k: int) -> list[dict]:
        """用指定文本检索"""
        if not self.embedding:
            return []
        try:
            vec = self.embedding.encode(text)

            # 如果有 retriever, 用 retriever 的语义检索
            if self.retriever and self.retriever.milvus:
                return self.retriever._semantic_search(text, top_k)

            # 否则只能返回空
            return []
        except Exception as e:
            logger.warning("HyDE 检索失败: {}", e)
            return []

    # ── RRF 融合 ──

    def _rrf_merge(self, docs_a: list[dict], docs_b: list[dict], top_k: int, k: int = 60) -> list[dict]:
        """RRF 融合两路检索结果"""
        if not docs_a and not docs_b:
            return []
        if not docs_a:
            return docs_b[:top_k]
        if not docs_b:
            return docs_a[:top_k]

        scores: dict[str, dict] = {}
        for lst in [docs_a, docs_b]:
            for rank, doc in enumerate(lst, start=1):
                key = doc.get("content", "")[:200].strip()
                rrf = 1.0 / (k + rank)
                if key in scores:
                    scores[key]["rrf"] += rrf
                else:
                    scores[key] = {**doc, "rrf": rrf}

        ranked = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)
        return ranked[:top_k]

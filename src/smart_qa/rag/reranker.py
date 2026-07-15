"""Reranker — 检索结果重排序

为什么需要 Reranker?

  问题: 语义检索 top_k=20 虽然召回率高, 但夹带噪音。
       取大了噪音多, 取小了漏信息。
  答案: Reranker 对 query-doc 对做精确打分,
        从 top_k=20 精选出 top_k=3, 首条命中率从 ~65% 提升到 ~90%。

三种后端:
  - llm:   LLM API 打分（免下载，默认）
  - local: 本地 Cross-Encoder（需下载 bge-reranker-v2-m3）
  - 自动降级: 启发式关键词匹配

Usage:
    reranker = Reranker(llm_client=llm)
    top3 = reranker.rerank(query, docs_top20, top_k=3)
"""

import re

from smart_qa.observability.logger import logger


class Reranker:
    """检索重排序器

    默认 LLM API 打分（免下载），可切换到本地 Cross-Encoder。

    流程:
      query + doc → LLM/Cross-Encoder → relevance_score → 排序 → top_k
    """

    def __init__(
        self,
        llm_client=None,
        backend: str = "local",
        model_name: str = "BAAI/bge-reranker-v2-m3",
    ):
        self.llm = llm_client
        self.backend = backend
        self.model_name = model_name
        self._model = None
        self._local_available = None  # None=未尝试, True=可用, False=不可用

        # 本地模型已下载 → 启动时即加载
        if self.backend == "local":
            self._ensure_local()

    def _ensure_local(self):
        """懒加载 Cross-Encoder，不调用不下载"""
        if self._local_available is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            self._local_available = True
            logger.info("Reranker 本地模型已加载 model={}", self.model_name)
        except Exception as e:
            logger.warning("Reranker 本地模型不可用，降级: {}", e)
            self._local_available = False

    def rerank(self, query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
        """对检索结果重排序"""
        if not docs:
            return []

        if len(docs) <= top_k:
            for d in docs:
                d["rerank_score"] = d.get("score", 0)
            return docs

        # 选后端: llm > local > heuristic
        if self.backend == "llm" and self.llm:
            scores = self._llm_rerank(query, docs)
        elif self.backend == "local":
            self._ensure_local()
            if self._local_available and self._model:
                scores = self._cross_encoder_rerank(query, docs)
            else:
                scores = self._heuristic_rerank(query, docs)
        else:
            scores = self._heuristic_rerank(query, docs)

        for i, doc in enumerate(docs):
            doc["rerank_score"] = round(float(scores[i]), 4)

        ranked = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)
        result = ranked[:top_k]

        logger.info(
            "Reranker({}) top{} from {} docs top_score={:.3f}",
            self.backend,
            top_k,
            len(docs),
            result[0]["rerank_score"] if result else 0,
        )
        return result

    # ── LLM API 打分 ──

    def _llm_rerank(self, query: str, docs: list[dict]) -> list[float]:
        """LLM 批量打分 — 一次 API 调用评多篇文档

        将文档分组（每组最多 5 篇），一次 prompt 批量评分，
        N 篇文档只需 N/5 次 API 调用，比逐篇打分快 5 倍。
        """
        batch_size = 5
        all_scores: list[float] = []

        for batch_start in range(0, len(docs), batch_size):
            batch = docs[batch_start : batch_start + batch_size]
            # 构建批量 prompt
            docs_text = ""
            for i, doc in enumerate(batch):
                content = doc.get("content", "")[:300]
                docs_text += f"[{i}] {content}\n"

            prompt = (
                "评估以下文档与用户问题的相关性，为每篇文档输出 0-1 之间的分数。\n"
                f"用户问题：{query}\n\n"
                f"{docs_text}\n"
                "请按格式输出（每行一个）：[编号] 分数\n"
                "例如：[0] 0.85"
            )
            try:
                resp = self.llm.invoke(prompt)
                text = resp.content if hasattr(resp, "content") else str(resp)
                # 解析 [N] score 格式
                batch_scores = self._parse_batch_scores(text, len(batch))
                all_scores.extend(batch_scores)
            except Exception as e:
                logger.debug("LLM batch rerank 失败: {}", e)
                all_scores.extend([0.5] * len(batch))

        return all_scores

    def _parse_batch_scores(self, text: str, expected: int) -> list[float]:
        """解析 LLM 批量打分输出"""
        scores = []
        for i in range(expected):
            pattern = rf"\[{i}\]\s*(\d+\.?\d*)"
            m = re.search(pattern, text)
            if m:
                score = min(max(float(m.group(1)), 0), 1)
            else:
                score = 0.5
            scores.append(score)
        return scores

    # ── Cross-Encoder 打分 ──

    def _cross_encoder_rerank(self, query: str, docs: list[dict]) -> list[float]:
        """Cross-Encoder 批量打分"""
        pairs = [(query, doc.get("content", "")) for doc in docs]
        try:
            scores = self._model.predict(pairs, batch_size=8, show_progress_bar=False)
            return list(scores)
        except Exception as e:
            logger.warning("Cross-Encoder 打分失败, 降级: {}", e)
            return self._heuristic_rerank(query, docs)

    # ── 启发式降级 ──

    def _heuristic_rerank(self, query: str, docs: list[dict]) -> list[float]:
        """启发式重排序 — 无模型时的降级方案"""
        query_terms = self._tokenize(query)
        scores = []
        for doc in docs:
            content = doc.get("content", "")
            header = doc.get("header", "")
            doc_terms = set(self._tokenize(content))
            overlap = len(query_terms & doc_terms) / max(len(query_terms | doc_terms), 1)
            exact_bonus = 0.0
            patterns = re.findall(r"[A-Z]\d{2,4}\s*(?:Pro|Max)?|[Ee]\d{2,3}", query)
            for p in patterns:
                if p in content:
                    exact_bonus += 0.3
            header_bonus = 0.0
            if header and any(t in header for t in query_terms if len(t) > 1):
                header_bonus = 0.2
            vector_score = doc.get("score", 0)
            if vector_score > 1:
                vector_score = min(vector_score / 10.0, 1.0)
            score = vector_score * 0.4 + overlap * 0.3 + exact_bonus + header_bonus
            scores.append(score)
        return scores

    def _tokenize(self, text: str) -> set[str]:
        cn_words = set(re.findall(r"[一-鿿]{1,4}", text.lower()))
        en_words = set(re.findall(r"[a-zA-Z\d]+", text.lower()))
        return cn_words | en_words

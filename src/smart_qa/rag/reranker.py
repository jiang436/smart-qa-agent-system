"""Reranker — 检索结果重排序

双阶段检索的第二阶段:
  Stage 1: Bi-Encoder 召回 top-20 (高召回)
  Stage 2: Cross-Encoder 精排 top-3 (高精度)

模型不可用时自动降级到启发式分数（关键词重叠 + 精确匹配 + 标题加权）。
"""

from __future__ import annotations

import re

from smart_qa.observability.logger import logger


class Reranker:
    """检索重排序器

    单例模式: 模型下载只尝试一次，成功后全局复用。
    后续所有 Reranker() 返回同一个实例。
    """

    _instance: Reranker | None = None
    _model = None
    _cross_encoder_available = True

    def __new__(cls, model_name: str = "BAAI/bge-reranker-v2-m3"):
        if cls._instance is not None:
            return cls._instance
        instance = super().__new__(cls)
        instance.model_name = model_name
        instance._model = None
        instance._cross_encoder_available = True

        # 先尝试本地缓存（避免不可达镜像站导致 30s+ 超时）
        try:
            from sentence_transformers import CrossEncoder

            instance._model = CrossEncoder(model_name, local_files_only=True)
            logger.info("Reranker 已加载 model={} (from cache)", model_name)
        except Exception:
            # 缓存不存在 → 尝试在线下载
            try:
                from sentence_transformers import CrossEncoder

                instance._model = CrossEncoder(model_name)
                logger.info("Reranker 已加载 model={} (downloaded)", model_name)
            except Exception as e:
                logger.warning("Reranker Cross-Encoder 不可用, 降级启发式: {}", e)
                instance._cross_encoder_available = False

        cls._instance = instance
        return instance

    def rerank(self, query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
        if not docs:
            return []
        if len(docs) <= top_k:
            for d in docs:
                d["rerank_score"] = d.get("score", 0)
            return docs

        if self._cross_encoder_available and self._model:
            scores = self._cross_encoder_rerank(query, docs)
        else:
            scores = self._heuristic_rerank(query, docs)

        for i, doc in enumerate(docs):
            doc["rerank_score"] = round(float(scores[i]), 4)
        ranked = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)
        result = ranked[:top_k]

        logger.info(
            "Reranker top{} from {} docs top_score={:.3f}",
            top_k, len(docs),
            result[0]["rerank_score"] if result else 0,
        )
        return result

    # ── Cross-Encoder 打分 ──

    def _cross_encoder_rerank(self, query: str, docs: list[dict]) -> list[float]:
        pairs = [(query, doc.get("content", "")) for doc in docs]
        try:
            scores = self._model.predict(pairs, batch_size=8, show_progress_bar=False)
            return list(scores)
        except Exception as e:
            logger.warning("Cross-Encoder 失败, 降级启发式: {}", e)
            return self._heuristic_rerank(query, docs)

    # ── 启发式降级 ──

    def _heuristic_rerank(self, query: str, docs: list[dict]) -> list[float]:
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

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        cn_words = set(re.findall(r"[一-鿿]{1,4}", text.lower()))
        en_words = set(re.findall(r"[a-zA-Z\d]+", text.lower()))
        return cn_words | en_words

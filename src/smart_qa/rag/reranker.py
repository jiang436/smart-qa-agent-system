"""Reranker — 检索结果重排序（参考 RAGFlow 设计）

三种后端 + 自动降级：
  - cross-encoder: 本地 BGE-Reranker-v2-m3 Cross-Encoder（默认，最准）
  - llm:           LLM API 批量打分（免下载，略慢）
  - heuristic:     关键词 + 精确匹配 + 向量分混合（纯规则，零依赖）

核心设计：
  1. 所有后端得分统一归一化到 [0, 1]
  2. 最终分 = 0.7 × 模型分 + 0.3 × 关键词重叠分
  3. Cross-Encoder 不可用 → 自动降级 LLM → heuristic

Usage:
    from smart_qa.rag.reranker import Reranker

    reranker = Reranker()                       # 默认 cross-encoder
    reranker = Reranker(backend="llm", llm=llm) # LLM 打分
    top5 = reranker.rerank(query, docs, top_k=5)
"""

from __future__ import annotations

import re
from typing import Any

from smart_qa.observability.logger import logger


class Reranker:
    """检索重排序器 — 三后端可插拔 + 自动降级"""

    def __init__(
        self,
        backend: str = "cross-encoder",
        llm_client: Any = None,
        model_name: str = "BAAI/bge-reranker-base",
    ):
        """
        Args:
            backend: "cross-encoder" | "llm" | "heuristic"
            llm_client: LLM 客户端（backend="llm" 时必需）
            model_name: Cross-Encoder 模型名
        """
        self.backend = backend
        self.llm = llm_client
        self.model_name = model_name
        self._model = None
        self._ce_available: bool | None = None  # None=未尝试, True/False=已确认

        # RAGFlow 风格混合权重
        self.model_weight: float = 0.7
        self.token_weight: float = 0.3

    # ═══════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════

    def rerank(self, query: str, docs: list[dict], top_k: int = 5) -> list[dict]:
        """对检索结果重排序

        流程:
          1. 选择后端（cross-encoder > llm > heuristic）
          2. 模型打分为每篇文档产生 [0,1] 分数
          3. 计算关键词重叠分
          4. 混合: final = model_weight × model_score + token_weight × token_score
          5. 排序 + top_k 截断
        """
        if not docs:
            return []
        if len(docs) <= top_k:
            for d in docs:
                d["rerank_score"] = d.get("score", 0)
            return docs

        # 1. 模型分
        model_scores = self._get_model_scores(query, docs)

        # 2. 关键词重叠分
        token_scores = self._get_token_scores(query, docs)

        # 3. 混合
        for i, doc in enumerate(docs):
            doc["rerank_score"] = round(
                self.model_weight * model_scores[i] + self.token_weight * token_scores[i], 4
            )

        # 4. 排序 + top_k
        ranked = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)
        result = ranked[:top_k]

        logger.info(
            "Reranker({}) top{} from {} docs best={:.3f}",
            self._active_backend(),
            top_k,
            len(docs),
            result[0]["rerank_score"],
        )
        return result

    # ═══════════════════════════════════════
    # 后端选择 + 自动降级
    # ═══════════════════════════════════════

    def _active_backend(self) -> str:
        if self.backend == "cross-encoder":
            self._ensure_cross_encoder()
            if self._ce_available and self._model:
                return "cross-encoder"
            elif self.llm:
                return "llm"
            return "heuristic"
        if self.backend == "llm" and self.llm:
            return "llm"
        return "heuristic"

    def _get_model_scores(self, query: str, docs: list[dict]) -> list[float]:
        backend = self._active_backend()
        if backend == "cross-encoder":
            scores = self._cross_encoder_score(query, docs)
        elif backend == "llm":
            scores = self._llm_score(query, docs)
        else:
            scores = self._heuristic_score(query, docs)
        return self._normalize(scores)

    # ═══════════════════════════════════════
    # Backend 1: Cross-Encoder
    # ═══════════════════════════════════════

    def _ensure_cross_encoder(self):
        if self._ce_available is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            self._ce_available = True
            logger.info("Reranker Cross-Encoder 已加载: {}", self.model_name)
        except Exception as e:
            logger.warning("Reranker Cross-Encoder 不可用，降级: {}", e)
            self._ce_available = False

    def _cross_encoder_score(self, query: str, docs: list[dict]) -> list[float]:
        pairs = [(query, doc.get("content", "")[:500]) for doc in docs]
        try:
            scores = self._model.predict(pairs, batch_size=8, show_progress_bar=False)
            return [float(s) for s in scores]
        except Exception as e:
            logger.warning("Cross-Encoder 打分失败，降级 heuristic: {}", e)
            return self._heuristic_score(query, docs)

    # ═══════════════════════════════════════
    # Backend 2: LLM 批量打分
    # ═══════════════════════════════════════

    def _llm_score(self, query: str, docs: list[dict]) -> list[float]:
        batch_size = 5
        all_scores: list[float] = []

        for start in range(0, len(docs), batch_size):
            batch = docs[start : start + batch_size]
            docs_text = ""
            for i, doc in enumerate(batch):
                docs_text += f"[{i}] {doc.get('content', '')[:300]}\n"

            prompt = (
                "评估以下文档与用户问题的相关性，为每篇输出 0-1 的分数。\n"
                f"用户问题：{query}\n\n{docs_text}\n"
                "按格式输出：[编号] 分数（如 [0] 0.85）"
            )
            try:
                resp = self.llm.invoke(prompt)
                text = resp.content if hasattr(resp, "content") else str(resp)
                batch_scores = self._parse_llm_scores(text, len(batch))
                all_scores.extend(batch_scores)
            except Exception as e:
                logger.warning("LLM batch rerank 失败: {}", e)
                all_scores.extend([0.5] * len(batch))

        return all_scores

    def _parse_llm_scores(self, text: str, expected: int) -> list[float]:
        scores = []
        for i in range(expected):
            m = re.search(rf"\[{i}\]\s*(\d+\.?\d*)", text)
            scores.append(min(max(float(m.group(1)), 0), 1) if m else 0.5)
        return scores

    # ═══════════════════════════════════════
    # Backend 3: Heuristic（多信号加权）
    # ═══════════════════════════════════════

    def _heuristic_score(self, query: str, docs: list[dict]) -> list[float]:
        query_terms = self._tokenize(query)
        query_patterns = re.findall(r"[A-Z]\d{2,4}\s*(?:Pro|Max)?|[Ee]\d{2,3}", query)

        scores = []
        for doc in docs:
            content = doc.get("content", "")
            header = doc.get("header", "") or doc.get("section", "")

            # 关键词 Jaccard 重叠
            doc_terms = self._tokenize(content)
            overlap = len(query_terms & doc_terms) / max(len(query_terms | doc_terms), 1)

            # 精确匹配加分（型号/错误码）
            exact_bonus = sum(0.3 for p in query_patterns if p in content)

            # 标题命中加分
            header_bonus = 0.2 if header and any(t in header for t in query_terms if len(t) > 1) else 0.0

            # 原始向量分归一化
            raw_score = doc.get("score", 0)
            vector_score = min(raw_score / 10.0, 1.0) if raw_score > 1 else raw_score

            # 加权组合
            score = 0.4 * vector_score + 0.4 * overlap + 0.2 * min(exact_bonus + header_bonus, 1.0)
            scores.append(min(score, 1.0))

        return scores

    # ═══════════════════════════════════════
    # 关键词重叠分（所有后端共享）
    # ═══════════════════════════════════════

    def _get_token_scores(self, query: str, docs: list[dict]) -> list[float]:
        """RAGFlow 风格 token_similarity：查询词在文档中的覆盖率"""
        query_terms = self._tokenize(query)
        if not query_terms:
            return [0.0] * len(docs)

        scores = []
        for doc in docs:
            content = doc.get("content", "")
            doc_terms = set(self._tokenize(content))
            overlap = sum(1 for t in query_terms if t in doc_terms)
            scores.append(round(overlap / len(query_terms), 4))
        return scores

    # ═══════════════════════════════════════
    # 分数归一化
    # ═══════════════════════════════════════

    @staticmethod
    def _normalize(scores: list[float]) -> list[float]:
        """Min-max 归一化到 [0, 1]（RAGFlow 风格）

        已在 [0, 1] 的分数保持不变，超出范围的进行 min-max 缩放。
        """
        if not scores:
            return scores
        mn, mx = min(scores), max(scores)
        # 所有分数已在 [0, 1] → 不缩放
        if mn >= 0 and mx <= 1:
            return scores
        # 无差异 → 全部置 0.5
        if mx - mn < 1e-10:
            return [0.5] * len(scores)
        # Min-max 到 [0, 1]
        return [round((s - mn) / (mx - mn), 4) for s in scores]

    # ═══════════════════════════════════════
    # 分词
    # ═══════════════════════════════════════

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        cn = set(re.findall(r"[一-鿿]{1,4}", text.lower()))
        en = set(re.findall(r"[a-zA-Z\d]+", text.lower()))
        return cn | en

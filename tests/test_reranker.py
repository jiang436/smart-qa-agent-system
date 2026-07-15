"""Reranker 测试 — 启发式降级模式"""

from smart_qa.rag.reranker import Reranker


class TestHeuristicReranker:
    def setup_method(self):
        self.reranker = Reranker.__new__(Reranker)
        self.reranker.model_name = "BAAI/bge-reranker-v2-m3"
        self.reranker._cross_encoder_available = False
        self.reranker._model = None

    def test_empty_docs_returns_empty(self):
        assert self.reranker.rerank("test", []) == []

    def test_less_docs_than_top_k(self, sample_docs):
        result = self.reranker.rerank("电池", sample_docs[:2], top_k=5)
        assert len(result) == 2

    def test_rerank_orders_by_relevance(self, sample_docs, sample_query):
        result = self.reranker.rerank(sample_query, sample_docs, top_k=3)
        assert len(result) == 3
        # 电池过热相关内容应该在前面
        assert "电池" in result[0]["content"]

    def test_rerank_score_field_added(self, sample_docs):
        result = self.reranker.rerank("Wi-Fi", sample_docs, top_k=2)
        for d in result:
            assert "rerank_score" in d

    def test_exact_match_boosted(self):
        docs = [
            {"content": "E05错误码表示传感器异常", "score": 0.3},
            {"content": "日常使用注意事项日常清洁保养", "score": 0.7},
        ]
        result = self.reranker.rerank("E05", docs, top_k=2)
        # E05 精确匹配应获得加分
        assert result[0]["rerank_score"] > 0

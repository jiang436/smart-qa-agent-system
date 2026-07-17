"""Reranker 测试 — 三后端 + 归一化 + 混合打分"""
import pytest
from unittest.mock import MagicMock, patch

from smart_qa.rag.reranker import Reranker


# ═══════════════════════════════════════
# Heuristic 后端
# ═══════════════════════════════════════


class TestHeuristicReranker:
    """Heuristic 模式 — 关键词 + 精确匹配 + 向量分混合"""

    def setup_method(self):
        self.reranker = Reranker(backend="heuristic")

    def test_empty_docs_returns_empty(self):
        assert self.reranker.rerank("test", []) == []

    def test_less_than_top_k(self, sample_docs):
        result = self.reranker.rerank("电池", sample_docs[:2], top_k=5)
        assert len(result) == 2

    def test_rerank_orders_by_relevance(self, sample_docs, sample_query):
        result = self.reranker.rerank(sample_query, sample_docs, top_k=3)
        assert len(result) == 3
        assert "电池" in result[0]["content"]

    def test_rerank_score_field_added(self, sample_docs):
        result = self.reranker.rerank("Wi-Fi", sample_docs, top_k=2)
        for d in result:
            assert "rerank_score" in d

    def test_exact_match_boosted(self):
        docs = [
            {"content": "E05 错误码表示传感器异常", "score": 0.3},
            {"content": "日常使用注意事项日常清洁保养", "score": 0.7},
        ]
        result = self.reranker.rerank("E05", docs, top_k=2)
        assert result[0]["rerank_score"] > 0

    def test_rerank_preserves_original_fields(self, sample_docs):
        result = self.reranker.rerank("test", sample_docs, top_k=3)
        for d in result:
            assert "content" in d
            assert "score" in d


# ═══════════════════════════════════════
# Token 重叠分
# ═══════════════════════════════════════


class TestTokenScores:
    """关键词重叠分"""

    def setup_method(self):
        self.reranker = Reranker(backend="heuristic")

    def test_perfect_overlap(self):
        scores = self.reranker._get_token_scores("边刷更换", [
            {"content": "边刷更换周期为3-6个月"},
        ])
        assert scores[0] > 0.5

    def test_no_overlap(self):
        scores = self.reranker._get_token_scores("XYZ未知词", [
            {"content": "边刷更换周期为3-6个月"},
        ])
        assert scores[0] == 0.0

    def test_empty_query(self):
        scores = self.reranker._get_token_scores("", [{"content": "test"}])
        assert scores[0] == 0.0


# ═══════════════════════════════════════
# 归一化
# ═══════════════════════════════════════


class TestNormalization:
    """分数归一化"""

    def test_already_normalized_unchanged(self):
        scores = [0.1, 0.5, 0.9]
        result = Reranker._normalize(scores)
        assert result == scores

    def test_minmax_rescaling(self):
        """范围外的分数 → min-max 缩放到 [0, 1]"""
        scores = [3.0, 5.0, 12.0]
        result = Reranker._normalize(scores)
        assert min(result) == 0.0
        assert max(result) == 1.0

    def test_negative_scores_rescaled(self):
        scores = [-2.0, 0.0, 2.0]
        result = Reranker._normalize(scores)
        assert min(result) == 0.0
        assert max(result) == 1.0

    def test_all_equal_scores(self):
        scores = [5.0, 5.0, 5.0]
        result = Reranker._normalize(scores)
        assert result == [0.5, 0.5, 0.5]

    def test_empty_list(self):
        assert Reranker._normalize([]) == []


# ═══════════════════════════════════════
# 后端降级
# ═══════════════════════════════════════


class TestBackendFallback:
    """后端自动降级"""

    def test_explicit_heuristic_works(self):
        reranker = Reranker(backend="heuristic")
        docs = [{"content": "test doc", "score": 0.5}, {"content": "another", "score": 0.3}]
        result = reranker.rerank("test", docs, top_k=1)
        assert len(result) == 1

    def test_cross_encoder_fallback_to_heuristic(self):
        """Cross-Encoder 不可用时降级 heuristic"""
        with patch("smart_qa.rag.reranker.Reranker._ensure_cross_encoder") as mock_ensure:
            # 模拟 CE 不可用
            reranker = Reranker(backend="cross-encoder")
            reranker._ce_available = False
            reranker._model = None

            docs = [{"content": "doc1", "score": 0.8}, {"content": "doc2", "score": 0.3}]
            result = reranker.rerank("query", docs, top_k=1)
            assert len(result) == 1
            assert reranker._active_backend() == "heuristic"


# ═══════════════════════════════════════
# 混合权重
# ═══════════════════════════════════════


class TestHybridScoring:
    """模型分 + token 分混合"""

    def setup_method(self):
        self.reranker = Reranker(backend="heuristic")
        self.reranker.model_weight = 0.7
        self.reranker.token_weight = 0.3

    def test_weights_sum_to_one(self):
        assert abs(self.reranker.model_weight + self.reranker.token_weight - 1.0) < 0.01

    def test_rerank_score_in_range(self):
        docs = [
            {"content": "边刷更换周期 3-6 个月", "score": 0.9},
            {"content": "WiFi 连接失败 重启路由器", "score": 0.7},
            {"content": "日常维护保养指南", "score": 0.5},
            {"content": "不相关的内容 XYZ", "score": 0.1},
        ]
        result = self.reranker.rerank("边刷多久换", docs, top_k=3)
        for d in result:
            assert 0 <= d["rerank_score"] <= 1


# ═══════════════════════════════════════
# 分词
# ═══════════════════════════════════════


class TestTokenize:
    """分词函数"""

    def test_chinese_tokens(self):
        tokens = Reranker._tokenize("边刷更换周期")
        # 分词结果应包含中文字符
        assert len(tokens) > 0

    def test_mixed_cn_en(self):
        tokens = Reranker._tokenize("X30 Pro 定时清扫")
        has_cn = any(len(t) > 0 and "一" <= t[0] <= "鿿" for t in tokens)
        has_en = any(t.isascii() and any(c.isdigit() for c in t) for t in tokens)
        assert has_cn or has_en

    def test_empty_text(self):
        assert Reranker._tokenize("") == set()

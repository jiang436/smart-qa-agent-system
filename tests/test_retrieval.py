"""MultiLayerRetriever 核心检索逻辑测试 — 使用独立方法测试，避免加载 Embedding 模型"""
import pytest

from smart_qa.rag.retrieval import MultiLayerRetriever, _STOP_WORDS


class TestKeywordExtraction:
    """关键词提取（纯 CPU，无需 Embedding 模型）"""

    def test_removes_stop_words(self):
        # 直接构造，跳过 __init__ 避免加载 embedding
        retriever = object.__new__(MultiLayerRetriever)
        keywords = retriever._extract_keywords("扫地机不走了怎么办")
        assert "的" not in keywords
        assert "了" not in keywords
        assert any(k for k in keywords if len(k) > 1)

    def test_finds_error_codes(self):
        retriever = object.__new__(MultiLayerRetriever)
        keywords = retriever._extract_keywords("错误码E05是什么")
        assert "E05" in keywords

    def test_finds_model_names(self):
        retriever = object.__new__(MultiLayerRetriever)
        keywords = retriever._extract_keywords("X30 Pro边刷怎么换")
        has_x30 = any("X30" in k or "Pro" in k for k in keywords)
        assert has_x30


class TestQueryExpansion:
    def test_expand_query_with_fault_keyword(self):
        retriever = object.__new__(MultiLayerRetriever)
        # "故障" 在 expansions 中，应该触发扩展
        result = retriever._expand_query("设备故障怎么处理")
        assert result is not None
        assert "异常" in result or "报错" in result or len(result) > len("设备故障怎么处理")

    def test_expand_query_no_match(self):
        retriever = object.__new__(MultiLayerRetriever)
        result = retriever._expand_query("xyz123")
        assert result is None or result == "xyz123"


class TestRetrievalHelpers:
    def setup_method(self):
        self.retriever = object.__new__(MultiLayerRetriever)

    def test_avg_score_empty(self):
        assert self.retriever._avg_score([]) == 0.0

    def test_avg_score_normal(self):
        docs = [{"score": 0.8}, {"score": 0.6}]
        assert self.retriever._avg_score(docs) == 0.7

    def test_dedup_and_sort_removes_duplicates(self):
        docs = [
            {"content": "文档A内容" * 20, "score": 0.9},
            {"content": "文档A内容" * 20, "score": 0.8},
            {"content": "文档B内容" * 20, "score": 0.7},
        ]
        result = self.retriever._dedup_and_sort(docs)
        assert len(result) == 2
        assert result[0]["score"] == 0.9

    def test_rrf_fusion_merges_both_sources(self):
        semantic = [
            {"content": "边刷更换步骤", "score": 0.9},
            {"content": "滤网清洗方法", "score": 0.6},
        ]
        bm25 = [
            {"content": "边刷更换周期", "score": 5.0},
            {"content": "其他内容", "score": 2.0},
        ]
        result = self.retriever._rrf_fusion([semantic, bm25], k=60, final_top_k=3)
        assert len(result) >= 1
        assert all("rrf_score" in d for d in result)

    def test_build_result_structure(self):
        result = self.retriever._build(
            docs=[{"content": "test", "score": 0.9}],
            source="L1_semantic",
            confidence="high",
            query_used="test",
            note="测试",
        )
        assert result["source"] == "L1_semantic"
        assert result["confidence"] == "high"
        assert result["total"] == 1

    def test_metadata_filter_boosts_matching(self):
        docs = [
            {"content": "X30 Pro 边刷更换", "header": "边刷", "category": "consumables", "score": 0.5},
            {"content": "通用清洁建议", "header": "清洁", "category": "maintenance", "score": 0.7},
        ]
        meta = {"header": "边刷"}
        result = self.retriever._apply_metadata_filter(docs, meta)
        assert result[0]["_meta_bonus"] > result[1]["_meta_bonus"]


class TestStopWords:
    def test_common_stop_words_present(self):
        assert "的" in _STOP_WORDS
        assert "了" in _STOP_WORDS
        assert "是" in _STOP_WORDS

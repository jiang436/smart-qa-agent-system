"""MultiLayerRetriever 完整检索链路测试 — mock embedding + LLM"""
import pytest
from unittest.mock import MagicMock, patch

from smart_qa.rag.retrieval import MultiLayerRetriever, _STOP_WORDS


class MockEmbedding:
    """Mock embedding 模型"""
    def encode(self, texts):
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        return np.random.rand(len(texts), 512).astype(np.float32)

    def cosine_similarity(self, a, b):
        return 0.75


class MockLLM:
    """Mock LLM 客户端"""
    def __init__(self, rewrite_result=None, decompose_result=None, metadata_result=None):
        self.rewrite_result = rewrite_result
        self.decompose_result = decompose_result
        self.metadata_result = metadata_result

    def invoke(self, prompt):
        if "改写" in prompt or "rewrite" in str(prompt):
            return type('R', (), {'content': self.rewrite_result or 'sao di ji qi ren ting zhi gong zuo'})()
        elif "拆分" in prompt or "NONE" in str(prompt):
            return type('R', (), {'content': self.decompose_result or 'NONE'})()
        elif "过滤条件" in prompt or "JSON" in str(prompt):
            return type('R', (), {'content': self.metadata_result or '{}'})()
        elif "相关性" in prompt or "分数" in str(prompt):
            return type('R', (), {'content': '[0] 0.85\n[1] 0.3'})()
        else:
            return type('R', (), {'content': 'sao di ji qi ren gai xie hou de cha xun'})()


class TestRetrieverWithMockEmbedding:
    """用 mock embedding 测试完整检索链路"""

    @pytest.fixture
    def retriever(self):
        with patch('smart_qa.rag.retrieval.get_embedding', return_value=MockEmbedding()):
            r = object.__new__(MultiLayerRetriever)
            r.embedding = MockEmbedding()
            r.milvus = None
            r.llm = None
            r.bm25 = MagicMock()
            r.bm25.doc_count = 0
            r.bm25.documents = []
            r._bm25_built = False
            r.reranker = None
            return r

    def test_full_parallel_retrieve_flow(self, retriever):
        """完整并行检索 + RRF 融合流程"""
        result = retriever._parallel_retrieve("bian shua gu zhang", top_k=5)
        assert "source" in result
        assert "confidence" in result
        assert "docs" in result
        assert "total" in result
        # 无 Milvus 无 BM25 → 降级 L4_llm
        assert result["source"] in ("RRF_fusion", "L4_llm")

    def test_cascade_retrieve_full_flow(self, retriever):
        """完整四层级联检索流程"""
        result = retriever._cascade_retrieve("ce shi wen ti")
        assert "source" in result
        assert "confidence" in result
        assert isinstance(result["total"], int)

    def test_retrieve_without_services(self, retriever):
        """无任何后端服务时正常降级"""
        result = retriever.retrieve("bian shua zen me huan", top_k=5)
        assert "source" in result
        assert isinstance(result["docs"], list)


class TestRetrieverWithMockLLM:
    """用 mock LLM 测试 Query 改写 / 拆分 / Self-Query"""

    @pytest.fixture
    def retriever(self):
        with patch('smart_qa.rag.retrieval.get_embedding', return_value=MockEmbedding()):
            r = object.__new__(MultiLayerRetriever)
            r.embedding = MockEmbedding()
            r.milvus = None
            r.bm25 = MagicMock()
            r.bm25.doc_count = 0
            r.bm25.documents = []
            r._bm25_built = False
            r.reranker = None
            return r

    def test_rewrite_query_with_mock_llm(self, retriever):
        retriever.llm = MockLLM(rewrite_result="sao di ji qi ren ting zhi gong zuo yuan yin pai cha")
        result = retriever._rewrite_query("bu zou le")
        assert result is not None
        assert "zou" in result.lower() or "gong zuo" in result.lower()

    def test_decompose_simple_query_returns_empty(self, retriever):
        retriever.llm = MockLLM(decompose_result="NONE")
        result = retriever._decompose_query("bian shua")
        assert result == []

    def test_decompose_complex_query(self, retriever):
        retriever.llm = MockLLM(decompose_result="X30 Pro bian shua geng huan zhou qi\nT10 bian shua geng huan zhou qi")
        result = retriever._decompose_query("X30 Pro T10 bian shua tong yong ma? duo jiu huan?")
        # 应该拆分出至少 1 个子问题
        assert len(result) > 0

    def test_parse_metadata_filter(self, retriever):
        retriever.llm = MockLLM(metadata_result='{"header": "X30 Pro"}')
        result = retriever._parse_metadata_filter("X30 Pro bian shua duo shao qian")
        assert "header" in result

    def test_parse_metadata_filter_empty(self, retriever):
        retriever.llm = MockLLM(metadata_result="{}")
        result = retriever._parse_metadata_filter("ni hao")
        assert result == {}


class TestRetrieverEdgeCases:
    def test_empty_retrieve(self):
        r = object.__new__(MultiLayerRetriever)
        r.embedding = MockEmbedding()
        r.milvus = None
        r.llm = None
        r.bm25 = MagicMock()
        r.bm25.doc_count = 0
        r._bm25_built = False
        r.reranker = None
        result = r.retrieve("", top_k=5)
        assert isinstance(result, dict)
        assert "docs" in result

    def test_avg_score_with_none_scores(self):
        r = object.__new__(MultiLayerRetriever)
        docs = [{"score": None}, {"score": 0}]
        assert r._avg_score(docs) == 0.0

    def test_apply_metadata_filter_no_filter(self):
        r = object.__new__(MultiLayerRetriever)
        docs = [{"content": "test", "score": 0.5}]
        result = r._apply_metadata_filter(docs, {})
        assert len(result) == 1
        assert "_meta_bonus" not in result[0]

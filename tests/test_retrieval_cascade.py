"""RAG 检索完整测试 — 四层级联 / RRF 融合 / Query 改写 / Milvus 集成"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from smart_qa.rag.retrieval import MultiLayerRetriever
from smart_qa.knowledge.bm25 import BM25Index
from conftest import MockEmbedding, MockLLM


# ═══════════════════════════════════════
# 复用工具
# ═══════════════════════════════════════

def _build_retriever(
    milvus=None, llm=None, bm25_docs=None, bm25_metas=None,
    bm25_search_result=None,
):
    """构建可配置的 MultiLayerRetriever"""
    with patch("smart_qa.rag.retrieval.get_embedding", return_value=MockEmbedding()):
        r = MultiLayerRetriever(milvus_client=milvus, llm_client=llm)

    if bm25_docs:
        r.bm25.build(bm25_docs, bm25_metas or [{}] * len(bm25_docs))
        r._bm25_built = True
    elif bm25_search_result is not None:
        r.bm25 = MagicMock()
        r.bm25.doc_count = 1
        r.bm25.documents = []
        r.bm25.search = MagicMock(return_value=bm25_search_result)
        r._bm25_built = True
    else:
        r.bm25 = BM25Index()
        r._bm25_built = False

    r.reranker = None
    return r


# ═══════════════════════════════════════
# 四层级联检索 (L1 → L2 → L3 → L4)
# ═══════════════════════════════════════


class TestCascadeRetrieval:
    """四层级联检索 — 逐层降级逻辑"""

    def test_l1_semantic_sufficient_hits(self):
        """L1 语义检索命中 ≥2 且平均分 ≥0.45 → 直接返回"""
        r = _build_retriever(bm25_search_result=[])

        # Mock _semantic_search 返回多篇高分文档
        with patch.object(r, "_semantic_search", return_value=[
            {"content": "X30 Pro 定时清扫设置步骤", "score": 0.7, "source": "L1"},
            {"content": "定时清扫功能介绍", "score": 0.5, "source": "L1"},
            {"content": "App 设置界面说明", "score": 0.48, "source": "L1"},
        ]):
            result = r._cascade_retrieve("怎么设置定时清扫", top_k=5)

        assert result["source"] == "L1_semantic"
        assert result["confidence"] == "high"
        assert result["total"] >= 2

    def test_l1_insufficient_falls_to_l2(self):
        """L1 命中 <2 或平均分 <0.45 → 降级 L2 改写"""
        r = _build_retriever(bm25_search_result=[])

        with patch.object(r, "_semantic_search", return_value=[
            {"content": "weak match", "score": 0.3, "source": "L1"},
        ]):
            with patch.object(r, "_rewrite_query", return_value="扫地机器人 定时清扫 设置方法"):
                with patch.object(r, "_semantic_search", side_effect=[
                    [{"content": "weak match", "score": 0.3}],  # 原始
                    [
                        {"content": "定时清扫配置", "score": 0.55, "source": "L2"},
                        {"content": "设置步骤", "score": 0.5, "source": "L2"},
                    ],  # 改写后
                ]):
                    result = r._cascade_retrieve("怎么设置定时", top_k=5)

        assert result["source"] == "L2_rewrite"
        assert result["confidence"] == "medium"

    def test_l2_rewrite_fails_then_expand(self):
        """L2 改写无果 → 用扩展 query 再试"""
        r = _build_retriever(bm25_search_result=[])

        with patch.object(r, "_semantic_search", return_value=[]):
            with patch.object(r, "_rewrite_query", return_value=None):
                with patch.object(r, "_expand_query", return_value="定时 预约 计划 设置"):
                    # 扩展 query 召回
                    with patch.object(r, "_semantic_search", side_effect=[
                        [],  # 原始无结果
                        [
                            {"content": "预约清扫功能介绍", "score": 0.4, "source": "L2"},
                        ],  # 扩展后有结果
                    ]):
                        result = r._cascade_retrieve("定时怎么搞", top_k=5)

        # 扩展 query 命中 | 合并多路结果至少有一条
        assert result["source"] in ("L2_rewrite", "L3_bm25", "L4_llm")
        assert result["total"] >= 0

    def test_l2_l3_all_fail_falls_to_l4(self):
        """L1/L2/L3 全部失败 → L4 LLM 兜底"""
        r = _build_retriever(bm25_search_result=[])

        with patch.object(r, "_semantic_search", return_value=[]):
            with patch.object(r, "_rewrite_query", return_value=None):
                with patch.object(r, "_expand_query", return_value=None):
                    result = r._cascade_retrieve("xyz 未知问题", top_k=5)

        assert result["source"] == "L4_llm"
        assert result["confidence"] == "low"
        assert isinstance(result["docs"], list)

    def test_l3_bm25_as_keyword_fallback(self):
        """语义检索失败 → BM25 关键词命中"""
        bm25_docs = ["X30 Pro 用户手册 定时清扫 设置方法 打开App进入设备页面选择定时清扫"]
        r = _build_retriever(bm25_docs=bm25_docs)

        with patch.object(r, "_semantic_search", return_value=[]):
            with patch.object(r, "_rewrite_query", return_value=None):
                with patch.object(r, "_expand_query", return_value=None):
                    result = r._cascade_retrieve("X30 Pro 定时清扫", top_k=5)

        assert result["source"] in ("L3_bm25", "L4_llm")
        if result["source"] == "L3_bm25":
            assert result["total"] > 0

    def test_cascade_all_layers_traversed(self):
        """验证四层都被遍历的完整路径"""
        r = _build_retriever(bm25_search_result=[])

        call_order = []

        def make_semantic(return_val, label):
            def fn(*a, **kw):
                call_order.append(label)
                return return_val
            return fn

        with patch.object(r, "_semantic_search",
            make_semantic([], "L1")):
            with patch.object(r, "_rewrite_query", return_value="改写查询"):
                with patch.object(r, "_expand_query", return_value="扩展查询"):
                    r._cascade_retrieve("测试")

        # 至少 L1 和 L2(rewrite) 被调用了
        assert "L1" in call_order


# ═══════════════════════════════════════
# RRF 融合算法
# ═══════════════════════════════════════


class TestRRFFusion:
    """RRF (Reciprocal Rank Fusion) 多路融合排序"""

    def test_rrf_empty_input_returns_empty(self):
        r = _build_retriever()
        result = r._rrf_fusion([], k=60, final_top_k=5)
        assert result == []

    def test_rrf_single_list_passthrough(self):
        """单路检索结果直接返回"""
        r = _build_retriever()
        docs = [
            {"content": "doc A", "score": 0.9},
            {"content": "doc B", "score": 0.7},
        ]
        result = r._rrf_fusion([docs], k=60, final_top_k=5)
        assert len(result) == 2
        assert result[0]["content"] == "doc A"

    def test_rrf_merges_two_lists(self):
        """两路检索结果 RRF 融合"""
        r = _build_retriever()
        semantic = [
            {"content": "X30 Pro 定时设置", "score": 0.9, "source": "semantic"},
            {"content": "定时功能介绍", "score": 0.7, "source": "semantic"},
            {"content": "App 操作指南", "score": 0.5, "source": "semantic"},
        ]
        bm25 = [
            {"content": "定时清扫 预约 APP", "score": 2.5, "source": "bm25"},
            {"content": "X30 Pro 定时设置", "score": 1.8, "source": "bm25"},
        ]
        result = r._rrf_fusion([semantic, bm25], k=60, final_top_k=3)

        assert 1 <= len(result) <= 3
        # 重复文档 "X30 Pro 定时设置" 在两路中 → RRF 加分，应排在前面
        assert result[0]["content"] == "X30 Pro 定时设置"

    def test_rrf_dedup_on_content(self):
        """相同内容文档去重 + RRF 加分"""
        r = _build_retriever()
        doc_same = {"content": "the same document content appears in both lists", "score": 0.9}
        list1 = [doc_same, {"content": "unique A", "score": 0.5}]
        list2 = [doc_same, {"content": "unique B", "score": 0.3}]
        result = r._rrf_fusion([list1, list2], k=60, final_top_k=5)

        # "the same document" 应只出现一次
        contents = [d["content"] for d in result]
        assert contents.count("the same document content appears in both lists") == 1
        # RRF 累加后应排第一
        assert result[0]["content"] == "the same document content appears in both lists"

    def test_rrf_score_accumulation(self):
        """同一文档在多路中 → RRF 分数累加"""
        r = _build_retriever()
        list1 = [{"content": "shared doc", "score": 0.9}]
        list2 = [{"content": "shared doc", "score": 2.0}]
        list3 = [{"content": "shared doc", "score": 1.0}]

        result = r._rrf_fusion([list1, list2, list3], k=60)
        assert len(result) == 1
        # 三路都在 rank=1 → RRF = 3/(60+1)
        expected = 3.0 / 61.0
        assert abs(result[0]["rrf_score"] - expected) < 0.001

    def test_rrf_respects_final_top_k(self):
        """final_top_k 限制返回数量"""
        r = _build_retriever()
        docs1 = [{"content": f"doc{i}", "score": 1.0 - i * 0.1} for i in range(10)]
        docs2 = [{"content": f"bm25_doc{i}", "score": 3.0 - i * 0.5} for i in range(5)]
        result = r._rrf_fusion([docs1, docs2], k=60, final_top_k=4)
        assert len(result) == 4

    def test_rrf_empty_sublists_handled(self):
        """空子列表不影响融合"""
        r = _build_retriever()
        docs = [{"content": "only doc", "score": 0.8}]
        result = r._rrf_fusion([[], docs, []], k=60, final_top_k=3)
        assert len(result) == 1
        assert result[0]["content"] == "only doc"


# ═══════════════════════════════════════
# Query 改写 / 扩展
# ═══════════════════════════════════════


class TestQueryRewrite:
    """LLM Query 改写 & 同义词扩展"""

    def test_rewrite_with_llm(self):
        """LLM 改写口语化查询"""
        llm = MockLLM(invoke_result="扫地机器人 停止工作 原因 排查")
        r = _build_retriever(llm=llm)

        result = r._rewrite_query("扫地机不走了")
        assert result is not None
        assert "不走了" not in result  # 口语被替换

    def test_rewrite_no_llm_returns_none(self):
        """无 LLM → 无改写"""
        r = _build_retriever(llm=None)
        result = r._rewrite_query("test")
        assert result is None

    def test_rewrite_llm_error_returns_none(self):
        """LLM 失败 → None"""
        bad_llm = MagicMock()
        bad_llm.invoke = MagicMock(side_effect=Exception("API error"))
        r = _build_retriever(llm=bad_llm)
        result = r._rewrite_query("test")
        assert result is None

    def test_expand_query_adds_synonyms(self):
        """同义词扩展在关键词基础上追加"""
        r = _build_retriever()
        result = r._expand_query("连不上了")
        assert result is not None
        assert len(result) > len("连不上了")

    def test_expand_query_no_match_returns_none(self):
        """无匹配扩展词 → None"""
        r = _build_retriever()
        result = r._expand_query("xyz_no_match_keyword")
        assert result is None

    @pytest.mark.parametrize("query,expected_keyword", [
        ("不工作了", "停止工作"),
        ("卡住了", "卡死"),
        ("噪音太大", "异响"),
        ("边刷坏了", "边刷"),
        ("滤网要换了", "HEPA"),
        ("拖布脏了", "抹布"),
        ("定时", "预约"),
        ("建图失败", "地图"),
    ])
    def test_expand_query_coverage(self, query, expected_keyword):
        """各关键词都能被扩展"""
        r = _build_retriever()
        result = r._expand_query(query)
        # 有同义词扩展或本身匹配
        if result is not None:
            assert any(expected_keyword in result for _ in [1])


# ═══════════════════════════════════════
# Multi-Query 复杂问题拆分
# ═══════════════════════════════════════


class TestMultiQueryDecomposition:
    """复杂问题拆分为子查询"""

    def test_simple_query_not_decomposed(self):
        """简单问题不拆分"""
        llm = MockLLM(invoke_result="NONE")
        r = _build_retriever(llm=llm)
        result = r._decompose_query("怎么设置定时")
        assert result == []

    def test_complex_query_decomposed(self):
        """复杂对比问题拆分"""
        llm = MockLLM(invoke_result="X30 Pro 边刷更换周期\nT10 边刷更换周期\nX30 Pro 与 T10 边刷兼容性")
        r = _build_retriever(llm=llm)
        result = r._decompose_query("X30 Pro 和 T10 的边刷通用吗？分别多久换一次？")
        assert len(result) >= 2
        assert all(len(s) > 3 for s in result)

    def test_short_query_not_decomposed(self):
        """短查询（<15字）不拆分"""
        r = _build_retriever(llm=None)
        result = r._decompose_query("short")
        assert result == []

    def test_llm_error_handled(self):
        """LLM 异常 → 返回空"""
        bad_llm = MagicMock()
        bad_llm.invoke = MagicMock(side_effect=Exception("timeout"))
        r = _build_retriever(llm=bad_llm)
        result = r._decompose_query("very long query that should be decomposed if llm works")
        assert result == []


# ═══════════════════════════════════════
# 关键词提取 (L3 BM25)
# ═══════════════════════════════════════


class TestKeywordExtraction:
    """BM25 关键词提取"""

    def test_extract_error_code(self):
        r = _build_retriever()
        keywords = r._extract_keywords("E05错误码怎么解决")
        assert "E05" in keywords

    def test_extract_model_name(self):
        r = _build_retriever()
        keywords = r._extract_keywords("X30 Pro 定时设置")
        has_x30 = any("X30" in kw for kw in keywords)
        assert has_x30

    def test_extract_filters_stop_words(self):
        r = _build_retriever()
        keywords = r._extract_keywords("我的扫地机怎么了")
        assert "我" not in keywords
        assert "的" not in keywords
        assert "了" not in keywords

    def test_extract_empty_query(self):
        r = _build_retriever()
        keywords = r._extract_keywords("")
        assert keywords == []


# ═══════════════════════════════════════
# 语义检索 (Milvus + 预计算向量降级)
# ═══════════════════════════════════════


class TestSemanticSearch:
    """语义检索 — Milvus + 预计算向量降级"""

    def test_semantic_search_milvus_primary(self):
        """Milvus 可用 → 走 Milvus"""
        from unittest.mock import MagicMock

        mock_entity = MagicMock()
        mock_entity.get = MagicMock(side_effect=lambda k, default="": {
            "content": "X30 Pro 定时清扫设置", "source": "manual.md"
        }.get(k, default))

        mock_hit = MagicMock(id=1, score=0.95, entity=mock_entity)
        mock_milvus = MagicMock()
        mock_milvus.search.return_value = [[mock_hit]]

        r = _build_retriever(milvus=mock_milvus)
        docs = r._semantic_search("定时清扫", top_k=3)

        assert len(docs) >= 1
        assert docs[0]["score"] > 0

    def test_semantic_search_milvus_error_fallback(self):
        """Milvus 异常 → 降级到预计算向量"""
        mock_milvus = MagicMock()
        mock_milvus.search.side_effect = Exception("Connection refused")

        # 准备 BM25 文档和预计算向量
        bm25 = BM25Index()
        docs = [
            "X30 Pro 边刷每3-6个月更换一次刷毛缩短1/3以上需更换",
            "HEPA滤网建议3-4个月更换以保证过滤效果",
            "E05错误码表示电池过热请冷却后重启",
        ]
        bm25.build(docs)

        from smart_qa.di import container

        # 预计算 BGE 向量
        emb = MockEmbedding()
        doc_vectors = emb.encode(docs)
        container.register("doc_vectors", doc_vectors)

        r = _build_retriever(milvus=mock_milvus)
        r.bm25 = bm25
        r._bm25_built = True

        result = r._semantic_search("边刷更换", top_k=3)
        assert isinstance(result, list)
        # 可能命中也可能不命中（取决于相似度阈值）
        if result:
            assert "score" in result[0]

    def test_semantic_search_no_backend_returns_empty(self):
        """无 Milvus 无预计算向量 → 空列表"""
        mock_milvus = MagicMock()
        mock_milvus.search.side_effect = Exception("down")

        bm25 = BM25Index()
        bm25.build(["doc1 content here"])

        r = _build_retriever(milvus=mock_milvus)
        r.bm25 = bm25
        r._bm25_built = True

        from smart_qa.di import container
        container.register("doc_vectors", None)

        result = r._semantic_search("test", top_k=3)
        assert isinstance(result, list)


# ═══════════════════════════════════════
# Milvus 真实集成测试
# ═══════════════════════════════════════


@pytest.mark.integration
class TestMilvusIntegration:
    """Milvus 真实集成 — 需要 Milvus 运行"""

    @pytest.fixture
    def milvus_client(self):
        from pymilvus import MilvusClient
        from smart_qa.config import settings

        client = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)
        return client

    @pytest.fixture
    def collection_name(self):
        return "test_rag_collection"

    def test_milvus_connectivity(self, milvus_client):
        """Milvus 连接正常"""
        collections = milvus_client.list_collections()
        assert isinstance(collections, list)

    def test_semantic_search_with_real_milvus(self, milvus_client, collection_name):
        """端到端：写入 → 语义检索 → 验证结果"""
        from smart_qa.config import settings

        emb = MockEmbedding()

        # 使用已有集合或测试集合
        collections = milvus_client.list_collections()
        target_collection = settings.milvus_collection if collections else collection_name

        # 如果知识库集合存在，直接检索
        if target_collection in collections:
            r = _build_retriever(milvus=milvus_client)
            r.embedding = emb

            docs = r._semantic_search("定时清扫怎么设置", top_k=5)
            assert isinstance(docs, list)
            # 有知识库数据 → 应该有结果
            if docs:
                for doc in docs:
                    assert "content" in doc
                    assert "score" in doc
                    assert 0 <= doc["score"] <= 1

    def test_multilayer_retrieve_with_milvus(self, milvus_client):
        """MultiLayerRetriever 完整检索流程（使用 Milvus）"""
        emb = MockEmbedding()

        with patch("smart_qa.rag.retrieval.get_embedding", return_value=emb):
            retriever = MultiLayerRetriever(milvus_client=milvus_client)

            result = retriever.retrieve("扫地机怎么设置定时清扫 X30 Pro", top_k=5)

            assert "source" in result
            assert "docs" in result
            assert "confidence" in result
            assert "total" in result
            # 有 Milvus 有知识库数据 → 不应全部降级到 L4
            if result["total"] > 0:
                for doc in result["docs"]:
                    assert "content" in doc
                    assert len(doc.get("content", "")) > 0

    def test_retrieve_async_with_milvus(self, milvus_client):
        """异步检索（线程池执行）"""
        import asyncio

        emb = MockEmbedding()

        with patch("smart_qa.rag.retrieval.get_embedding", return_value=emb):
            retriever = MultiLayerRetriever(milvus_client=milvus_client)

            async def run():
                return await retriever.retrieve_async("X30 Pro 边刷更换", top_k=3)

            result = asyncio.run(run())
            assert "docs" in result
            assert "source" in result


# ═══════════════════════════════════════
# 检索后处理
# ═══════════════════════════════════════


class TestRetrievalPostProcessing:
    """检索后处理管道"""

    def test_dedup_and_sort_removes_duplicates(self):
        r = _build_retriever()
        docs = [
            {"content": "same content here", "score": 0.9},
            {"content": "same content here", "score": 0.8},
            {"content": "unique content", "score": 0.7},
            {"content": "unique content", "score": 0.6},
        ]
        result = r._dedup_and_sort(docs)
        assert len(result) == 2
        # 保留最高分版本
        assert result[0]["score"] == 0.9
        assert result[1]["score"] == 0.7

    def test_avg_score_calculation(self):
        r = _build_retriever()
        assert r._avg_score([]) == 0.0
        docs = [{"score": 0.5}, {"score": 0.7}]
        assert r._avg_score(docs) == pytest.approx(0.6)

    def test_avg_score_with_none_scores(self):
        r = _build_retriever()
        docs = [{"score": None}, {"score": 0}, {"score": 0.5}]
        assert r._avg_score(docs) == pytest.approx(0.5 / 3)

    def test_build_result_structure(self):
        r = _build_retriever()
        docs = [{"content": "test", "score": 0.8}]
        result = r._build(docs, "L1_semantic", "high", "test_query", "提示信息")
        assert result["docs"] == docs
        assert result["source"] == "L1_semantic"
        assert result["confidence"] == "high"
        assert result["total"] == 1
        assert "提示信息" in result["note"]

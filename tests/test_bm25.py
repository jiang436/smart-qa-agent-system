"""BM25 索引测试"""

from smart_qa.knowledge.bm25 import BM25Index


class TestBM25Index:
    def setup_method(self):
        self.bm25 = BM25Index()

    def test_empty_index_search_returns_empty(self):
        assert self.bm25.search("test") == []
        assert self.bm25.doc_count == 0
        assert self.bm25.is_built is False

    def test_build_and_search(self):
        docs = [
            "X30 Pro 扫地机器人电池过热保护",
            "如何重置扫地机器人Wi-Fi连接",
            "边刷更换周期为3-6个月",
        ]
        self.bm25.build(docs)
        assert self.bm25.doc_count == 3
        assert self.bm25.is_built is True

        results = self.bm25.search("电池", top_k=2)
        assert len(results) >= 1
        assert "电池" in results[0]["content"]

    def test_save_and_load(self, tmp_path):
        docs = ["测试文档一", "测试文档二"]
        self.bm25.build(docs)

        path = tmp_path / "bm25_test.pkl"
        self.bm25.save(str(path))

        bm25_2 = BM25Index()
        assert bm25_2.load(str(path)) is True
        assert bm25_2.doc_count == 2

    def test_load_nonexistent_file(self):
        bm25 = BM25Index()
        assert bm25.load("/nonexistent/path.pkl") is False

    def test_add_documents_increments_count(self):
        self.bm25.build(["原始文档"])
        assert self.bm25.doc_count == 1

        self.bm25.add_documents(["新增文档一", "新增文档二"])
        assert self.bm25.doc_count == 3

    def test_add_documents_updates_search(self):
        self.bm25.build(["原始文档没有关键词"])
        self.bm25.add_documents(["新增文档包含扫地机"])

        results = self.bm25.search("扫地机")
        assert len(results) >= 1

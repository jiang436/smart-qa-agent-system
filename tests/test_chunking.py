"""Chunking 分片测试"""

from smart_qa.rag.chunking import SmartDocumentSplitter


class TestSmartDocumentSplitter:
    def setup_method(self):
        self.splitter = SmartDocumentSplitter(chunk_size=200, chunk_overlap=20)

    def test_split_empty_text(self):
        chunks = self.splitter.split("", "txt", {"source": "test"})
        assert chunks == []

    def test_split_short_text(self):
        chunks = self.splitter.split("你好", "txt", {"source": "test"})
        assert len(chunks) >= 1
        assert "你好" in chunks[0]["content"]

    def test_split_markdown_by_headers(self):
        text = """# 标题一
这是第一段内容
## 子标题
这是第二段内容"""
        chunks = self.splitter.split(text, "markdown", {"source": "test.md"})
        assert len(chunks) >= 1

    def test_detect_type_by_filename(self):
        assert SmartDocumentSplitter.detect_type("readme.md") == "markdown"
        assert SmartDocumentSplitter.detect_type("doc.txt") == "txt"

    def test_detect_type_by_content(self):
        # 无后缀时通过内容判断
        t = SmartDocumentSplitter.detect_type("test", "# 标题\n内容")
        assert t is not None

    def test_chunk_metadata_preserved(self):
        chunks = self.splitter.split("一些测试文本内容", "txt", {"source": "test.md", "title": "测试"})
        for c in chunks:
            assert c.get("source") == "test.md"
            assert c.get("title") == "测试"

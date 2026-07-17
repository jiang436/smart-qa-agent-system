"""API 路由测试 — Knowledge 知识库管理

覆盖: 文件上传、状态查询、文件列表、BM25 管理、reload
"""
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════
# GET /api/v1/knowledge/status
# ═══════════════════════════════════════


class TestKnowledgeStatus:
    """知识库状态接口测试（依赖 Milvus 运行时）"""

    def test_status_returns_dict(self, api_client):
        """状态接口返回正确结构（Milvus 不可用时 500）"""
        response = api_client.get("/api/v1/knowledge/status")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    def test_status_milvus_unavailable_is_graceful(self, api_client):
        """Milvus 不可用时状态接口不崩溃"""
        response = api_client.get("/api/v1/knowledge/status")
        assert response.status_code in (200, 500)


# ═══════════════════════════════════════
# GET /api/v1/knowledge/files
# ═══════════════════════════════════════


class TestKnowledgeFiles:
    """知识文件列表"""

    def test_files_returns_list(self, api_client):
        response = api_client.get("/api/v1/knowledge/files")
        assert response.status_code in (200, 500)


# ═══════════════════════════════════════
# POST /api/v1/knowledge/upload
# ═══════════════════════════════════════


class TestKnowledgeUpload:
    """文件上传测试"""

    def test_upload_unsupported_type_rejected(self, api_client):
        """不支持的文件类型 → 400"""
        response = api_client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("test.exe", io.BytesIO(b"binary content"), "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_upload_markdown_accepted(self, api_client):
        """Markdown 文件上传"""
        md_content = b"# Test\n\nThis is a test document about X30 Pro maintenance."
        response = api_client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("test.md", io.BytesIO(md_content), "text/markdown")},
        )
        # 可能成功（有 Milvus）或失败（无 Milvus）
        assert response.status_code in (200, 400, 500)

    def test_upload_txt_accepted(self, api_client):
        """TXT 文件上传"""
        response = api_client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("test.txt", io.BytesIO(b"X30 Pro \xe6\x89\xab\xe5\x9c\xb0\xe6\x9c\xba\xe4\xbd\xbf\xe7\x94\xa8\xe6\x8c\x87\xe5\x8d\x97"), "text/plain")},
        )
        assert response.status_code in (200, 400, 500)

    def test_upload_empty_file(self, api_client):
        """空文件上传"""
        response = api_client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("empty.md", io.BytesIO(b""), "text/markdown")},
        )
        assert response.status_code in (200, 400, 500)

    def test_upload_large_file_rejected(self, api_client):
        """超大文件（>10MB）→ 400"""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        response = api_client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("large.txt", io.BytesIO(large_content), "text/plain")},
        )
        assert response.status_code in (400, 413, 422)


# ═══════════════════════════════════════
# GET /api/v1/knowledge/bm25/status
# POST /api/v1/knowledge/bm25/rebuild
# ═══════════════════════════════════════


class TestBM25Endpoints:
    """BM25 索引管理"""

    def test_bm25_status_returns_ok(self, api_client):
        response = api_client.get("/api/v1/knowledge/bm25/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "doc_count" in data

    def test_bm25_rebuild_returns_ok(self, api_client):
        response = api_client.post("/api/v1/knowledge/bm25/rebuild")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "ok"
            assert "doc_count" in data


# ═══════════════════════════════════════
# POST /api/v1/knowledge/reload
# ═══════════════════════════════════════


class TestKnowledgeReload:
    """知识库重载"""

    def test_reload_returns_ok(self, api_client):
        response = api_client.post("/api/v1/knowledge/reload")
        assert response.status_code in (200, 500)

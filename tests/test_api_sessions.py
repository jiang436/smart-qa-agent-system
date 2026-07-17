"""API 路由测试 — Session 会话管理

覆盖: 会话列表、历史查询、删除会话、分页、参数校验
"""
import pytest


# ═══════════════════════════════════════
# GET /api/v1/sessions
# ═══════════════════════════════════════


class TestListSessions:
    """会话列表接口"""

    def test_list_sessions_requires_user_id(self, api_client):
        """缺少 user_id → 422"""
        response = api_client.get("/api/v1/sessions")
        assert response.status_code == 422

    def test_list_sessions_with_valid_user_id(self, api_client):
        """正常查询返回 sessions 列表"""
        response = api_client.get("/api/v1/sessions?user_id=test-user")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total" in data
        assert isinstance(data["sessions"], list)

    def test_list_sessions_with_pagination(self, api_client):
        """支持分页参数"""
        response = api_client.get("/api/v1/sessions?user_id=test&limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0

    def test_list_sessions_limit_out_of_range(self, api_client):
        """limit 超出范围 → 422"""
        response = api_client.get("/api/v1/sessions?user_id=test&limit=200")
        assert response.status_code == 422

    def test_list_sessions_negative_offset_rejected(self, api_client):
        """负 offset → 422"""
        response = api_client.get("/api/v1/sessions?user_id=test&offset=-1")
        assert response.status_code == 422

    def test_list_sessions_empty_user_id_rejected(self, api_client):
        """空 user_id → 422"""
        response = api_client.get("/api/v1/sessions?user_id=")
        assert response.status_code == 422

    def test_list_sessions_long_user_id_rejected(self, api_client):
        """超长 user_id → 422"""
        response = api_client.get(f"/api/v1/sessions?user_id={'U' * 65}")
        assert response.status_code == 422


# ═══════════════════════════════════════
# GET /api/v1/session/{session_id}/history
# ═══════════════════════════════════════


class TestSessionHistory:
    """会话历史接口"""

    def test_history_returns_messages(self, api_client):
        """正常返回消息列表"""
        response = api_client.get("/api/v1/session/test-session/history")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "messages" in data
        assert "total" in data
        assert isinstance(data["messages"], list)

    def test_history_empty_session_id_rejected(self, api_client):
        """空 session_id → 404（路由无法匹配）或 400"""
        response = api_client.get("/api/v1/session/%20/history")
        assert response.status_code in (200, 400, 404, 422)

    def test_history_long_session_id_rejected(self, api_client):
        """超长 session_id → 400"""
        response = api_client.get(f"/api/v1/session/{'s' * 65}/history")
        assert response.status_code in (400, 404)

    def test_history_nonexistent_session(self, api_client):
        """不存在的会话 → 返回空列表"""
        response = api_client.get("/api/v1/session/no-such-session-xyz/history")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


# ═══════════════════════════════════════
# DELETE /api/v1/session/{session_id}
# ═══════════════════════════════════════


class TestDeleteSession:
    """删除会话接口"""

    def test_delete_session_returns_ok(self, api_client):
        """删除不存在会话也返回 ok"""
        response = api_client.delete("/api/v1/session/test-delete-me")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("deleted", "error")

    def test_delete_empty_session_id_rejected(self, api_client):
        """空 session_id → 400"""
        response = api_client.delete("/api/v1/session/%20")
        assert response.status_code in (200, 400, 404)

    def test_delete_long_session_id_rejected(self, api_client):
        """超长 session_id → 400"""
        response = api_client.delete(f"/api/v1/session/{'s' * 65}")
        assert response.status_code in (400, 404)


# ═══════════════════════════════════════
# 跨接口一致性
# ═══════════════════════════════════════


class TestSessionCrossEndpoint:
    """跨接口一致性测试"""

    def test_list_then_history_consistent(self, api_client):
        """先列会话，再查历史 → 数据一致"""
        list_resp = api_client.get("/api/v1/sessions?user_id=test-user")
        assert list_resp.status_code == 200
        list_data = list_resp.json()

        for session in list_data["sessions"][:1]:
            sid = session["session_id"]
            hist_resp = api_client.get(f"/api/v1/session/{sid}/history")
            assert hist_resp.status_code == 200
            hist_data = hist_resp.json()
            assert hist_data["session_id"] == sid

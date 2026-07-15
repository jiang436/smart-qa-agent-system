"""用户认证测试 — User 模型 + Auth 路由"""

import pytest
from fastapi.testclient import TestClient


class TestUserModel:
    """User 模型的密码哈希和验证（纯逻辑，不需要数据库）"""

    def test_hash_password_returns_tuple(self):
        from smart_qa.models.user import User

        h, salt = User.hash_password("test123")
        assert len(h) > 0
        assert len(salt) == 32

    def test_hash_deterministic_with_same_salt(self):
        from smart_qa.models.user import User

        h1, salt = User.hash_password("test123")
        h2, _ = User.hash_password("test123", salt)
        assert h1 == h2

    def test_hash_different_with_different_salt(self):
        from smart_qa.models.user import User

        h1, _ = User.hash_password("test123")
        h2, _ = User.hash_password("test123")
        assert h1 != h2

    def test_verify_password_correct(self):
        from smart_qa.models.user import User

        h_saved, salt_saved = User.hash_password("test123")
        h_check, _ = User.hash_password("test123", salt_saved)
        assert h_check == h_saved

    def test_verify_password_wrong(self):
        from smart_qa.models.user import User

        h_saved, salt_saved = User.hash_password("test123")
        h_check, _ = User.hash_password("wrong", salt_saved)
        assert h_check != h_saved


class TestUserSessionToken:
    """UserSession 令牌生成"""

    def test_token_generates_unique(self):
        from smart_qa.models.user import UserSession

        t1 = UserSession.generate_token()
        t2 = UserSession.generate_token()
        assert t1 != t2
        assert len(t1) > 32


@pytest.mark.skip(reason="需要数据库，仅用于本地验证")
class TestAuthAPI:
    """认证 API 端到端测试（需要本地 PostgreSQL + 空数据库）"""

    def setup_method(self):
        from smart_qa.web import app

        self.client = TestClient(app)

    def test_register_and_login(self):
        r = self.client.post("/api/v1/register", json={"username": "testuser", "password": "test123"})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["username"] == "testuser"

        r2 = self.client.post("/api/v1/login", json={"username": "testuser", "password": "test123"})
        assert r2.status_code == 200
        assert r2.json()["token"] != data["token"]

    def test_wrong_password(self):
        r = self.client.post("/api/v1/login", json={"username": "testuser", "password": "wrong"})
        assert r.status_code == 401

    def test_duplicate_register(self):
        self.client.post("/api/v1/register", json={"username": "testdup", "password": "test123"})
        r = self.client.post("/api/v1/register", json={"username": "testdup", "password": "test123"})
        assert r.status_code == 409

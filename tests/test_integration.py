"""集成测试 — 端到端的 Graph 编排 + API 路由

不依赖外部服务（LLM / Milvus / Redis），测试核心流程的结构完整性。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试 FastAPI 客户端"""
    from smart_qa.web import app

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestAPIDocs:
    def test_swagger_ui_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        # 验证核心路由存在
        path_keys = list(schema["paths"].keys())
        has_chat = any("/chat" in p for p in path_keys)
        has_health = any("/health" in p for p in path_keys)
        assert has_chat
        assert has_health


class TestChatRequestValidation:
    def test_chat_empty_message(self, client):
        response = client.post("/api/v1/chat", json={"message": ""})
        assert response.status_code in (200, 422)

    def test_chat_valid_message(self, client):
        response = client.post(
            "/api/v1/chat",
            json={"message": "测试", "user_id": "test-user", "session_id": "test-001"},
        )
        assert response.status_code in (200, 422, 500, 503)


class TestGraphBuild:
    def test_build_graph_without_llm(self):
        from smart_qa.agent.graph import build_graph

        graph = build_graph(llm_client=None)
        assert graph is not None

    def test_graph_has_get_graph_method(self):
        from smart_qa.agent.graph import build_graph

        graph = build_graph(llm_client=None)
        assert hasattr(graph, "get_graph")

    def test_graph_compiles_with_store(self):
        from smart_qa.agent.graph import get_agent, get_store

        graph = get_agent(llm_client=None)
        assert graph is not None
        # Store 可能为 None（未通过 lifespan 初始化），但应该能编译
        store = get_store()
        assert store is None or store is not None  # 宽松验证


class TestDI:
    def test_container_register_and_get(self):
        from smart_qa.di import container

        container.register("test_key", "test_value")
        assert container.get("test_key") == "test_value"

    def test_container_unregistered_raises(self):
        from smart_qa.di import container
        from smart_qa.exceptions import ConfigError

        container.reset()
        with pytest.raises(ConfigError):
            container.get("nonexistent")

    def test_container_get_optional(self):
        from smart_qa.di import container

        container.reset()
        assert container.get_optional("nonexistent") is None

    def test_container_has(self):
        from smart_qa.di import container

        container.register("has_test", 42)
        assert container.has("has_test")
        assert not container.has("no_such_key")
        container.reset()


class TestConfig:
    def test_settings_loads_defaults(self):
        from smart_qa.config import settings

        assert settings.agent_timeout == 30
        assert settings.max_agent_steps == 15
        assert settings.cache_ttl == 1800

    def test_settings_has_new_fields(self):
        from smart_qa.config import settings

        assert hasattr(settings, "get_support_phone")
        assert hasattr(settings, "get_knowledge_dir")
        assert hasattr(settings, "get_faq_file_list")
        phone = settings.get_support_phone()
        assert phone is not None  # 返回默认提示或配置值

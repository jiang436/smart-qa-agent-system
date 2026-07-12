"""核心配置 — 基于 pydantic-settings 的环境变量管理

所有配置通过 .env 文件或环境变量注入，支持:
  - LLM 提供商配置 (API Key / Base URL / 模型)
  - 数据库连接 (PostgreSQL / Redis / Milvus)
  - 安全限流参数
  - 缓存配置
  - Agent 行为参数

Usage:
    from smart_qa.config import settings
    api_key = settings.llm_api_key
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置 — 自动从 .env / 环境变量加载"""

    # ── LLM ──
    llm_api_key: str = "***"
    llm_base_url: str = "https://api.deepseek.com/v1"
    lightweight_model: str = "deepseek-chat"
    heavy_model: str = "deepseek-chat"

    # ── Database ──
    postgres_dsn: str = "postgresql+asyncpg://user:password@localhost:5432/agent"
    redis_url: str = "redis://localhost:6379/0"

    # ── Milvus ──
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "knowledge_base"

    # ── Rate Limit ──
    global_rate_limit: int = 100
    global_refill_rate: int = 10
    user_rate_limit: int = 20
    user_refill_rate: int = 5
    daily_token_budget: int = 1_000_000

    # ── Cache ──
    cache_ttl: int = 1800
    cache_similarity_threshold: float = 0.95

    # ── Agent ──
    max_agent_steps: int = 15
    agent_timeout: int = 30

    # ── Embedding ──
    embedding_backend: str = "local"  # local / ollama / api
    embedding_model: str = "BAAI/bge-small-zh-v1.5"  # 模型名
    embedding_base_url: str = ""  # ollama/api 服务地址

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

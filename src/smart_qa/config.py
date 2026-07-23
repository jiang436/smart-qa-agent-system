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
    llm_api_key: str = ""
    llm_base_url: str = ""
    lightweight_model: str = "deepseek-chat"
    # ── Database ──
    postgres_dsn: str = "postgresql+asyncpg://user:password@localhost:5432/agent"
    redis_url: str = "redis://localhost:6379/0"

    # ── Milvus ──
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "knowledge_base"

    # ── Knowledge Data Paths ──
    knowledge_dir: str = "data/knowledge"
    faq_files: str = "data/faq_knowledge_base.json"

    # ── Business Config ──
    support_phone: str = ""  # 售后客服热线
    default_device_model: str = ""
    company_name: str = "智家科技"
    agent_name: str = "小智"

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
    agent_timeout: int = 60  # LoopDetector 硬超时 (秒)
    loop_semantic_threshold: float = 0.92  # 语义循环检测相似度阈值
    loop_repeated_tool_threshold: int = 3  # 连续相同工具调用触发警告

    # ── Retrieval ──
    retrieval_l1_threshold: float = 0.45  # L1 语义检索平均分阈值
    retrieval_l1_min_docs: int = 2  # L1 语义检索最少文档数
    retrieval_l2_threshold: float = 0.35  # L2 改写检索平均分阈值
    retrieval_l2_min_docs: int = 1  # L2 改写检索最少文档数
    retrieval_top_k: int = 5  # 默认返回文档数
    retrieval_crag_max_retries: int = 2  # C-RAG 最大重试次数

    # ── Chunking ──
    chunk_size: int = 800
    chunk_overlap: int = 100

    # ── Memory ──
    short_term_window: int = 6  # 短期记忆窗口 (消息数)
    cache_lru_capacity: int = 1000  # 本地缓存最大条目

    # ── Reflection ──
    reflection_max_rounds: int = 3  # 自我反思最大迭代次数

    # ── Reranker ──
    reranker_backend: str = "cross-encoder"  # cross-encoder / llm / heuristic
    reranker_model: str = "BAAI/bge-reranker-large"
    reranker_model_weight: float = 0.7  # 模型分权重 (token分权重 = 1 - model_weight)

    # ── Embedding ──
    embedding_backend: str = "local"  # local / ollama / api
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_fallback_model: str = ""

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Observability ──
    otel_service_name: str = "smart-qa-agent"
    phoenix_data_dir: str = "D:/ai_data/phoenix"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_knowledge_dir(self) -> str:
        """返回知识库目录（已解析相对路径）"""
        return self.knowledge_dir

    def get_support_phone(self) -> str:
        """返回售后热线，未配置时给出提示"""
        return self.support_phone or "（请配置售后热线: SUPPORT_PHONE）"

    def get_faq_file_list(self) -> list[str]:
        """解析 FAQ 文件列表"""
        return [f.strip() for f in self.faq_files.split(",") if f.strip()]


settings = Settings()

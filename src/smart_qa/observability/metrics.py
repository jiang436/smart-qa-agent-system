"""可观测 — Prometheus 指标

对外暴露 /metrics 端点，供 Prometheus 抓取。

指标设计:
  - Counter: 累计计数（请求数、错误数、token 消耗）
  - Histogram: 延迟分布（请求延迟、检索延迟）
  - Gauge: 瞬时值（活跃会话数、缓存大小）

标签维度:
  - intent: qa / troubleshoot / consumables / general
  - scenario: 对应的业务场景
  - status: success / error / blocked
"""

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

try:
    from fastapi import FastAPI, Response

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class MetricsManager:
    """Prometheus 指标管理器

    提供:
      - 应用启动时注册 /metrics 端点
      - 请求计数、延迟、Token 消耗的便捷记录方法

    用法:
      metrics = MetricsManager()
      metrics.setup_metrics(app)

      # 在中间件或路由里
      metrics.record_request(intent="qa", status="success")
      metrics.observe_latency(intent="qa", latency=0.45)
      metrics.track_token_usage(user_id="U1001", tokens=1500)
    """

    def __init__(self):
        if not HAS_PROMETHEUS:
            self.requests_total = None
            self.errors_total = None
            self.tokens_consumed = None
            self.request_latency = None
            self.retrieval_latency = None
            self.active_sessions = None
            self.cache_hits = None
            self.cache_misses = None
            self.cache_size = None
            return

        # ── Counter: 累计请求 ──
        self.requests_total = Counter(
            "qa_agent_requests_total",
            "Total number of agent requests",
            ["intent", "scenario", "status"],
        )

        # ── Counter: 错误总数 ──
        self.errors_total = Counter(
            "qa_agent_errors_total",
            "Total number of errors",
            ["error_type"],  # timeout / retrieval_failed / llm_error / security_blocked
        )

        # ── Counter: Token 消耗 ──
        self.tokens_consumed = Counter(
            "qa_agent_tokens_consumed_total",
            "Total tokens consumed",
            ["user_id", "model"],
        )

        # ── Histogram: 请求延迟 ──
        self.request_latency = Histogram(
            "qa_agent_request_latency_seconds",
            "Request latency in seconds",
            ["intent"],
            buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0],
        )

        # ── Histogram: 检索延迟 ──
        self.retrieval_latency = Histogram(
            "qa_agent_retrieval_latency_seconds",
            "Retrieval latency in seconds",
            ["source"],  # L1_semantic / L2_rewrite / L3_bm25 / L4_llm
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
        )

        # ── Gauge: 活跃会话数 ──
        self.active_sessions = Gauge(
            "qa_agent_active_sessions",
            "Number of active sessions",
        )

        # ── Gauge: 缓存命中率 ──
        self.cache_hits = Counter(
            "qa_agent_cache_hits_total",
            "Total cache hits",
            ["cache_type"],  # semantic / session
        )
        self.cache_misses = Counter(
            "qa_agent_cache_misses_total",
            "Total cache misses",
            ["cache_type"],
        )

        # ── Gauge: 缓存条目数 ──
        self.cache_size = Gauge(
            "qa_agent_cache_size",
            "Number of entries in semantic cache",
        )

    def setup_metrics(self, app: FastAPI):
        """将 /metrics 端点注册到 FastAPI 应用

        Args:
            app: FastAPI 应用实例
        """

        @app.get("/metrics")
        async def metrics_endpoint():
            """Prometheus 指标端点"""
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )

    # ── 便捷记录方法 ──

    def record_request(self, intent: str = "general", scenario: str = "", status: str = "success"):
        """记录一次请求"""
        if not HAS_PROMETHEUS or not self.requests_total:
            return
        self.requests_total.labels(
            intent=intent,
            scenario=scenario or intent,
            status=status,
        ).inc()

    def record_error(self, error_type: str):
        """记录一次错误"""
        self.errors_total.labels(error_type=error_type).inc()

    def observe_latency(self, intent: str, latency: float):
        """记录请求延迟"""
        self.request_latency.labels(intent=intent).observe(latency)

    def observe_retrieval(self, source: str, latency: float):
        """记录检索延迟"""
        self.retrieval_latency.labels(source=source).observe(latency)

    def track_token_usage(self, user_id: str, tokens: int, model: str = "gpt-4o"):
        """追踪 token 消耗"""
        self.tokens_consumed.labels(user_id=user_id, model=model).inc(tokens)

    def record_cache_hit(self, cache_type: str = "semantic"):
        """记录缓存命中"""
        self.cache_hits.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str = "semantic"):
        """记录缓存未命中"""
        self.cache_misses.labels(cache_type=cache_type).inc()

    def set_cache_size(self, size: int):
        """设置当前缓存条目数"""
        self.cache_size.set(size)

    def set_active_sessions(self, count: int):
        """设置当前活跃会话数"""
        self.active_sessions.set(count)

    def get_cache_hit_rate(self, cache_type: str = "semantic") -> float:
        """计算缓存命中率"""
        hits = self.cache_hits.labels(cache_type=cache_type)._value.get()
        misses = self.cache_misses.labels(cache_type=cache_type)._value.get()
        total = hits + misses
        return hits / total if total > 0 else 0.0


# ── 全局单例 ──
_metrics_manager: MetricsManager | None = None


def get_metrics() -> MetricsManager:
    """获取全局 MetricsManager 实例"""
    global _metrics_manager
    if _metrics_manager is None:
        _metrics_manager = MetricsManager()
    return _metrics_manager


def setup_metrics(app: FastAPI):
    """便捷函数：将 Prometheus /metrics 端点注册到 FastAPI

    Usage (in main.py):
        from smart_qa.observability.metrics import setup_metrics
        setup_metrics(app)
    """
    manager = get_metrics()
    manager.setup_metrics(app)

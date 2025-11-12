"""可观测 — 分布式链路追踪

基于 OpenTelemetry，实现 Agent 执行链路的端到端追踪。

追踪维度:
  - Agent 各步骤的时间消耗（router / retrieval / generation / reflection）
  - LLM 调用详情（模型、token 数、延迟）
  - 工具调用详情（工具名、参数、结果）

使用方式:
  tracer = Tracer(service_name="smart-qa-agent")
  with tracer.start_span("rag_retrieval") as span:
      span.set_attribute("query", query)
      result = retriever.retrieve(query)
"""

import time
from contextlib import contextmanager
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import SpanKind, Status, StatusCode

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


class Tracer:
    """分布式链路追踪器

    封装 OpenTelemetry，提供:
      - 自动创建 Span 的上下文管理器
      - Agent 步骤追踪
      - LLM 调用追踪
      - 工具调用追踪
    """

    def __init__(self, service_name: str = "smart-qa-agent", otlp_endpoint: str | None = None):
        """
        Args:
            service_name: 服务名称（显示在追踪系统中）
            otlp_endpoint: OTLP 收集器地址，为 None 时仅输出到控制台
        """
        self.service_name = service_name
        self._initialized = False
        self._tracer = None

        if HAS_OTEL:
            self._setup(otlp_endpoint)
        else:
            print("[Tracer] OpenTelemetry 未安装，追踪功能禁用")

    def _setup(self, otlp_endpoint: str | None = None):
        """初始化 OpenTelemetry Provider"""
        resource = Resource.create({"service.name": self.service_name})

        provider = TracerProvider(resource=resource)

        # 控制台导出（开发环境）
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # OTLP 导出（生产环境）
        if otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                print(f"[Tracer] OTLP 导出已配置: {otlp_endpoint}")
            except Exception as e:
                print(f"[Tracer] OTLP 配置失败: {e}")

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(self.service_name)
        self._initialized = True
        print(f"[Tracer] 已初始化: {self.service_name}")

    @contextmanager
    def start_span(self, name: str, kind: str = "internal", attributes: dict[str, Any] | None = None):
        """创建追踪 Span（上下文管理器）

        Args:
            name: Span 名称，如 "router.classify"、"rag.retrieve"
            kind: Span 类型 (internal / client / server)
            attributes: 附加属性

        Yields:
            Span 对象（或虚拟 Span，当 OTEL 不可用时）
        """
        if not self._initialized:
            # 无 OTEL 时的降级实现：仅计时间
            class _FakeSpan:
                def __init__(self, name):
                    self.name = name
                    self.attributes = {}
                    self.start_time = time.time()

                def set_attribute(self, key, value):
                    self.attributes[key] = value

                def set_status(self, status):
                    pass

                def record_exception(self, exc):
                    pass

            span = _FakeSpan(name)
            try:
                yield span
            finally:
                elapsed = time.time() - span.start_time
                if elapsed > 1.0:  # 只记录 >1s 的慢操作
                    print(f"[Tracer] {name}: {elapsed:.2f}s")
            return

        kind_map = {
            "internal": SpanKind.INTERNAL,
            "client": SpanKind.CLIENT,
            "server": SpanKind.SERVER,
        }
        span = self._tracer.start_span(name, kind=kind_map.get(kind, SpanKind.INTERNAL))

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
        finally:
            span.end()

    # ── 便捷追踪方法 ──

    def trace_agent_step(self, step_name: str, attributes: dict[str, Any] | None = None):
        """追踪 Agent 执行步骤

        Usage:
            with tracer.trace_agent_step("router.classify", {"query": query}) as span:
                intent = router.classify(query)
        """
        return self.start_span(f"agent.{step_name}", kind="internal", attributes=attributes)

    def trace_llm_call(self, model: str, prompt_length: int = 0):
        """追踪 LLM 调用

        Usage:
            with tracer.trace_llm_call("gpt-4o", prompt_length=len(prompt)) as span:
                response = llm.invoke(prompt)
                span.set_attribute("tokens", response.usage.total_tokens)
        """
        return self.start_span(
            "llm.call",
            kind="client",
            attributes={"model": model, "prompt_length": prompt_length},
        )

    def trace_tool_call(self, tool_name: str, arguments: dict | None = None):
        """追踪工具调用

        Usage:
            with tracer.trace_tool_call("get_device_status", {"device_id": "X30"}) as span:
                result = mcp_client.call("device", "get_device_status", {"device_id": "X30"})
        """
        return self.start_span(
            f"tool.{tool_name}",
            kind="client",
            attributes={"tool": tool_name, "arguments": str(arguments)[:200]},
        )

    def trace_retrieval(self, source: str, query: str):
        """追踪检索操作

        Usage:
            with tracer.trace_retrieval("L1_semantic", query) as span:
                docs = retriever._semantic_search(query)
                span.set_attribute("hits", len(docs))
        """
        return self.start_span(
            f"retrieval.{source}",
            kind="internal",
            attributes={"source": source, "query": query[:200]},
        )


# ── 全局单例 ──
_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    """获取全局 Tracer 实例"""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer

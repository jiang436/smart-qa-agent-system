"""Logfire 可观测 — 一键接入全栈可观测

替换三套独立组件（loguru + Prometheus + OTEL），实现：
  - 日志、指标、追踪合一，单点配置
  - 零代码 auto-instrumentation（FastAPI / SQLAlchemy / httpx / Pydantic）

使用方式（web.py lifespan 中调用）:
    from smart_qa.observability.logfire_setup import setup_logfire
    await setup_logfire()

环境变量:
    LOGFIRE_TOKEN    — Pydantic Logfire API Token（为空则跳过）
    LOGFIRE_SERVICE  — 服务名（默认 smart-qa-agent）
    LOGFIRE_ENV      — 环境名（默认 development）

原理:
    Logfire 底层基于 OpenTelemetry，instrument 函数自动注册 Span 处理器。
    FastAPI 请求、SQLAlchemy 查询、httpx LLM 调用、Pydantic 模型校验
    全部自动生成 Trace，无需手动打点。

降级策略:
    无 LOGFIRE_TOKEN → 静默跳过，不影响现有 loguru/Prometheus 监控。
"""

from __future__ import annotations

import os

from smart_qa.observability.logger import logger

_initialized = False


async def setup_logfire(app=None, engine=None):
    """初始化 Logfire 并接入全栈 auto-instrumentation

    仅在 LOGFIRE_TOKEN 配置时生效，无 token 时静默跳过。

    Args:
        app: FastAPI 应用实例（用于 instrument_fastapi）
        engine: SQLAlchemy 引擎实例（用于 instrument_sqlalchemy）
    """
    global _initialized
    if _initialized:
        return

    token = os.getenv("LOGFIRE_TOKEN", "").strip()
    if not token:
        logger.info("Logfire 未配置 (LOGFIRE_TOKEN 为空)，跳过")
        return

    service_name = os.getenv("LOGFIRE_SERVICE", "smart-qa-agent")
    env_name = os.getenv("LOGFIRE_ENV", "development")

    try:
        import logfire

        # ── 1. 初始化 Logfire ──
        logfire.configure(
            token=token,
            service_name=service_name,
            environment=env_name,
        )
        logger.info("Logfire 已初始化 service={} env={}", service_name, env_name)

        # ── 2. FastAPI 自动追踪 ──
        # 捕获所有 API 请求的 method/path/status/duration
        if app is not None:
            logfire.instrument_fastapi(app)
            logger.debug("Logfire instrument: FastAPI")
        else:
            logger.debug("Logfire: 跳过 FastAPI（未传入 app）")

        # ── 3. httpx 自动追踪（LLM 调用） ──
        # 捕获对外 HTTP 请求的 URL/status/duration
        logfire.instrument_httpx()
        logger.debug("Logfire instrument: httpx")

        # ── 4. SQLAlchemy 自动追踪 ──
        # 捕获数据库查询的 SQL/耗时/行数
        if engine is not None:
            logfire.instrument_sqlalchemy(engine=engine)
            logger.debug("Logfire instrument: SQLAlchemy")
        else:
            logger.debug("Logfire: 跳过 SQLAlchemy（未传入 engine）")

        # ── 5. Pydantic 自动追踪 ──
        # 捕获模型创建/校验/序列化过程
        logfire.instrument_pydantic()
        logger.debug("Logfire instrument: Pydantic")

        # ── 6. 系统指标（CPU/内存/GC） ──
        logfire.instrument_system_metrics()
        logger.debug("Logfire instrument: System Metrics")

        _initialized = True
        logger.info("Logfire 全栈可观测已就绪")

    except Exception as e:
        logger.warning("Logfire 初始化失败: {}，不影响现有监控", e)

"""统一日志 — loguru 优先 + Loki 推送 + 标准 logging 降级

Usage:
    from smart_qa.observability.logger import logger
    logger.info("用户提问: {}", query)

说明:
    - loguru 可用时使用 loguru（支持 {} 格式）
    - loguru 不可用时降级到标准 logging（%s 格式）
    - Loki 推送可选（通过环境变量 LOKI_URL 启用）
"""

from __future__ import annotations

import logging
import os
import sys


class _Logger:
    """日志适配器 — loguri / logging 双后端自动适配"""

    def __init__(self):
        self._loguru = False
        self._stdlib = False
        self._logger: logging.Logger | None = None
        self._loki_url = os.getenv("LOKI_URL", "")
        self._loki_labels = {"app": "smart-qa-agent", "env": os.getenv("ENV", "dev")}

        # ═══════════════════════════════════════
        # 尝试 loguru（支持 {} 格式）
        # ═══════════════════════════════════════
        try:
            from loguru import logger as _loguru

            _loguru.remove()
            _loguru.add(
                sys.stderr,
                format=(
                    "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> "
                    "| <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>"
                ),
                level="DEBUG",
                colorize=True,
            )
            if self._loki_url:
                _loguru.add(
                    self._loki_sink, format="{time} {level} {name} {function} {message}", level="INFO", serialize=True
                )
            self._loguru = True
            self._loguru_logger = _loguru
            return
        except ImportError:
            pass

        # ═══════════════════════════════════════
        # 降级: 标准 logging（支持 %s 格式）
        # ═══════════════════════════════════════
        self._stdlib = True
        fmt = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s — %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=fmt, datefmt="%H:%M:%S", stream=sys.stderr)

        if self._loki_url:
            handler = _LokiHandler(self._loki_url, self._loki_labels)
            handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(handler)

        self._stdlib_logger = logging.getLogger("qa_agent")

    # ── 格式化辅助 ──

    @staticmethod
    def _fmt(msg: str, args: tuple) -> tuple[str, tuple]:
        """loguru 模式下不需要转换，stdlib 模式需要 {} → %s"""
        # 浅替换：防止 {:.1f} 等格式符被破坏
        import re

        msg = re.sub(r"\{([^}]*)\}", lambda m: f"%{m.group(1)}" if m.group(1) else "%s", msg)
        return msg, args

    # ── Loki sink（loguru 模式）──

    def _loki_sink(self, message):
        import json
        import urllib.request

        record = message.record
        payload = {
            "streams": [
                {
                    "stream": self._loki_labels,
                    "values": [
                        [
                            str(int(record["time"].timestamp() * 1e9)),
                            json.dumps({"level": record["level"].name, "message": str(record["message"])}),
                        ]
                    ],
                }
            ]
        }
        try:
            req = urllib.request.Request(
                f"{self._loki_url}/loki/api/v1/push",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

    # ── 日志方法 ──

    def debug(self, msg, *args, **kwargs):
        if self._loguru:
            self._loguru_logger.debug(msg, *args, **kwargs)
        else:
            msg, args = self._fmt(msg, args)
            self._stdlib_logger.debug(msg % args, **kwargs) if args else self._stdlib_logger.debug(msg, **kwargs)

    def info(self, msg, *args, **kwargs):
        if self._loguru:
            self._loguru_logger.info(msg, *args, **kwargs)
        else:
            msg, args = self._fmt(msg, args)
            self._stdlib_logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        if self._loguru:
            self._loguru_logger.warning(msg, *args, **kwargs)
        else:
            msg, args = self._fmt(msg, args)
            self._stdlib_logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self._loguru:
            self._loguru_logger.error(msg, *args, **kwargs)
        else:
            msg, args = self._fmt(msg, args)
            self._stdlib_logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self._loguru:
            self._loguru_logger.critical(msg, *args, **kwargs)
        else:
            msg, args = self._fmt(msg, args)
            self._stdlib_logger.critical(msg, *args, **kwargs)


class _LokiHandler(logging.Handler):
    """标准 logging → Loki HTTP 推送"""

    def __init__(self, url, labels):
        super().__init__()
        self._url = url
        self._labels = labels

    def emit(self, record):
        import json
        import urllib.request

        payload = {
            "streams": [
                {
                    "stream": self._labels,
                    "values": [
                        [
                            str(int(record.created * 1e9)),
                            json.dumps({"level": record.levelname, "message": self.format(record)}),
                        ]
                    ],
                }
            ]
        }
        try:
            req = urllib.request.Request(
                f"{self._url}/loki/api/v1/push",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass


logger = _Logger()

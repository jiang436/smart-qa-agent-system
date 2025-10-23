"""统一日志 — loguru 优先 + Loki 推送 + 标准 logging 降级

Usage:
    from src.observability.logger import logger
    logger.info("用户提问: {}", query)
"""

import logging
import os
import re
import sys


class _Logger:
    """适配器 — loguru {} / Loki / logging % 三种后端自动适配"""

    def __init__(self):
        self._logger = None
        self._loki_url = os.getenv("LOKI_URL", "")
        self._loki_labels = {"app": "smart-qa-agent", "env": os.getenv("ENV", "dev")}

        # 尝试 loguru
        try:
            from loguru import logger as _loguru

            _loguru.remove()
            _loguru.add(
                sys.stderr,
                format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
                level="DEBUG",
                colorize=True,
            )
            # 如果有 Loki URL, 加 Loki sink
            if self._loki_url:
                _loguru.add(
                    self._loki_sink,
                    format="{time} {level} {name} {function} {message}",
                    level="INFO",
                    serialize=True,
                )
            self._logger = _loguru
            return
        except ImportError:
            pass

        # 降级: 标准 logging
        fmt = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s — %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=fmt, datefmt="%H:%M:%S", stream=sys.stderr)

        # Loki handler for standard logging
        if self._loki_url:
            handler = _LokiHandler(self._loki_url, self._loki_labels)
            handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(handler)

        self._logger = logging.getLogger("qa_agent")

    def _loki_sink(self, message):
        """loguru → Loki sink"""
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
            pass  # Loki 不可用时静默丢弃

    def _fmt(self, msg, args):
        msg = re.sub(r"\{\}", "%s", msg)
        return msg, args

    def debug(self, msg, *args, **kwargs):
        msg, args = self._fmt(msg, args)
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        msg, args = self._fmt(msg, args)
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        msg, args = self._fmt(msg, args)
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        msg, args = self._fmt(msg, args)
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        msg, args = self._fmt(msg, args)
        self._logger.critical(msg, *args, **kwargs)


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

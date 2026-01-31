"""向后兼容 — 从 src 重导出"""
from src.app.config import settings, Settings

__all__ = ["settings", "Settings"]

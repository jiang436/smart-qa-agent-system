"""统一依赖注入容器

替代项目中分散的 get_llm_client()、全局 _shared_bm25、单例懒加载等混用模式。
所有依赖通过 AppContainer 注册和获取，支持测试时替换。

Usage:
    from smart_qa.di import container

    # 注册（在 lifespan 中）
    container.register("llm", llm_client)
    container.register("bm25", bm25_index)

    # 获取
    llm = container.get("llm")
    bm25 = container.get("bm25")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from smart_qa.exceptions import ConfigError


class AppContainer:
    """轻量 DI 容器 — 替代全局变量和分散的工厂函数

    特性:
      - 按名称注册/获取依赖
      - 支持懒加载工厂函数（首次 get 时才构建）
      - 支持测试时替换
      - 线程安全（基于 dict，CPython GIL 保证基本安全）
    """

    def __init__(self):
        self._instances: dict[str, Any] = {}
        self._factories: dict[str, Any] = {}

    # ── 注册 ──

    def register(self, name: str, instance: Any) -> None:
        """注册已创建的实例"""
        self._instances[name] = instance

    def register_factory(self, name: str, factory: Callable[..., Any]) -> None:
        """注册懒加载工厂函数（首次 get() 时调用）"""
        self._factories[name] = factory

    # ── 获取 ──

    def get(self, name: str, default: Any = None) -> Any:
        """获取依赖实例

        Args:
            name: 依赖名称
            default: 未注册时的默认值

        Returns:
            注册的实例或默认值

        Raises:
            ConfigError: 未注册且无默认值时抛出
        """
        if name in self._instances:
            return self._instances[name]

        if name in self._factories:
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance

        if default is not None:
            return default

        raise ConfigError(f"依赖未注册: '{name}'")

    def get_optional(self, name: str) -> Any | None:
        """获取可选依赖，未注册时返回 None（不抛异常）"""
        if name in self._instances:
            return self._instances[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance
        return None

    # ── 状态检查 ──

    def has(self, name: str) -> bool:
        """检查依赖是否已注册"""
        return name in self._instances or name in self._factories

    def registered_names(self) -> list[str]:
        """列出所有已注册的依赖名"""
        return list(self._instances.keys()) + list(self._factories.keys())

    # ── 清理 ──

    def reset(self):
        """清空所有依赖（测试清理用）"""
        self._instances.clear()
        self._factories.clear()


# ── 全局容器实例 ──
container = AppContainer()

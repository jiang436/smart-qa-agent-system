"""统一异常层次结构

所有业务异常从此模块抛出，便于统一处理、日志记录和降级响应。

Usage:
    from smart_qa.exceptions import RetrievalError, LLMError, ConfigError

    raise RetrievalError("Milvus 连接超时", details={"host": host})
"""


class QAException(Exception):
    """QA 系统基础异常 — 所有业务异常的基类"""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── 检索层异常 ──


class RetrievalError(QAException):
    """检索失败（向量检索 / BM25 / 索引不可用）"""


class VectorStoreError(RetrievalError):
    """Milvus / 向量存储异常"""


class BM25Error(RetrievalError):
    """BM25 索引异常"""


class DocumentParseError(QAException):
    """文档解析失败"""


# ── LLM 层异常 ──


class LLMError(QAException):
    """LLM 调用失败"""


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""


class LLMRateLimitError(LLMError):
    """LLM 限流 / 额度耗尽"""


# ── Agent 层异常 ──


class AgentError(QAException):
    """Agent 执行异常"""


class RouterError(AgentError):
    """意图路由异常"""


class LoopDetectedError(AgentError):
    """检测到 Agent 循环"""


class ScenarioError(AgentError):
    """场景执行异常"""


# ── 配置 / 基础设施异常 ──


class ConfigError(QAException):
    """配置缺失或无效"""


class DatabaseError(QAException):
    """数据库操作异常"""


class CacheError(QAException):
    """缓存操作异常"""


class SecurityError(QAException):
    """安全检查拦截"""

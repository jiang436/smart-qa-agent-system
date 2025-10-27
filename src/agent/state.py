"""LangGraph 状态定义"""

from collections.abc import Sequence
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Agent 全局状态"""

    # ── 对话相关 ──
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    session_id: str

    # ── 场景路由 ──
    intent: str | None  # 意图: qa / troubleshoot / consumables / general
    scenario: str | None  # 场景名称

    # ── 当前步骤 ──
    step: int  # 当前执行步数
    max_steps: int  # 最大执行步数
    tool_calls_history: list[str]  # 已调用的工具列表（防循环检测用）

    # ── 检索 & 回答 ──
    retrieved_docs: list[dict] | None  # 检索到的文档
    final_answer: str | None  # 最终回答

    # ── 记忆层 ──
    user_profile: dict | None  # 用户画像（设备/偏好）
    short_term: dict | None  # 短期对话上下文
    task_memory: dict | None  # 当前任务执行状态

    # ── 异常监控 ──
    error: str | None  # 错误信息
    loop_detected: bool  # 是否检测到循环

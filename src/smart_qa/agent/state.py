"""LangGraph 全局状态定义

定义 AgentState TypedDict，作为 LangGraph StateGraph 各节点间传递的唯一数据载体。
所有节点都通过读取和更新此状态来协作。

状态设计原则:
  - 消息驱动：messages 字段通过 Annotated[Sequence, add_messages] 自动追加，
    每个节点可以通过 .messages[-1] 获取最新消息。
  - 幂等字段：intent / scenario / final_answer 等字段每轮由 Router 和 Scenario
    重新写入，不会跨步累积。
  - 记忆分层：user_profile / short_term / task_memory 对应 L3/L2/L4 记忆层，
    分别由 memory_reader / RAGAgent / 场景节点 管理生命周期。

状态流转（从入口到出口）:
    memory_reader  →  Router  →  Scenario  →  guard_check  →  memory_writer  →  END
        设置          设置         设置           检查             持久化
    user_profile    intent      final_answer   loop_detected     user_profile
                    scenario    retrieved_docs                   (更新)
                                task_memory
"""

from collections.abc import Sequence
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Agent 全局状态

    所有字段都是可选的（TypedDict 语义下通过 | None 显式标注），
    实际运行时各节点在约定的字段上读写。

    字段分组:
        ── 对话基础（memory_reader 初始化，chat.py 创建初始状态）
        - messages: LangGraph 管理的消息列表（自动追加，不手动修改）
        - user_id / session_id: 用户和会话标识

        ── 路由结果（Router Agent 每轮写入）
        - intent: 当前轮次的意图分类结果
        - scenario: 对应场景名称

        ── 执行进度（LoopDetector 维护）
        - step / max_steps: 步数计数器与上限
        - max_execution_time: 壁钟超时（秒）
        - tool_calls_history: 工具调用记录（防循环检测）

        ── 检索与回答（Scenario 节点写入）
        - retrieved_docs: RAG 检索到的文档列表
        - final_answer: 最终生成的回答

        ── 记忆层（各记忆节点读写）
        - user_profile: L3 长期画像（设备型号/偏好等）
        - short_term: L2 短期上下文（最近 6 轮摘要）
        - task_memory: L4 任务状态（故障排查进度/HITL待确认）

        ── 异常监控（LoopDetector 写入）
        - error: 错误信息（非阻塞）
        - loop_detected: 防循环检测结果
    """

    # ── 对话基础 ──
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    session_id: str

    # ── 场景路由 ──
    intent: str | None  # 意图: qa / troubleshoot / consumables / device_control / report / general
    scenario: str | None  # 场景名称（与 intent 一致，便于 dispatch）

    # ── 执行进度 ──
    step: int  # 当前执行步数（每轮 +1）
    max_steps: int  # 步数上限（默认 15，超出后 LoopDetector 触发 force_stop）
    max_execution_time: int  # 壁钟超时（秒，默认 60，超时后 LoopDetector 触发 force_stop）
    tool_calls_history: list[str]  # 已调用的工具名列表（LoopDetector 检查重复调用用）

    # ── 检索与回答 ──
    retrieved_docs: list[dict] | None  # 检索到的文档列表（含 content / source / score）
    final_answer: str | None  # Agent 的最终回答文本

    # ── 记忆层 ──
    user_profile: dict | None  # 用户画像（device_model / preferred_mode / home_layout / tags）
    short_term: dict | None  # 短期对话上下文（summary / recent_messages）
    task_memory: dict | None  # 当前任务执行状态（故障排查 stage / HITL pending_purchase）

    # ── 异常监控 ──
    error: str | None  # 错误信息（场景异常时设置，不阻塞主流程）
    loop_detected: bool  # 是否检测到循环（LoopDetector 设置，decide 读取）

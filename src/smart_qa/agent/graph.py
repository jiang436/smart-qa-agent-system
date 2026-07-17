"""LangGraph StateGraph 主图 — 编排所有 Agent + MemorySaver + LangGraph Store 长期记忆"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

# 兼容 LangGraph >= 1.0 的 InjectedStore（旧版本无此注解）
try:
    from langgraph.store.base import InjectedStore
except ImportError:
    InjectedStore = None  # type: ignore

# LangGraph node config 类型（兼容各版本）
try:
    from langgraph.types import RunnableConfig  # noqa: F811
except ImportError:
    try:
        from langgraph.runtime import RunnableConfig  # noqa: F811
    except ImportError:
        RunnableConfig = None  # type: ignore

from smart_qa.agent.agents.router_agent import RouterAgent
from smart_qa.agent.guards.loop_detector import LoopDetector
from smart_qa.agent.state import AgentState
from smart_qa.config import settings
from smart_qa.observability.logger import logger
from smart_qa.scenarios.qa_scenario import QAScenario
from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario

_memory = MemorySaver()

# LangGraph Store — 延迟初始化（web.py lifespan 中 setup）
_store = None

# 构建 store 类型注解（兼容 LangGraph 各版本）
_StoreAnnotation = Annotated[object, InjectedStore()] if InjectedStore is not None else None


def set_store(store: Any) -> None:
    """注入 LangGraph Store 实例（由 web.py lifespan 调用）

    同时注册到 DI 容器，方便其他模块获取。
    """
    global _store
    _store = store
    try:
        from smart_qa.di import container
        container.register("store", store)
    except Exception:
        pass
    logger.info("LangGraph Store 已注入: {}", type(store).__name__)


def get_store() -> Any | None:
    """获取 LangGraph Store 实例（优先全局引用，回退到 DI 容器）"""
    global _store
    if _store is not None:
        return _store
    try:
        from smart_qa.di import container
        if container.has("store"):
            return container.get("store")
    except Exception:
        pass
    return None


async def memory_reader_node(state: dict[str, Any], config: RunnableConfig | None = None, *, store: _StoreAnnotation = None) -> dict[str, Any]:
    """记忆读取节点 — 从 LangGraph Store 加载用户画像

    在 router 之前执行，将持久化的用户信息注入 state。

    Store namespace:  ('users', user_id)
    Store key:       'profile'
    Store value:     dict(device_model, preferred_mode, home_layout, tags, …)
    """
    # 优先用 LangGraph 注入的 store，回退到全局实例
    _active_store = store if store is not None else _store
    if _active_store is None:
        return state

    user_id = state.get("user_id", "anonymous")
    if not user_id or user_id in ("anonymous", "", "default"):
        return state

    try:
        item = await _active_store.aget(("users", user_id), "profile")
        if item and item.value:
            state["user_profile"] = item.value
            logger.debug("Store 加载用户画像 user={} profile={}", user_id, item.value)
    except Exception as e:
        logger.debug("Store 读取失败 user={} err={}", user_id, e)

    return state


async def memory_writer_node(state: dict[str, Any], config: RunnableConfig | None = None, *, store: _StoreAnnotation = None) -> dict[str, Any]:
    """记忆写入节点 — 从对话中提取用户画像并写入 LangGraph Store

    在 guard_check 之后、END 之前执行。
    只写入 LTM 层级的确信信息（设备型号、偏好、户型等）。
    写入失败不阻塞主流程。
    """
    _active_store = store if store is not None else _store
    if _active_store is None:
        return state
    user_id = state.get("user_id", "anonymous")
    if not user_id or user_id in ("anonymous", "", "default"):
        return state
    if not state.get("final_answer"):
        return state

    # 提取用户消息
    query = _extract_user_query(state)
    if not query:
        return state

    # LLM 结构化提取
    try:
        from smart_qa.di import container

        llm = container.get("llm")
        prompt = (
            "从用户消息中提取以下信息，只输出 JSON，没有的字段填 null：\n"
            "1. device_model: 扫地机器人型号（从对话中识别，如用户提到具体型号）\n"
            "2. preferred_mode: 偏好模式 (quiet/strong/standard)\n"
            "3. home_layout: 户型描述 (如\"三室两厅\")\n\n"
            f"用户消息: {query}\n"
            'JSON: {"device_model": ..., "preferred_mode": ..., "home_layout": ...}'
        )
        resp = await llm.ainvoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
        # 提取 JSON 块
        json_match = re.search(r"\{[^{}]*\}", text)
        if json_match:
            extracted = json.loads(json_match.group(0))
        else:
            extracted = {}

        device_model = extracted.get("device_model")
        preferred_mode = extracted.get("preferred_mode")
        home_layout = extracted.get("home_layout")
    except Exception as e:
        logger.debug("LLM 用户画像提取失败: {}", e)
        device_model = preferred_mode = home_layout = None

    if not any([device_model, preferred_mode, home_layout]):
        return state

    # 加载现有画像，合并后写入
    try:
        item = await _active_store.aget(("users", user_id), "profile")
        profile = item.value.copy() if (item and item.value) else {}
    except Exception:
        profile = {}

    changed = False
    if device_model and not profile.get("device_model"):
        profile["device_model"] = device_model
        changed = True
    if preferred_mode and not profile.get("preferred_mode"):
        profile["preferred_mode"] = preferred_mode
        changed = True
    if home_layout and not profile.get("home_layout"):
        profile["home_layout"] = home_layout
        changed = True

    # 标签合并
    new_tags = [t for t in [device_model, preferred_mode, home_layout] if t]
    if new_tags:
        existing_tags = profile.get("tags", [])
        if isinstance(existing_tags, list):
            merged = list(set(existing_tags + new_tags))
            if len(merged) > len(existing_tags):
                profile["tags"] = merged
                changed = True

    if changed:
        profile.setdefault("visits", 0)
        profile["visits"] = profile.get("visits", 0) + 1
        try:
            await _active_store.aput(("users", user_id), "profile", profile)
            logger.info("Store 写入 user={} profile={}", user_id, profile)
        except Exception as e:
            logger.warning("Store 写入失败 user={} err={}", user_id, e)

    return state


def _extract_user_query(state: dict[str, Any]) -> str:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "") or getattr(msg, "role", "")
            content = getattr(msg, "content", "")
        if role in ("human", "user") and content:
            return content
    return ""


# ═══════════════════════════════════════════
# 通用场景处理器
# ═══════════════════════════════════════════


async def handle_general(state: dict[str, Any]) -> dict[str, Any]:
    """通用场景 — 分层响应规则

    三层响应逻辑:
      第一层（礼貌寒暄）：纯问候/道别/感谢 → 友好简短回应，引导业务问题
      第二层（业务内问题）：由 router 分发到 qa/troubleshoot/consumables，此处不处理
      第三层（超出职责范围）：与扫地机器人无关的问题 → 统一拒绝模板
    """
    if not isinstance(state, dict):
        return state

    from smart_qa.agent.persona import (
        OUT_OF_SCOPE_REJECTION,
        WELCOME_MESSAGE,
        get_greeting_reply,
        is_out_of_scope,
        is_pure_greeting,
    )

    state.pop("final_answer", None)
    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if hasattr(msg, "content"):
            role = getattr(msg, "type", None) or (msg.get("role", "") if isinstance(msg, dict) else "")
            if role in ("human", "user", ""):
                query = msg.content if hasattr(msg, "content") else msg.get("content", "")
                break

    if not query:
        state["final_answer"] = WELCOME_MESSAGE
        return state

    greeting_type = is_pure_greeting(query)
    if greeting_type is not None:
        state["final_answer"] = get_greeting_reply(greeting_type)
        return state

    if is_out_of_scope(query):
        state["final_answer"] = OUT_OF_SCOPE_REJECTION
        return state

    try:
        from smart_qa.agent.persona import get_system_prompt
        from smart_qa.di import container

        llm = container.get("llm")
        persona = get_system_prompt("general")
        is_fresh = len(messages) <= 1
        history_text = ""
        if not is_fresh and len(messages) > 1:
            recent = []
            for m in messages[-6:-1]:
                c = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
                r = getattr(m, "type", "") or (m.get("role", "") if isinstance(m, dict) else "")
                recent.append(f"{'用户' if r in ('human', 'user') else '助手'}: {c[:80]}")
            history_text = "对话历史:\n" + "\n".join(recent) + "\n\n"

        prompt = (
            persona
            + "\n\n"
            + history_text
            + f"用户刚说: {query}\n\n"
            + (
                "请简短友好地回应，表明自己是智能家居客服小智，引导用户说出扫地机器人相关问题。"
                if is_fresh
                else "请结合对话历史自然回应，理解'那'、'它'等指代词。用户问题若与扫地机器人完全无关，使用固定拒绝话术回应。"
            )
        )
        response = await llm.ainvoke(prompt)
        answer = response.content if hasattr(response, "content") else str(response)
        state["final_answer"] = answer.strip() or WELCOME_MESSAGE
    except Exception:
        state["final_answer"] = WELCOME_MESSAGE

    return state


# ═══════════════════════════════════════════
# 图构建
# ═══════════════════════════════════════════


def build_graph(llm_client: Any = None) -> StateGraph:
    """构建 Agent 编排图（MemorySaver + LangGraph Store 长期记忆）"""
    logger.info("构建 LangGraph 编排图")

    router_agent = RouterAgent(llm_client=llm_client)
    loop_detector = LoopDetector(
        max_steps=settings.max_agent_steps,
        max_execution_time=settings.agent_timeout,
        semantic_threshold=settings.loop_semantic_threshold,
        repeated_tool_threshold=settings.loop_repeated_tool_threshold,
    )
    workflow = StateGraph(AgentState)

    workflow.add_node("memory_reader", memory_reader_node)
    workflow.add_node("router", router_agent.route)
    workflow.add_node("qa", QAScenario.run)
    workflow.add_node("troubleshoot", TroubleshootScenario.run)
    workflow.add_node("general_handler", handle_general)
    workflow.add_node("guard_check", loop_detector.check)
    workflow.add_node("memory_writer", memory_writer_node)

    # memory_reader → router → [scenarios] → guard_check → memory_writer → END
    workflow.set_entry_point("memory_reader")
    workflow.add_edge("memory_reader", "router")

    workflow.add_conditional_edges(
        "router",
        RouterAgent.dispatch,
        {
            "qa": "qa",
            "troubleshoot": "troubleshoot",
            "general": "general_handler",
            "done": "guard_check",
        },
    )

    workflow.add_edge("qa", "guard_check")
    workflow.add_edge("troubleshoot", "guard_check")
    workflow.add_edge("general_handler", "guard_check")

    workflow.add_conditional_edges(
        "guard_check",
        LoopDetector.decide,
        {
            "continue": "router",
            "stop": "memory_writer",
            "done": "memory_writer",
        },
    )

    workflow.add_edge("memory_writer", END)

    return workflow.compile(checkpointer=_memory, store=_store)


def get_agent(llm_client=None):
    return build_graph(llm_client=llm_client)

"""LangGraph StateGraph 主图 — 编排所有 Agent + MemorySaver + LangGraph Store 长期记忆"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from smart_qa.agent.agents.router_agent import RouterAgent
from smart_qa.agent.guards.loop_detector import LoopDetector
from smart_qa.agent.state import AgentState
from smart_qa.observability.logger import logger
from smart_qa.scenarios.consumables_scenario import ConsumablesScenario
from smart_qa.scenarios.device_control_scenario import DeviceControlScenario
from smart_qa.scenarios.qa_scenario import QAScenario
from smart_qa.scenarios.report_scenario import ReportScenario
from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario

_memory = MemorySaver()

# LangGraph Store — 延迟初始化（web.py lifespan 中 setup）
_store = None
_store_cm = None


def set_store(store):
    """注入 LangGraph Store 实例（由 web.py lifespan 调用）"""
    global _store
    _store = store
    logger.info("LangGraph Store 已注入: {}", type(store).__name__)


def get_store():
    return _store


async def memory_reader_node(state: dict, config, *, store) -> dict:
    """记忆读取节点 — 从 LangGraph Store 加载用户画像

    在 router 之前执行，将持久化的用户信息注入 state。

    Store namespace:  ('users', user_id)
    Store key:       'profile'
    Store value:     dict(device_model, preferred_mode, home_layout, tags, …)
    """
    user_id = state.get("user_id", "anonymous")
    if not user_id or user_id in ("anonymous", "", "default"):
        return state
    if store is None:
        return state

    try:
        item = await store.aget(("users", user_id), "profile")
        if item and item.value:
            state["user_profile"] = item.value
            logger.debug("Store 加载用户画像 user={} profile={}", user_id, item.value)
    except Exception as e:
        logger.debug("Store 读取失败 user={} err={}", user_id, e)

    return state


async def memory_writer_node(state: dict, config, *, store) -> dict:
    """记忆写入节点 — 从对话中提取用户画像并写入 LangGraph Store

    在 guard_check 之后、END 之前执行。
    同时负责将 final_answer 补入 messages（场景节点只设 answer 不 append 消息），
    确保 MemorySaver checkpoint 包含完整对话历史。
    """
    user_id = state.get("user_id", "anonymous")
    if not user_id or user_id in ("anonymous", "", "default"):
        return state
    if not state.get("final_answer"):
        return state
    if store is None:
        return state

    # ── 将 final_answer 补入 messages ──
    # 场景节点仅设置 final_answer，从不追加到 messages。
    # 此处补上 assistant 消息，使 MemorySaver checkpoint 保留完整对话。
    # 后续 _persist 中已自带去重逻辑（见 stream_handler._persist）。
    final_answer: str = state["final_answer"]
    messages = list(state.get("messages", []))
    if not _last_msg_is_answer(messages, final_answer):
        from langchain_core.messages import AIMessage

        messages.append(AIMessage(content=final_answer))
        state["messages"] = messages

    # 提取用户消息
    query = _extract_user_query(state)
    if not query:
        return state

    # 模式匹配提取
    device_model = _extract_device(query)
    preferred_mode = _extract_preferred_mode(query)
    home_layout = _extract_home_layout(query)

    if not any([device_model, preferred_mode, home_layout]):
        return state

    # 加载现有画像，合并后写入
    try:
        item = await store.aget(("users", user_id), "profile")
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
            await store.aput(("users", user_id), "profile", profile)
            logger.info("Store 写入 user={} profile={}", user_id, profile)
        except Exception as e:
            logger.warning("Store 写入失败 user={} err={}", user_id, e)

    return state


def _last_msg_is_answer(messages: list, answer: str) -> bool:
    """判断 messages 最后一条是否已经是 answer"""
    if not messages:
        return False
    last = messages[-1]
    if hasattr(last, "content"):
        return last.content == answer
    if isinstance(last, dict):
        return last.get("content") == answer
    return False


# ═══════════════════════════════════════════
# 模式匹配工具
# ═══════════════════════════════════════════

_DEVICE_MODELS = ["X30 Pro", "X20 Pro", "T10", "X30", "X20", "R10", "R20"]
_MODE_KEYWORDS = {
    "安静模式": "quiet",
    "静音模式": "quiet",
    "安静": "quiet",
    "强力模式": "strong",
    "强力": "strong",
    "标准模式": "standard",
    "标准": "standard",
}
_HOME_PATTERN = __import__("re").compile(r"([一二两三四五六七八九十\d]+)[室房](?:[一二两三四五六七八九十\d]+厅)?")


def _extract_user_query(state: dict) -> str:
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


def _extract_device(text: str) -> str | None:
    for model in _DEVICE_MODELS:
        if model.lower() in text.lower():
            return model
    return None


def _extract_preferred_mode(text: str) -> str | None:
    for keyword, value in _MODE_KEYWORDS.items():
        if keyword in text:
            return value
    return None


def _extract_home_layout(text: str) -> str | None:
    m = _HOME_PATTERN.search(text)
    return m.group(0) if m else None


# ═══════════════════════════════════════════
# 通用场景处理器
# ═══════════════════════════════════════════


async def handle_general(state: dict) -> dict:
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
        from smart_qa.deps import get_llm_client

        llm = get_llm_client()
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


def build_graph(llm_client=None) -> StateGraph:
    """构建 Agent 编排图（MemorySaver + LangGraph Store 长期记忆）"""
    logger.info("构建 LangGraph 编排图")

    router_agent = RouterAgent(llm_client=llm_client)
    loop_detector = LoopDetector(max_steps=15)
    workflow = StateGraph(AgentState)

    workflow.add_node("memory_reader", memory_reader_node)
    workflow.add_node("router", router_agent.route)
    workflow.add_node("qa", QAScenario.run)
    workflow.add_node("troubleshoot", TroubleshootScenario.run)
    workflow.add_node("consumables", ConsumablesScenario.run)
    workflow.add_node("device_control", DeviceControlScenario.run)
    workflow.add_node("report", ReportScenario.run)
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
            "consumables": "consumables",
            "device_control": "device_control",
            "report": "report",
            "general": "general_handler",
            "done": "guard_check",
        },
    )

    workflow.add_edge("qa", "guard_check")
    workflow.add_edge("troubleshoot", "guard_check")
    workflow.add_edge("consumables", "guard_check")
    workflow.add_edge("device_control", "guard_check")
    workflow.add_edge("report", "guard_check")
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

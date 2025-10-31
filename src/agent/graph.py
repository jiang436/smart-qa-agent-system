"""LangGraph StateGraph 主图 — 编排所有 Agent + MemorySaver 记忆"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agent.agents.router_agent import RouterAgent
from src.agent.guards.loop_detector import LoopDetector
from src.agent.state import AgentState
from src.app.scenarios.consumables_scenario import ConsumablesScenario
from src.app.scenarios.qa_scenario import QAScenario
from src.app.scenarios.troubleshoot_scenario import TroubleshootScenario
from src.observability.logger import logger

_memory = MemorySaver()


async def handle_general(state: dict) -> dict:
    """通用场景 — 分层响应规则

    三层响应逻辑:
      第一层（礼貌寒暄）：纯问候/道别/感谢 → 友好简短回应，引导业务问题
      第二层（业务内问题）：由 router 分发到 qa/troubleshoot/consumables，此处不处理
      第三层（超出职责范围）：与扫地机器人无关的问题 → 统一拒绝模板

    本函数处理：
      - 空消息 → 欢迎语
      - 已在 router 中标记的 general 意图（寒暄已回复 / 越界已拒绝）
      - LLM 兜底（无法匹配任何规则时的自然回应）
    """
    if not isinstance(state, dict):
        return state

    from src.agent.persona import (
        WELCOME_MESSAGE,
        is_pure_greeting,
        get_greeting_reply,
        is_out_of_scope,
        OUT_OF_SCOPE_REJECTION,
    )

    # 每轮重新生成，不读旧缓存
    state.pop("final_answer", None)

    messages = state.get("messages", [])
    query = ""
    for msg in reversed(messages):
        if hasattr(msg, "content"):
            role = getattr(msg, "type", None) or (msg.get("role", "") if isinstance(msg, dict) else "")
            if role in ("human", "user", ""):
                query = msg.content if hasattr(msg, "content") else msg.get("content", "")
                break

    # ── 空消息 → 欢迎语（首次进入界面） ──
    if not query:
        state["final_answer"] = WELCOME_MESSAGE
        return state

    # ── 第一层：礼貌寒暄（兜底，router 应该已经处理，此处防漏） ──
    greeting_type = is_pure_greeting(query)
    if greeting_type is not None:
        state["final_answer"] = get_greeting_reply(greeting_type)
        return state

    # ── 第三层：超出职责范围（兜底，router 应该已经处理） ──
    if is_out_of_scope(query):
        state["final_answer"] = OUT_OF_SCOPE_REJECTION
        return state

    # ── LLM 兜底：无法匹配任何规则时的自然回应 ──
    try:
        from src.agent.persona import get_system_prompt
        from src.app.deps import get_llm_client

        llm = get_llm_client()
        persona = get_system_prompt("general")

        is_fresh = len(messages) <= 1
        history_text = ""
        if not is_fresh and len(messages) > 1:
            recent = []
            for m in messages[-6:-1]:
                c = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
                r = getattr(m, "type", "") or (m.get("role", "") if isinstance(m, dict) else "")
                recent.append(f"{'用户' if r in ('human','user') else '助手'}: {c[:80]}")
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
        # LLM 不可用时，用默认欢迎语
        state["final_answer"] = WELCOME_MESSAGE

    return state


def build_graph(llm_client=None) -> StateGraph:
    """构建 Agent 编排图（带 MemorySaver 持久化记忆）"""
    logger.info("构建 LangGraph 编排图")

    router_agent = RouterAgent(llm_client=llm_client)
    loop_detector = LoopDetector(max_steps=15)
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_agent.route)
    workflow.add_node("qa", QAScenario.run)
    workflow.add_node("troubleshoot", TroubleshootScenario.run)
    workflow.add_node("consumables", ConsumablesScenario.run)
    workflow.add_node("general_handler", handle_general)
    workflow.add_node("guard_check", loop_detector.check)

    workflow.set_entry_point("router")

    workflow.add_conditional_edges("router", RouterAgent.dispatch, {
        "qa": "qa", "troubleshoot": "troubleshoot",
        "consumables": "consumables", "general": "general_handler",
        "done": END,  # FAQ 高置信命中 → 直接返回，跳过 RAG
    })

    workflow.add_edge("qa", "guard_check")
    workflow.add_edge("troubleshoot", "guard_check")
    workflow.add_edge("consumables", "guard_check")
    workflow.add_edge("general_handler", "guard_check")

    workflow.add_conditional_edges("guard_check", LoopDetector.decide, {
        "continue": "router", "stop": END, "done": END,
    })

    return workflow.compile(checkpointer=_memory)


def get_agent(llm_client=None):
    return build_graph(llm_client=llm_client)

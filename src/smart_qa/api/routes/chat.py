"""对话路由 — POST /chat, /chat/stream

多轮对话支持:
  MemorySaver（LangGraph 内置）处理同次启动内的连续对话。
  PostgreSQL 持久化确保服务重启后用户上下文不丢失。
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from smart_qa.api.deps import check_rate_limit, check_security
from smart_qa.api.stream_handler import SSEStreamHandler
from smart_qa.deps import get_agent_graph, get_security
from smart_qa.memory.conversation_store import load_messages, save_messages
from smart_qa.models.chat_schema import ChatRequest, ChatResponse
from smart_qa.observability.logger import logger
from smart_qa.security import SensitiveFilter

router = APIRouter()


def _create_initial_state(user_id: str, message: str, session_id: str = "") -> dict:
    """创建 Agent 初始状态

    MemorySaver 自动恢复同 session 的对话记忆（本进程内）。
    PG 持久化保证重启后上下文不丢失。
    """
    return {
        "messages": [{"role": "user", "content": message}],
        "user_id": user_id,
        "session_id": session_id or str(uuid.uuid4())[:12],
        "intent": None,
        "scenario": None,
        "step": 0,
        "max_steps": 15,
        "tool_calls_history": [],
        "final_answer": None,
        "error": None,
    }


async def _restore_context(state: dict, graph) -> dict:
    """从 PostgreSQL 恢复对话上下文（服务重启后 MemorySaver 丢失时生效）

    策略:
      1. 尝试从 MemorySaver 获取已有状态
      2. MemorySaver 有历史 → 跳过 PG（MemorySaver 已是完整上下文）
      3. MemorySaver 无历史 → 从 PG 加载 → 合并到当前 state
    """
    session_id = state["session_id"]
    config = {"configurable": {"thread_id": session_id}}

    try:
        snapshot = await graph.aget_state(config)
        if snapshot and snapshot.values.get("messages"):
            return state  # MemorySaver 已有上下文
    except Exception:
        pass

    try:
        history = await load_messages(session_id)
        if history:
            state["messages"] = history + state["messages"]
            logger.info("PG 对话上下文恢复: session={} msgs={}", session_id, len(history))
    except Exception as e:
        logger.debug("PG 对话上下文恢复失败: {}", e)

    return state


# ═══════════════════════════════════════════
# 非流式对话
# ═══════════════════════════════════════════


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _rl: None = Depends(check_rate_limit),
    _sec: None = Depends(check_security),
    security: SensitiveFilter = Depends(get_security),
):
    graph = get_agent_graph()

    if not request.message.strip():
        from smart_qa.agent.persona import WELCOME_MESSAGE

        return ChatResponse(
            answer=WELCOME_MESSAGE,
            session_id=request.session_id or str(uuid.uuid4())[:12],
            intent="general",
        )

    state = _create_initial_state(request.user_id, request.message, request.session_id)
    session_id = state["session_id"]
    config = {"configurable": {"thread_id": session_id}}

    logger.info("收到对话请求 user={} msg_len={} session={}", request.user_id, len(request.message), session_id)

    # 恢复 PG 上下文（重启后 MemorySaver 丢失时）
    state = await _restore_context(state, graph)

    t0 = time.time()
    try:
        result = await graph.ainvoke(state, config=config)
        elapsed = time.time() - t0
        intent = result.get("intent", "general")
        answer = security.check_output(result.get("final_answer", ""))
        logger.info("对话完成 user={} intent={} latency={:.1f}s", request.user_id, intent, elapsed)

        # 持久化到 PostgreSQL
        try:
            final_messages = result.get("messages", state.get("messages", []))
            if isinstance(final_messages, list) and len(final_messages) > 1:
                await save_messages(session_id, request.user_id, final_messages, intent=intent)
        except Exception as e:
            logger.debug("PG 对话保存失败: {}", e)

        return ChatResponse(
            answer=answer or "抱歉，处理您的问题时出现了错误。",
            session_id=result.get("session_id", session_id),
            intent=intent,
        )
    except Exception as e:
        logger.error("对话异常 user={} err={}", request.user_id, str(e))
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


# ═══════════════════════════════════════════
# 流式对话
# ═══════════════════════════════════════════


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    _rl: None = Depends(check_rate_limit),
    _sec: None = Depends(check_security),
):
    graph = get_agent_graph()
    state = _create_initial_state(request.user_id, request.message, request.session_id)

    # 流式也恢复 PG 上下文
    state = await _restore_context(state, graph)

    return StreamingResponse(
        SSEStreamHandler.stream_agent_response(
            agent_executor=graph,
            query=request.message,
            user_id=request.user_id,
            initial_state=state,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

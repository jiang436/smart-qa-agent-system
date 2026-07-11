"""对话路由 — POST /chat, /chat/stream"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from smart_qa.api.deps import check_rate_limit, check_security
from smart_qa.api.stream_handler import SSEStreamHandler
from smart_qa.deps import get_agent_graph, get_security
from smart_qa.models.chat_schema import ChatRequest, ChatResponse
from smart_qa.observability.logger import logger
from smart_qa.security import SensitiveFilter

router = APIRouter()


def _create_initial_state(user_id: str, message: str, session_id: str = "") -> dict:
    """创建 Agent 初始状态 — MemorySaver 自动恢复记忆

    空消息处理：当前端首次进入智能问答界面时，可能发送空消息，
    此时返回欢迎语而非通用问候。
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
        "final_answer": None,  # 每轮强制清空，防止上轮残留
        "error": None,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _rl: None = Depends(check_rate_limit),
    _sec: None = Depends(check_security),
    security: SensitiveFilter = Depends(get_security),
):
    graph = get_agent_graph()

    # ── 空消息 → 直接返回欢迎语，无需走整条链路 ──
    if not request.message.strip():
        from smart_qa.agent.persona import WELCOME_MESSAGE

        return ChatResponse(
            answer=WELCOME_MESSAGE,
            session_id=request.session_id or str(uuid.uuid4())[:12],
            intent="general",
        )

    state = _create_initial_state(request.user_id, request.message, request.session_id)
    logger.info("收到对话请求 user={} msg_len={}", request.user_id, len(request.message))

    t0 = time.time()
    try:
        config = {"configurable": {"thread_id": state["session_id"]}}
        result = await graph.ainvoke(state, config=config)
        elapsed = time.time() - t0
        intent = result.get("intent", "general")
        answer = security.check_output(result.get("final_answer", ""))
        logger.info("对话完成 user={} intent={} latency={:.1f}s", request.user_id, intent, elapsed)
        return ChatResponse(
            answer=answer or "抱歉，处理您的问题时出现了错误。",
            session_id=result.get("session_id", request.session_id),
            intent=intent,
        )
    except Exception as e:
        logger.error("对话异常 user={} err={}", request.user_id, str(e))
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    _rl: None = Depends(check_rate_limit),
    _sec: None = Depends(check_security),
):
    graph = get_agent_graph()
    state = _create_initial_state(request.user_id, request.message, request.session_id)

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

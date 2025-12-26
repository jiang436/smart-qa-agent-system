"""SSE 流式输出 — 将 Agent 执行过程实时推送到前端"""
import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from src.database.redis import RedisClient


class SSEStreamHandler:
    """SSE 流处理器"""

    @staticmethod
    async def stream_agent_response(
        agent_executor,
        query: str,
        user_id: str,
        initial_state: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        # 阶段 1: 意图识别
        yield SSEStreamHandler._format_event("status", {"stage": "意图识别", "message": "正在理解您的问题..."})
        await asyncio.sleep(0.05)

        if agent_executor is None:
            yield SSEStreamHandler._format_event("error", {"message": "Agent 服务未初始化"})
            return

        if initial_state is None:
            initial_state = {
                "messages": [{"role": "user", "content": query}],
                "user_id": user_id,
                "session_id": "",
                "intent": None,
                "step": 0,
                "max_steps": 15,
                "tool_calls_history": [],
                "error": None,
                "loop_detected": False,
            }

        try:
            yield SSEStreamHandler._format_event("status", {"stage": "检索", "message": "正在查找信息..."})

            config = {"configurable": {"thread_id": initial_state.get("session_id", "default")}}
            result = await agent_executor.ainvoke(initial_state, config=config)
            final_answer = result.get("final_answer", "")
            intent = result.get("intent", "")

            if final_answer:
                yield SSEStreamHandler._format_event("status", {"stage": "生成", "message": "正在生成回答..."})
                for ch in final_answer:
                    yield SSEStreamHandler._format_event("token", {"text": ch})
                    await asyncio.sleep(0.02)
            else:
                yield SSEStreamHandler._format_event("token", {"text": "抱歉，未能生成回答。"})

            # 持久化所有记忆层
            await SSEStreamHandler._persist(result)

            yield SSEStreamHandler._format_event("citation", {"message": "以上信息来自产品资料"})
            sid = result.get("session_id", initial_state.get("session_id", ""))
            yield SSEStreamHandler._format_event("done", {"message": "回答完成", "intent": intent, "session_id": sid})

        except Exception as e:
            yield SSEStreamHandler._format_event("error", {"message": str(e)[:200]})

    @staticmethod
    async def _persist(state: dict):
        """持久化对话上下文到 Redis"""
        sid = state.get("session_id")
        if not sid:
            return
        try:
            # messages（最近 20 条）
            history = state.get("messages", [])
            answer = state.get("final_answer", "") or ""
            all_msgs = history + [{"role": "assistant", "content": answer}]
            await RedisClient.set_json(f"history:{sid}", all_msgs[-20:], ttl=86400)

            # user_profile
            profile = state.get("user_profile")
            if profile:
                await RedisClient.set_json(f"profile:{sid}", profile, ttl=86400)

            # short_term
            short = state.get("short_term")
            if short:
                await RedisClient.set_json(f"short:{sid}", short, ttl=86400)

            # task_memory（故障排查进度）
            task = state.get("task_memory")
            if task:
                await RedisClient.set_json(f"diag:{sid}", task, ttl=86400)
        except Exception:
            pass

    @staticmethod
    def _format_event(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def get_sse_response(headers: dict[str, str] | None = None) -> dict:
        h = {"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}
        if headers:
            h.update(headers)
        h.setdefault("X-Accel-Buffering", "no")
        return h

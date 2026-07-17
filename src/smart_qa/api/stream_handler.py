"""SSE 流式输出 — 用 LangGraph astream 实现真正的逐节点推送"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from smart_qa.memory.conversation_store import save_messages
from smart_qa.observability.logger import logger


class SSEStreamHandler:
    """SSE 流处理器 — 真正边执行边推送"""

    @staticmethod
    async def stream_agent_response(
        agent_executor,
        query: str,
        user_id: str,
        initial_state: dict[str, Any] | None = None,
        output_filter=None,
    ) -> AsyncGenerator[str, None]:
        if agent_executor is None:
            yield SSEStreamHandler._event("error", {"message": "Agent 服务未初始化"})
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

        session_id = initial_state.get("session_id", "default")
        config = {"configurable": {"thread_id": session_id}}

        # 节点中文名映射
        _NODE_LABELS = {
            "memory_reader": ("准备", "正在加载用户信息..."),
            "router": ("意图识别", "正在理解您的问题..."),
            "qa": ("检索中", "正在查找相关资料..."),
            "troubleshoot": ("故障诊断", "正在排查问题..."),
            "general_handler": ("处理中", "正在处理..."),
            "guard_check": ("校验", "正在检查回答质量..."),
            "memory_writer": ("保存", "正在保存对话..."),
        }

        result = {}
        try:
            # 流式遍历每个节点
            async for chunk in agent_executor.astream(initial_state, config=config):
                for node_name, node_output in chunk.items():
                    label, msg = _NODE_LABELS.get(node_name, (node_name, f"执行中: {node_name}"))
                    yield SSEStreamHandler._event("status", {"stage": label, "message": msg, "node": node_name})

                    # 累积结果（最后一个非 None 的 output 覆盖）
                    if isinstance(node_output, dict):
                        result.update(node_output)

            # 输出 final_answer
            final_answer = result.get("final_answer", "")
            intent = result.get("intent", "")

            if final_answer:
                if output_filter:
                    final_answer = output_filter(final_answer)
                yield SSEStreamHandler._event("status", {"stage": "生成回答", "message": "完成"})
                # 以词为单位流式输出
                for ch in final_answer:
                    yield SSEStreamHandler._event("token", {"text": ch})
                    await asyncio.sleep(0.015)
            else:
                yield SSEStreamHandler._event("token", {"text": "抱歉，未能生成回答。"})

            # 持久化
            await SSEStreamHandler._persist(result)

            # 提取引用信息
            retrieved_docs = result.get("retrieved_docs", [])
            citations = []
            seen = set()
            for i, doc in enumerate(retrieved_docs[:5]):
                content = doc.get("content", "")
                if not content:
                    continue
                # 用 content 前 80 字符去重
                key = content[:80]
                if key in seen:
                    continue
                seen.add(key)
                # source 优先取原始文件路径（在 chunk 的 source metadata 中）
                file_src = doc.get("file", "") or doc.get("filename", "") or doc.get("src", "")
                citations.append({
                    "doc_id": str(doc.get("doc_id", i)),
                    "source": file_src or doc.get("source", ""),
                    "matched_sentence": content[:200],
                })

            yield SSEStreamHandler._event("done", {
                "message": "回答完成",
                "intent": intent,
                "session_id": result.get("session_id", session_id),
                "citations": citations,
            })

        except Exception as e:
            logger.error("SSE 流式异常: {}", str(e)[:200])
            yield SSEStreamHandler._event("error", {"message": str(e)[:200]})

    @staticmethod
    async def _persist(state: dict):
        sid = state.get("session_id")
        uid = state.get("user_id", "anonymous")
        if not sid:
            return
        try:
            messages = state.get("messages", [])
            if isinstance(messages, list) and len(messages) > 1:
                await save_messages(session_id=sid, user_id=uid, messages=messages, intent=state.get("intent"))
        except Exception as e:
            logger.debug("SSE persist 失败: {}", e)

    @staticmethod
    def _event(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def get_sse_response(headers: dict[str, str] | None = None) -> dict:
        h = {"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}
        if headers:
            h.update(headers)
        h.setdefault("X-Accel-Buffering", "no")
        return h

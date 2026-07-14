"""SSE 流式输出 — 将 Agent 执行过程实时推送到前端

流式策略:
  - Agent 完整执行后才输出（astream_events 暂不支持本图的复杂节点结构）
  - 回答按 10 字符分块推送（取代逐字推送），平衡实时性与渲染开销
  - 通过 yield 生成 SSE 事件流，事件类型:
      - status:   阶段状态推送（意图识别/检索/生成等）
      - token:    回答文本片段（前端逐 chunk 渲染）
      - citation: 引用来源信息
      - done:     回答完成，含 intent 和 session_id
      - error:    错误信息

用法:
    return StreamingResponse(
        SSEStreamHandler.stream_agent_response(graph, query, user_id, state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
"""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from smart_qa.memory.conversation_store import save_messages
from smart_qa.observability.logger import logger


class SSEStreamHandler:
    """SSE 流处理器

    以 Server-Sent Events 格式将 Agent 执行过程推送到前端。
    所有方法均为 @staticmethod，无状态实例。

    事件格式:
        event: {event_type}
        data: {"key": "value", ...}

    CHUNK_SIZE:
        每次 yield 的字符数。10 字符/批 ≈ 每批 1-3 个中文词，
        前端渲染时感知流畅而不碎片。
    """

    CHUNK_SIZE = 10  # 每批推送字符数（平衡实时性与渲染开销）

    @staticmethod
    async def stream_agent_response(
        agent_executor,
        query: str,
        user_id: str,
        initial_state: dict[str, Any] | None = None,
        output_filter=None,
    ) -> AsyncGenerator[str, None]:
        """执行 Agent 并流式推送 SSE 事件

        主要流程:
            1. 发送 status: 意图识别 事件
            2. 校验 agent_executor 和 initial_state
            3. 发送 status: 检索 事件
            4. 调用 agent_executor.ainvoke(state) 完整执行图
            5. 发送 status: 生成 事件 + token 块（10 字符/批）
            6. 持久化结果到 PostgreSQL
            7. 发送 citation + done 事件

        Args:
            agent_executor: 编译后的 LangGraph CompiledStateGraph
            query: 用户原始输入文本
            user_id: 用户标识符
            initial_state: Agent 初始状态字典（含 messages, session_id 等）。
                          为 None 时使用默认空状态（兜底）。
            output_filter: 输出 PII 过滤函数（SensitiveFilter.check_output 的引用）。
                           为 None 时不进行输出过滤。

        Yields:
            SSE 事件字符串，格式 "event: {type}\\ndata: {json}\\n\\n"

        Events:
            status:   状态更新 (stage / message)
            token:    文本片段 (text)
            citation: 引用信息 (message)
            done:     完成通知 (intent / session_id)
            error:    错误信息 (message)
        """
        sid = (initial_state or {}).get("session_id", "?")
        logger.info("SSE 流开始 user={} session={} query={}", user_id, sid, query[:80])
        yield SSEStreamHandler._format_event("status", {"stage": "意图识别", "message": "正在理解您的问题..."})

        if agent_executor is None:
            logger.error("SSE 流错误: Agent 未初始化 user={}", user_id)
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
                "max_execution_time": 60,
                "tool_calls_history": [],
                "error": None,
                "loop_detected": False,
            }

        try:
            config = {"configurable": {"thread_id": initial_state.get("session_id") or str(uuid.uuid4())[:12]}}
            yield SSEStreamHandler._format_event("status", {"stage": "检索", "message": "正在查找信息..."})

            result = await agent_executor.ainvoke(initial_state, config=config)
            final_answer = result.get("final_answer", "")
            intent = result.get("intent", "")

            if final_answer:
                if output_filter:
                    final_answer = output_filter(final_answer)
                yield SSEStreamHandler._format_event("status", {"stage": "生成", "message": "正在生成回答..."})
                for i in range(0, len(final_answer), SSEStreamHandler.CHUNK_SIZE):
                    chunk = final_answer[i : i + SSEStreamHandler.CHUNK_SIZE]
                    yield SSEStreamHandler._format_event("token", {"text": chunk})
            else:
                yield SSEStreamHandler._format_event("token", {"text": "抱歉，未能生成回答。"})

            await SSEStreamHandler._persist(result)

            yield SSEStreamHandler._format_event("citation", {"message": "以上信息来自产品资料"})
            sid = result.get("session_id", initial_state.get("session_id", ""))
            yield SSEStreamHandler._format_event("done", {"message": "回答完成", "intent": intent, "session_id": sid})

            logger.info("SSE 流完成 user={} intent={} session={} answer_len={}", user_id, intent, sid, len(final_answer))

        except Exception as e:
            logger.error("SSE 流异常 user={} session={} err={}", user_id, sid, str(e)[:200])
            yield SSEStreamHandler._format_event("error", {"message": str(e)[:200]})

    @staticmethod
    async def _persist(state: dict):
        """持久化对话上下文到 PostgreSQL

        从 state 中提取 messages 和 session_id，调用 save_messages 保存。
        保存失败不影响主流程（仅捕获异常，不传播）。

        Args:
            state: Agent 执行完成后的最终状态字典
                   （包含 messages、session_id、intent 等字段）
        """
        sid = state.get("session_id")
        if not sid:
            return
        try:
            messages = state.get("messages", [])
            intent = state.get("intent", "")
            if isinstance(messages, list) and len(messages) > 1:
                await save_messages(sid, state.get("user_id", ""), messages, intent=intent)
        except Exception:
            pass

    @staticmethod
    def _format_event(event: str, data: dict[str, Any]) -> str:
        """格式化 SSE 事件字符串

        将事件名和数据字典拼接为 SSE 协议格式。

        Args:
            event: 事件类型（status / token / citation / done / error）
            data:  事件数据字典，自动转为 JSON

        Returns:
            str — "event: {event}\\ndata: {json}\\n\\n"
        """
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def get_sse_response(headers: dict[str, str] | None = None) -> dict:
        """获取 SSE 响应头

        生成标准的 SSE HTTP 响应头。

        Args:
            headers: 额外的自定义头部（可选）

        Returns:
            dict — 合并后的响应头字典
        """
        h = {"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}
        if headers:
            h.update(headers)
        return h

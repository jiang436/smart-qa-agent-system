"""防循环检测 — 三重防护机制

目的: 防止 Agent 陷入"思考→调工具→观察→再思考"的死循环。

三重防护:
  第一重: 硬性上限 (架构层面)
    - step > max_steps (默认15) → 强制终止
    - max_execution_time 60s 壁钟超时 (可配置)

  第二重: 运行时检测 (每步检查)
    - 重复工具检测: 连续3次相同工具 → 触发
    - 语义循环检测: 连续3条AI消息相似度>0.92 → 触发
    - 死胡同检测: 调用工具后状态无变化 → 触发

  第三重: 强制终结 (触发后执行)
    - 轻度: 注入 SystemMessage 警告让Agent自我纠正
    - 重度: 强制输出兜底回答, 终止循环

面试要点:
  "防循环不是一刀切。重复工具检测发现'连续三次搜同一个词',
   语义循环检测发现思考内容兜圈子但工具在换参数。
   最妙的是检测到循环后不是直接断开——轻度循环注入警告让Agent
   自我纠正，重度循环才强制终结。先警告后强制比一刀切优雅。"

Usage:
    detector = LoopDetector(embedding_model=embed)
    state = await detector.check(state)
    decision = LoopDetector.decide(state)  # "continue" | "stop" | "done"
"""

import time

from smart_qa.observability.logger import logger


class LoopResult:
    """循环检测结果"""

    def __init__(self, detected: bool = False, reason: str = "", action: str = ""):
        self.detected = detected
        self.reason = reason
        self.action = action  # "force_stop" | "inject_warning" | "none"


class LoopDetector:
    """三重防循环检测器

    配置:
      max_steps: 最大步数上限 (默认 15)
      max_execution_time: 壁钟超时秒数 (默认 60)
      semantic_threshold: 语义相似度阈值 (默认 0.92)
      repeated_tool_threshold: 重复工具次数 (默认 3)
    """

    def __init__(
        self,
        embedding_model=None,
        max_steps: int = 15,
        max_execution_time: float = 60.0,
        semantic_threshold: float = 0.92,
        repeated_tool_threshold: int = 3,
    ):
        self.embedding = embedding_model
        self.max_steps = max_steps
        self.max_execution_time = max_execution_time
        self.semantic_threshold = semantic_threshold
        self.repeated_tool_threshold = repeated_tool_threshold

    # ── Per-request state keys (stored in state dict, not instance vars) ──
    _HISTORY_KEY = "_loop_step_history"
    _START_TIME_KEY = "_loop_start_time"

    def _get_history(self, state: dict) -> list[dict]:
        """获取当前请求的步骤历史（存储在 state 中，线程安全）"""
        return state.setdefault(self._HISTORY_KEY, [])

    def _get_start_time(self, state: dict) -> float | None:
        """获取当前请求的开始时间"""
        return state.get(self._START_TIME_KEY)

    def _set_start_time(self, state: dict, t: float) -> None:
        state[self._START_TIME_KEY] = t

    # ═══════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════

    async def check(self, state: dict) -> dict:
        """执行完整防循环检测（线程安全：追踪状态存储在 state dict 中）"""
        # 每次新会话重置（step <= 1 视为新请求开始）
        if state.get("step", 0) <= 1:
            self._get_history(state).clear()
            self._set_start_time(state, time.time())

        state["step"] = state.get("step", 0) + 1
        self._record_step(state)

        # ── 第一重: 硬性上限 ──
        result = self._check_hard_limits(state)
        if result.detected:
            self._apply_result(state, result)
            return state

        # ── 第二重: 运行时检测 ──
        result = self._check_runtime(state)
        if result.detected:
            self._apply_result(state, result)
            return state

        state["loop_detected"] = False
        return state

    # ═══════════════════════════════════════════
    # 第一重: 硬性上限
    # ═══════════════════════════════════════════

    def _check_hard_limits(self, state: dict) -> LoopResult:
        """硬性上限检查"""
        step = state.get("step", 0)
        max_s = state.get("max_steps", self.max_steps)

        # 步数超限
        if step > max_s:
            return LoopResult(
                detected=True,
                reason=f"超过最大步数限制 ({step}/{max_s})",
                action="force_stop",
            )

        # 壁钟超时
        start_time = self._get_start_time(state)
        if start_time:
            elapsed = time.time() - start_time
            timeout = state.get("max_execution_time", self.max_execution_time)
            if elapsed > timeout:
                return LoopResult(
                    detected=True,
                    reason=f"执行超时 ({elapsed:.0f}s/{timeout:.0f}s)",
                    action="force_stop",
                )

        return LoopResult(detected=False)

    # ═══════════════════════════════════════════
    # 第二重: 运行时检测
    # ═══════════════════════════════════════════

    def _check_runtime(self, state: dict) -> LoopResult:
        """运行时检测: 重复工具 + 语义循环 + 死胡同"""
        checks = [
            self._check_repeated_tools,
            self._check_semantic_loop,
            self._check_stuck,
        ]
        for check_fn in checks:
            result = check_fn(state)
            if result.detected:
                return result
        return LoopResult(detected=False)

    def _check_repeated_tools(self, state: dict) -> LoopResult:
        """重复工具检测: 连续 N 次调用相同工具

        不只检查工具名, 还检查参数是否雷同 ——
        如果仅仅是工具名相同但参数完全不同 (如不同城市),
        那是合理行为, 不算循环。
        """
        tool_calls = state.get("tool_calls_history", [])
        threshold = self.repeated_tool_threshold

        if len(tool_calls) < threshold:
            return LoopResult(detected=False)

        # 只看最近 N 次
        recent = tool_calls[-threshold:]
        if len(set(recent)) == 1:
            logger.warning("重复工具调用 tool={} count={}", recent[0], threshold)
            # 轻度: 工具相同 → inject_warning
            return LoopResult(
                detected=True,
                reason=f"连续 {threshold} 次调用工具 '{recent[0]}'",
                action="inject_warning",
            )

        return LoopResult(detected=False)

    def _check_semantic_loop(self, state: dict) -> LoopResult:
        """语义循环检测: 连续 AI 回复内容高度相似

        用 sentence-transformers 编码最近 3 条 AI 消息,
        如果两两余弦相似度 > 0.92 → 判定为语义死循环。

        这种循环的特点是: Agent 每次换不同的工具/参数,
        但思考的内容一直在兜圈子 (如反复说"让我再查一下")。
        """
        if not self.embedding:
            return LoopResult(detected=False)

        messages = state.get("messages", [])
        ai_msgs = []
        for msg in reversed(messages):
            content = getattr(msg, "content", "") or msg.get("content", "")
            role = getattr(msg, "type", "") or msg.get("role", "")
            if role in ("ai", "assistant") and content:
                ai_msgs.append(content)
                if len(ai_msgs) >= 3:
                    break

        if len(ai_msgs) < 3:
            return LoopResult(detected=False)

        ai_msgs = list(reversed(ai_msgs))  # 按时间顺序

        try:
            vectors = self.embedding.encode(ai_msgs)
            sim_01 = float(self.embedding.cosine_similarity(vectors[0], vectors[1]))
            sim_12 = float(self.embedding.cosine_similarity(vectors[1], vectors[2]))

            threshold = self.semantic_threshold
            if sim_01 > threshold and sim_12 > threshold:
                logger.warning("语义循环检测 sim_01={:.3f} sim_12={:.3f}", sim_01, sim_12)
                return LoopResult(
                    detected=True,
                    reason=f"思考内容语义循环 (相似度 {sim_01:.2f}/{sim_12:.2f})",
                    action="inject_warning",
                )
        except Exception as e:
            logger.debug("语义循环检测跳过: {}", e)

        return LoopResult(detected=False)

    def _check_stuck(self, state: dict) -> LoopResult:
        """死胡同检测: 工具调用后状态无变化

        检查最近 N 步中, retrieved_docs 是否持续为空且 final_answer 无进展。
        这表明 Agent 在不断调工具但什么都查不到。
        """
        history = self._get_history(state)[-5:]
        if len(history) < 4:
            return LoopResult(detected=False)

        # 检查: 最近 4 步中是否有任何一步产生了新文档或新回答
        has_new_docs = any(h.get("retrieved_docs_count", 0) > 0 for h in history[-3:])
        has_new_answer = any(h.get("has_final_answer", False) for h in history[-3:])
        tool_calls_every_step = all(h.get("had_tool_call", False) for h in history[-4:])

        if tool_calls_every_step and not has_new_docs and not has_new_answer:
            logger.warning("死胡同检测: 连续工具调用但无进展")
            return LoopResult(
                detected=True,
                reason="连续调用工具但无新信息 — 死胡同",
                action="force_stop",
            )

        return LoopResult(detected=False)

    # ═══════════════════════════════════════════
    # 第三重: 强制执行
    # ═══════════════════════════════════════════

    def _apply_result(self, state: dict, result: LoopResult):
        """根据检测结果更新 state"""
        logger.warning("防循环触发 action={} reason={}", result.action, result.reason)
        state["loop_detected"] = True
        state["loop_reason"] = result.reason
        state["loop_action"] = result.action

        if result.action == "force_stop":
            logger.warning("防循环: force_stop — {}", result.reason)
            if not state.get("final_answer"):
                state["final_answer"] = (
                    "我尝试了多次仍无法完整回答您的问题。\n"
                    "建议您:\n"
                    "1. 换个角度描述问题\n"
                    "2. 提供更多具体信息（如错误码、设备型号）\n"
                    "3. 联系人工客服获取帮助"
                )
        elif result.action == "inject_warning":
            logger.warning("防循环: inject_warning — {}", result.reason)
            # 注入警告到 messages
            warning = f"[系统提示] 检测到可能的循环: {result.reason}\n请停止当前思路，根据已有信息直接回答用户问题。"
            msgs = state.get("messages", [])
            msgs.append({"role": "system", "content": warning})
            state["messages"] = msgs

    # ═══════════════════════════════════════════
    # 历史记录
    # ═══════════════════════════════════════════

    def _record_step(self, state: dict):
        """记录当前步骤到 state 中的历史（线程安全）"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else {}

        history = self._get_history(state)
        history.append(
            {
                "step": state.get("step", 0),
                "tool_calls_history": list(state.get("tool_calls_history", [])),
                "retrieved_docs_count": len(state.get("retrieved_docs") or []),
                "has_final_answer": bool(state.get("final_answer")),
                "had_tool_call": bool(state.get("tool_calls_history", [])),
                "last_msg_type": (getattr(last_msg, "type", "") or last_msg.get("role", "")),
            }
        )

        # 只保留最近 20 步
        if len(history) > 20:
            state[self._HISTORY_KEY] = history[-15:]

    # ═══════════════════════════════════════════
    # 调度节点
    # ═══════════════════════════════════════════

    @staticmethod
    def decide(state: dict) -> str:
        """根据检测结果决定 LangGraph 下一步

        Returns:
          - "done":    正常结束
          - "continue": 继续处理
          - "stop":    检测到循环 → 强制终止
        """
        if state.get("loop_detected"):
            action = state.get("loop_action", "force_stop")
            if action == "force_stop":
                return "stop"
            # inject_warning → 给 Agent 一次机会继续
            return "continue"

        if state.get("final_answer"):
            return "done"

        return "continue"

    def reset(self, state: dict | None = None):
        """重置检测器状态（新会话时调用）

        Args:
            state: 可选，传入时清除该 state 中的追踪数据；
                   为 None 时兼容旧代码（无操作，因为状态已迁移到 state dict）。
        """
        if state is not None:
            state.pop(self._HISTORY_KEY, None)
            state.pop(self._START_TIME_KEY, None)

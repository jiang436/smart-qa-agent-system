"""L4 任务记忆 — 多步骤执行追踪 & 自动清理

管理长任务的执行状态，支持:
  1. 步骤追踪: 记录当前执行到哪一步
  2. 中断恢复: 任务被中断后能从上次状态继续 (LangGraph Checkpoint)
  3. 自动清理: 任务完成后自动删除临时数据
  4. 防循环参考: 记录已执行的工具调用序列

存储位置:
  - LangGraph State.task_memory (当前会话)
  - Redis (跨会话恢复，TTL=30min)

Usage:
    from src.memory.task_memory import TaskMemory
    tm = TaskMemory()
    tm.start_task(state, "troubleshoot", {"fault_type": "不工作"})
    tm.advance_step(state, 2)
    tm.finish_task(state)
"""

from datetime import UTC, datetime
from typing import Any

from src.observability.logger import logger

# 任务类型配置
TASK_CONFIG: dict[str, dict[str, Any]] = {
    "troubleshoot": {
        "max_steps": 5,
        "timeout_seconds": 600,  # 10 分钟
        "auto_cleanup": True,
    },
    "consumables": {
        "max_steps": 4,
        "timeout_seconds": 300,
        "auto_cleanup": True,
    },
    "whole_house_cleaning": {
        "max_steps": 20,
        "timeout_seconds": 3600,  # 1 小时
        "auto_cleanup": True,
    },
}


class TaskMemory:
    """L4 任务记忆管理器

    追踪多步骤任务的:
      - 当前状态 (stage / step / round)
      - 工具调用历史 (防循环)
      - 中间结果 (用于后续步骤引用)
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client

    # ── 任务生命周期 ──

    def start_task(self, state: dict, task_type: str, initial_context: dict[str, Any] | None = None) -> dict:
        """开始一个新任务

        Args:
            state: AgentState
            task_type: 任务类型 (troubleshoot / consumables / whole_house_cleaning)
            initial_context: 初始上下文

        Returns:
            更新后的 task_memory
        """
        config = TASK_CONFIG.get(task_type, {"max_steps": 10, "timeout_seconds": 600, "auto_cleanup": True})

        task = {
            "task_id": f"{task_type}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "task_type": task_type,
            "status": "running",
            "stage": "init",
            "current_step": 0,
            "total_steps": 0,
            "max_steps": config["max_steps"],
            "timeout_seconds": config["timeout_seconds"],
            "started_at": datetime.now(UTC).isoformat(),
            "tool_calls": [],
            "context": initial_context or {},
            "results": [],
        }
        state["task_memory"] = task
        state["tool_calls_history"] = []

        logger.info("L4 任务开始 type={} max_steps={}", task_type, config["max_steps"])
        return task

    def advance_step(self, state: dict, step_num: int, result: dict[str, Any] | None = None):
        """推进到下一步

        Args:
            state: AgentState
            step_num: 当前步骤编号
            result: 该步骤的结果
        """
        task = state.get("task_memory")
        if not task:
            logger.warning("L4 advance_step 但 task_memory 为空")
            return

        task["current_step"] = step_num
        if result:
            task["results"].append(
                {
                    "step": step_num,
                    "result": result,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        # 检查是否超步数
        if step_num >= task["max_steps"]:
            logger.warning("L4 任务超步数 type={} step={}/{}", task["task_type"], step_num, task["max_steps"])
            task["status"] = outcome = "max_steps_exceeded"

        logger.debug("L4 步骤推进 type={} step={}/{}", task["task_type"], step_num, task["max_steps"])

    def record_tool_call(self, state: dict, tool_name: str, success: bool = True):
        """记录一次工具调用（用于防循环检测）

        Args:
            state: AgentState
            tool_name: 工具名
            success: 是否成功
        """
        task = state.get("task_memory")
        if task:
            task.setdefault("tool_calls", []).append(
                {
                    "tool": tool_name,
                    "success": success,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        # 同时写入 state.tool_calls_history (供 LoopDetector 使用)
        state.setdefault("tool_calls_history", []).append(tool_name)

        # 重复工具检测
        history = state["tool_calls_history"]
        if len(history) >= 3 and len(set(history[-3:])) == 1:
            logger.warning("L4 检测到重复工具调用 tool={} count=3", tool_name)

    def finish_task(self, state: dict, outcome: str = "success", summary: str = ""):
        """完成任务并自动清理

        Args:
            state: AgentState
            outcome: 结果 (success / failed / escalated / cancelled)
            summary: 任务结果摘要
        """
        task = state.get("task_memory")
        if not task:
            return

        logger.info("L4任务完成 type={} outcome={} steps={}", task.get("task_type"), outcome, task["current_step"])
        task["status"] = outcome
        task["finished_at"] = datetime.now(UTC).isoformat()
        task["summary"] = summary

        logger.info("L4 任务完成 type={} outcome={} total_steps={}", task["task_type"], outcome, task["current_step"])

        # 自动清理临时状态
        if task.get("auto_cleanup", True) or TASK_CONFIG.get(task["task_type"], {}).get("auto_cleanup", True):
            self._cleanup(state)

    def _cleanup(self, state: dict):
        """清理任务临时数据"""
        task = state.get("task_memory", {})
        task_type = task.get("task_type", "unknown")

        # 保留: task_type, outcome, summary, finished_at (供 L2/L3 使用)
        summary_data = {
            "last_task_type": task_type,
            "last_outcome": task.get("status", "unknown"),
            "last_summary": task.get("summary", ""),
            "last_finished_at": task.get("finished_at", ""),
        }

        # 写入 Redis 短期留存 (30 分钟)
        session_id = state.get("session_id")
        if session_id and self.redis:
            try:
                import asyncio

                asyncio.ensure_future(self.redis.set_json(f"task_result:{session_id}", summary_data, ttl=1800))
            except Exception:
                pass

        # 清理 state 中的临时数据
        state["task_memory"] = summary_data
        state["tool_calls_history"] = []
        logger.debug("L4 清理完成 last_task={}", task_type)

    # ── 中断恢复 ──

    def save_checkpoint(self, state: dict) -> str:
        """保存任务检查点 (用于 LangGraph Checkpoint)

        Returns:
            checkpoint_id
        """
        task = state.get("task_memory")
        session_id = state.get("session_id", "unknown")

        if not task:
            logger.debug("L4 checkpoint 跳过: 无活跃任务")
            return ""

        checkpoint = {
            "session_id": session_id,
            "checkpoint_at": datetime.now(UTC).isoformat(),
            "task": task,
            "step": state.get("step", 0),
            "saved_state": {
                "intent": state.get("intent"),
                "scenario": state.get("scenario"),
                "current_step": task.get("current_step", 0),
                "tool_calls_history": state.get("tool_calls_history", []),
            },
        }

        checkpoint_id = f"ckpt_{session_id}_{task.get('task_id', '')}"

        # 写入 Redis (TTL=任务超时时间)
        if self.redis:
            try:
                import asyncio

                ttl = task.get("timeout_seconds", 600)
                asyncio.ensure_future(self.redis.set_json(checkpoint_id, checkpoint, ttl=ttl))
            except Exception:
                pass

        logger.info("L4 检查点保存 id={} step={}", checkpoint_id, task.get("current_step", 0))
        return checkpoint_id

    async def restore_checkpoint(self, session_id: str, task_id: str = "") -> dict | None:
        """恢复任务检查点

        Returns:
            恢复后的 state 增量，或 None (无可恢复的检查点)
        """
        checkpoint_id = f"ckpt_{session_id}_{task_id}" if task_id else f"ckpt_{session_id}_"

        if self.redis:
            try:
                # 查找最新的 checkpoint
                keys = await self.redis._client.keys(f"ckpt_{session_id}_*")
                if not keys:
                    return None
                checkpoint = await self.redis.get_json(keys[0])
                if checkpoint:
                    logger.info("L4 检查点恢复 session={}", session_id)
                    return checkpoint
            except Exception as e:
                logger.warning("L4 检查点恢复失败 session={}: {}", session_id, e)

        return None

    # ── 超时检测 ──

    def is_expired(self, state: dict) -> bool:
        """检查当前任务是否超时"""
        task = state.get("task_memory")
        if not task or task.get("status") != "running":
            return False

        started = task.get("started_at", "")
        if not started:
            return False

        try:
            elapsed = (datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds()
            timeout = task.get("timeout_seconds", 600)
            if elapsed > timeout:
                logger.warning("L4 任务超时 type={} elapsed={:.0f}s timeout={}s", task["task_type"], elapsed, timeout)
                return True
        except Exception:
            pass

        return False

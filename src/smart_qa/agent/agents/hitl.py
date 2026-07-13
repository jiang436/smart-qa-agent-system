"""Human-in-the-Loop — 复杂操作用户确认机制

文档第 2.5 节: 全屋清洁场景中的 HITL

触发场景:
  - 耗材推荐: Agent 生成推荐列表后，等用户确认再下单
  - 非可逆操作: 重置设备、清除数据前，让用户确认
  - 高风险操作: 涉及费用、隐私、数据删除

设计原则:
  1. Agent 先完成任务规划，然后暂停
  2. 向用户展示"做了什么决定、打算怎么执行"
  3. 等用户确认/修改/拒绝
  4. 根据用户反馈继续或调整
  5. 超时兜底（用户 60 秒未回复 → 安全默认）
"""

import time


class HITLManager:
    """Human-in-the-Loop 管理器"""

    def __init__(self, timeout_seconds=60):
        self.timeout = timeout_seconds
        self.pending_approvals = {}

    def request_approval(self, session_id: str, context: dict) -> dict:
        """
        请求用户确认。

        流程:
          1. Agent 完成规划，生成 approval_context
          2. HITL 暂停 Agent 执行，等待用户输入
          3. 向用户展示: 做了什么决定 + 打算怎么执行 + 风险提示
          4. 等待用户确认 (approve / reject / modify)
          5. 返回用户决策

        Args:
          session_id: 会话 ID
          context: {
              "action": 动作描述, "details": 具体内容,
              "risk": "low|medium|high", "options": [可选修改项]
          }

        Returns:
          {"decision": "approve|reject|modify", "feedback": "..."}
        """
        self.pending_approvals[session_id] = {
            "context": context,
            "timestamp": time.time(),
            "resolved": False,
        }

        # 生成给用户的确认信息
        approval_message = self._format_approval_message(context)
        # 这里通过 WebSocket 或 API 推送给前端

        return {
            "status": "pending_approval",
            "message": approval_message,
            "session_id": session_id,
        }

    def resolve_approval(self, session_id: str, decision: str, feedback: str = "") -> dict:
        """
        用户做出决策后，继续执行。

        Args:
          decision: "approve" | "reject" | "modify"
          feedback: 用户的修改意见（仅 modify 时需要）
        """
        if session_id not in self.pending_approvals:
            return {"error": "no pending approval"}

        record = self.pending_approvals[session_id]
        record["resolved"] = True
        record["decision"] = decision
        record["feedback"] = feedback

        return {
            "decision": decision,
            "feedback": feedback,
            "context": record["context"],
        }

    def check_timeout(self, session_id: str) -> bool:
        """检查是否超时"""
        if session_id not in self.pending_approvals:
            return False
        record = self.pending_approvals[session_id]
        if record["resolved"]:
            return False
        elapsed = time.time() - record["timestamp"]
        if elapsed > self.timeout:
            # 超时: 默认拒绝高风险，低风险自动通过
            risk = record["context"].get("risk", "medium")
            if risk == "low":
                return True  # 自动通过
            elif risk == "high":
                return True  # 超时拒绝
            else:
                return True  # 超时视为拒绝
        return False

    def _format_approval_message(self, context: dict) -> str:
        """格式化确认信息"""
        action = context.get("action", "未知操作")
        details = context.get("details", "")
        risk = context.get("risk", "medium")

        risk_label = {"low": "?? 低风险", "medium": "?? 中风险", "high": "?? 高风险"}
        parts = [
            "?? 需要您确认:",
            f"操作: {action}",
            f"详情: {details}",
            f"风险: {risk_label.get(risk, risk)}",
            "",
            "请选择:",
            "  1. ? 确认执行",
            "  2. ? 取消",
        ]
        return "\n".join(parts)

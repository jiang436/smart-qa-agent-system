"""报告生成场景 — 生成设备使用报告

用户请求:
  - "生成我的使用报告"
  - "给我看看最近的清洁数据"
  - "查看使用统计"
  - "我的设备用了多少次"

流程:
  1. 确认用户身份
  2. 查询 PostgreSQL 获取使用统计数据
  3. 调用 ReportAgent 生成结构化报告
  4. 返回格式化的文本报告

报告类型:
  - monthly: 月度使用报告（默认）
  - consumable: 耗材更换提醒
  - abnormal: 异常事件汇总
"""

from __future__ import annotations

import time

from smart_qa.agent.agents.report_agent import ReportAgent
from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger


class ReportScenario:
    """报告生成场景

    用法:
        result_state = await ReportScenario.run(state)
    """

    _report_agent: ReportAgent | None = None

    @classmethod
    def _get_agent(cls, llm_client=None) -> ReportAgent:
        """懒加载 ReportAgent 单例"""
        if cls._report_agent is None:
            from smart_qa.database.postgres import PostgresClient

            cls._report_agent = ReportAgent(llm_client=llm_client, db_client=PostgresClient())
        elif llm_client:
            cls._report_agent.llm = llm_client
        return cls._report_agent

    @classmethod
    async def run(cls, state: dict) -> dict:
        """执行报告生成

        Args:
            state: AgentState 字典

        Returns:
            更新后的 state，final_answer 已填充为报告内容
        """
        start_time = time.time()
        query = extract_user_query(state)
        user_id = state.get("user_id", "anonymous")
        logger.info(
            "报告场景开始 user={} query={} type={}",
            user_id,
            query[:60],
            cls._detect_report_type(query) if query else "?",
        )
        if not query:
            state["final_answer"] = "您好！请问需要生成什么类型的报告？例如「生成我的使用报告」或「查看耗材状态」。"
            return state

        # 确定报告类型
        report_type = cls._detect_report_type(query)

        try:
            from smart_qa.deps import get_llm_client

            agent = cls._get_agent(llm_client=get_llm_client())
            # 注入报告类型到 task_memory
            task = state.get("task_memory") or {}
            task["report_type"] = report_type
            state["task_memory"] = task

            state = await agent.generate_report(state)
        except Exception as e:
            logger.error("报告生成异常: {}", e)
            state["final_answer"] = "抱歉，生成报告时遇到了问题。\n请稍后重试，或者联系人工客服获取帮助。"
            state["error"] = str(e)[:200]

        elapsed = time.time() - start_time
        logger.info("报告生成完成 type={} latency={:.1f}s", report_type, elapsed)
        return state

    @staticmethod
    def _detect_report_type(query: str) -> str:
        """从查询中检测报告类型"""
        q = query.lower()
        if any(kw in q for kw in ["耗材", "更换", "配件", "滤网", "边刷", "主刷", "拖布"]):
            return "consumable"
        if any(kw in q for kw in ["异常", "故障", "错误", "问题"]):
            return "abnormal"
        if any(kw in q for kw in ["周报", "周", "本周", "最近一周"]):
            return "weekly"
        return "monthly"  # 默认月度

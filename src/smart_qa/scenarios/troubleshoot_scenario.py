"""故障排查场景 — 错误码精确匹配 + RAG 知识库检索"""

import re

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger

# ── 错误码映射表（硬编码秒回 + 引用）──
ERROR_CODE_MAP = {
    "E01": {"cause": "左轮过载或卡死", "solution": "检查左轮是否有异物缠绕，手动转动确认是否顺滑"},
    "E02": {"cause": "右轮过载或卡死", "solution": "检查右轮，清除缠绕物"},
    "E03": {"cause": "悬崖传感器异常", "solution": "将扫地机放回平整地面，清洁底部悬崖传感器"},
    "E04": {"cause": "尘盒未安装", "solution": "确认尘盒完全推入，听到咔哒声"},
    "E05": {"cause": "保险杠（前撞）卡住", "solution": "轻拍保险杠测试回弹，清除卡住的异物，确保保险杠能自由活动"},
    "E06": {"cause": "主刷堵转", "solution": "拆出主刷，清理缠绕毛发和两端轴承，确保转动无阻"},
    "E07": {"cause": "Wi-Fi 连接失败", "solution": "检查路由器2.4G信号，长按Wi-Fi键5秒重新配网"},
    "E08": {"cause": "水箱未安装", "solution": "安装水箱支架后再使用拖地功能"},
}


class TroubleshootScenario:

    @staticmethod
    def _extract_query(state: dict) -> str:
        return extract_user_query(state)

    @staticmethod
    def _extract_error_code(text: str) -> str | None:
        for pattern in [r"[Ee](\d{2,3})", r"错误\s*(\d{2,3})", r"[Ee]rror\s*(\d{2,3})"]:
            match = re.search(pattern, text)
            if match:
                code = f"E{match.group(1)}"
                return code if code in ERROR_CODE_MAP else None
        return None

    @staticmethod
    async def run(state: dict) -> dict:
        query = TroubleshootScenario._extract_query(state)
        if not query:
            state["final_answer"] = "请描述您的设备遇到了什么问题？比如错误码、故障现象等，我来帮您排查。"
            return state

        # ── 错误码精确匹配 ──
        error_code = TroubleshootScenario._extract_error_code(query)
        if error_code and error_code in ERROR_CODE_MAP:
            entry = ERROR_CODE_MAP[error_code]
            state["final_answer"] = (
                f"识别到错误码 {error_code}：\n"
                f"原因：{entry['cause']}\n"
                f"解决方法：{entry['solution']}\n\n"
                f"如按以上步骤操作后问题仍未解决，请联系售后客服。"
            )
            state["retrieved_docs"] = [{
                "content": f"错误码 {error_code}：{entry['cause']} — {entry['solution']}",
                "source": "xiaomi_fault_codes.md",
                "doc_id": error_code,
            }]
            return state

        # ── RAG 检索知识库 ──
        try:
            from smart_qa.scenarios.qa_scenario import QAScenario
            rag = QAScenario._get_rag_agent()
            rag_state = await rag.retrieve_and_generate({
                "messages": [{"role": "user", "content": query}],
                "user_id": state.get("user_id", ""),
                "session_id": state.get("session_id", ""),
            })
            kb_answer = rag_state.get("final_answer", "")
            kb_docs = rag_state.get("retrieved_docs", [])
            if kb_answer and len(kb_answer) >= 20:
                state["final_answer"] = kb_answer
                state["retrieved_docs"] = kb_docs
                return state
        except Exception as e:
            logger.warning("故障排查 RAG 失败: {}", e)

        # ── 兜底 ──
        state["final_answer"] = (
            "抱歉，我暂时无法定位您描述的问题。建议您：\n"
            "1. 尝试重启设备（长按电源键 10 秒）\n"
            "2. 在米家 APP 中查看是否有固件更新\n"
            "3. 清洁所有传感器和充电触点\n"
            "4. 如仍无法解决，请联系售后客服"
        )
        return state

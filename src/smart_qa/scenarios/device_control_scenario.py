"""设备控制场景 — 查询状态 / 开始清扫 / 停止 / 回充 / 设置模式 / 定时

使用 DeviceManager 模拟真实 IoT 设备交互。
当前为 Mock 数据，接入真实设备后 DeviceManager 自动切换。

用户请求:
  - "检查我的设备状态" → 查询设备信息
  - "开始清扫" / "开始拖地" → 启动清扫
  - "停止" / "暂停" → 停止清扫
  - "回去充电" / "回充" → 返回充电座
  - "设为安静模式" / "强力模式" → 切换模式
  - "设置每天9点清扫客厅" → 定时任务
"""

from __future__ import annotations

import re
import time

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.agent.tools.device import DeviceManager
from smart_qa.observability.logger import logger


class DeviceControlScenario:
    """设备控制场景

    用法:
        result_state = await DeviceControlScenario.run(state)
    """

    _device_manager: DeviceManager | None = None

    @classmethod
    def _get_manager(cls) -> DeviceManager:
        if cls._device_manager is None:
            cls._device_manager = DeviceManager()
        return cls._device_manager

    @classmethod
    async def run(cls, state: dict) -> dict:
        """执行设备控制

        Args:
            state: AgentState

        Returns:
            state 含 final_answer 为设备响应消息
        """
        start_time = time.time()
        query = extract_user_query(state)
        if not query:
            state["final_answer"] = "您好！我可以帮您查看设备状态、开始清扫、设置定时等，请问需要什么？"
            return state

        user_id = state.get("user_id", "anonymous")
        manager = cls._get_manager()
        q = query.lower()

        try:
            # ── 命令识别 ──
            if cls._is_status_query(q):
                device = manager.get_device(user_id)
                if device:
                    status_text = manager.format_device_status(device)
                    state["final_answer"] = f"📊 设备状态:\n  {status_text}"
                else:
                    state["final_answer"] = "未找到您的设备信息，请先绑定设备。"

            elif cls._is_start_cleaning(q):
                mode = cls._extract_mode(q)
                result = manager.start_cleaning(user_id, mode)
                state["final_answer"] = result.get("message", "操作完成")

            elif cls._is_stop_cleaning(q):
                result = manager.stop_cleaning(user_id)
                state["final_answer"] = result.get("message", "已停止")

            elif cls._is_return_charge(q):
                result = manager.return_to_charge(user_id)
                state["final_answer"] = result.get("message", "设备正在返回充电座")

            elif cls._is_set_mode(q):
                mode = cls._extract_mode(q)
                result = manager.set_mode(user_id, mode)
                state["final_answer"] = result.get("message", "已切换模式")

            elif cls._is_schedule(q):
                time_match = re.search(r"(\d{1,2})[：:点](\d{0,2})", q)
                room_match = re.search(r"清扫(.+)", q)
                if time_match:
                    h, m = time_match.group(1), time_match.group(2) or "00"
                    time_str = f"{h}:{m}"
                    room = room_match.group(1).strip() if room_match else "全屋"
                    result = manager.create_schedule(user_id, time_str, room)
                    state["final_answer"] = result.get("message", "定时设置成功")
                else:
                    state["final_answer"] = "请指定时间，例如「每天9点清扫客厅」"

            else:
                state["final_answer"] = (
                    "我可以帮您:\n"
                    "  • 查看设备状态 — 「检查我的设备」\n"
                    "  • 开始清扫 — 「开始打扫」\n"
                    "  • 停止 — 「停止清扫」\n"
                    "  • 回充 — 「回去充电」\n"
                    "  • 切换模式 — 「设为安静模式」\n"
                    "  • 定时 — 「每天9点清扫客厅」"
                )

        except Exception as e:
            logger.error("设备控制异常: {}", e)
            state["final_answer"] = "抱歉，操作设备时遇到了问题，请稍后重试。"
            state["error"] = str(e)[:200]

        elapsed = time.time() - start_time
        logger.info("设备控制完成 latency={:.1f}s", elapsed)
        return state

    # ── 命令检测 ──

    @staticmethod
    def _is_status_query(q: str) -> bool:
        return any(kw in q for kw in ["状态", "设备", "情况", "怎么样", "多少电", "电量", "在线", "信息"])

    @staticmethod
    def _is_start_cleaning(q: str) -> bool:
        return any(kw in q for kw in ["开始清扫", "开始打扫", "开始拖地", "开始扫地", "打扫", "清扫", "扫地"])

    @staticmethod
    def _is_stop_cleaning(q: str) -> bool:
        return any(kw in q for kw in ["停止", "暂停", "停", "别扫了", "别拖了"])

    @staticmethod
    def _is_return_charge(q: str) -> bool:
        return any(kw in q for kw in ["回充", "回去充电", "充电", "回去", "返回充电座"])

    @staticmethod
    def _is_set_mode(q: str) -> bool:
        return any(kw in q for kw in ["模式", "安静", "强力", "标准", "设为", "切换"])

    @staticmethod
    def _is_schedule(q: str) -> bool:
        return any(kw in q for kw in ["定时", "每天", "每天", "预约"])

    @staticmethod
    def _extract_mode(q: str) -> str:
        if any(kw in q for kw in ["安静", "静音"]):
            return "quiet"
        if any(kw in q for kw in ["强力", "强劲", "最大"]):
            return "strong"
        return "standard"

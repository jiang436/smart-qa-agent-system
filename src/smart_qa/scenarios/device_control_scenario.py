"""设备控制场景 — Function Calling 驱动

LLM 根据用户自然语言自动选择工具：
  - get_device_status → "设备状态" / "还有多少电" / "尘盒满了吗"
  - start_cleaning    → "开始清扫" / "打扫客厅"
  - stop_cleaning     → "停止" / "别扫了"
  - return_to_charge  → "回去充电" / "回充"
  - set_cleaning_mode → "安静模式" / "切换强力"
  - create_schedule   → "每天9点扫客厅"
"""

from __future__ import annotations

import json
import re
import time

from langchain_core.tools import tool

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.agent.tools.device import DeviceManager
from smart_qa.observability.logger import logger

# ═══════════════════════════════════════════
# Function Calling 工具定义
# ═══════════════════════════════════════════

_device_manager: DeviceManager | None = None


def _get_manager() -> DeviceManager:
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager


@tool
def get_device_status(user_id: str) -> dict:
    """获取扫地机器人当前信息，仅在用户问「状态」「电量」「设备信息」时调用。不要在执行动作前先调用它。"""
    dev = _get_manager().get_device(user_id)
    if not dev:
        return {"status": "error", "message": "未找到设备信息，请先绑定设备。"}
    return {"status": "ok", "device": {k: v for k, v in dev.items() if k != "source"}}


@tool
def start_cleaning(user_id: str, mode: str = "standard") -> dict:
    """立刻开始扫地/拖地/清扫。用户说「开始打扫」「扫地」「清扫」时直接调用。mode: quiet/standard/strong，默认standard。"""
    return _get_manager().start_cleaning(user_id, mode)


@tool
def stop_cleaning(user_id: str) -> dict:
    """停止/暂停当前清扫。用户说「停止」「别扫了」「暂停」时调用。"""
    return _get_manager().stop_cleaning(user_id)


@tool
def return_to_charge(user_id: str) -> dict:
    """让设备回去充电。用户说「回充」「回去充电」「充电」时调用。"""
    return _get_manager().return_to_charge(user_id)


@tool
def set_cleaning_mode(user_id: str, mode: str) -> dict:
    """切换清扫模式但不启动。用户说「设为安静模式」「切换强力」时调用。mode: quiet/standard/strong。"""
    return _get_manager().set_mode(user_id, mode)


@tool
def create_schedule(user_id: str, time_str: str, room: str = "全屋") -> dict:
    """创建定时清扫。用户说「每天X点打扫」「定时」「预约」时调用。time_str=HH:MM如08:00，room如客厅/卧室/全屋。"""
    return _get_manager().create_schedule(user_id, time_str, room)


DEVICE_TOOLS = [
    get_device_status,
    start_cleaning,
    stop_cleaning,
    return_to_charge,
    set_cleaning_mode,
    create_schedule,
]


# ═══════════════════════════════════════════
# 场景
# ═══════════════════════════════════════════

class DeviceControlScenario:
    """设备控制场景 — Function Calling 自动路由"""

    @staticmethod
    async def run(state: dict) -> dict:
        query = extract_user_query(state)
        if not query:
            state["final_answer"] = "您好！我可以帮您查看设备状态、开始清扫、设置定时等，请问需要什么？"
            return state

        user_id = state.get("user_id", "anonymous")
        t0 = time.time()

        try:
            from smart_qa.di import container

            llm = container.get("llm")
            llm_with_tools = llm.bind_tools(DEVICE_TOOLS)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是扫地机器人控制助手。严格按以下规则选择工具:\n"
                        "- 用户说「清扫/打扫/扫地/开始」→ 直接调 start_cleaning，不要先查状态\n"
                        "- 用户说「停止/暂停」→ 调 stop_cleaning\n"
                        "- 用户说「回充/充电」→ 调 return_to_charge\n"
                        "- 用户说「安静/强力/切换模式」→ 调 set_cleaning_mode\n"
                        "- 用户说「每天X点/定时/预约」→ 调 create_schedule\n"
                        "- 只在用户明确问「状态/电量/信息」时才调 get_device_status\n"
                        "用户ID: " + user_id
                    ),
                },
                {"role": "user", "content": query},
            ]

            response = await llm_with_tools.ainvoke(messages)

            # LLM 是否选择了工具
            tool_calls = getattr(response, "tool_calls", None) or []
            if tool_calls:
                answer = await _execute_tool_calls(tool_calls, user_id)
            else:
                # 没选工具 → LLM 直接用自然语言回复
                answer = response.content if hasattr(response, "content") else str(response)
                if not answer or len(answer) < 5:
                    answer = (
                        "我可以帮您:\n"
                        "  • 查看设备状态 — 「检查我的设备」\n"
                        "  • 开始清扫 — 「开始打扫」\n"
                        "  • 停止 — 「停止清扫」\n"
                        "  • 回充 — 「回去充电」\n"
                        "  • 切换模式 — 「设为安静模式」\n"
                        "  • 定时 — 「每天9点清扫客厅」"
                    )

            state["final_answer"] = answer
            elapsed = time.time() - t0
            logger.info("设备控制完成 tool_calls={} latency={:.1f}s", len(tool_calls), elapsed)

        except Exception as e:
            logger.error("设备控制异常: {}", e)
            state["final_answer"] = "抱歉，操作设备时遇到了问题，请稍后重试。"

        return state


async def _execute_tool_calls(tool_calls: list, user_id: str) -> str:
    """执行 LLM 选择的工具调用"""
    tool_map = {t.name: t for t in DEVICE_TOOLS}

    parts = []
    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args", {})
        # 注入 user_id
        args["user_id"] = user_id

        logger.info("Function Call: {}({})", name, {k: v for k, v in args.items() if k != "user_id"})

        tool_func = tool_map.get(name)
        if tool_func:
            try:
                result = tool_func.invoke(args)
                if isinstance(result, dict):
                    msg = result.get("message", json.dumps(result, ensure_ascii=False))
                    if result.get("status") == "ok" and "device" in result:
                        # 格式化设备状态
                        dev = result["device"]
                        msg = (
                            f"📱 型号: {dev.get('model', '?')}\n"
                            f"🔋 电量: {dev.get('battery', '?')}%\n"
                            f"💧 水量: {dev.get('water_level', '?')}\n"
                            f"🗑️ 尘盒: {dev.get('dust_bin', '?')}\n"
                            f"🧹 拖布: {dev.get('mop', '?')}\n"
                            f"📶 在线: {'是' if dev.get('online') else '否'}\n"
                            f"⚡ 状态: {dev.get('status', '?')}\n"
                            f"🔧 固件: {dev.get('firmware', '?')}"
                        )
                    parts.append(msg)
                else:
                    parts.append(str(result))
            except Exception as e:
                parts.append(f"操作失败: {str(e)[:100]}")
        else:
            parts.append(f"未知操作: {name}")

    return "\n\n".join(parts) if parts else "操作完成"

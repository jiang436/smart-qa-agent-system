"""设备管理模块 — DeviceManager (设备状态查询 / 定时任务)

提供对扫地机器人设备的状态查询和控制功能。
当前使用 Mock 数据，后期接入真实 OneNET API。
"""

import re

from smart_qa.agent.tools.onenet_adapter import OneNETDeviceAdapter


class DeviceManager:
    """设备管理器 — 查询设备状态 & 控制设备 & 定时任务

    当前使用 Mock 数据模拟真实设备响应。
    接入真实设备后，onontrol 方法对接 MQTT/OneNET 指令下发。
    """

    def __init__(self):
        self.onenet = None
        try:
            self.onenet = OneNETDeviceAdapter()
        except Exception as e:
            print(f"[Device] OneNET init failed: {e}")

    def get_device(self, user_id: str) -> dict | None:
        if self.onenet:
            d = self.onenet.get_device(user_id)
            if d and d.get("source") != "local_mock":
                return d
        return self._mock(user_id)

    def start_cleaning(self, user_id: str, mode: str = "standard") -> dict:
        """开始清扫"""
        dev = self.get_device(user_id)
        if not dev:
            return {"status": "error", "message": "设备未绑定"}
        if not dev.get("online"):
            return {"status": "error", "message": "设备离线，无法开始清扫"}
        if dev.get("battery", 0) < 15:
            return {"status": "error", "message": f"电量不足 ({dev['battery']}%)，请先充电"}

        mode_names = {"quiet": "安静", "standard": "标准", "strong": "强力"}
        mode_label = mode_names.get(mode, "标准")
        return {
            "status": "ok",
            "action": "start_cleaning",
            "message": f"已开始{mode_label}模式清扫",
            "details": {"mode": mode, "device": dev.get("model", "")},
        }

    def stop_cleaning(self, user_id: str) -> dict:
        """停止清扫"""
        dev = self.get_device(user_id)
        if not dev:
            return {"status": "error", "message": "设备未绑定"}
        return {
            "status": "ok",
            "action": "stop_cleaning",
            "message": "已停止清扫，设备正在返回充电座",
        }

    def return_to_charge(self, user_id: str) -> dict:
        """返回充电"""
        dev = self.get_device(user_id)
        if not dev:
            return {"status": "error", "message": "设备未绑定"}
        return {
            "status": "ok",
            "action": "return_to_charge",
            "message": "设备正在返回充电座",
        }

    def set_mode(self, user_id: str, mode: str) -> dict:
        """设置清扫模式"""
        valid_modes = {"quiet": "安静模式", "standard": "标准模式", "strong": "强力模式"}
        if mode not in valid_modes:
            return {"status": "error", "message": f"不支持的模式，可选: {', '.join(valid_modes.values())}"}
        return {
            "status": "ok",
            "action": "set_mode",
            "message": f"已切换至{valid_modes[mode]}",
            "details": {"mode": mode},
        }

    def create_schedule(self, uid, time_str, room):
        if not re.match(r"^\d{1,2}:\d{2}$", time_str or ""):
            return {"status": "error", "message": "时间格式错误，请使用 HH:MM 格式"}
        dev = self.get_device(uid)
        if not dev:
            return {"status": "error", "message": "device not bound"}
        return {
            "status": "ok",
            "task": {"user_id": uid, "time": time_str, "room": room, "device": dev["model"]},
            "message": f"已设置定时清扫: 每天 {time_str} 清扫 {room}",
        }

    def format_device_status(self, d):
        return "\n  ".join(
            [
                f"📱 型号: {d.get('model', '未知')}",
                f"🔋 电量: {d.get('battery', '?')}%",
                f"💧 水量: {d.get('water_level', '?')}",
                f"🗑️ 尘盒: {d.get('dust_bin', '?')}",
                f"🧹 拖布: {d.get('mop', '?')}",
                f"📶 在线: {'是' if d.get('online') else '否'}",
                f"⚡ 状态: {d.get('status', '?')}",
                f"⏱️ 已用: {d.get('total_clean_hours', 0)} 小时",
                f"🔧 固件: {d.get('firmware', '?')}",
            ]
        )

    def _mock(self, uid):
        db = {
            "U1001": {
                "model": "X30 Pro",
                "battery": 85,
                "water_level": "充足",
                "dust_bin": "未满",
                "mop": "已安装",
                "online": True,
                "status": "standby",
                "total_clean_hours": 128,
                "firmware": "v3.2.1",
                "source": "模拟",
            },
            "U1002": {
                "model": "X30 Pro",
                "battery": 32,
                "water_level": "不足",
                "dust_bin": "已满",
                "mop": "未安装",
                "online": True,
                "status": "cleaning",
                "total_clean_hours": 256,
                "firmware": "v2.8.0",
                "source": "模拟",
            },
            "U1003": {
                "model": "X30 Pro",
                "battery": 0,
                "water_level": "充足",
                "dust_bin": "未满",
                "mop": "已安装",
                "online": False,
                "status": "offline",
                "total_clean_hours": 67,
                "firmware": "v3.1.0",
                "source": "模拟",
            },
        }
        return db.get(uid)

"""设备管理模块 — DeviceManager (设备状态查询 / 定时任务)

提供对扫地机器人设备的状态查询和控制功能。
当前使用 Mock 数据，后期接入真实 OneNET API。
"""

import re

from smart_qa.agent.tools.onenet_adapter import OneNETAdapter


class DeviceManager:
    """设备管理器 — 查询设备状态 & 创建定时任务"""

    def __init__(self):
        self.onenet = None
        try:
            self.onenet = OneNETAdapter()
        except Exception as e:
            print(f"[Device] OneNET init failed: {e}")

    def get_device(self, user_id: str) -> dict | None:
        if self.onenet:
            d = self.onenet.get_device(user_id)
            if d and d.get("source") != "local_mock":
                return d
        return self._mock(user_id)

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
        }
        return db.get(uid)

    def create_schedule(self, uid, time_str, room):
        if not re.match(r"^\d{1,2}:\d{2}$", time_str or ""):
            return {"status": "error", "message": "time format error"}
        dev = self.get_device(uid)
        if not dev:
            return {"status": "error", "message": "device not bound"}
        return {
            "status": "ok",
            "task": {"user_id": uid, "time": time_str, "room": room, "device": dev["model"]},
            "message": f"Scheduled: {time_str} clean {room}",
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

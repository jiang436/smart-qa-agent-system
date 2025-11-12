# MCP Device Server — OneNET IoT + local mock
import json
import os
import sys


class DeviceDataAdapter:
    def __init__(self):
        self.onenet = None
        self._init_onenet()

    def _init_onenet(self):
        ak = os.getenv("ONENET_API_KEY", "")
        if ak:
            try:
                from .onenet_adapter import OneNETDeviceAdapter

                self.onenet = OneNETDeviceAdapter()
                print("[Device] OneNET adapter ready")
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
            ,
            },
            ,
            },
        }
        return db.get(uid)

    def create_schedule(self, uid, time_str, room):
        import re

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
                f"Model: {d['model']}",
                f"Battery: {d['battery']}%",
                f"Water: {d['water_level']}",
                f"Dustbin: {d['dust_bin']}",
                f"Mop: {d['mop']}",
                f"Online: {d['online']}",
                f"Status: {d.get('status', '?')}",
                f"Source: {d.get('source', '?')}",
            ]
        )


class MCPDeviceServer:
    TOOLS = [
        {
            "name": "get_device_status",
            "description": "Query device status",
            "input_schema": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
        },
        {
            "name": "create_schedule",
            "description": "Create scheduled cleaning",
            "input_schema": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "time": {"type": "string"}, "room": {"type": "string"}},
                "required": ["user_id", "time", "room"],
            },
        },
    ]

    def __init__(self):
        self.adapter = DeviceDataAdapter()

    def handle_request(self, req):
        m = req.get("method")
        if m == "list_tools":
            return {"result": {"tools": self.TOOLS}}
        elif m == "call_tool":
            p = req.get("params", {})
            name = p.get("name")
            args = p.get("arguments", {})
            if name == "get_device_status":
                d = self.adapter.get_device(args.get("user_id", ""))
                if not d:
                    return {"result": {"content": [{"type": "text", "text": "Device not found"}]}}
                return {"result": {"content": [{"type": "text", "text": self.adapter.format_device_status(d)}]}}
            elif name == "create_schedule":
                r = self.adapter.create_schedule(args.get("user_id", ""), args.get("time", ""), args.get("room", ""))
                return {"result": {"content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False)}]}}
        return {"error": {"code": -32601, "message": "unknown"}}

    def run_stdio(self):
        for line in sys.stdin:
            try:
                r = json.loads(line.strip())
                sys.stdout.write(json.dumps(self.handle_request(r), ensure_ascii=False) + "\n")
                sys.stdout.flush()
            except Exception as e:
                sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    MCPDeviceServer().run_stdio()

# OneNET IoT Platform Adapter (中移物联网)
#
# OneNET is China Mobile's IoT platform (open.iot.10086.cn)
# Supports REST API to query device datapoints
#
# Auth: Master-API-Key in header, or Token-based auth
# API Docs: https://open.iot.10086.cn/doc/
#
# Your OneNET setup:
#   Product:  Wy87oxUFbz
#   Device:   X30Pro_Virtual_01
import os

import requests


class OneNETDeviceAdapter:
    """OneNET IoT platform adapter"""

    # OneNET API base URL
    API_BASE = "https://api.heclouds.com"

    def __init__(self):
        self.api_key = os.getenv("ONENET_API_KEY", "")
        self.product_id = os.getenv("ONENET_PRODUCT_ID", "")

    def get_device(self, user_id: str) -> dict | None:
        """Get device data by user_id -> mapped device_name"""
        device_name = os.getenv(f"ONENET_DEVICE_{user_id}", "")
        if not device_name or not self.api_key:
            return self._mock(user_id)

        try:
            # Step 1: Get device ID by name
            device_id = self._get_device_id(device_name)
            if not device_id:
                return None

            # Step 2: Get latest datapoints
            data = self._get_datapoints(device_id)
            if data:
                return self._parse_data(data, device_name)

            return None
        except Exception as e:
            print(f"[OneNET] Error: {e}")
            return None

    def _get_device_id(self, device_name: str) -> str | None:
        """Query device ID by device name"""
        headers = {"api-key": self.api_key}
        try:
            resp = requests.get(
                f"{self.API_BASE}/devices",
                params={"device_name": device_name, "product_id": self.product_id},
                headers=headers,
                timeout=5,
            ).json()
            if resp.get("errno") == 0:
                devices = resp.get("data", {}).get("devices", [])
                if devices:
                    return devices[0].get("id")
            return None
        except Exception as e:
            print(f"[OneNET] get_device_id failed: {e}")
            return None

    def _get_datapoints(self, device_id: str) -> dict | None:
        """Get latest datapoints from device"""
        headers = {"api-key": self.api_key}
        try:
            resp = requests.get(
                f"{self.API_BASE}/devices/{device_id}/datapoints",
                params={"datastream_id": "battery,status,dustbin,water_level,clean_area,fault_code,work_hours"},
                headers=headers,
                timeout=5,
            ).json()
            if resp.get("errno") == 0:
                return resp.get("data", {})
            return None
        except Exception as e:
            print(f"[OneNET] get_datapoints failed: {e}")
            return None

    def _parse_data(self, data: dict, device_name: str) -> dict:
        """Parse OneNET datapoints into unified format"""

        def val(stream_id, default=0):
            stream = data.get(stream_id, {})
            points = stream.get("datapoints", [])
            if points:
                return points[-1].get("value", default)
            return default

        return {
            "model": device_name,
            "battery": int(val("battery", 100)),
            "status": str(val("status", "standby")),
            "water_level": "充足" if int(val("water_level", 1)) == 1 else "不足",
            "dust_bin": "未满" if int(val("dustbin", 1)) == 1 else "已满",
            "mop": "已安装",
            "online": True,
            "total_clean_hours": int(val("work_hours", 0)),
            "fault_code": int(val("fault_code", 0)),
            "source": "OneNET",
        }

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
                "source": "local_mock",
            },
            "U1001": {
                "model": "X30 Pro",
                "battery": 32,
                "water_level": "不足",
                "dust_bin": "已满",
                "mop": "未安装",
                "online": True,
                "status": "cleaning",
                "total_clean_hours": 256,
                "firmware": "v2.8.0",
                "source": "local_mock",
            },
            "U1001": {
                "model": "X30 Pro",
                "battery": 0,
                "water_level": "充足",
                "dust_bin": "未满",
                "mop": "已安装",
                "online": False,
                "status": "offline",
                "total_clean_hours": 67,
                "firmware": "v3.1.0",
                "source": "local_mock",
            },
        }
        return db.get(uid)

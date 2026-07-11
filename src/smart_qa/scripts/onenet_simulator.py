# OneNET device simulator
import os
import random
import time

import requests

API_KEY = os.getenv("ONENET_API_KEY", "")
PRODUCT_ID = os.getenv("ONENET_PRODUCT_ID", "Wy87oxUFbz")
DEVICE_NAME = os.getenv("ONENET_DEVICE_U1001", "X30Pro_Virtual_01")
API_BASE = "https://api.heclouds.com"
INTERVAL = 30


class SimulatedDevice:
    def __init__(self):
        self.battery = 85
        self.status = "standby"
        self.dustbin = 1
        self.water_level = 1
        self.clean_area = 0
        self.work_hours = 128
        self.fault_code = 0
        self.cycle = 0

    def update(self):
        self.cycle += 1
        phase = self.cycle % 10
        if self.status == "charging":
            self.battery = min(100, self.battery + 5)
            if self.battery >= 100:
                self.status = "standby"
        elif self.status == "cleaning":
            self.battery = max(0, self.battery - random.randint(2, 5))
            self.clean_area += random.randint(2, 5)
            self.work_hours += 0.5
            if self.battery < 15:
                self.status = "charging"
        elif self.status == "standby" and phase == 0:
            self.status = "cleaning"
        if self.status == "cleaning" and random.random() < 0.3:
            self.dustbin = 0 if self.dustbin == 1 else 1
        if random.random() < 0.1 and self.status != "fault":
            self.status = "fault"
            self.fault_code = random.choice([5, 6, 7])
        if self.status == "fault" and phase % 2 == 0:
            self.status = "standby"
            self.fault_code = 0

    def to_points(self):
        return [
            {"id": "battery", "datapoints": [{"value": self.battery}]},
            {"id": "status", "datapoints": [{"value": self.status}]},
            {"id": "dustbin", "datapoints": [{"value": self.dustbin}]},
            {"id": "water_level", "datapoints": [{"value": self.water_level}]},
            {"id": "clean_area", "datapoints": [{"value": self.clean_area}]},
            {"id": "work_hours", "datapoints": [{"value": int(self.work_hours)}]},
            {"id": "fault_code", "datapoints": [{"value": self.fault_code}]},
        ]


def upload(device_name, points):
    headers = {"api-key": API_KEY}
    try:
        resp = requests.get(
            API_BASE + "/devices",
            params={"device_name": device_name, "product_id": PRODUCT_ID},
            headers=headers,
            timeout=5,
        ).json()
        if resp.get("errno") != 0:
            return False
        devices = resp.get("data", {}).get("devices", [])
        if not devices:
            return False
        did = devices[0].get("id")
        r = requests.post(
            API_BASE + "/devices/" + str(did) + "/datapoints",
            headers={**headers, "Content-Type": "application/json"},
            json={"datastreams": points},
            timeout=5,
        ).json()
        return r.get("errno") == 0
    except Exception as e:
        print("[Upload]", e)
        return False


def main():
    if not API_KEY:
        print("Set ONENET_API_KEY env var")
        return
    dev = SimulatedDevice()
    print("Simulator started:", DEVICE_NAME, "(every", INTERVAL, "s)")
    try:
        while True:
            dev.update()
            ok = upload(DEVICE_NAME, dev.to_points())
            dust = "OK" if dev.dustbin else "FULL"
            fault = f"E0{dev.fault_code}" if dev.fault_code else "none"
            s = f"{time.strftime('%H:%M:%S')} batt:{dev.battery}% st:{dev.status} dust:{dust} fault:{fault}"
            print("  {} {}".format("OK" if ok else "FAIL", s))
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("Stopped")


if __name__ == "__main__":
    main()

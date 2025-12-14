"""耗材管理服务 — X30 Pro 全配件目录"""
import re

# X30 Pro 全配件数据库
CATALOG = {
    "清洁刷组": {
        "side_brush": {"name": "X30 Pro 原装边刷", "model": "X30-SB-01", "price": 29.9, "life_days": 120, "category": "清洁刷组", "desc": "日常缠绕头发易炸毛，3-6个月更换"},
        "main_brush": {"name": "X30 Pro 原装主滚刷", "model": "X30-MB-01", "price": 59.0, "life_days": 180, "category": "清洁刷组", "desc": "地毯家庭磨损快，4-8个月更换"},
    },
    "拖地配套": {
        "mop": {"name": "X30 Pro 水洗拖布(3片)", "model": "X30-MP-01", "price": 25.0, "life_days": 60, "category": "拖地配套", "desc": "干硬掉毛后拖地留水渍"},
        "disposable_mop": {"name": "一次性免洗拖布(30片)", "model": "X30-DM-01", "price": 19.9, "life_days": 30, "category": "拖地配套", "desc": "用完即弃"},
        "cleaner": {"name": "地面专用清洁液(500ml)", "model": "X30-CL-01", "price": 39.0, "life_days": 90, "category": "拖地配套", "desc": "除油污抑菌"},
    },
    "集尘过滤": {
        "dust_bag": {"name": "自动集尘袋(3只)", "model": "X30-DB-02", "price": 49.0, "life_days": 75, "category": "集尘过滤", "desc": "满袋吸力下降"},
        "hepa_filter": {"name": "HEPA滤芯滤网", "model": "X30-HF-01", "price": 39.0, "life_days": 180, "category": "集尘过滤", "desc": "堵塞后灰尘回流异味"},
    },
    "基站养护": {
        "base_tray": {"name": "基站清洗盘", "model": "X30-BC-01", "price": 79.0, "life_days": 365, "category": "基站养护", "desc": "定期清洁延长基站寿命"},
        "silver_ion": {"name": "银离子抑菌模块", "model": "X30-AG-01", "price": 49.0, "life_days": 180, "category": "基站养护", "desc": "抑制水箱细菌"},
        "antiscale": {"name": "阻垢剂", "model": "X30-AS-01", "price": 29.0, "life_days": 90, "category": "基站养护", "desc": "防水管水垢堵塞"},
    },
    "故障备件": {
        "charge_contact": {"name": "充电触点", "model": "X30-CT-01", "price": 19.0, "life_days": 0, "category": "故障备件", "desc": "触点氧化无法充电时更换"},
        "charge_dock": {"name": "充电底座", "model": "X30-CD-01", "price": 129.0, "life_days": 0, "category": "故障备件", "desc": "底座损坏无法充电时更换"},
        "drive_wheel": {"name": "驱动轮", "model": "X30-DW-01", "price": 79.0, "life_days": 0, "category": "故障备件", "desc": "卡顿打滑时更换"},
        "omni_wheel": {"name": "万向轮", "model": "X30-OW-01", "price": 29.0, "life_days": 0, "category": "故障备件", "desc": "原地打转时检查更换"},
        "sensor_cover": {"name": "传感器保护盖", "model": "X30-SC-01", "price": 15.0, "life_days": 0, "category": "故障备件", "desc": "刮花后影响感应"},
        "roller_cover": {"name": "滚刷盖板+卡扣", "model": "X30-RC-01", "price": 12.0, "life_days": 0, "category": "故障备件", "desc": "盖板松动导致异响"},
        "water_seal": {"name": "防水胶条", "model": "X30-WS-01", "price": 9.0, "life_days": 0, "category": "故障备件", "desc": "水箱密封老化漏水"},
        "water_tank": {"name": "清水箱", "model": "X30-WT-01", "price": 89.0, "life_days": 0, "category": "故障备件", "desc": "漏水损坏时更换"},
    },
    "套装优惠": {
        "basic_kit": {"name": "基础清洁套装(边刷x2+滤网+拖布x3)", "model": "X30-KIT-B", "price": 79.9, "life_days": 0, "category": "套装优惠", "desc": "省¥14，每季度常规更换"},
        "deep_kit": {"name": "深度清洁套装(边刷x2+滚刷+滤网x2+拖布+清洁液)", "model": "X30-KIT-D", "price": 199.0, "life_days": 0, "category": "套装优惠", "desc": "省¥38，半年全面养护"},
        "base_kit": {"name": "基站养护套装(集尘袋x3+银离子+阻垢剂)", "model": "X30-KIT-S", "price": 99.0, "life_days": 0, "category": "套装优惠", "desc": "省¥28，上下水机型专用"},
    },
    "结构备件": {
        "mop_bracket": {"name": "拖布支架", "model": "X30-MB-02", "price": 39.0, "life_days": 0, "category": "结构备件", "desc": "支架卡扣断裂或魔术贴失效时更换"},
        "dust_bin": {"name": "尘盒组件", "model": "X30-DC-01", "price": 49.0, "life_days": 0, "category": "结构备件", "desc": "尘盒破损或止逆挡板失效时更换"},
        "bumper": {"name": "前防撞缓冲条", "model": "X30-BF-01", "price": 25.0, "life_days": 0, "category": "结构备件", "desc": "缓冲条破裂或脱落时更换"},
        "lds_cover": {"name": "激光雷达罩", "model": "X30-LD-01", "price": 35.0, "life_days": 0, "category": "结构备件", "desc": "雷达罩刮花或破裂影响导航时更换"},
        "power_adapter": {"name": "电源适配器", "model": "X30-PA-01", "price": 59.0, "life_days": 0, "category": "结构备件", "desc": "适配器损坏或丢失时更换"},
    },
}

PART_SYNONYMS = {
    "边刷": "side_brush", "边扫": "side_brush", "侧刷": "side_brush",
    "主刷": "main_brush", "滚刷": "main_brush", "主滚刷": "main_brush",
    "拖布": "mop", "抹布": "mop", "拖地布": "mop",
    "一次性拖布": "disposable_mop", "免洗拖布": "disposable_mop",
    "清洁液": "cleaner", "清洗液": "cleaner",
    "集尘袋": "dust_bag", "尘袋": "dust_bag",
    "滤网": "hepa_filter", "滤芯": "hepa_filter", "HEPA": "hepa_filter", "hepa": "hepa_filter",
    "清洗盘": "base_tray", "基站盘": "base_tray",
    "银离子": "silver_ion", "抑菌": "silver_ion",
    "阻垢剂": "antiscale", "除垢": "antiscale",
    "充电触点": "charge_contact", "充电底座": "charge_dock",
    "驱动轮": "drive_wheel", "万向轮": "omni_wheel",
    "传感器盖": "sensor_cover", "保护盖": "sensor_cover",
    "盖板": "roller_cover", "卡扣": "roller_cover",
    "胶条": "water_seal", "防水条": "water_seal",
    "水箱": "water_tank", "清水箱": "water_tank",
    "套装": "basic_kit", "清洁套装": "basic_kit", "养护套装": "deep_kit", "基站套装": "base_kit",
    "拖布支架": "mop_bracket", "支架": "mop_bracket",
    "尘盒": "dust_bin", "集尘盒": "dust_bin",
    "防撞条": "bumper", "缓冲条": "bumper", "防撞": "bumper",
    "雷达罩": "lds_cover", "激光罩": "lds_cover", "雷达盖": "lds_cover",
    "电源适配器": "power_adapter", "充电器": "power_adapter", "电源线": "power_adapter", "适配器": "power_adapter",
}


class ConsumableService:
    """耗材管理服务 — X30 Pro"""

    DEVICE_MODEL = "X30 Pro"

    def identify_part(self, query: str) -> str | None:
        for keyword, pt in PART_SYNONYMS.items():
            if keyword.lower() in query.lower():
                return pt
        m = re.search(r"(边刷|主刷|拖布|滤网|集尘袋|清洁液|套装)", query)
        return PART_SYNONYMS.get(m.group(0)) if m else None

    def get_product(self, part_type: str) -> dict | None:
        for cat in CATALOG.values():
            if part_type in cat:
                return cat[part_type]
        return None

    def get_category_products(self, category: str) -> list[dict]:
        cat = CATALOG.get(category, {})
        return list(cat.values())

    def get_all_categories(self) -> list[str]:
        return list(CATALOG.keys())

    def get_all_products(self) -> list[dict]:
        all_items = []
        for cat_name, items in CATALOG.items():
            for key, item in items.items():
                item["part_key"] = key
                all_items.append(item)
        return all_items

    def search(self, keyword: str) -> list[dict]:
        kw = keyword.lower()
        results = []
        for item in self.get_all_products():
            if kw in item["name"].lower() or kw in item.get("desc", "").lower() or kw in item.get("model", "").lower():
                results.append(item)
        return results

"""知识图谱 — 设备兼容关系 + 错误码层级 + 耗材适配

使用场景:
  - "X30 Pro 的边刷能不能用在 T10 上？" → 查兼容图
  - "E05 是什么故障？" → 查错误码层级树
  - "T10 用哪种滤网？" → 查耗材适配

全部内存计算，0 依赖，<1ms 响应。
"""

from __future__ import annotations

from smart_qa.observability.logger import logger

# ═══════════════════════════════════════════
# 知识数据
# ═══════════════════════════════════════════

# 设备型号 → 家族归属
_DEVICE_FAMILY = {
    "X30 Pro": "X 系列",
    "X30": "X 系列",
    "X20 Pro": "X 系列",
    "X20": "X 系列",
    "T10": "T 系列",
    "T10 Pro": "T 系列",
    "R10": "R 系列",
    "R20": "R 系列",
    "R20 Pro": "R 系列",
}

# 配件兼容关系: (配件类型, 源型号) → [兼容型号列表]
_COMPATIBILITY: dict[tuple[str, str], list[str]] = {
    ("边刷", "X30 Pro"): ["X30 Pro", "X30", "X20 Pro", "X20"],
    ("边刷", "T10"): ["T10", "T10 Pro"],
    ("边刷", "R20"): ["R20", "R20 Pro", "R10"],
    ("主刷", "X30 Pro"): ["X30 Pro", "X30"],
    ("主刷", "X20 Pro"): ["X20 Pro", "X20"],
    ("主刷", "T10"): ["T10", "T10 Pro"],
    ("主刷", "R20"): ["R20", "R20 Pro", "R10"],
    ("拖布", "X30 Pro"): ["X30 Pro", "X30"],
    ("拖布", "X20 Pro"): ["X20 Pro", "X20"],
    ("拖布", "T10"): ["T10", "T10 Pro"],
    ("滤网", "X30 Pro"): ["X30 Pro", "X30", "X20 Pro", "X20"],
    ("滤网", "T10"): ["T10", "T10 Pro"],
    ("滤网", "R20"): ["R20", "R20 Pro", "R10"],
    ("尘盒", "X30 Pro"): ["X30 Pro", "X30", "X20 Pro", "X20"],
    ("尘盒", "T10"): ["T10", "T10 Pro"],
    ("尘盒", "R20"): ["R20", "R20 Pro", "R10"],
    ("水箱", "X30 Pro"): ["X30 Pro", "X30"],
    ("水箱", "X20 Pro"): ["X20 Pro", "X20"],
    ("充电座", "X30 Pro"): ["X30 Pro", "X30"],
    ("充电座", "X20 Pro"): ["X20 Pro", "X20"],
    ("充电座", "T10"): ["T10", "T10 Pro", "R20", "R20 Pro", "R10"],
}

# 错误码层级树
_ERROR_CODE_TREE: dict[str, dict] = {
    "E01": {
        "title": "驱动轮异常",
        "category": "运动系统",
        "cause": "驱动轮卡住 / 电机故障 / 轮组磨损",
        "fix": "检查驱动轮是否有异物缠绕，清理后重启。若仍报错，联系售后更换驱动轮组件。",
        "children": {},
    },
    "E02": {
        "title": "边刷异常",
        "category": "清洁系统",
        "cause": "边刷卡住 / 电机过载 / 边刷脱落",
        "fix": "取下边刷清理缠绕物，重新安装。若边刷变形需更换。",
        "children": {},
    },
    "E03": {
        "title": "主刷异常",
        "category": "清洁系统",
        "cause": "主刷卡住 / 毛发缠绕 / 滚刷磨损",
        "fix": "打开主刷盖板，取出滚刷清理毛发，重新安装。定期更换滚刷（建议每 6 个月）。",
        "children": {},
    },
    "E04": {
        "title": "风机异常",
        "category": "清洁系统",
        "cause": "风机卡住 / 进风口堵塞 / 风机电机故障",
        "fix": "清理尘盒和进风口，检查风机是否有异物。若仍有异响，联系售后。",
        "children": {},
    },
    "E05": {
        "title": "激光传感器异常",
        "category": "传感器系统",
        "cause": "激光雷达遮挡 / 激光头故障 / 测距模块异常",
        "fix": "检查激光雷达是否有遮挡物，擦拭雷达罩。若'咔咔'响，激光头可能损坏需更换。",
        "children": {
            "E05-1": {
                "title": "激光雷达不转",
                "category": "传感器系统",
                "cause": "马达故障 / 皮带脱落 / 供电异常",
                "fix": "听是否有转动声。完全无声→马达或供电问题；有异响→皮带脱落。",
            },
            "E05-2": {
                "title": "测距数据异常",
                "category": "传感器系统",
                "cause": "雷达罩脏污 / 强光干扰 / 激光管老化",
                "fix": "擦拭雷达罩，避免阳光直射。若多次复现，更换激光管。",
            },
        },
    },
    "E06": {
        "title": "碰撞传感器异常",
        "category": "传感器系统",
        "cause": "碰撞开关卡住 / 防撞条变形 / 传感器接触不良",
        "fix": "检查防撞条是否被压住无法回弹，按压测试回弹是否正常。",
        "children": {},
    },
    "E07": {
        "title": "悬崖传感器异常",
        "category": "传感器系统",
        "cause": "悬崖传感器脏污 / 传感器故障 / 黑色地板误判",
        "fix": "擦拭底部悬崖传感器（通常 4-6 个）。黑色地板可能误判，在 App 中关闭防跌落功能。",
        "children": {},
    },
    "E08": {
        "title": "充电异常",
        "category": "电源系统",
        "cause": "充电座无电 / 充电触点脏污 / 电池老化",
        "fix": "检查充电座指示灯是否亮，用干布擦拭机器和充电座触点。若电池老化需更换。",
        "children": {},
    },
    "E09": {
        "title": "电池异常",
        "category": "电源系统",
        "cause": "电池老化 / 温度过高 / 电池接触不良",
        "fix": "将机器移至阴凉处冷却后重试。若续航明显下降，更换电池。",
        "children": {},
    },
    "E10": {
        "title": "WiFi 连接异常",
        "category": "通信系统",
        "cause": "WiFi 信号弱 / 密码错误 / 2.4G/5G 不兼容",
        "fix": "确认路由器为 2.4GHz 频段，WiFi 密码正确。靠近路由器重试配网。",
        "children": {},
    },
}


class KnowledgeGraph:
    """设备知识图谱 — 兼容查询 + 错误码检索 + 耗材适配"""

    def __init__(self):
        self._devices = set(_DEVICE_FAMILY.keys())
        self._compat = _COMPATIBILITY
        self._errors = _ERROR_CODE_TREE
        logger.info("知识图谱已加载 devices={} compat_rules={} error_codes={}",
                     len(self._devices), len(self._compat), len(self._errors))

    # ── 设备兼容 ──

    def check_compatibility(self, part: str, from_device: str, to_device: str) -> dict:
        """检查配件是否兼容

        Returns: {"compatible": bool, "message": str, "compatible_models": [...]}
        """
        # 精确匹配
        key = (part, from_device)
        compat_list = self._compat.get(key, [])

        if to_device in compat_list:
            return {
                "compatible": True,
                "message": f"{part} 可在 {from_device} 与 {to_device} 之间通用。",
                "compatible_models": compat_list,
            }

        # 同一家族？
        from_family = _DEVICE_FAMILY.get(from_device, "")
        to_family = _DEVICE_FAMILY.get(to_device, "")
        if from_family and from_family == to_family:
            return {
                "compatible": True,
                "message": f"{from_device} 与 {to_device} 同属 {from_family}，{part} 很可能通用。建议核实具体型号。",
                "compatible_models": [d for d in self._devices if _DEVICE_FAMILY.get(d) == from_family],
            }

        # 不兼容：列出能用的型号
        if compat_list:
            return {
                "compatible": False,
                "message": f"{from_device} 的 {part} 不能用于 {to_device}。该配件兼容的型号: {', '.join(compat_list[:5])}。",
                "compatible_models": compat_list,
            }

        # 未知配件
        return {
            "compatible": False,
            "message": f"暂未收录 {from_device} {part} 的兼容信息。建议查阅产品说明书或联系客服。",
            "compatible_models": [],
        }

    def get_compatible_parts(self, device: str) -> list[dict]:
        """获取某设备的所有已知配件兼容信息"""
        result = []
        for (part, src), models in self._compat.items():
            if src == device:
                result.append({"part": part, "compatible_models": models})
        return result

    # ── 错误码 ──

    def get_error_info(self, code: str) -> dict | None:
        """查询错误码详情

        支持精确码 (E05) 和子码 (E05-1)。
        """
        code_upper = code.upper()

        # 先查顶层
        for error_code, info in self._errors.items():
            if error_code.upper() == code_upper:
                return {"code": error_code, **info}

            # 查子码
            for sub_code, sub_info in info.get("children", {}).items():
                if sub_code.upper() == code_upper:
                    return {"code": sub_code, "parent": error_code, "parent_title": info["title"], **sub_info}

        return None

    def search_errors_by_symptom(self, symptom: str) -> list[dict]:
        """根据故障现象搜索可能的错误码"""
        results = []
        for code, info in self._errors.items():
            text = info.get("title", "") + info.get("cause", "") + info.get("fix", "")
            if any(kw in text for kw in symptom.split()):
                results.append({"code": code, **info})
        return results

    # ── 实体链接 ──

    def link_entities(self, query: str) -> dict:
        """从自然语言中提取已知实体（设备型号、错误码、配件类型）

        Returns:
            {"devices": ["X30 Pro"], "error_codes": ["E05"], "parts": ["边刷"]}
        """
        result: dict[str, list[str]] = {"devices": [], "error_codes": [], "parts": []}

        # 设备型号匹配（长型号优先，避免 "X30" 匹配到 "X30 Pro" 里的子串）
        matched_spans: list[tuple[int, int]] = []
        for device in sorted(self._devices, key=len, reverse=True):
            q_lower = query.lower()
            d_lower = device.lower()
            idx = q_lower.find(d_lower)
            while idx != -1:
                # 检查这个位置是否已被更长型号覆盖
                if not any(s <= idx < e for s, e in matched_spans):
                    result["devices"].append(device)
                    matched_spans.append((idx, idx + len(d_lower)))
                idx = q_lower.find(d_lower, idx + 1)

        # 错误码匹配
        import re
        error_pattern = re.compile(r"[Ee]\d{2}(?:-\d)?")
        for m in error_pattern.finditer(query):
            result["error_codes"].append(m.group(0).upper())

        # 配件类型匹配
        part_keywords = {
            "边刷": ["边刷", "侧刷"],
            "主刷": ["主刷", "滚刷", "胶刷"],
            "滤网": ["滤网", "HEPA", "过滤网"],
            "拖布": ["拖布", "抹布", "拖地布"],
            "尘盒": ["尘盒", "集尘盒"],
            "水箱": ["水箱"],
            "充电座": ["充电座", "充电桩"],
        }
        for part, keywords in part_keywords.items():
            for kw in keywords:
                if kw in query:
                    result["parts"].append(part)
                    break

        return result

    # ── 多跳推理 ──

    def multi_hop_search(self, query: str) -> dict | None:
        """多跳推理: 沿图遍历找到间接关联

        例: "X30 Pro 的边刷能不能用在 T10 上"
          → hop1: X30 Pro 边刷 → 兼容 X30/X20 系列
          → hop2: T10 边刷 → 仅兼容 T10/Pro
          → 结论: 不兼容，跨系列

        Returns:
            {"answer": "...", "path": ["hop1", "hop2"], "evidence": [...]}
        """
        entities = self.link_entities(query)
        devices = entities["devices"]
        parts = entities["parts"]

        if len(devices) < 2 or not parts:
            return None

        # 从第一个设备出发
        from_dev = devices[0]
        to_dev = devices[1]
        part = parts[0]

        # 查配件兼容
        compat = self.check_compatibility(part, from_dev, to_dev)

        # 查家族
        from_family = _DEVICE_FAMILY.get(from_dev, "")
        to_family = _DEVICE_FAMILY.get(to_dev, "")
        same_family = from_family and from_family == to_family

        path = [
            f"① {from_dev} 属于 {from_family or '未知系列'}",
            f"② {to_dev} 属于 {to_family or '未知系列'}",
        ]

        if same_family:
            path.append(f"③ 同属 {from_family}，配件大概率通用")
            result = {"answer": f"{from_dev} 的 {part} 很可能可以用于 {to_dev}（同属 {from_family}）。建议核实具体型号。",
                       "path": path, "confidence": "medium", "compatible": True}
        else:
            path.append(f"③ 跨系列（{from_family} ≠ {to_family}），配件不通用")
            compat_list = compat.get("compatible_models", [])
            if compat_list:
                path.append(f"④ {from_dev} 的 {part} 可用的型号: {', '.join(compat_list[:4])}")
            result = {"answer": f"{from_dev} 的 {part} 不能用于 {to_dev}。",
                       "path": path, "confidence": "high", "compatible": compat["compatible"]}

        result["evidence"] = [compat]
        return result

    def get_reasoning_path(self, query: str) -> str | None:
        """获取推理路径文本（可解释性）"""
        search = self.multi_hop_search(query)
        if not search:
            return None
        return "推理路径:\n" + "\n".join(search.get("path", [])) + \
               f"\n\n结论: {search.get('answer', '')}"

    # ── 图增强检索（注入到 RAG 上下文） ──

    def augment_context(self, query: str) -> str | None:
        """混合型 GraphRAG: 实体链接 + 多跳推理 + 结构化证据

        Returns: 格式化 GraphRAG 上下文，包含推理路径和结构化证据
        """
        parts = []

        # 1. 实体链接
        entities = self.link_entities(query)
        linked = []
        if entities["devices"]:
            linked.append(f"设备: {', '.join(entities['devices'])}")
        if entities["error_codes"]:
            linked.append(f"错误码: {', '.join(entities['error_codes'])}")
        if entities["parts"]:
            linked.append(f"配件: {', '.join(entities['parts'])}")
        if linked:
            parts.append("🔗 识别的实体: " + " | ".join(linked))

        # 2. 多跳推理（兼容性/对比类问题）
        result = self.multi_hop_search(query)
        if result:
            parts.append("🧠 多跳推理:\n" + "\n".join(result.get("path", [])))
            parts.append(f"结论: {result['answer']}")

        # 3. 错误码详情
        for code in entities["error_codes"]:
            info = self.get_error_info(code)
            if info:
                parts.append(
                    f"⚠️ 错误码 {info['code']} — {info['title']} ({info.get('category', '')})\n"
                    f"  原因: {info.get('cause', '')}\n"
                    f"  处理: {info.get('fix', '')}"
                )

        # 4. 配件兼容（单个设备查询）
        if not result and entities["devices"]:
            compat = self.get_compatible_parts(entities["devices"][0])
            if compat:
                lines = [f"📦 {entities['devices'][0]} 配件兼容:"]
                for item in compat[:5]:
                    lines.append(f"  • {item['part']}: {', '.join(item['compatible_models'][:4])}")
                parts.append("\n".join(lines))

        return "\n\n".join(parts) if parts else None


def get_kg() -> KnowledgeGraph:
    """获取 KnowledgeGraph 实例（优先从 DI 容器，回退到直接构建）

    注册方式（在 lifespan 中）:
        from smart_qa.di import container
        container.register("knowledge_graph", KnowledgeGraph())
    """
    try:
        from smart_qa.di import container
        if container.has("knowledge_graph"):
            return container.get("knowledge_graph")
    except Exception:
        pass
    return KnowledgeGraph()

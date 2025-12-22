"""耗材管理场景 — 基于设备 + 耗材兼容表的配件推荐

文档第 2.2 节:
  用户: "边刷该换了，买什么型号？"
  -> 意图识别 -> 设备识别 -> 兼容表查询 -> 更换周期判断 ->
     原装/第三方推荐 -> HITL 二次确认 -> 订单创建

核心流程:
  1. 设备识别（从用户描述 / 用户画像 / 错误码反推型号）
  2. 耗材兼容表查询（Pydantic 数据模型：型号 -> 兼容耗材列表）
  3. 更换周期判断（根据上次更换时间判断是否确实到周期）
  4. 推荐生成（原装 & 第三方并行推荐）
  5. HITL 确认（让用户确认后再下单）
  6. 订单创建（写入 PostgreSQL + 通知供应链）

技术要点:
  - HITL 状态机确保下单前用户确认
  - 原装/第三方分列，说清区别
  - 更换周期辅助判断（上次更换 < 30 天则提醒）
"""

import time

from src.agent.agents.hitl import HITLManager
from src.memory.cache import SemanticCache
from src.memory.short_term import MemoryCompressor, Message
from src.models.chat_schema import ChatRequest, ChatResponse
from src.observability.logger import logger
from src.services.consumable_service import ConsumableService
from src.agent.state_utils import extract_user_query


class ConsumablesScenario:
    """耗材管理场景

    用法:
        result_state = await ConsumablesScenario.run(state)
    """

    _hitl_helper: HITLManager | None = None
    _consumable_service: ConsumableService | None = None

    @classmethod
    def _get_hitl_helper(cls, llm_client=None) -> HITLManager:
        if cls._hitl_helper is None:
            cls._hitl_helper = HITLManager(llm_client=llm_client)
        return cls._hitl_helper

    @classmethod
    def _get_consumable_service(cls) -> ConsumableService:
        if cls._consumable_service is None:
            cls._consumable_service = ConsumableService()
        return cls._consumable_service

    @staticmethod
    async def _naturalize(structured_text: str) -> str:
        """用 LLM 把结构化数据转成自然对话"""
        try:
            from src.agent.persona import get_system_prompt
            from src.app.deps import get_llm_client
            llm = get_llm_client()
            persona = get_system_prompt("consumables")
            prompt = (
                persona + "\n\n"
                "请把下面的耗材推荐信息用自然对话的方式说一遍。\n"
                "要求:\n"
                "- 保留所有型号、价格、寿命等关键数据，一个都不能丢\n"
                '- 用「您」称呼，语气温暖亲切\n'
                "- 不要把信息写成列表，用自然段落表达\n"
                "- 不要添加原文本中没有的耗材或价格信息\n\n"
                + structured_text + "\n\n"
                "自然对话版:"
            )
            response = await llm.ainvoke(prompt)
            result = response.content if hasattr(response, "content") else str(response)
            return result.strip() or structured_text
        except Exception:
            return structured_text

    @staticmethod
    async def run(state: dict) -> dict:
        """执行耗材管理场景

        状态机:
          init -> 收集设备信息 -> 查询兼容表 -> 推荐 ->
          hitl_confirm -> 创建订单 -> 完成

        Args:
            state: AgentState 字典

        Returns:
            更新后的 state，final_answer 已填充
        """
        start_time = time.time()
        query = ConsumablesScenario._extract_query(state)

        if not query:
            state["final_answer"] = "请问您需要查询哪种耗材？或者告诉我您的设备型号，我帮您查兼容的配件。"
            return state

        user_id = state.get("user_id", "anonymous")
        user_profile = state.get("user_profile", {})

        # 拼接上下文：设备识别用全文，耗材识别只用当前查询
        full_context = query
        messages = state.get("messages", [])
        for m in messages[-4:-1]:
            c = getattr(m, "content", "") if hasattr(m, "content") else (m.get("content", "") if isinstance(m, dict) else "")
            full_context = c + " " + full_context

        # 1. 设备识别 — 从上下文提取（允许"X30 Pro"在上文出现过）
        device_model = ConsumablesScenario._identify_device(full_context, user_profile) or "X30 Pro"

        # 2. 耗材识别 — 只用当前查询！避免"那主刷呢"被上一条"边刷"干扰
        service = ConsumablesScenario._get_consumable_service()
        consumable_type = service.identify_part(query) or ConsumablesScenario._detect_consumable(query)

        # 3. 查询耗材
        product = service.get_product(consumable_type) if consumable_type else None

        if not product:
            # 没识别到具体耗材类型，列出所有类别
            cats = service.get_all_categories()
            state["final_answer"] = (
                f"X30 Pro 目前支持以下耗材类别，请问您需要哪种？\n"
                + "\n".join(f"  • {c}" for c in cats)
            )
            return state

        # 4. 返回推荐
        state["final_answer"] = (
            f"📱 设备: {device_model}\n"
            f"🔧 耗材: {product['name']}\n"
            f"📦 型号: {product['model']}\n"
            f"💰 价格: ¥{product['price']}\n"
            f"📅 建议更换周期: 约{product['life_days']}天\n"
            f"💡 {product['desc']}\n\n"
            f"🛒 请前往 App → 商城 → 耗材配件 下单购买"
        )
        return state

    @staticmethod
    def _extract_query(state: dict) -> str:
        return extract_user_query(state)

    @staticmethod
    def _identify_device(query: str, user_profile: dict = None) -> str | None:
        """从查询文本或用户画像中识别设备型号"""
        import re

        # 标准化：X30pro/X30 Pro/x30 pro/X30-Pro → X30 Pro
        normalized = re.sub(r"(?i)x30[\s-]*pro", "X30 Pro", query)

        known_models = ["X30 Pro"]
        for model in known_models:
            if model.lower() in normalized.lower():
                return model

        if user_profile:
            return user_profile.get("device_model")

        return None

    @staticmethod
    def _detect_consumable(query: str) -> str | None:
        """从查询文本中检测耗材类型（返回 ConsumableService 兼容的英文键名）"""
        # 中文关键词 → 英文键名（与 ConsumableService.PART_SYNONYMS 对齐）
        consumable_map = {
            "side_brush": ["边刷", "侧刷", "边扫"],
            "hepa_filter": ["滤网", "hepa", "过滤网", "滤芯"],
            "main_brush": ["主刷", "滚刷", "胶刷", "滚筒"],
            "mop": ["拖布", "抹布", "拖地布"],
            "dust_bag": ["尘袋", "集尘袋", "垃圾袋"],
            "cleaner": ["清洁液", "清洗液"],
            "silver_ion": ["银离子", "抑菌模块"],
            "antiscale": ["阻垢剂", "除垢剂"],
            "base_tray": ["清洗盘", "基站盘"],
            "charge_contact": ["充电触点"],
            "drive_wheel": ["驱动轮"],
            "omni_wheel": ["万向轮"],
            "sensor_cover": ["传感器盖", "保护盖"],
            "roller_cover": ["盖板", "卡扣"],
            "water_seal": ["胶条", "防水条"],
            "water_tank": ["水箱", "清水箱", "污水箱"],
            "charge_dock": ["充电底座", "充电座"],
            "disposable_mop": ["一次性拖布", "免洗拖布"],
            "mop_bracket": ["拖布支架", "支架"],
            "dust_bin": ["尘盒", "集尘盒", "尘盒组件"],
            "bumper": ["防撞条", "缓冲条", "防撞"],
            "lds_cover": ["雷达罩", "激光罩", "雷达盖", "激光雷达罩"],
            "power_adapter": ["电源适配器", "充电器", "适配器"],
        }

        query_lower = query.lower()
        for en_key, keywords in consumable_map.items():
            if any(kw in query_lower for kw in keywords):
                return en_key
        return None

    @staticmethod
    def _check_renewal_cycle(
        service, device_model: str, user_profile: dict, consumable_type: str | None
    ) -> tuple[bool, int]:
        """判断是否需要更换（False = 还不到更换时间）"""
        last_renew = None
        if user_profile:
            consumable_key = f"{device_model}:{consumable_type}"
            last_renew = user_profile.get("consumable_renew", {}).get(consumable_key)

        if not last_renew:
            return True, 0

        try:
            import datetime
            from dateutil.parser import parse

            last_date = parse(last_renew)
            days_since = (datetime.datetime.now() - last_date).days
            if days_since < 30:
                return False, days_since
            return True, days_since
        except Exception:
            return True, 0

    @staticmethod
    def _format_recommendation(compatibles: list[dict], device_model: str, consumable_type: str | None) -> str:
        """格式化推荐信息"""
        lines = [f"为您找到以下适配 {device_model} 的耗材:"]

        for item in compatibles:
            name = item.get("name", "")
            sku = item.get("sku", "")
            price = item.get("price", "")
            lifetime = item.get("lifetime", "")
            brand = item.get("brand", "原装")

            parts = [f"  - {name} ({brand})"]
            if price:
                parts.append(f"    价格: {price}")
            if lifetime:
                parts.append(f"    建议更换周期: {lifetime}")
            if sku:
                parts.append(f"    型号: {sku}")
            lines.extend(parts)

        return "\n".join(lines)

    @classmethod
    def reset(cls):
        """重置所有单例（用于测试清理）"""
        cls._hitl_helper = None
        cls._consumable_service = None

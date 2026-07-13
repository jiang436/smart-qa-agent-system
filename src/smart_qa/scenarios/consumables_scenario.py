"""耗材管理场景 — 基于设备 + 耗材兼容表的配件推荐 + HITL 确认下单

核心流程（两轮对话）:

  第一轮: 推荐
    1. 设备识别 → 2. 耗材兼容表查询 → 3. 推荐生成
    4. 设置 state.task_memory.pending_purchase
    5. 返回推荐 + 询问是否下单

  第二轮: 确认
    1. RouterAgent 检测到 pending_purchase → 路由到 consumables
    2. ConsumablesScenario 检测到 pending_purchase
    3. 判断用户意图 (yes/no)
    4. yes → 创建订单 (PostgreSQL) → 返回确认信息
    5. no → 取消 → 返回取消信息
"""

from __future__ import annotations

import time

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger
from smart_qa.services.consumable_service import ConsumableService


class ConsumablesScenario:
    """耗材管理场景

    用法:
        result_state = await ConsumablesScenario.run(state)
    """

    _consumable_service: ConsumableService | None = None

    @classmethod
    def _get_consumable_service(cls) -> ConsumableService:
        if cls._consumable_service is None:
            cls._consumable_service = ConsumableService()
        return cls._consumable_service

    @staticmethod
    async def run(state: dict) -> dict:
        """执行耗材管理场景

        状态机:
          init → 收集设备信息 → 查询兼容表 → 推荐 → HITL 确认 → 创建订单 → 完成
        """
        start = time.time()
        query = ConsumablesScenario._extract_query(state)

        if not query:
            state["final_answer"] = "请问您需要查询哪种耗材？或者告诉我您的设备型号，我帮您查兼容的配件。"
            return state

        user_id = state.get("user_id", "anonymous")
        user_profile = state.get("user_profile", {})
        task_memory = state.get("task_memory") or {}

        # ═══════════════════════════════════════
        # Phase 2: HITL 确认 — 用户对推荐做出回应
        # ═══════════════════════════════════════
        pending = task_memory.get("pending_purchase")
        if pending:
            result = await ConsumablesScenario._handle_approval(user_id, query, pending, state)
            elapsed = time.time() - start
            logger.info("耗材 HITL 完成 decision={} latency={:.1f}s", result.get("decision"), elapsed)
            return result

        # ═══════════════════════════════════════
        # Phase 1: 推荐
        # ═══════════════════════════════════════

        full_context = query
        messages = state.get("messages", [])
        for m in messages[-4:-1]:
            c = (
                getattr(m, "content", "")
                if hasattr(m, "content")
                else (m.get("content", "") if isinstance(m, dict) else "")
            )
            full_context = c + " " + full_context

        device_model = ConsumablesScenario._identify_device(full_context, user_profile) or "X30 Pro"
        service = ConsumablesScenario._get_consumable_service()
        consumable_type = service.identify_part(query) or ConsumablesScenario._detect_consumable(query)

        product = service.get_product(consumable_type) if consumable_type else None

        if not product:
            cats = service.get_all_categories()
            state["final_answer"] = "X30 Pro 目前支持以下耗材类别，请问您需要哪种？\n" + "\n".join(
                f"  • {c}" for c in cats
            )
            return state

        # ── 生成推荐 + 设置待确认 ──
        recommendation = (
            f"📱 设备: {device_model}\n"
            f"🔧 耗材: {product['name']}\n"
            f"📦 型号: {product['model']}\n"
            f"💰 价格: ¥{product['price']}\n"
            f"📅 建议更换周期: 约{product['life_days']}天\n"
            f"💡 {product['desc']}\n\n"
        )

        # 保存待确认信息
        pending_info = {
            "device_model": device_model,
            "consumable_type": consumable_type,
            "product_name": product["name"],
            "product_model": product["model"],
            "price": product["price"],
        }

        state["task_memory"] = {**task_memory, "pending_purchase": pending_info}
        state["final_answer"] = recommendation + "🛒 需要帮您下单购买吗？(回复「是」「确认」「下单」或「不用了」)"

        elapsed = time.time() - start
        logger.info("耗材推荐完成 latency={:.1f}s", elapsed)
        return state

    @staticmethod
    async def _handle_approval(user_id: str, query: str, pending: dict, state: dict) -> dict:
        """处理用户对推荐的确认/拒绝"""
        q = query.lower().strip()

        # 确认关键词
        confirm = any(
            kw in q for kw in ["是", "确认", "下单", "买", "要", "好的", "可以", "嗯", "好", "行", "ok", "yes"]
        )
        reject = any(kw in q for kw in ["不", "不要", "不用", "算了", "取消", "no", "别"])

        if confirm and not reject:
            return await ConsumablesScenario._place_order(user_id, pending, state)
        elif reject:
            state["task_memory"] = {
                k: v for k, v in (state.get("task_memory") or {}).items() if k != "pending_purchase"
            }
            state["final_answer"] = "好的，已取消订单。如果您以后需要，随时告诉我。"
            return state
        else:
            # 没明确确认也没拒绝 — 再问一次
            state["final_answer"] = (
                f"您想购买「{pending.get('product_name', '')}」吗？\n回复「确认」下单，或「不用了」取消。"
            )
            return state

    @staticmethod
    async def _place_order(user_id: str, pending: dict, state: dict) -> dict:
        """创建订单"""
        from smart_qa.database.postgres import PostgresClient

        device_model = pending.get("device_model", "X30 Pro")
        consumable_type = pending.get("consumable_type", "")
        product_name = pending.get("product_name", "")

        try:
            from smart_qa.database.engine import get_session_factory
            from smart_qa.database.postgres import PostgresClient

            factory = get_session_factory()
            async with factory() as session:
                order = await PostgresClient.create_order(
                    db=session,
                    user_id=user_id,
                    device_model=device_model,
                    part_type=consumable_type,
                    part_name=product_name,
                    quantity=1,
                    price=pending.get("price"),
                    source="HITL",
                )
                await session.commit()

            state["task_memory"] = {
                k: v for k, v in (state.get("task_memory") or {}).items() if k != "pending_purchase"
            }
            state["final_answer"] = (
                f"✅ 订单已创建！\n"
                f"📦 {product_name}\n"
                f"💰 ¥{pending.get('price', '?')}\n"
                f"📋 订单号: {order.order_id}\n\n"
                f"预计3-5个工作日送达，请注意查收。"
            )
        except Exception as e:
            logger.error("订单创建失败: {}", e)
            state["final_answer"] = "抱歉，下单时遇到了问题，请稍后重试或前往 App 商城购买。"

        return state

    # ═══════════════════════════════════════
    # 工具方法（不变）
    # ═══════════════════════════════════════

    @staticmethod
    def _extract_query(state: dict) -> str:
        return extract_user_query(state)

    @staticmethod
    def _identify_device(query: str, user_profile: dict = None) -> str | None:
        import re

        normalized = re.sub(r"(?i)x30[\s-]*pro", "X30 Pro", query)
        if "X30 Pro" in normalized:
            return "X30 Pro"
        if user_profile:
            return user_profile.get("device_model")
        return None

    @staticmethod
    def _detect_consumable(query: str) -> str | None:
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
        q = query.lower()
        for en_key, keywords in consumable_map.items():
            if any(kw in q for kw in keywords):
                return en_key
        return None

    @classmethod
    def reset(cls):
        cls._consumable_service = None

"""耗材管理场景 — 基于 LLM 语义分析的 Agentic 流程

核心流程（由 LLM 分析驱动，非硬编码 if/else）:

  1. LLM 分析用户查询 → 结构化意图: {action, category, product_keyword}
  2. 根据 action 分发:
     - track_order      → 查询物流
     - view_category    → 展示类别下产品列表
     - identify_product → 匹配具体产品 → 推荐 + HITL
     - browse           → 展示所有类别
     - confirm          → 确认购买（HITL）
     - reject           → 取消购买
     - unknown          → 无法理解时友好回复

⚠️ 订单与物流均为模拟数据
"""

from __future__ import annotations

import json
import random
import time

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger
from smart_qa.services.consumable_service import ConsumableService

# ── LLM 分析 prompt 模板 ──
_ANALYZE_PROMPT = """你是一个智能家居耗材管理助手的意图分析模块。你的任务是理解用户的查询并返回结构化 JSON。

可用耗材类别:
{category_list}

全部配件:
{product_list}

请分析用户查询，返回以下 JSON（仅 JSON，不要其他文字）:

{{
  "action": "browse" | "view_category" | "identify_product" | "track_order" | "unknown",
  "category": null | "类别名称（必须与上面列出的类别名完全一致）",
  "product_keyword": null | "用户提到的配件关键词（用于在产品库中搜索）",
  "reason": "简短说明你的判断理由"
}}

action 选择规则:
- browse: 用户表示要买耗材/看配件/有什么, 没有指定具体类别或配件
- view_category: 用户提到了某个类别名称（如"清洁刷组""结构备件"）
- identify_product: 用户提到了具体的配件（如"边刷""滤网""拖布"）或想购买某配件
- track_order: 用户想查订单/物流/到哪了
- unknown: 完全无法理解或与耗材无关

用户查询: {query}
"""


class ConsumablesScenario:
    """耗材管理场景（模拟订单系统）

    基于 LLM 语义分析驱动流程分发，而非硬编码关键词匹配。
    """

    _consumable_service: ConsumableService | None = None

    @classmethod
    def _get_consumable_service(cls) -> ConsumableService:
        if cls._consumable_service is None:
            cls._consumable_service = ConsumableService()
        return cls._consumable_service

    @classmethod
    async def _analyze_query(cls, query: str) -> dict:
        """用 LLM 分析用户查询，返回结构化意图"""
        service = cls._get_consumable_service()
        categories = service.get_all_categories()
        products = service.get_all_products()

        prompt = _ANALYZE_PROMPT.format(
            category_list="\n".join(f"  - {c}" for c in categories),
            product_list="\n".join(f"  - {p['name']}（{p['model']}）" for p in products),
            query=query,
        )

        try:
            from smart_qa.deps import get_llm_client

            llm = get_llm_client()
            response = await llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            # 提取 JSON（处理 LLM 偶尔加 markdown 包围的情况）
            if "```" in content:
                content = content.split("```")[0] if content.startswith("```") else content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            result = json.loads(content)
            if result.get("action") not in ("browse", "view_category", "identify_product", "track_order", "unknown"):
                result["action"] = "unknown"
            return result
        except Exception as e:
            logger.warning("LLM 意图分析失败 query={} err={}", query[:40], e)
            return {"action": "unknown", "category": None, "product_keyword": None}

    @staticmethod
    async def run(state: dict) -> dict:
        """执行耗材管理场景

        LLM 驱动流程分发：
          1. 订单/物流查询拦截（关键词快检）
          2. pending_purchase 检查（HITL）
          3. LLM 语义分析 → 分发 action
          4. 根据 action 执行对应逻辑
        """
        start = time.time()
        query = extract_user_query(state)
        user_id = state.get("user_id", "anonymous")
        logger.info("耗材场景开始 user={} query={}", user_id, query[:60])

        raw_tm = state.get("task_memory")
        pending_info = (raw_tm or {}).get("pending_purchase") if raw_tm else None

        # 从 messages 恢复 pending_purchase（SystemMessage + RemoveMessage 跨轮持久）
        if not pending_info:
            from langchain_core.messages import SystemMessage as _SM

            for m in state.get("messages", []):
                if isinstance(m, _SM) and getattr(m, "content", "").startswith("__pending_purchase__:"):
                    try:
                        import json as _json

                        pending_info = _json.loads(m.content[len("__pending_purchase__:"):])
                        break
                    except Exception:
                        pass

        if not query:
            state["final_answer"] = "请问您需要查询哪种耗材？或者告诉我您的设备型号，我帮您查兼容的配件。"
            return state

        if any(kw in query for kw in ["订单", "物流", "到哪了", "快递", "运单", "跟踪", "签收"]):
            result = await ConsumablesScenario._handle_order_query(user_id)
            state["final_answer"] = result
            return state

        # ── HITL 确认：有未处理的待确认订单 → 先处理 ──
        if pending_info:
            logger.info("HITL triggered via pending_purchase={}", pending_info.get("product_name"))
            state["final_answer"] = await ConsumablesScenario._handle_approval(user_id, query, pending_info, state)
            return state
        # ── LLM 语义分析 ──
        analysis = await ConsumablesScenario._analyze_query(query)
        action = analysis.get("action", "unknown")
        category = analysis.get("category")
        product_keyword = analysis.get("product_keyword")
        logger.info("LLM 分析结果 query={} action={} category={} keyword={}", query[:40], action, category, product_keyword)

        service = ConsumablesScenario._get_consumable_service()
        user_profile = state.get("user_profile", {})

        # 分发 action
        if action == "track_order":
            result = await ConsumablesScenario._handle_order_query(user_id)
            state["final_answer"] = result

        elif action == "view_category" and category:
            products = service.get_category_products(category)
            lines = [f"📂 {category} — 以下配件可选：\n"]
            for p in products:
                lines.append(f"  • {p['name']}  ¥{p['price']}")
                lines.append(f"    型号: {p['model']}  {p.get('desc', '')}")
            lines.append("\n回复配件的完整名称帮您下单。")
            state["final_answer"] = "\n".join(lines)

        elif action == "identify_product":
            # 先尝试按关键词精准搜索
            matched = None
            if product_keyword:
                matched = service.search(product_keyword)

            if not matched:
                # 回落：搜索整个 query
                matched = service.search(query)

            if matched:
                product = matched[0]
                device_model = ConsumablesScenario._identify_device(query, user_profile) or "X30 Pro"

                # 从全量产品中找到 part_type key
                consumable_type = None
                for p in service.get_all_products():
                    if p.get("part_key") and p["name"] == product.get("name"):
                        consumable_type = p["part_key"]
                        break

                pending_info = {
                    "device_model": device_model,
                    "consumable_type": consumable_type,
                    "product_name": product["name"],
                    "product_model": product["model"],
                    "price": product["price"],
                }
                state["task_memory"] = {**(state.get("task_memory") or {}), "pending_purchase": pending_info}
                # 存入 messages 确保跨轮持久（MemorySaver 通过 add_messages 保存 messages）
                from langchain_core.messages import SystemMessage
                state["messages"] = list(state.get("messages", [])) + [
                    SystemMessage(id="pending_purchase", content=f"__pending_purchase__:{json.dumps(pending_info)}")
                ]
                state["final_answer"] = (
                    f"📱 设备: {device_model}\n"
                    f"🔧 耗材: {product['name']}\n"
                    f"📦 型号: {product['model']}\n"
                    f"💰 价格: ¥{product['price']}\n"
                    f"📅 建议更换周期: 约{product['life_days']}天\n"
                    f"💡 {product['desc']}\n\n"
                    "🛒 需要帮您下单购买吗？(回复「是」「确认」「下单」或「不用了」)"
                )

        elif action == "browse":
            state["final_answer"] = ConsumablesScenario._build_category_list(service)

        else:
            state["final_answer"] = (
                "抱歉，我不太确定您需要什么耗材。\n"
                "您可以告诉我具体的配件名称（如「边刷」「滤网」），"
                "或者我说当前支持的类别，您选一个看看。\n"
                "回复「看看类别」查看所有可选分类。"
            )

        elapsed = time.time() - start
        logger.info("耗材场景完成 user={} latency={:.1f}s", user_id, elapsed)
        return state

    # ═══════════════════════════════════════
    # 子流程
    # ═══════════════════════════════════════

    @staticmethod
    async def _handle_order_query(user_id: str) -> str:
        """查询用户最新订单物流状态"""
        try:
            from sqlalchemy import select

            from smart_qa.database.engine import get_session_factory
            from smart_qa.models.virtual_order import LogisticsEvent, VirtualOrder

            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(
                    select(VirtualOrder)
                    .where(VirtualOrder.user_id == user_id)
                    .order_by(VirtualOrder.created_at.desc())
                    .limit(1)
                )
                order = result.scalar_one_or_none()
                if order:
                    event_result = await session.execute(
                        select(LogisticsEvent)
                        .where(LogisticsEvent.order_id == order.order_id)
                        .order_by(LogisticsEvent.id.desc())
                        .limit(1)
                    )
                    last_event = event_result.scalar_one_or_none()

                    from smart_qa.models.order_schema import STATUS_LABELS

                    label = STATUS_LABELS.get(order.status, order.status)
                    msg = (
                        f"📋 订单状态查询\n"
                        f"订单号: {order.order_id}\n"
                        f"商品: {order.part_name}\n"
                        f"状态: {label}\n"
                        f"快递: {order.express_company or '待发货'} {order.tracking_number or ''}\n"
                    )
                    if last_event:
                        msg += f"最新: {last_event.message}\n"
                    msg += "\n回复「继续购买」返回耗材选购，或对我说「推进物流」看看下一步。"
                    return msg
                else:
                    return "您目前没有进行中的订单。需要购买耗材吗？告诉我您需要什么配件。"
        except Exception as e:
            logger.warning("订单查询失败: {}", e)
            return "订单查询服务暂时不可用，请稍后再试。"

    @staticmethod
    async def _handle_approval(user_id: str, query: str, pending: dict, state: dict) -> str:
        """处理用户对推荐的确认/拒绝"""
        from smart_qa.deps import get_llm_client

        llm = get_llm_client()
        prompt = (
            f"用户正在确认是否购买「{pending.get('product_name', '')}」（¥{pending.get('price', 0)}）。\n"
            f"用户回复: {query}\n\n"
            "请判断用户意图，仅返回 JSON:\n"
            '{"intent": "confirm" | "reject" | "ambiguous"}\n\n'
            "规则:\n"
            '- "confirm": 用户明确同意购买（是、确认、下单、好的、可以、买）\n'
            '- "reject": 用户明确拒绝（不、不要、不用、算了、取消）\n'
            '- "ambiguous": 不确定或没明确表态'
        )

        try:
            response = await llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            if "```" in content:
                content = content.split("```")[1].replace("json", "", 1).split("```")[0]
            parsed = json.loads(content.strip())
            intent = parsed.get("intent", "ambiguous")
        except Exception:
            q = query.lower().strip()
            confirm = any(kw in q for kw in ["是", "确认", "下单", "买", "要", "好的", "可以", "嗯", "好", "行"])
            reject = any(kw in q for kw in ["不", "不要", "不用", "算了", "取消"])
            intent = "confirm" if confirm and not reject else ("reject" if reject else "ambiguous")

        if intent == "confirm":
            result = await ConsumablesScenario._place_order(user_id, pending, state)
            ConsumablesScenario._cleanup_pending_msg(state)
            return result
        if intent == "reject":
            state["task_memory"] = {
                k: v for k, v in (state.get("task_memory") or {}).items() if k != "pending_purchase"
            }
            ConsumablesScenario._cleanup_pending_msg(state)
            return "好的，已取消订单。如果您以后需要，随时告诉我。"
        return f"您想购买「{pending.get('product_name', '')}」吗？\n回复「确认」下单，或「不用了」取消。"

    @staticmethod
    async def _place_order(user_id: str, pending: dict, state: dict) -> str:
        """创建虚拟订单并自动模拟物流"""
        product_name = pending.get("product_name", "")
        price = pending.get("price", 0)
        consumable_type = pending.get("consumable_type", "")

        try:
            from smart_qa.database.engine import get_session_factory
            from smart_qa.services.order_simulation import OrderSimulationService

            factory = get_session_factory()
            async with factory() as session:
                order = await OrderSimulationService.create_order(
                    db=session,
                    user_id=user_id,
                    part_type=consumable_type,
                    part_name=product_name,
                    price=price,
                )
                order = await OrderSimulationService.confirm_order(session, order)

                scenarios = ["normal"] * 80 + ["damaged"] * 8 + ["lost"] * 5 + ["out_of_stock"] * 2 + ["returned"] * 5
                scenario = random.choice(scenarios)

                order = await OrderSimulationService.start_shipping(session, order, scenario)
                for _ in range(3):
                    order, _event = await OrderSimulationService.advance_logistics(session, order, scenario)
                await session.commit()

            state["task_memory"] = {
                k: v for k, v in (state.get("task_memory") or {}).items() if k != "pending_purchase"
            }
            return (
                f"✅ 订单已创建！\n"
                f"📦 {product_name} × 1\n"
                f"💰 ¥{price}\n"
                f"📋 订单号: {order.order_id}\n"
                f"📮 快递: {order.express_company} ({order.tracking_number})\n\n"
                f"您可以随时对我说「查订单」或「物流状态」来跟踪最新进度。"
            )
        except Exception as e:
            logger.error("订单创建失败: {}", e)
            return "抱歉，下单时遇到了问题，请稍后重试或前往 App 商城购买。"

    # ═══════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════

    @staticmethod
    def _build_category_list(service: ConsumableService) -> str:
        """生成类别列表回复"""
        cats = service.get_all_categories()
        return "X30 Pro 目前支持以下耗材类别，请问您需要哪种？\n" + "\n".join(f"  • {c}" for c in cats)

    @staticmethod
    def _identify_device(query: str, user_profile: dict | None = None) -> str | None:
        """从查询或画像中提取设备型号"""
        import re

        normalized = re.sub(r"(?i)x30[\s-]*pro", "X30 Pro", query)
        for model in ["X30 Pro", "X30", "X20 Pro", "T10", "R10", "R20"]:
            if model.lower() in normalized.lower():
                return model
        if user_profile:
            return user_profile.get("device_model")
        return None

    @staticmethod
    def _cleanup_pending_msg(state: dict):
        """清理已消费的 pending_purchase SystemMessage"""
        from langchain_core.messages import RemoveMessage, SystemMessage

        for m in list(state.get("messages", [])):
            if isinstance(m, SystemMessage) and getattr(m, "content", "").startswith("__pending_purchase__:"):
                msg_list = list(state.get("messages", []))
                msg_list.append(RemoveMessage(id="pending_purchase"))
                state["messages"] = msg_list
                break

    @classmethod
    def reset(cls):
        cls._consumable_service = None

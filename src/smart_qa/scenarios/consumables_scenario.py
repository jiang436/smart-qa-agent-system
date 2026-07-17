"""耗材管理场景 — ReAct Agent (LLM + Tools 自主决策)

不再使用 JSON 解析 + if/elif 状态机。
LLM 在 ReAct 循环中自主决定调用哪些工具、以什么顺序、输出什么回答。

流程示例:
  "购买耗材" → LLM 调用 list_categories() → 展示类别
  "集尘过滤" → LLM 调用 get_products("集尘过滤") → 展示产品
  "两个都要，每种买3个" → LLM 调用 add_to_cart() ×2 → 展示购物车
  "确认" → LLM 调用 confirm_purchase() → 创建订单
  "查订单" → LLM 调用 track_order() → 展示物流

购物车存在模块级 dict 中，key=session_id，重启丢失（可接受，验证场景）。
"""

from __future__ import annotations

import random
import time

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger
from smart_qa.services.consumable_service import ConsumableService

# ── 数据服务 ──

_service = ConsumableService()

# ── 购物车（模块级，key=session_id，重启丢失）──

_carts: dict[str, list[dict]] = {}


# ═══════════════════════════════════════
# ReAct Tools
# ═══════════════════════════════════════


@tool
async def list_categories() -> str:
    """获取所有耗材类别的名称列表。用户说"看看""有什么""买耗材"时调用。"""
    cats = _service.get_all_categories()
    return "当前支持的耗材类别:\n" + "\n".join(f"  • {c}" for c in cats)


@tool
async def get_products(category: str) -> str:
    """获取指定类别下的所有产品详情（名称、型号、价格、描述）。

    Args:
        category: 类别名称，必须与 list_categories() 返回的名称完全一致
    """
    products = _service.get_category_products(category)
    if not products:
        return f"未找到「{category}」类别"
    lines = [f"📂 {category} — 以下配件可选："]
    for p in products:
        life = f"，{p['life_days']}天更换周期" if p.get("life_days") else ""
        lines.append(f"\n  • {p['name']}  ¥{p['price']}")
        lines.append(f"    型号: {p['model']}  {p.get('desc', '')}{life}")
    return "\n".join(lines)


@tool
async def search_product(keyword: str) -> str:
    """在产品库中搜索匹配的产品（按名称、型号、描述）。

    Args:
        keyword: 搜索关键词，如"边刷""滤网""集尘袋"
    """
    results = _service.search(keyword)
    if not results:
        return f"未找到与「{keyword}」匹配的产品"
    lines = [f"找到 {len(results)} 个匹配产品："]
    for p in results:
        lines.append(f"  • {p['name']}  ¥{p['price']}  {p.get('desc', '')}")
    return "\n".join(lines)


@tool
async def add_to_cart(session_id: str, product_name: str, quantity: int = 1) -> str:
    """将指定产品加入购物车。

    用户说"买这个""两个都要""每种买N个"时调用。
    "两个都要"需要为该类别下的每个产品分别调用一次。

    Args:
        session_id: 会话 ID（从系统提示中获取）
        product_name: 产品完整名称（必须与 get_products 返回的 name 完全一致）
        quantity: 购买数量，默认为 1
    """
    all_products = _service.get_all_products()
    product = next((p for p in all_products if p["name"] == product_name), None)
    if not product:
        return f"未找到产品「{product_name}」。请先用 get_products 或 search_product 确认产品名称。"

    if session_id not in _carts:
        _carts[session_id] = []

    _carts[session_id].append(
        {
            "name": product["name"],
            "model": product["model"],
            "price": product["price"],
            "quantity": quantity,
        }
    )
    subtotal = product["price"] * quantity
    return f"✅ 已加入购物车: {product_name} ×{quantity}  ¥{subtotal}"


@tool
async def show_cart(session_id: str) -> str:
    """查看当前购物车中的所有商品和总价。

    Args:
        session_id: 会话 ID（从系统提示中获取）
    """
    items = _carts.get(session_id, [])
    if not items:
        return "🛒 购物车是空的"
    lines = ["🛒 购物车内容："]
    total = 0.0
    for item in items:
        subtotal = item["price"] * item["quantity"]
        total += subtotal
        lines.append(f"  • {item['name']} ×{item['quantity']}  ¥{subtotal:.1f}")
    lines.append(f"\n💰 合计: ¥{total:.1f}")
    lines.append("\n回复「确认」下单，或「不用了」取消。")
    return "\n".join(lines)


@tool
async def clear_cart(session_id: str) -> str:
    """清空购物车。用户取消购买或说"不要了"时调用。

    Args:
        session_id: 会话 ID（从系统提示中获取）
    """
    _carts[session_id] = []
    return "🛒 购物车已清空"


@tool
async def confirm_purchase(session_id: str, user_id: str) -> str:
    """确认购买购物车中所有商品，创建订单并模拟物流。

    用户明确说"确认""下单""好的"时调用。
    调用前先用 show_cart 展示购物车内容给用户确认。

    Args:
        session_id: 会话 ID
        user_id: 用户 ID（从系统提示中获取）
    """
    items = _carts.get(session_id, [])
    if not items:
        return "购物车是空的，没有可下单的商品。"
    try:
        from smart_qa.database.engine import get_session_factory
        from smart_qa.services.order_simulation import OrderSimulationService

        factory = get_session_factory()
        async with factory() as session:
            total_price = 0.0
            item_names = []
            for item in items:
                subtotal = item["price"] * item["quantity"]
                total_price += subtotal
                item_names.append(f"{item['name']}×{item['quantity']}")

            # 合并所有商品为一个订单
            combined_name = "、".join(item_names)
            order = await OrderSimulationService.create_order(
                db=session,
                user_id=user_id,
                part_type="consumable",
                part_name=combined_name,
                price=total_price,
            )
            order = await OrderSimulationService.confirm_order(session, order)

            scenarios = ["normal"] * 80 + ["damaged"] * 8 + ["lost"] * 5 + ["out_of_stock"] * 2 + ["returned"] * 5
            scenario = random.choice(scenarios)
            order = await OrderSimulationService.start_shipping(session, order, scenario)
            for _ in range(3):
                order, _event = await OrderSimulationService.advance_logistics(session, order, scenario)
            await session.commit()

        _carts[session_id] = []

        lines = [
            "🎉 **订单已成功提交！**\n",
            "| 项目 | 内容 |",
            "|-----|------|",
            f"| 📋 **订单号** | {order.order_id} |",
            f"| 📦 **商品** | {combined_name} |",
            f"| 💰 **合计** | **¥{total_price:.0f}** |",
            f"| 🚚 **快递** | {order.express_company} ({order.tracking_number}) |",
            "",
            "您可以随时对我说 **「查订单」** 查看物流状态～😊",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error("订单创建失败: {}", e)
        return "抱歉，下单时遇到了问题，请稍后重试。"


async def _track_order_impl(user_id: str) -> str:
    """查询用户最新订单的物流状态（直接调用的实现）"""
    try:
        from sqlalchemy import select

        from smart_qa.database.engine import get_session_factory
        from smart_qa.models.order_schema import STATUS_LABELS
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
            if not order:
                return "您目前没有进行中的订单。需要购买耗材吗？"

            event_result = await session.execute(
                select(LogisticsEvent)
                .where(LogisticsEvent.order_id == order.order_id)
                .order_by(LogisticsEvent.id.desc())
                .limit(1)
            )
            last_event = event_result.scalar_one_or_none()

            label = STATUS_LABELS.get(order.status, order.status)
            msg = (
                f"📋 订单状态\n"
                f"订单号: {order.order_id}\n"
                f"商品: {order.part_name}\n"
                f"状态: {label}\n"
                f"快递: {order.express_company or '待发货'} {order.tracking_number or ''}"
            )
            if last_event:
                msg += f"\n最新动态: {last_event.message}"
            return msg
    except Exception as e:
        logger.warning("订单查询失败: {}", e)
        return "订单查询服务暂时不可用。"


async def _list_orders_impl(user_id: str, status_filter: list[str] | None = None) -> str:
    """列出用户所有订单，可选按状态过滤"""
    try:
        from sqlalchemy import select

        from smart_qa.database.engine import get_session_factory
        from smart_qa.models.order_schema import STATUS_LABELS
        from smart_qa.models.virtual_order import VirtualOrder

        factory = get_session_factory()
        async with factory() as session:
            query = select(VirtualOrder).where(VirtualOrder.user_id == user_id)
            if status_filter:
                query = query.where(VirtualOrder.status.in_(status_filter))
            query = query.order_by(VirtualOrder.created_at.desc())

            result = await session.execute(query)
            orders = result.scalars().all()
            if not orders:
                if status_filter:
                    return "没有符合条件的订单。"
                return "您目前没有订单记录。"

            lines = [f"📋 共 {len(orders)} 笔订单：\n"]
            for o in orders:
                label = STATUS_LABELS.get(o.status, o.status)
                lines.append(f"  • {o.order_id[:12]}  {o.part_name}  ¥{o.price}  [{label}]")
            lines.append("\n回复订单号可查看详情，或说「查订单」看最新物流。")
            return "\n".join(lines)
    except Exception as e:
        logger.warning("订单列表查询失败: {}", e)
        return "订单查询服务暂时不可用。"


@tool
async def track_order(user_id: str) -> str:
    """查询用户最新订单的物流状态。

    用户说"查订单""物流""到哪了"时调用。

    Args:
        user_id: 用户 ID（从系统提示中获取）
    """
    return await _track_order_impl(user_id)


# ═══════════════════════════════════════
# Tools 列表
# ═══════════════════════════════════════

_TOOLS = [
    list_categories,
    get_products,
    search_product,
    add_to_cart,
    show_cart,
    confirm_purchase,
    clear_cart,
    track_order,
]

_AGENT_PROMPT = """你是一个智能家居耗材管理助手，专门帮助用户购买和查询扫地机器人配件。

当前用户: {user_id}
当前会话: {session_id}

## 可用工具

1. 浏览搜索: list_categories(), get_products(category), search_product(keyword)
2. 购物车:   add_to_cart(session_id, product_name, quantity), show_cart(session_id), clear_cart(session_id)
3. 下单:     confirm_purchase(session_id, user_id)
4. 查询:     track_order(user_id)

## 工作流程

- 用户说"买耗材""看看"→ list_categories()
- 用户选了某个类别 → get_products(category)
- 用户指定产品 → add_to_cart()，注意理解自然语言数量
- 用户说"两个都要""全部都要" → 遍历该类别的产品，各调用一次 add_to_cart()
- 用户确认下单 → 先用 show_cart() 给用户确认，然后等用户说"确认"再调用 confirm_purchase()
- 用户取消 → clear_cart()
- 用户查订单/物流 → track_order()

## 注意事项

- session_id 和 user_id 必须从系统提示中获取，不要问用户
- 每次调用 add_to_cart() 只加一个产品
- 如果用户说"每种买N个"，quantity 参数设为 N
- 工具返回的文本就是回复内容，直接输出即可
- 如果用户的问题与耗材完全无关，礼貌拒绝并引导回耗材话题
"""


def _build_agent_prompt(state: dict) -> str:
    """构建 ReAct Agent 系统提示"""
    return _AGENT_PROMPT.format(
        user_id=state.get("user_id", "anonymous"),
        session_id=state.get("session_id", "default"),
    )


# ═══════════════════════════════════════
# 场景入口（替换旧 run()）
# ═══════════════════════════════════════


class ConsumablesScenario:
    """耗材管理场景 — ReAct Agent (LLM + Tools)"""

    _consumable_service: ConsumableService | None = None

    @classmethod
    def _get_consumable_service(cls) -> ConsumableService:
        if cls._consumable_service is None:
            cls._consumable_service = ConsumableService()
        return cls._consumable_service

    @staticmethod
    async def run(state: dict) -> dict:
        """执行耗材管理场景（ReAct Agent 自主决策）"""
        start = time.time()
        query = extract_user_query(state)
        user_id = state.get("user_id", "anonymous")
        logger.info("耗材 Agent 开始 user={} query={}", user_id, query[:60])

        if not query:
            state["final_answer"] = "请问您需要什么耗材？"
            return state

        # 订单查询直接拦截（不浪费 LLM 决策）
        ORDER_TRACKING = ["订单", "物流", "到哪了", "快递", "运单", "跟踪", "签收", "包裹", "收货", "没收到"]
        if any(kw in query for kw in ORDER_TRACKING):
            # 状态过滤检测
            status_filter = None
            NOT_RECEIVED = ["没收货", "未收货", "进行中", "在途", "在路上", "没到", "待收货", "未签收"]
            RECEIVED = ["已签收", "已收到", "已完成", "到了", "签收"]
            if any(kw in query for kw in NOT_RECEIVED):
                status_filter = ["shipped", "in_transit", "processing"]
            elif any(kw in query for kw in RECEIVED):
                status_filter = ["delivered", "signed"]

            # 列表 vs 单条
            LIST_KEYS = ["其他", "所有", "全部", "有哪些", "列表", "历史", "记录", "还有", "几个", "没收货", "未收货"]
            if any(kw in query for kw in LIST_KEYS):
                state["final_answer"] = await _list_orders_impl(user_id, status_filter)
            else:
                state["final_answer"] = await _track_order_impl(user_id)
            return state

        # 获取 LLM
        from smart_qa.deps import get_llm_client

        llm = get_llm_client()

        # TESTING 模式：MockLLM 不支持 bind_tools，直接返回简单回复
        import os as _os

        if _os.environ.get("TESTING") == "true":
            state["final_answer"] = "测试模式：已进入耗材选购流程，请继续提问。"
            return state

        system_prompt = _build_agent_prompt(state)

        # 构建 ReAct Agent
        agent = create_react_agent(
            model=llm,
            tools=_TOOLS,
            prompt=system_prompt,
        )

        # 传入当前对话消息（含历史），让 LLM 理解上下文
        messages = list(state.get("messages", []))

        try:
            result = await agent.ainvoke({"messages": messages})
            final = result["messages"][-1]
            state["final_answer"] = final.content if hasattr(final, "content") else str(final)
        except Exception as e:
            logger.error("耗材 Agent 异常: {}", e)
            state["final_answer"] = "抱歉，处理您的请求时出现了问题，请稍后重试。"

        elapsed = time.time() - start
        logger.info("耗材 Agent 完成 user={} latency={:.1f}s", user_id, elapsed)
        return state

    # ── 保留的工具方法（供 router 场景连续性使用）──

    @staticmethod
    def _build_history_context(state: dict) -> str:
        """从 messages 提取最近 2 轮对话历史"""
        messages = state.get("messages", [])
        recent = []
        for m in messages[-6:]:
            role = ""
            content = ""
            if hasattr(m, "content"):
                role = getattr(m, "type", "") or (m.get("role", "") if isinstance(m, dict) else "")
                content = m.content[:120] if m.content else ""
            elif isinstance(m, dict):
                role = m.get("role", "")
                content = str(m.get("content", ""))[:120]
            if role in ("human", "user"):
                recent.append(f"用户: {content}")
            elif role in ("ai", "assistant"):
                recent.append(f"助手: {content}")
        return "\n".join(recent[-4:]) if recent else ""

    @staticmethod
    def _save_scenario_context(state: dict, ctx: dict):
        """保存场景上下文到 task_memory"""
        ctx["scenario"] = "consumables"
        state["task_memory"] = {**(state.get("task_memory") or {}), "scenario_context": ctx}

    @classmethod
    def reset(cls):
        cls._consumable_service = None
        _carts.clear()

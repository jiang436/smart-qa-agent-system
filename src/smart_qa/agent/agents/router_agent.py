"""Router Agent — 意图分类 + 场景路由

使用 LLM 对用户输入进行快速意图分类，将用户分发到对应的业务场景。

分类标准:
  - qa:           知识问答（产品手册、使用方法、参数规格相关）
  - troubleshoot: 故障排查（设备异常、错误码、不工作相关）
  - consumables:  耗材管理（边刷/滤网/耗材更换、购买推荐）
  - general:      闲聊/问候/无关内容

工作流程:
  1. 提取用户最新一条消息
  2. 加载 CoT 路由提示模板
  3. 调用 LLM 分类意图
  4. 写入 state.intent
  5. dispatch 根据意图分发到对应场景
"""

from typing import Literal

from smart_qa.agent.prompts.loader import load_cot_prompt
from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger


class RouterAgent:
    """Router Agent: 意图分类器

    用法:
        state = await RouterAgent.route(state)
        next_node = RouterAgent.dispatch(state)
    """

    # 意图关键词映射（无 LLM 时的降级方案）
    INTENT_KEYWORDS = {
        "device_control": [
            "开始清扫",
            "开始打扫",
            "停止清扫",
            "停止打扫",
            "暂停",
            "充电",
            "回充",
            "回去充电",
            "设备状态",
            "状态",
            "模式",
            "安静模式",
            "强力模式",
            "定时清扫",
            "定时",
            "预约清扫",
        ],
        "report": [
            "报告",
            "统计",
            "使用情况",
            "使用数据",
            "清洁记录",
            "月度报告",
            "使用分析",
            "看看数据",
            "生成",
            "周报",
            "月报",
            "报表",
        ],
        "qa": [
            "怎么",
            "如何",
            "什么",
            "为什么",
            "能不能",
            "支持",
            "设置",
            "连接",
            "说明书",
            "参数",
            "规格",
            "功能",
            "使用",
            "定时",
            "清扫模式",
            "地图",
            "电压",
            "噪音",
            "尘盒",
        ],
        "troubleshoot": [
            "不工作",
            "坏了",
            "故障",
            "错误",
            "异常",
            "不动",
            "不转",
            "没反应",
            "无法",
            "不了",
            "连不上",
            "掉线",
            "开不了机",
            "E0",
            "E1",
            "错误码",
            "一直响",
            "指示灯",
            "卡住",
        ],
        "consumables": [
            "换",
            "买",
            "购",
            "耗材",
            "边刷",
            "滤网",
            "主刷",
            "拖布",
            "配件",
            "多少钱",
            "价格",
            "哪里买",
            "原装",
            "第三方",
            "套装",
        ],
    }

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 客户端（用于意图分类），不传则使用关键词匹配
        """
        self.llm = llm_client
        self._cot_prompt = None

    def _get_cot_prompt(self) -> str:
        """获取 CoT 路由提示模板（缓存）"""
        if self._cot_prompt is None:
            try:
                self._cot_prompt = load_cot_prompt("router")
            except FileNotFoundError:
                self._cot_prompt = ""
        return self._cot_prompt

    # ── FAQ 高置信度阈值（LCS ≥ 此值才使用 FAQ 预写答案）──
    FAQ_HIGH_CONFIDENCE = 0.95  # 95% 相似度才使用FAQ预写答案

    async def route(self, state: dict) -> dict:
        """路由节点：关键词优先筛选，LLM 语义兜底

        三层过滤 + 一层 LLM 分流：

        ┌─ Layer 1: 关键词快筛（<1ms）
        │   ├── is_pure_greeting()     → 问候/寒暄 → 直接回复，不走 LLM
        │   ├── is_out_of_scope()      → 明显越界   → 拒绝话术，不走 LLM
        │   ├── hard_faq               → 你是谁/能干什么 → 硬编码回复
        │   ├── 多轮诊断上下文          → 诊断进行中 → 复用上次意图
        │   ├── pending_purchase       → HITL 待确认 → 强制走耗材场景
        │   └── 多问题检测              → 一次只能问一个
        │
        ├─ Layer 2: LLM 语义分类（~1s）
        │   ├── qa / general        → FAQ 高置信匹配 or RAG
        │   ├── troubleshoot        → 故障排查决策树
        │   ├── consumables         → 耗材推荐 / HITL
        │   ├── device_control      → 设备控制指令
        │   └── report              → 报告生成
        │
        └─ Layer 3: 场景内二次兜底（LLM ~1s）
            └── general 场景的 handle_general()
                  ├── is_pure_greeting()     关键词再次兜底
                  ├── is_out_of_scope()      关键词再次兜底
                  └── LLM 生成回复            prompt: "无关内容用拒绝话术"

        设计原则：
            80% 的常见越界/问候用关键词在 <1ms 内拦截，
            剩下 20% 的边缘情况由 LLM 语义理解处理。
            关键词快且便宜在前，LLM 灵活但慢在后兜底。
        """
        from smart_qa.agent.persona import OUT_OF_SCOPE_REJECTION, get_greeting_reply, is_out_of_scope, is_pure_greeting

        # 1. 提取用户最新消息，清除上轮残留
        state.pop("final_answer", None)
        state.pop("intent", None)
        query = self._extract_query(state)
        if not query:
            state["intent"] = "general"
            return state

        # ── 第一层：礼貌寒暄 ──
        greeting_type = is_pure_greeting(query)
        if greeting_type is not None:
            state["final_answer"] = get_greeting_reply(greeting_type)
            state["intent"] = "general"
            return state

        # ── 第三层：超出职责范围 ──
        if is_out_of_scope(query):
            state["final_answer"] = OUT_OF_SCOPE_REJECTION
            state["intent"] = "general"
            return state

        # ── 硬编码 FAQ（你是谁/能干什么，<1ms）──
        hard_faq = {
            "你是谁": "我是小智，智能家居客服助手，专门解答扫地机器人问题。有什么可以帮您的？",
            "能干什么": "我可以帮您解答扫地机器人的使用问题、排查故障、推荐耗材配件。请尽管问！",
            "叫什么": "我叫小智，您的智能家居客服助手。",
        }
        for k, v in hard_faq.items():
            if k in query:
                state["final_answer"] = v
                state["intent"] = "general"
                return state

        # ── 进行中的多轮诊断 → 先判断是否在回答排查问题 ──
        task = state.get("task_memory") or {}
        if task.get("diagnosis_stage") == "diagnosis":
            is_short_answer = len(query) <= 10 or any(
                query.startswith(kw) for kw in ["是", "对", "有", "嗯", "不", "没", "亮", "能", "可以"]
            )
            if is_short_answer:
                state["intent"] = "troubleshoot"
                return state
            if self.llm:
                is_answer = await self._is_diagnosis_answer(query, state)
                if is_answer:
                    state["intent"] = "troubleshoot"
                    return state
            state["task_memory"] = {}
            logger.info("诊断中用户切换话题 query={}", query[:60])
        if task.get("pending_purchase"):
            state["intent"] = "consumables"
            return state

        # ── 多问题检测 ──
        import re

        questions = re.findall(r"[？?]", query)
        lines = [line.strip() for line in query.split("\n") if line.strip() and re.search(r"[？?。]$", line.strip())]
        if len(questions) > 1 or len(lines) > 1:
            state["final_answer"] = "我一次只能处理一个问题，请逐个提问。"
            state["intent"] = "general"
            return state

        # ═══════════════════════════════════════
        # ★ LLM 意图分类（带上下文，理解指代）
        # ═══════════════════════════════════════
        intent = None
        if "intent" in state and state["intent"] in ("qa", "consumables", "general"):
            intent = state.pop("intent")
        else:
            history_context = self._build_history_context(state)
            from smart_qa.observability.tracer import get_tracer

            tracer = get_tracer()
            with tracer.start_span("router.classify", attributes={"query": query[:100]}):
                intent = await self._classify_intent(query, history_context)

            source = "LLM" if self.llm else "关键词"
            logger.info("意图分类({}) intent={} query={}", source, intent, query[:80])

        # ═══════════════════════════════════════
        # ★ 根据意图分流
        # ═══════════════════════════════════════

        if intent in ("qa", "general"):
            from smart_qa.knowledge.faq_matcher import get_faq_matcher

            faq_answer = get_faq_matcher().match(query, threshold=self.FAQ_HIGH_CONFIDENCE)
            if faq_answer:
                logger.info("FAQ高置信命中 intent={}", intent)
                state["final_answer"] = faq_answer
            state["intent"] = "qa"
            return state

        state["intent"] = intent
        state["scenario"] = intent
        return state

    @staticmethod
    def dispatch(
        state: dict,
    ) -> Literal["qa", "troubleshoot", "consumables", "device_control", "report", "general", "done"]:
        """根据意图分发到对应场景

        FAQ 命中（final_answer 已设）→ "done"，直接返回，跳过 RAG
        """
        # FAQ 已命中，不跑 RAG
        if state.get("final_answer") and state.get("intent") == "qa":
            return "done"

        intent = state.get("intent", "general")
        valid_intents = ["qa", "troubleshoot", "consumables", "report", "device_control", "general"]
        if intent not in valid_intents:
            intent = "general"
        return intent

    def _extract_query(self, state: dict) -> str:
        return extract_user_query(state)

    def _build_history_context(self, state: dict) -> str:
        """拼接最近对话历史，让 LLM 理解指代（"那主刷呢" → 上文在聊耗材）"""
        messages = state.get("messages", [])
        if len(messages) <= 1:
            return ""
        recent = []
        for m in messages[-4:]:  # 最近 4 条（2 轮对话）
            if hasattr(m, "content"):
                role = getattr(m, "type", "") or (m.get("role", "") if isinstance(m, dict) else "")
                content = m.content if hasattr(m, "content") else m.get("content", "")
                if role in ("human", "user"):
                    recent.append(f"用户: {content[:100]}")
                elif role in ("ai", "assistant"):
                    recent.append(f"助手: {content[:100]}")
        return "\n".join(recent) if recent else ""

    async def _is_diagnosis_answer(self, query: str, state: dict) -> bool:
        """判断用户消息是否在回答当前排查问题（而非提出新问题）

        用 LLM 精确判断，因为通用意图分类在诊断上下文中容易把"深度清洁模式怎么开"
        也判成 troubleshoot。
        """
        task = state.get("task_memory") or {}
        fault_type = task.get("fault_type", "")
        current_step = task.get("current_step", 0)
        tree = None
        if fault_type:
            from smart_qa.scenarios.troubleshoot_scenario import DIAGNOSIS_TREE

            tree = DIAGNOSIS_TREE.get(fault_type)
        current_question = ""
        if tree and current_step < len(tree.get("steps", [])):
            current_question = tree["steps"][current_step].get("question", "")

        prompt = (
            "你正在通过多轮对话帮用户排查故障。上一轮你问了用户一个问题。\n"
            "请判断用户的这条消息是在回答你的问题，还是提出了一个全新的问题/话题。\n\n"
            f"上一轮你问的问题：{current_question}\n"
            f"用户刚才说：{query}\n\n"
            "只输出一个词：answer（在回答排查问题）或 new（新话题）"
        )
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            return "answer" in content.lower() and "new" not in content.lower()
        except Exception:
            return True  # LLM 不可用时保守处理：认为是在回答

    async def _classify_intent(self, query: str, history: str = "") -> str:
        """意图分类: LLM 优先（语义理解），关键词兜底（无 LLM 时）"""
        if self.llm:
            result = await self._llm_classify(query, history)
            if result != "general":
                return result
        return self._keyword_classify(query)

    async def _llm_classify(self, query: str, history: str = "") -> str:
        """LLM 意图分类 — 带对话历史，理解指代"""
        from smart_qa.agent.prompts.loader import load_cot_prompt

        cot = load_cot_prompt("router")
        history_block = f"对话历史:\n{history}\n\n" if history else ""
        prompt = f"判断意图(qa/troubleshoot/consumables/report/device_control/general):\n{cot}\n\n{history_block}用户: {query}\n意图:"
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            for i in ["qa", "troubleshoot", "consumables", "report", "device_control", "general"]:
                if i in content.lower():
                    return i
        except Exception:
            pass
        return "general"

    def _keyword_classify(self, query: str) -> str:
        """基于关键词的意图分类（无 LLM 时的降级方案）"""
        scores = {"qa": 0, "troubleshoot": 0, "consumables": 0, "report": 0, "device_control": 0}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in query:
                    scores[intent] += 1

        import re

        if re.search(r"[Ee]\d{2,3}", query):
            scores["troubleshoot"] += 3

        max_score = max(scores.values())
        if max_score >= 1:
            for intent, score in scores.items():
                if score == max_score:
                    return intent

        return "general"

    # -- 便捷方法: 独立使用 --

    def classify(self, query: str) -> str:
        """同步分类方法（使用关键词匹配）"""
        return self._keyword_classify(query)

"""Router Agent — 意图分类 + 场景路由

使用 LLM 对用户输入进行快速意图分类，将用户分发到对应的业务场景。
关键词映射优先从 data/router_keywords.json 加载，回退到内置默认。
"""

import json
import os
from typing import Literal

from smart_qa.agent.state_utils import extract_user_query
from smart_qa.observability.logger import logger


def _load_intent_keywords() -> dict[str, list[str]]:
    """加载意图关键词映射（外部 JSON 优先，内置兜底）"""
    json_path = "data/router_keywords.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return _BUILTIN_INTENT_KEYWORDS


# ── 内置默认关键词映射（外部 JSON 不可用时的兜底）──
_BUILTIN_INTENT_KEYWORDS: dict[str, list[str]] = {
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
            "小米",
            "米家",
            "石头",
            "追觅",
            "科沃斯",
            "云鲸",
            "iRobot",
            "推荐",
            "哪个好",
            "区别",
            "对比",
            "性价比",
            "值得",
            "入门",
            "旗舰",
            "选购",
            "哪款",
            "哪一款",
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
    }

# ── 模块级加载（外部 JSON 优先，内置兜底）──
INTENT_KEYWORDS = _load_intent_keywords()


class RouterAgent:
    """Router Agent: 意图分类器

    用法:
        state = await RouterAgent.route(state)
        next_node = RouterAgent.dispatch(state)
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 客户端（用于意图分类），不传则使用关键词匹配
        """
        self.llm = llm_client
        self._intent_keywords = INTENT_KEYWORDS

    async def route(self, state: dict) -> dict:
        """意图分类节点 — pipeline: 预处理 → 快检 → 状态 → 分类 → 分流"""
        state.pop("final_answer", None)
        state.pop("intent", None)
        query = self._extract_query(state)
        if not query:
            state["intent"] = "general"
            return state

        # ── Pipeline Stage 1: 快速预检 ──
        skip = self._pre_check(query, state)
        if skip is not None:
            return skip

        # ── Pipeline Stage 2: 多轮状态感知 ──
        skip = await self._check_diagnosis_state(query, state)
        if skip is not None:
            return skip

        # ── Pipeline Stage 3: 多问题检测 ──
        if self._is_multi_question(query):
            state["final_answer"] = "我一次只能处理一个问题，请逐个提问。"
            state["intent"] = "general"
            return state

        # ── Pipeline Stage 4: LLM 意图分类 ──
        intent = await self._classify_with_trace(query, state)

        # ── Pipeline Stage 5: 意图分流 ──
        return self._dispatch_by_intent(query, intent, state)

    # ── Pipeline Stage 1: 快速预检 ──

    def _pre_check(self, query: str, state: dict) -> dict | None:
        """快速预检：寒暄 + 越界 + 硬编码 FAQ，<1ms"""
        from smart_qa.agent.persona import OUT_OF_SCOPE_REJECTION, get_greeting_reply, is_out_of_scope, is_pure_greeting

        greeting_type = is_pure_greeting(query)
        if greeting_type is not None:
            state["final_answer"] = get_greeting_reply(greeting_type)
            state["intent"] = "general"
            return state

        if is_out_of_scope(query):
            state["final_answer"] = OUT_OF_SCOPE_REJECTION
            state["intent"] = "general"
            return state

        return None

    # ── Pipeline Stage 2: 多轮状态感知 ──

    async def _check_diagnosis_state(self, query: str, state: dict) -> dict | None:
        """判断是否处于多轮诊断中"""
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

        return None

    # ── Pipeline Stage 3: 多问题检测 ──

    @staticmethod
    def _is_multi_question(query: str) -> bool:
        import re

        questions = re.findall(r"[？?]", query)
        lines = [ln.strip() for ln in query.split("\n") if ln.strip() and re.search(r"[？?。]$", ln.strip())]
        return len(questions) > 1 or len(lines) > 1

    # ── Pipeline Stage 4: LLM 分类 ──

    async def _classify_with_trace(self, query: str, state: dict) -> str:
        """LLM 意图分类（带对话历史）"""
        # 诊断切换话题时可能已预分类，直接复用
        cached = state.pop("intent", None)
        if cached in ("qa", "troubleshoot", "general"):
            return cached

        history = self._build_history_context(state)
        intent = await self._classify_intent(query, history)
        logger.info("LLM意图分类 intent={} query={}", intent, query[:80])
        return intent

    # ── Pipeline Stage 5: 意图分流 ──

    def _dispatch_by_intent(self, query: str, intent: str, state: dict) -> dict:
        """根据意图分流到对应场景"""
        if intent in ("qa", "general"):
            state["intent"] = "qa"
            return state

        if intent == "troubleshoot":
            state["intent"] = intent
            state["scenario"] = intent
            return state

        # 其他未知意图 → 兜底 qa
        state["intent"] = "qa"
        return state

    @staticmethod
    def dispatch(
        state: dict,
    ) -> Literal["qa", "troubleshoot", "general", "done"]:
        """根据意图分发到对应场景

        FAQ 命中（final_answer 已设）→ "done"，直接返回，跳过 RAG
        """
        # FAQ 已命中，不跑 RAG
        if state.get("final_answer") and state.get("intent") == "qa":
            return "done"

        intent = state.get("intent", "general")
        if intent not in ("qa", "troubleshoot", "general"):
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
            try:
                from smart_qa.scenarios.troubleshoot_scenario import DIAGNOSIS_TREE
                tree = DIAGNOSIS_TREE.get(fault_type)
            except ImportError:
                pass
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
        """意图分类: LLM 优先 + 关键词信号纠偏

        策略:
          - LLM 说 general 或失败 → 关键词兜底
          - LLM 与关键词一致 → 采纳
          - LLM 与关键词冲突 → 关键词胜出（规则系统经过人工调优，比 LLM 意图分类更可靠）
        """
        kw_result = self._keyword_classify(query)

        if self.llm:
            llm_result = await self._llm_classify(query, history)
            # LLM 说 general → 关键词兜底
            if llm_result == "general":
                return kw_result
            # LLM 与关键词一致 → 采纳
            if llm_result == kw_result:
                return llm_result
            # LLM 与关键词冲突 → 关键词优先（规则经过人工调优）
            if kw_result != "general":
                logger.info(
                    "关键词覆盖LLM分类 llm={} kw={} query={}",
                    llm_result, kw_result, query[:60]
                )
                return kw_result
            # LLM 有具体意图但关键词无信号 → 采纳 LLM
            return llm_result

        return kw_result

    async def _llm_classify(self, query: str, history: str = "") -> str:
        """LLM 意图分类 — 带对话历史，理解指代"""
        from smart_qa.agent.prompts.loader import load_cot_prompt

        cot = load_cot_prompt("router")
        history_block = f"对话历史:\n{history}\n\n" if history else ""
        prompt = f"判断意图(qa/troubleshoot/general):\n{cot}\n\n{history_block}用户: {query}\n意图:"
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            for i in ["qa", "troubleshoot", "general"]:
                if i in content.lower():
                    return i
        except Exception:
            pass
        return "general"

    def _keyword_classify(self, query: str) -> str:
        """基于加权关键词的意图分类（LLM 不可用时的降级方案）

        改进：
          - 长关键词权重 > 短关键词（"开始清扫" > "清扫"）
          - 错误码 +3 权重（强信号）
          - 多类别冲突时按优先级化解
        """
        scores = {"qa": 0, "troubleshoot": 0, "general": 0}

        for intent, keywords in self._intent_keywords.items():
            for kw in keywords:
                if kw in query:
                    # 长关键词加权: 2字=1分, 3字=1.5分, 4+字=2分
                    weight = 1.0
                    if len(kw) >= 4:
                        weight = 2.0
                    elif len(kw) >= 3:
                        weight = 1.5
                    scores[intent] += weight

        import re

        # 错误码强信号 → troubleshoot +3
        if re.search(r"[Ee]\d{2,3}", query):
            scores["troubleshoot"] += 3

        # ── 冲突化解规则 ──

        # 规则1: "怎么/如何/多久/什么/续航" 等信息询问词 → QA
        qa_inquiry_patterns = ["怎么", "如何", "能不能", "可以", "能", "多久", "续航", "适合"]
        if any(p in query for p in qa_inquiry_patterns):
            if any(c in query for c in ["边刷", "滤网", "主刷", "滚刷", "拖布", "抹布", "HEPA",
                                          "定时", "设置", "连接", "配网", "联网", "绑定",
                                          "清扫", "全屋扫", "扫", "地图", "禁区", "模式", "户型", "面积", "适合"]):
                scores["qa"] += 2.5  # 强推到 qa

        # 规则2: "坏了" + 售后词 → QA（问的是保修/退换，不是故障排查）
        if "坏了" in query:
            warranty_keywords = ["免费", "保修", "售后", "退换", "能换"]
            if any(w in query for w in warranty_keywords) and not re.search(r"[Ee]\d{2,3}", query):
                scores["qa"] += 2.0

        # 规则3: 长叙述 (>20字) + 负面描述 → 大概率 troubleshoot
        if len(query) > 20:
            narrative_signals = ["没电", "不干净", "水渍", "以前", "不如", "总是", "一直", "越来越"]
            if any(s in query for s in narrative_signals):
                scores["troubleshoot"] += 2.0

        # 规则4: "能/可以/支持…控制" → QA（兼容性询问，非控制指令）
        if any(p in query for p in ["能控制", "可以控制", "支持控制", "能用"]):
            scores["qa"] += 3.0

        # 规则4.5: 代词开头的短查询（"它X"/"那X"/"这个"）→ 大概率是追问上文
        pronoun_starts = ["它", "那", "这", "这个", "那个", "这些"]
        if any(query.startswith(p) for p in pronoun_starts) and len(query) <= 10:
            scores["qa"] += 2.0

        # ── 取最高分 ──
        max_score = max(scores.values())
        if max_score >= 1:
            priority_order = ["troubleshoot", "qa", "general"]
            for intent in priority_order:
                if scores[intent] == max_score:
                    return intent

        return "general"

    # -- 便捷方法: 独立使用 --

    def classify(self, query: str) -> str:
        """同步分类方法（使用关键词匹配）"""
        return self._keyword_classify(query)

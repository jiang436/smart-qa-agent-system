"""Persona 逻辑测试 — 寒暄识别 / 越界检测 / System Prompt 生成

覆盖 is_pure_greeting、is_out_of_scope、get_system_prompt 的边界情况
"""
import pytest
from smart_qa.agent.persona import (
    PERSONA,
    WELCOME_MESSAGE,
    OUT_OF_SCOPE_REJECTION,
    GREETING_PATTERNS,
    GREETING_REPLIES,
    COMMON_STYLE,
    SCENARIO_RULES,
    get_greeting_reply,
    get_system_prompt,
    get_polish_prompt,
    is_out_of_scope,
    is_pure_greeting,
)


# ═══════════════════════════════════════
# is_pure_greeting — 寒暄识别
# ═══════════════════════════════════════


class TestPureGreeting:
    """寒暄识别 — 第一层过滤"""

    # ── 问候 ──
    @pytest.mark.parametrize("query", [
        "你好", "您好", "嗨", "哈喽", "hi", "hello", "hey",
        "你好！", "在吗", "在不在", "在不", "在么", "有人在吗",
    ])
    def test_hello_patterns(self, query):
        """各类问候语被识别"""
        result = is_pure_greeting(query)
        assert result is not None
        assert result in ("hello", "default")

    @pytest.mark.parametrize("query", [
        "早上好", "中午好", "下午好", "晚上好", "晚安", "早安",
    ])
    def test_time_greetings(self, query):
        """时段问候"""
        result = is_pure_greeting(query)
        assert result in ("morning", "hello", "default")

    # ── 道别 ──
    @pytest.mark.parametrize("query", [
        "再见", "拜拜", "bye", "回头见", "下次见", "先这样", "好的谢谢", "88", "886",
    ])
    def test_farewell_patterns(self, query):
        """道别语被识别"""
        result = is_pure_greeting(query)
        assert result in ("bye", "thanks", "default")

    # ── 感谢 ──
    @pytest.mark.parametrize("query", [
        "谢谢", "感谢", "多谢", "谢了", "谢谢啦", "谢谢您", "辛苦了", "麻烦你了", "费心了",
    ])
    def test_thanks_patterns(self, query):
        """感谢语被识别"""
        result = is_pure_greeting(query)
        assert result is not None

    # ── 确认 ──
    @pytest.mark.parametrize("query", ["嗯嗯", "好的", "好呢", "ok", "OK", "okay"])
    def test_acknowledgement_patterns(self, query):
        """确认回复被识别"""
        result = is_pure_greeting(query)
        assert result is not None

    # ── 打扰 ──
    @pytest.mark.parametrize("query", ["打扰一下", "打扰了", "请问一下", "问一下", "咨询一下"])
    def test_disturb_patterns(self, query):
        """打扰模式被识别"""
        result = is_pure_greeting(query)
        assert result is not None

    # ── 非寒暄 ──
    @pytest.mark.parametrize("query", [
        "扫地机器人怎么用", "X30 Pro 设置定时", "边刷怎么换",
        "错误码E05", "连不上WiFi了", "帮我推荐一款", "你好请问怎么设置",
    ])
    def test_business_queries_not_greeting(self, query):
        """业务问题不被误判为寒暄"""
        result = is_pure_greeting(query)
        assert result is None

    def test_empty_query(self):
        """空字符串"""
        assert is_pure_greeting("") is None


# ═══════════════════════════════════════
# get_greeting_reply — 友好回复
# ═══════════════════════════════════════


class TestGreetingReply:
    """友好回复生成"""

    def test_each_type_returns_nonempty(self):
        """每种寒暄类型都有对应回复"""
        for gtype in GREETING_REPLIES:
            reply = get_greeting_reply(gtype)
            assert len(reply) > 0

    def test_default_reply_exists(self):
        assert len(get_greeting_reply("unknown_type")) > 0


# ═══════════════════════════════════════
# is_out_of_scope — 越界检测
# ═══════════════════════════════════════


class TestOutOfScope:
    """越界检测 — 第三层过滤"""

    # ── 纯寒暄不被误判越界 ──
    def test_greeting_not_out_of_scope(self):
        assert is_out_of_scope("你好") is False
        assert is_out_of_scope("在吗") is False

    # ── 业务问题不被判越界 ──
    @pytest.mark.parametrize("query", [
        "扫地机器人怎么连WiFi", "X30 Pro 边刷更换周期", "E05错误码怎么解决",
        "滤网多久换一次", "充电座不工作了", "建图失败怎么办",
        "定时清扫怎么设置", "拖布发黄了要不要换",
    ])
    def test_business_queries_in_scope(self, query):
        """扫地机业务问题在职责内"""
        assert is_out_of_scope(query) is False

    # ── 越界问题 ──
    @pytest.mark.parametrize("query", [
        "帮我写一段 Python 代码", "推荐一只股票",
        "合同怎么起草", "帮我写一篇论文",
        "帮我查一下天气预报", "我的手机坏了怎么办",
    ])
    def test_clearly_out_of_scope(self, query):
        """明显越界问题"""
        assert is_out_of_scope(query) is True

    # ── 边界：业务词+越界词混合 ──
    def test_mixed_query_with_business_context(self):
        """包含业务关键词不判越界（如'扫地机器人股票'——虽然奇怪但不应被误判）"""
        # "扫地机器人" 是业务关键词 → 不判越界
        assert is_out_of_scope("扫地机器人的股票怎么样") is False

    def test_vpn_with_business_context(self):
        """敏感词+业务词 → 不判越界"""
        assert is_out_of_scope("扫地机器人的WiFi需要vpn吗") is False

    def test_phone_without_business_context(self):
        """越界设备 + 无业务上下文 → 判越界"""
        assert is_out_of_scope("我的手机屏幕碎了") is True

    def test_empty_query(self):
        assert is_out_of_scope("") is False


# ═══════════════════════════════════════
# get_system_prompt — 场景 Prompt
# ═══════════════════════════════════════


class TestSystemPrompt:
    """各场景 System Prompt 生成"""

    def test_qa_prompt_nonempty(self):
        prompt = get_system_prompt("qa")
        assert len(prompt) > 0
        assert PERSONA["name"] in prompt

    def test_troubleshoot_prompt_nonempty(self):
        prompt = get_system_prompt("troubleshoot")
        assert len(prompt) > 0
        assert "排查" in prompt or "故障" in prompt

    def test_general_prompt_nonempty(self):
        prompt = get_system_prompt("general")
        assert len(prompt) > 0

    def test_unknown_scenario_falls_to_general(self):
        """未知场景回退到 general"""
        prompt = get_system_prompt("nonexistent")
        assert len(prompt) > 0

    def test_all_scenarios_have_common_style(self):
        """所有场景包含通用说话风格"""
        for scenario in ["qa", "troubleshoot", "general"]:
            prompt = get_system_prompt(scenario)
            assert "说话风格" in prompt or "语气" in prompt

    def test_qa_scenario_has_source_rule(self):
        """QA 场景包含来源标注规则"""
        prompt = get_system_prompt("qa")
        assert "[来源]" in prompt or "后台" in prompt.lower()


# ═══════════════════════════════════════
# get_polish_prompt — 润色 Prompt
# ═══════════════════════════════════════


class TestPolishPrompt:
    """回答润色 Prompt"""

    def test_polish_prompt_contains_original(self):
        text = "您的边刷需要更换了。"
        result = get_polish_prompt(text)
        assert text in result

    def test_polish_prompt_has_constraints(self):
        result = get_polish_prompt("test")
        assert "禁止" in result
        assert "润色" in result


# ═══════════════════════════════════════
# 欢迎语和拒绝模板
# ═══════════════════════════════════════


class TestStaticMessages:
    """静态消息模板"""

    def test_welcome_message_nonempty(self):
        assert len(WELCOME_MESSAGE) > 0
        assert PERSONA["name"] in WELCOME_MESSAGE

    def test_out_of_scope_rejection_nonempty(self):
        assert len(OUT_OF_SCOPE_REJECTION) > 0

    def test_greeting_patterns_compiled(self):
        """所有寒暄正则模式可编译"""
        import re
        for pattern in GREETING_PATTERNS:
            re.compile(pattern)  # 不抛异常即可

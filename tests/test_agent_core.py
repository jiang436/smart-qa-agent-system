"""Agent 核心测试 — Persona + state_utils + LoopDetector.decide"""
from smart_qa.agent.guards.loop_detector import LoopDetector
from smart_qa.agent.persona import get_greeting_reply, is_out_of_scope, is_pure_greeting
from smart_qa.agent.state_utils import extract_user_query, get_messages


class TestPersonaGreeting:
    def test_pure_greeting_hello(self):
        assert is_pure_greeting("你好") is not None
        assert is_pure_greeting("您好") is not None
        assert is_pure_greeting("嗨") is not None

    def test_pure_greeting_goodbye(self):
        assert is_pure_greeting("再见") is not None
        assert is_pure_greeting("拜拜") is not None

    def test_pure_greeting_thanks(self):
        assert is_pure_greeting("谢谢") is not None
        assert is_pure_greeting("多谢") is not None

    def test_pure_greeting_returns_none_for_business_query(self):
        assert is_pure_greeting("怎么设置定时清扫") is None
        assert is_pure_greeting("机器不工作了") is None
        assert is_pure_greeting("") is None

    def test_pure_greeting_morning(self):
        assert is_pure_greeting("早上好") is not None

    def test_get_greeting_reply_matches_type(self):
        reply = get_greeting_reply("hello")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_get_greeting_reply_default_fallback(self):
        reply = get_greeting_reply("nonexistent_type")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_get_greeting_reply_default_when_none(self):
        reply = get_greeting_reply()
        assert isinstance(reply, str)
        assert len(reply) > 0


class TestPersonaOutOfScope:
    def test_investment_rejected(self):
        assert is_out_of_scope("你觉得买什么股票好") is True
        assert is_out_of_scope("推荐几只基金") is True

    def test_politics_rejected(self):
        assert is_out_of_scope("你对当前政策怎么看") is True

    def test_code_development_rejected(self):
        assert is_out_of_scope("帮我写一段代码") is True
        assert is_out_of_scope("这个bug怎么修") is True

    def test_normal_qa_not_rejected(self):
        assert is_out_of_scope("怎么设置定时清扫") is False
        assert is_out_of_scope("X30 Pro支持多大面积") is False

    def test_empty_query_not_rejected(self):
        assert is_out_of_scope("") is False
        assert is_out_of_scope("你好") is False

    def test_error_code_not_rejected(self):
        assert is_out_of_scope("E05错误怎么解决") is False

    def test_gaming_out_of_scope(self):
        assert is_out_of_scope("推荐一个好玩的游戏") is True


class TestStateUtils:
    def test_get_messages_with_dicts(self):
        state = {"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}]}
        msgs = get_messages(state)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "你好！"

    def test_get_messages_empty(self):
        assert get_messages({}) == []
        assert get_messages({"messages": []}) == []

    def test_get_messages_missing_key(self):
        assert get_messages({"other": "data"}) == []

    def test_extract_user_query_returns_latest_user(self):
        state = {
            "messages": [
                {"role": "assistant", "content": "你好！请问有什么可以帮您？"},
                {"role": "user", "content": "怎么重置Wi-Fi"},
            ]
        }
        assert extract_user_query(state) == "怎么重置Wi-Fi"

    def test_extract_user_query_multiple_messages(self):
        state = {
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
                {"role": "user", "content": "重置Wi-Fi"},
            ]
        }
        assert extract_user_query(state) == "重置Wi-Fi"

    def test_extract_user_query_empty(self):
        assert extract_user_query({}) == ""
        assert extract_user_query({"messages": []}) == ""

    def test_extract_user_query_fallback_to_last(self):
        state = {"messages": [{"role": "assistant", "content": "你好！"}]}
        assert extract_user_query(state) == "你好！"


class TestLoopDetectorDecide:
    def test_no_loop_with_answer_returns_done(self):
        state = {"loop_detected": False, "final_answer": "这是回答"}
        assert LoopDetector.decide(state) == "done"

    def test_no_loop_no_answer_returns_continue(self):
        state = {"loop_detected": False, "final_answer": None}
        assert LoopDetector.decide(state) == "continue"

    def test_no_loop_empty_answer_returns_continue(self):
        state = {"loop_detected": False, "final_answer": ""}
        assert LoopDetector.decide(state) == "continue"

    def test_loop_force_stop_returns_stop(self):
        state = {"loop_detected": True, "loop_action": "force_stop"}
        assert LoopDetector.decide(state) == "stop"

    def test_loop_inject_warning_returns_continue(self):
        state = {"loop_detected": True, "loop_action": "inject_warning"}
        assert LoopDetector.decide(state) == "continue"

    def test_loop_no_action_defaults_force_stop(self):
        state = {"loop_detected": True}
        assert LoopDetector.decide(state) == "stop"

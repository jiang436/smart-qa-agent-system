"""LoopDetector 三层防护测试"""
import time

import pytest

from smart_qa.agent.guards.loop_detector import LoopDetector, LoopResult


class MockEmbedding:
    """Mock embedding for semantic loop tests"""
    def encode(self, texts):
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        return np.random.rand(len(texts), 4).astype(np.float32)

    def cosine_similarity(self, a, b):
        return 0.0  # default: not similar


class TestHardLimitsLayer1:
    """第一重：硬性上限"""

    def test_step_limit_triggers(self):
        detector = LoopDetector(max_steps=5)
        state = {"step": 6, "max_steps": 5}
        result = detector._check_hard_limits(state)
        assert result.detected is True
        assert result.action == "force_stop"

    def test_step_within_limit_passes(self):
        detector = LoopDetector(max_steps=10)
        state = {"step": 5, "max_steps": 10}
        result = detector._check_hard_limits(state)
        assert result.detected is False

    def test_timeout_triggers(self):
        detector = LoopDetector(max_execution_time=0.1)
        detector._set_start_time(state := {}, time.time() - 1.0)  # 1s ago
        state.update({"step": 3, "max_execution_time": 0.1})
        result = detector._check_hard_limits(state)
        assert result.detected is True
        assert result.action == "force_stop"

    def test_timeout_not_yet_passes(self):
        detector = LoopDetector(max_execution_time=999)
        detector._set_start_time(state := {}, time.time())
        state["step"] = 3
        result = detector._check_hard_limits(state)
        assert result.detected is False


class TestRuntimeDetectionLayer2:
    """第二重：运行时检测"""

    def test_repeated_tools_detected(self):
        detector = LoopDetector(repeated_tool_threshold=3)
        state = {
            "tool_calls_history": ["search", "search", "search"],
        }
        result = detector._check_repeated_tools(state)
        assert result.detected is True
        assert result.action == "inject_warning"

    def test_different_tools_pass(self):
        detector = LoopDetector(repeated_tool_threshold=3)
        state = {
            "tool_calls_history": ["search", "get_device", "search"],
        }
        result = detector._check_repeated_tools(state)
        assert result.detected is False

    def test_fewer_than_threshold_passes(self):
        detector = LoopDetector(repeated_tool_threshold=5)
        state = {
            "tool_calls_history": ["search", "search"],
        }
        result = detector._check_repeated_tools(state)
        assert result.detected is False

    def test_semantic_loop_detected(self):
        detector = LoopDetector(embedding_model=MockEmbedding(), semantic_threshold=0.01)
        # force high similarity
        detector.embedding.cosine_similarity = lambda a, b: 0.95
        state = {
            "messages": [
                {"role": "ai", "content": "rang wo zai cha yi xia"},
                {"role": "user", "content": "... "},
                {"role": "ai", "content": "wo zai cha yi xia zi liao"},
                {"role": "user", "content": "... "},
                {"role": "ai", "content": "zai kan yi ci jian suo jie guo"},
            ],
        }
        result = detector._check_semantic_loop(state)
        assert result.detected is True

    def test_semantic_loop_no_embedding_passes(self):
        detector = LoopDetector(embedding_model=None)
        state = {"messages": [
            {"role": "ai", "content": "A"}, {"role": "ai", "content": "B"}, {"role": "ai", "content": "C"},
        ]}
        result = detector._check_semantic_loop(state)
        assert result.detected is False

    def test_semantic_loop_not_enough_messages(self):
        detector = LoopDetector(embedding_model=MockEmbedding())
        state = {"messages": [{"role": "ai", "content": "A"}]}
        result = detector._check_semantic_loop(state)
        assert result.detected is False

    def test_stuck_detection(self):
        detector = LoopDetector()
        state = {
            "tool_calls_history": ["search"],
            detector._HISTORY_KEY: [
                {"had_tool_call": True, "retrieved_docs_count": 0, "has_final_answer": False},
                {"had_tool_call": True, "retrieved_docs_count": 0, "has_final_answer": False},
                {"had_tool_call": True, "retrieved_docs_count": 0, "has_final_answer": False},
                {"had_tool_call": True, "retrieved_docs_count": 0, "has_final_answer": False},
                {"had_tool_call": True, "retrieved_docs_count": 0, "has_final_answer": False},
            ],
        }
        result = detector._check_stuck(state)
        assert result.detected is True
        assert result.action == "force_stop"


class TestEnforcementLayer3:
    """第三重：强制执行"""

    def test_force_stop_sets_answer(self):
        detector = LoopDetector()
        state = {}
        result = LoopResult(detected=True, reason="test", action="force_stop")
        detector._apply_result(state, result)
        assert "final_answer" in state
        assert state["loop_detected"]
        assert state["loop_action"] == "force_stop"

    def test_inject_warning_adds_message(self):
        detector = LoopDetector()
        state = {"messages": []}
        result = LoopResult(detected=True, reason="test", action="inject_warning")
        detector._apply_result(state, result)
        assert len(state["messages"]) > 0
        assert state["messages"][0]["role"] == "system"

    def test_force_stop_preserves_existing_answer(self):
        detector = LoopDetector()
        state = {"final_answer": "already set"}
        result = LoopResult(detected=True, reason="test", action="force_stop")
        detector._apply_result(state, result)
        assert state["final_answer"] == "already set"  # 不应该覆盖


class TestDecideDispatch:
    """dispatch 决策"""

    def test_decide_done_on_answer(self):
        result = LoopDetector.decide({"final_answer": "hello"})
        assert result == "done"

    def test_decide_continue_no_answer(self):
        result = LoopDetector.decide({"final_answer": None})
        assert result == "continue"

    def test_decide_stop_on_loop_force_stop(self):
        result = LoopDetector.decide({
            "loop_detected": True,
            "loop_action": "force_stop",
        })
        assert result == "stop"

    def test_decide_continue_on_loop_warning(self):
        result = LoopDetector.decide({
            "loop_detected": True,
            "loop_action": "inject_warning",
        })
        assert result == "continue"


class TestCheckFullFlow:
    """完整 check 流程"""

    @pytest.mark.asyncio
    async def test_normal_flow_no_detection(self):
        detector = LoopDetector(max_steps=100)
        state = {"step": 1, "messages": [{"role": "user", "content": "test"}]}
        result = await detector.check(state)
        assert result["step"] == 2
        assert result.get("loop_detected") is False

    @pytest.mark.asyncio
    async def test_step_limit_detected(self):
        detector = LoopDetector(max_steps=3)
        state = {"step": 5}
        result = await detector.check(state)
        assert result.get("loop_detected") is True
        assert result.get("loop_action") == "force_stop"

    @pytest.mark.asyncio
    async def test_new_session_resets(self):
        detector = LoopDetector(max_steps=10)
        state = {"step": 0, detector._HISTORY_KEY: [{"step": 99}]}
        await detector.check(state)
        # step 0 应该重置历史
        assert len(detector._get_history(state)) <= 1

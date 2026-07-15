"""Pydantic Schema 校验测试"""

import pytest
from pydantic import ValidationError

from smart_qa.models.approval_schema import ApproveRequest
from smart_qa.models.chat_schema import ChatRequest, ChatResponse
from smart_qa.models.device_schema import DeviceStatus, ScheduleCreate
from smart_qa.models.report_schema import UsageStats


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(user_id="U1001", message="怎么设置定时清扫")
        assert req.user_id == "U1001"

    def test_empty_user_id_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(user_id="", message="test")

    def test_empty_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(user_id="U1", message="")

    def test_message_too_long_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(user_id="U1", message="x" * 2001)

    def test_empty_session_id_defaults(self):
        req = ChatRequest(user_id="U1", message="test")
        assert req.session_id == ""


class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(answer="测试回答", session_id="s1")
        assert resp.intent == "general"

    def test_invalid_intent_raises(self):
        with pytest.raises(ValidationError):
            ChatResponse(answer="test", session_id="s1", intent="invalid_intent")


class TestDeviceStatus:
    def test_valid_status(self):
        d = DeviceStatus(user_id="U1", battery=50)
        assert d.battery == 50

    def test_battery_overflow_raises(self):
        with pytest.raises(ValidationError):
            DeviceStatus(user_id="U1", battery=101)

    def test_battery_negative_raises(self):
        with pytest.raises(ValidationError):
            DeviceStatus(user_id="U1", battery=-1)


class TestScheduleCreate:
    def test_valid_time(self):
        s = ScheduleCreate(user_id="U1", time="09:30")
        assert s.time == "09:30"

    def test_invalid_time_raises(self):
        with pytest.raises(ValidationError):
            ScheduleCreate(user_id="U1", time="25:00")

    def test_invalid_time_format_raises(self):
        with pytest.raises(ValidationError):
            ScheduleCreate(user_id="U1", time="9点半")


class TestApproveRequest:
    def test_valid_approve(self):
        req = ApproveRequest(session_id="s1", decision="approve")
        assert req.decision == "approve"

    def test_invalid_decision_raises(self):
        with pytest.raises(ValidationError):
            ApproveRequest(session_id="s1", decision="maybe")

    def test_empty_session_id_raises(self):
        with pytest.raises(ValidationError):
            ApproveRequest(session_id="", decision="approve")

    def test_feedback_too_long_raises(self):
        with pytest.raises(ValidationError):
            ApproveRequest(session_id="s1", decision="modify", feedback="x" * 501)


class TestUsageStats:
    def test_defaults(self):
        s = UsageStats()
        assert s.total_cleans >= 0
        assert s.total_days == 30

    def test_negative_cleans_raises(self):
        with pytest.raises(ValidationError):
            UsageStats(total_cleans=-1)

    def test_days_overflow_raises(self):
        with pytest.raises(ValidationError):
            UsageStats(total_days=400)

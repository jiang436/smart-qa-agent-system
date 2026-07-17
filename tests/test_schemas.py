"""Pydantic Schema 校验测试"""
import pytest
from pydantic import ValidationError

from smart_qa.models.chat_schema import ChatRequest, ChatResponse


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



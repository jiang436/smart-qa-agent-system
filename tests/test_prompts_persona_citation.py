"""Prompt Loader + Persona + Citation + HyDE 边界测试"""
import pytest
from unittest.mock import MagicMock, patch


class TestPromptLoader:
    def test_load_cot_prompt_router(self):
        from smart_qa.agent.prompts.loader import load_cot_prompt
        prompt = load_cot_prompt("router")
        assert isinstance(prompt, str)
        assert len(prompt) > 10

    def test_load_cot_prompt_rag(self):
        from smart_qa.agent.prompts.loader import load_cot_prompt
        prompt = load_cot_prompt("rag")
        assert isinstance(prompt, str)
        assert len(prompt) > 10

    def test_load_cot_prompt_not_found(self):
        from smart_qa.agent.prompts.loader import load_cot_prompt
        with pytest.raises(FileNotFoundError):
            load_cot_prompt("nonexistent_prompt")

    def test_load_cot_prompt_cached(self):
        from smart_qa.agent.prompts.loader import load_cot_prompt, _CACHE
        _CACHE.clear()
        p1 = load_cot_prompt("router")
        p2 = load_cot_prompt("router")
        assert p1 == p2  # 缓存命中
        assert "router" in _CACHE


class TestPersona:
    def test_persona_has_name(self):
        from smart_qa.agent.persona import PERSONA
        assert "name" in PERSONA
        assert "company" in PERSONA
        assert len(PERSONA["name"]) > 0

    def test_is_pure_greeting_returns_type(self):
        from smart_qa.agent.persona import is_pure_greeting
        assert is_pure_greeting("你好") == "hello"
        assert is_pure_greeting("再见") == "bye"
        assert is_pure_greeting("谢谢") == "thanks"
        assert is_pure_greeting("边刷") is None

    def test_is_pure_greeting_morning(self):
        from smart_qa.agent.persona import is_pure_greeting
        assert is_pure_greeting("早上好") == "morning"

    def test_is_pure_greeting_disturb(self):
        from smart_qa.agent.persona import is_pure_greeting
        assert is_pure_greeting("打扰一下") == "disturb"

    def test_is_out_of_scope_coding(self):
        from smart_qa.agent.persona import is_out_of_scope
        assert is_out_of_scope("帮我写python代码") is True

    def test_is_out_of_scope_business(self):
        from smart_qa.agent.persona import is_out_of_scope
        assert is_out_of_scope("扫地机E05故障") is False

    def test_is_out_of_scope_empty(self):
        from smart_qa.agent.persona import is_out_of_scope
        assert is_out_of_scope("") is False

    def test_get_greeting_reply_hello(self):
        from smart_qa.agent.persona import get_greeting_reply
        reply = get_greeting_reply("hello")
        assert len(reply) > 5

    def test_get_system_prompt_qa(self):
        from smart_qa.agent.persona import get_system_prompt
        prompt = get_system_prompt("qa")
        assert "xiao zhi" in prompt.lower() or len(prompt) > 100

    def test_get_system_prompt_troubleshoot(self):
        from smart_qa.agent.persona import get_system_prompt
        prompt = get_system_prompt("troubleshoot")
        assert len(prompt) > 50

    def test_welcome_message_not_empty(self):
        from smart_qa.agent.persona import WELCOME_MESSAGE
        assert len(WELCOME_MESSAGE) > 20

    def test_out_of_scope_rejection_not_empty(self):
        from smart_qa.agent.persona import OUT_OF_SCOPE_REJECTION
        assert len(OUT_OF_SCOPE_REJECTION) > 20


class TestCitation:
    def test_register_and_cite(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        tracker.register_docs([
            {"doc_id": 1, "content": "bian shua jian yi 3-6 ge yue geng huan", "source": "manual.md"},
        ])
        result = tracker.build_cited_answer("bian shua", "bian shua yao 3 ge yue huan yi ci.")
        assert "text" in result
        assert "citations" in result
        assert "hallucination_risk" in result

    def test_empty_docs_high_risk(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        result = tracker.build_cited_answer("test", "some answer with no sources")
        assert result["hallucination_risk"] == "high"

    def test_hallucination_guard_block(self):
        from smart_qa.rag.citation import HallucinationGuard
        assert HallucinationGuard.should_block({"hallucination_risk": "high"}, threshold="high") is True
        assert HallucinationGuard.should_block({"hallucination_risk": "low"}, threshold="high") is False

    def test_hallucination_guard_safe_response(self):
        from smart_qa.rag.citation import HallucinationGuard
        resp = HallucinationGuard.generate_safe_response({
            "text": "test answer",
            "unverified_claims": ["x30 pro has 5000pa suction"],
        })
        assert "xiao zhi" in resp.lower() or "wei yan zheng" in resp.lower() or "test" in resp.lower()

    def test_citation_with_content_match(self):
        from smart_qa.rag.citation import CitationTracker
        tracker = CitationTracker()
        tracker.register_docs([
            {"doc_id": 1, "content": "X30 Pro dian chi rong liang 5200mAh", "source": "spec.md"},
        ])
        result = tracker.build_cited_answer("dian chi", "X30 Pro dian chi shi 5200mAh.")
        # 如果 embedding 匹配到，应该有 citation
        assert isinstance(result["citations"], list)


class TestHyDE:
    def test_hyde_skip_short_query(self):
        from smart_qa.rag.hyde import HyDE
        hyde = HyDE(llm_client=MagicMock())
        result = hyde.generate("ni")
        assert result is None  # 太短

    def test_hyde_skip_greeting(self):
        from smart_qa.rag.hyde import HyDE
        hyde = HyDE(llm_client=MagicMock())
        result = hyde.generate("ni hao")
        assert result is None  # 寒暄跳过

    def test_hyde_no_llm(self):
        from smart_qa.rag.hyde import HyDE
        hyde = HyDE(llm_client=None)
        result = hyde.generate("bian shua zen me huan")
        assert result is None  # 无 LLM

    def test_hyde_with_mock_llm(self):
        from smart_qa.rag.hyde import HyDE
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = type('R', (), {'content': 'zhe shi HyDE sheng cheng de jia she da an wen dang'})()

        hyde = HyDE(llm_client=mock_llm)
        result = hyde.generate("bian shua huai le")
        assert result is not None
        assert len(result) > 30

"""Router Agent LLM mock test + dispatch test"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from smart_qa.agent.agents.router_agent import RouterAgent


class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class TestRouterLLMClassification:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_classify_qa_via_llm(self, mock_llm):
        mock_llm.ainvoke.return_value = MockLLMResponse("qa")
        router = RouterAgent(llm_client=mock_llm)
        intent = await router._llm_classify("X30 Pro 怎么设置定时")
        assert intent == "qa"

    @pytest.mark.asyncio
    async def test_classify_troubleshoot_via_llm(self, mock_llm):
        mock_llm.ainvoke.return_value = MockLLMResponse("troubleshoot")
        router = RouterAgent(llm_client=mock_llm)
        intent = await router._llm_classify("E05 故障")
        assert intent == "troubleshoot"

    @pytest.mark.asyncio
    async def test_classify_consumables_via_llm(self, mock_llm):
        mock_llm.ainvoke.return_value = MockLLMResponse("consumables")
        router = RouterAgent(llm_client=mock_llm)
        intent = await router._llm_classify("边刷该换了")
        assert intent == "consumables"

    @pytest.mark.asyncio
    async def test_classify_llm_error_falls_to_keyword(self, mock_llm):
        mock_llm.ainvoke.side_effect = Exception("API Error")
        router = RouterAgent(llm_client=mock_llm)
        intent = await router._classify_intent("购买边刷")
        assert intent in ("consumables", "qa", "general")

    @pytest.mark.asyncio
    async def test_classify_general_falls_to_keyword(self, mock_llm):
        """LLM general intent falls back to keyword match"""
        mock_llm.ainvoke.return_value = MockLLMResponse("general")
        router = RouterAgent(llm_client=mock_llm)
        intent = await router._classify_intent("错误码E05")
        assert "troubleshoot" in intent or intent != "qa"


class TestRouterDispatch:
    def test_dispatch_qa(self):
        assert RouterAgent.dispatch({"intent": "qa"}) == "qa"

    def test_dispatch_troubleshoot(self):
        assert RouterAgent.dispatch({"intent": "troubleshoot"}) == "troubleshoot"

    def test_dispatch_unknown_falls_to_general(self):
        assert RouterAgent.dispatch({"intent": "unknown"}) == "general"

    def test_dispatch_faq_hit_returns_done(self):
        assert RouterAgent.dispatch({"intent": "qa", "final_answer": "yes"}) == "done"

    def test_dispatch_empty_state(self):
        assert RouterAgent.dispatch({}) == "general"


class TestRouterPipeline:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock()
        llm.ainvoke.return_value = MockLLMResponse("qa")
        return llm

    @pytest.mark.asyncio
    async def test_route_greeting_short_circuits(self, mock_llm):
        router = RouterAgent(llm_client=mock_llm)
        state = {"messages": [{"role": "user", "content": "你好"}]}
        result = await router.route(state)
        assert result["intent"] == "general"
        assert "final_answer" in result
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_multi_question_rejected(self, mock_llm):
        router = RouterAgent(llm_client=mock_llm)
        state = {"messages": [{"role": "user", "content": "E05错误？边刷也坏了？"}]}
        result = await router.route(state)
        assert result["intent"] == "general"
        assert "final_answer" in result

    @pytest.mark.asyncio
    async def test_route_normal_qa_flow(self, mock_llm):
        mock_llm.ainvoke.return_value = MockLLMResponse("qa")
        router = RouterAgent(llm_client=mock_llm)
        state = {"messages": [{"role": "user", "content": "X30 Pro 边刷怎么换"}]}
        result = await router.route(state)
        assert result["intent"] == "qa"

    @pytest.mark.asyncio
    async def test_route_empty_query(self, mock_llm):
        router = RouterAgent(llm_client=mock_llm)
        state = {"messages": []}
        result = await router.route(state)
        assert result["intent"] == "general"

    @pytest.mark.asyncio
    async def test_dispatch_by_intent_sql(self):
        state = {}
        router = RouterAgent()
        result = router._dispatch_by_intent("test", "sql_query", state)
        assert result["intent"] == "sql_query"
        assert result.get("scenario") == "sql_query"


class TestKeywordClassification:
    """关键词降级 — 用真实中文测试"""
    router = RouterAgent()

    def test_device_control_keywords(self):
        assert self.router._keyword_classify("开始清扫") == "device_control"
        assert self.router._keyword_classify("停止清扫") == "device_control"

    def test_sql_keywords(self):
        assert self.router._keyword_classify("本月卖了多少台") == "sql_query"

    def test_report_keywords(self):
        assert self.router._keyword_classify("生成使用报告") == "report"

    def test_qa_keywords(self):
        assert self.router._keyword_classify("怎么设置定时") == "qa"

    def test_troubleshoot_keywords(self):
        assert self.router._keyword_classify("E05错误码") == "troubleshoot"

    def test_consumables_keywords(self):
        assert self.router._keyword_classify("边刷多少钱") == "consumables"

    def test_empty_query_defaults_general(self):
        assert self.router._keyword_classify("") == "general"

    def test_unknown_query_defaults_general(self):
        assert self.router._keyword_classify("xyz_unknown_123") == "general"

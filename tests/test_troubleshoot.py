"""TroubleshootScenario 测试 — 错误码匹配 + RAG 兜底"""
import pytest

from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario, ERROR_CODE_MAP


class TestErrorCodeMatching:
    """错误码精确匹配"""

    def test_extract_known_error_code(self):
        code = TroubleshootScenario._extract_error_code("报错E05")
        assert code == "E05"
        assert code in ERROR_CODE_MAP

    def test_extract_lowercase_error(self):
        code = TroubleshootScenario._extract_error_code("显示e03")
        assert code == "E03"

    def test_extract_e_with_three_digits(self):
        code = TroubleshootScenario._extract_error_code("E002故障")
        assert code is None  # 只有 E01-E08

    def test_extract_no_error_code(self):
        code = TroubleshootScenario._extract_error_code("不工作了")
        assert code is None

    def test_extract_chinese_pattern(self):
        code = TroubleshootScenario._extract_error_code("错误 05 怎么解决")
        assert code == "E05"

    def test_extract_empty_string(self):
        code = TroubleshootScenario._extract_error_code("")
        assert code is None

    def test_error_code_map_has_solutions(self):
        """所有错误码都有原因和解决方案"""
        for code, entry in ERROR_CODE_MAP.items():
            assert "cause" in entry, f"Missing cause for {code}"
            assert "solution" in entry, f"Missing solution for {code}"
            assert len(entry["cause"]) > 0
            assert len(entry["solution"]) > 0

    def test_all_expected_error_codes_exist(self):
        """E01~E08 都在映射表中"""
        for i in range(1, 9):
            code = f"E{i:02d}"
            assert code in ERROR_CODE_MAP, f"Missing {code}"


class TestTroubleshootRun:
    """故障排查运行流程"""

    @pytest.mark.asyncio
    async def test_error_code_direct_match(self):
        """错误码精确匹配 → 返回解决方案"""
        state = {"messages": [{"role": "user", "content": "E05错误"}]}
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        assert "E05" in result["final_answer"]
        assert "retrieved_docs" in result

    @pytest.mark.asyncio
    async def test_error_code_lowercase(self):
        state = {"messages": [{"role": "user", "content": "显示e01"}]}
        result = await TroubleshootScenario.run(state)
        assert "E01" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_no_error_code_falls_back_to_rag_or_default(self):
        """无错误码 → RAG 或兜底"""
        state = {"messages": [{"role": "user", "content": "扫地机有点奇怪的问题"}]}
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        assert len(result["final_answer"]) > 10

    @pytest.mark.asyncio
    async def test_empty_query_returns_prompt(self):
        state = {"messages": []}
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        assert len(result["final_answer"]) > 0

    @pytest.mark.asyncio
    async def test_error_code_response_includes_fix_steps(self):
        state = {"messages": [{"role": "user", "content": "E04"}]}
        result = await TroubleshootScenario.run(state)
        assert "解决" in result["final_answer"] or "方法" in result["final_answer"]

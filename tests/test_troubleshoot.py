"""TroubleshootScenario 多轮对话状态机测试"""
import pytest

from smart_qa.scenarios.troubleshoot_scenario import TroubleshootScenario, ERROR_CODE_MAP, DIAGNOSIS_TREE


class TestErrorCodeMatching:
    def test_extract_known_error_code(self):
        code = TroubleshootScenario._extract_error_code("报错E05")
        assert code == "E05"
        assert code in ERROR_CODE_MAP

    def test_extract_lowercase_error(self):
        code = TroubleshootScenario._extract_error_code("显示e03")
        assert code == "E03"

    def test_extract_no_error_code(self):
        code = TroubleshootScenario._extract_error_code("不工作了")
        assert code is None

    def test_error_code_map_has_solutions(self):
        for code, entry in ERROR_CODE_MAP.items():
            assert "cause" in entry
            assert "solution" in entry
            assert len(entry["cause"]) > 0
            assert len(entry["solution"]) > 0


class TestFaultTypeMatching:
    def test_match_not_working(self):
        fault = TroubleshootScenario._match_fault_type("扫地机不工作了")
        assert fault == "不工作/不开机"

    def test_match_cleaning_issue(self):
        fault = TroubleshootScenario._match_fault_type("扫不干净")
        assert fault == "清扫不干净"

    def test_match_charging_issue(self):
        fault = TroubleshootScenario._match_fault_type("无法回充")
        assert fault == "无法回充"

    def test_match_noise(self):
        fault = TroubleshootScenario._match_fault_type("噪音太大")
        assert fault == "异常噪音"

    def test_match_wifi(self):
        fault = TroubleshootScenario._match_fault_type("连不上wifi")
        assert fault == "Wi-Fi 连接失败"

    def test_no_match_returns_none(self):
        fault = TroubleshootScenario._match_fault_type("今天天气真好")
        assert fault is None


class TestResponseDetection:
    def test_positive_responses(self):
        for resp in ["是", "对", "有", "嗯", "可以", "能的", "恢复了"]:
            assert TroubleshootScenario._is_positive_response(resp), f"'{resp}' should be positive"

    def test_negative_responses(self):
        for resp in ["不", "没", "没有", "不行", "还是", "仍然"]:
            assert not TroubleshootScenario._is_positive_response(resp), f"'{resp}' should be negative"


class TestDiagnosisTree:
    def test_tree_has_expected_entries(self):
        assert len(DIAGNOSIS_TREE) >= 10

    def test_each_entry_has_required_fields(self):
        for name, entry in DIAGNOSIS_TREE.items():
            assert "conditions" in entry, f"Missing conditions in {name}"
            assert "causes" in entry, f"Missing causes in {name}"
            assert "steps" in entry, f"Missing steps in {name}"
            for step in entry["steps"]:
                assert "question" in step
                assert "if_yes" in step
                assert "if_no" in step

    def test_max_diagnosis_rounds(self):
        assert TroubleshootScenario.MAX_DIAGNOSIS_ROUNDS == 5


class TestHandleInit:
    @pytest.mark.asyncio
    async def test_init_with_error_code(self):
        state = {"messages": [{"role": "user", "content": "E05错误"}]}
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result
        assert "E05" in result.get("final_answer", "")

    @pytest.mark.asyncio
    async def test_init_with_no_query(self):
        state = {"messages": []}
        result = await TroubleshootScenario.run(state)
        assert "final_answer" in result

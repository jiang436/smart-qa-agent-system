"""Eval 指标测试"""
import pytest
from smart_qa.evaluation.metrics import keyword_recall, intent_accuracy, summary


class TestKeywordRecall:
    def test_all_keywords_found(self):
        assert keyword_recall("X30 Pro 电池过热", ["X30 Pro", "电池"]) == 1.0

    def test_partial_keywords_found(self):
        recall = keyword_recall("电池过热怎么处理", ["电池", "Wi-Fi", "重置"])
        assert recall == pytest.approx(1 / 3)

    def test_no_keywords(self):
        assert keyword_recall("你好", []) == 1.0

    def test_empty_answer(self):
        assert keyword_recall("", ["电池"]) == 0.0


class TestIntentAccuracy:
    def test_all_correct(self):
        assert intent_accuracy([{"intent_correct": True}, {"intent_correct": True}]) == 1.0

    def test_partial_correct(self):
        assert intent_accuracy([{"intent_correct": True}, {"intent_correct": False}]) == 0.5

    def test_empty_list(self):
        assert intent_accuracy([]) == 0.0


class TestSummary:
    def test_empty_results(self):
        assert summary([])["total_cases"] == 0

    def test_all_passed(self):
        results = [
            {"passed": True, "intent_correct": True, "keyword_recall": 1.0, "latency": 0.5, "judge_verdict": "PASS"},
            {"passed": True, "intent_correct": True, "keyword_recall": 0.8, "latency": 1.0, "judge_verdict": "PASS"},
        ]
        report = summary(results)
        assert report["pass_rate"] == 1.0
        assert report["judge_breakdown"]["PASS"] == 2

    def test_mixed(self):
        results = [
            {"passed": True, "intent_correct": True, "keyword_recall": 1.0, "latency": 0.5, "judge_verdict": "PASS"},
            {"passed": False, "intent_correct": False, "keyword_recall": 0.0, "latency": 2.0, "judge_verdict": "FAIL"},
        ]
        report = summary(results)
        assert report["pass_rate"] == 0.5
        assert report["intent_accuracy"] == 0.5

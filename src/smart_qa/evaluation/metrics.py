"""评测指标工具函数"""

from __future__ import annotations


def keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """关键词召回率: 期望关键词在回答中出现比例"""
    if not expected_keywords:
        return 1.0
    if not answer:
        return 0.0
    lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in lower)
    return hits / len(expected_keywords)


def intent_accuracy(results: list[dict]) -> float:
    """意图分类准确率"""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.get("intent_correct"))
    return correct / len(results)


def summary(results: list[dict]) -> dict:
    """生成评测汇总报告

    Args:
        results: EvalRunner._run_single 返回的结果列表

    Returns:
        {
            "total_cases": N,
            "pass_count": N,
            "pass_rate": 0.xx,
            "intent_accuracy": 0.xx,
            "avg_keyword_recall": 0.xx,
            "avg_latency_seconds": 0.xx,
            "judge_breakdown": {"PASS": N, "WEAK_PASS": N, "FAIL": N},
        }
    """
    if not results:
        return {
            "total_cases": 0,
            "pass_count": 0,
            "pass_rate": 0,
            "intent_accuracy": 0,
            "avg_keyword_recall": 0,
            "avg_latency_seconds": 0,
            "judge_breakdown": {},
        }

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    correct_intent = sum(1 for r in results if r.get("intent_correct"))

    kw_recalls = [r.get("keyword_recall", 0) for r in results if r.get("keyword_recall") is not None]
    latencies = [r.get("latency", 0) for r in results if r.get("latency") is not None]

    judge_breakdown: dict[str, int] = {}
    for r in results:
        v = r.get("judge_verdict", "?") or "?"
        judge_breakdown[v] = judge_breakdown.get(v, 0) + 1

    return {
        "total_cases": total,
        "pass_count": passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "intent_accuracy": round(correct_intent / len(results), 4),
        "avg_keyword_recall": round(sum(kw_recalls) / len(kw_recalls), 4) if kw_recalls else 0,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "judge_breakdown": judge_breakdown,
    }

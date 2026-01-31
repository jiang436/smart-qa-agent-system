"""评测指标"""


def intent_accuracy(predictions: list[str], expected: list[str]) -> float:
    """意图分类准确率"""
    if not predictions:
        return 0.0
    correct = sum(1 for p, e in zip(predictions, expected) if p == e)
    return correct / len(predictions)


def keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """回答关键词召回率"""
    if not expected_keywords:
        return 1.0  # 无关键词要求视为通过
    found = sum(1 for kw in expected_keywords if kw in answer)
    return found / len(expected_keywords)


def latency_within_threshold(latency: float, threshold: float = 3.0) -> bool:
    """响应时间是否在阈值内"""
    return latency <= threshold


def summary(results: list[dict]) -> dict:
    """汇总所有评测结果"""
    total = len(results)
    if total == 0:
        return {"error": "no results"}

    correct_intent = sum(1 for r in results if r.get("intent_correct", False))
    avg_keyword_recall = sum(r.get("keyword_recall", 0) for r in results) / total
    avg_latency = sum(r.get("latency", 0) for r in results) / total

    return {
        "total_cases": total,
        "intent_accuracy": correct_intent / total,
        "avg_keyword_recall": avg_keyword_recall,
        "avg_latency_seconds": avg_latency,
        "pass_rate": sum(1 for r in results if r.get("passed", False)) / total,
    }

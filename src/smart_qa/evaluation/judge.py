"""LLM-as-Judge — 自动评估回答质量

用 LLM 对 Agent 回答做多维度打分, 替代人工评估。

维度:
  1. accuracy:    事实是否正确 (0-1)
  2. completeness: 是否完整回答 (0-1)
  3. relevance:    是否与问题相关 (0-1)
  4. conciseness:  是否简洁无冗余 (0-1)

综合: PASS / WEAK_PASS / FAIL
"""

import json

from smart_qa.observability.logger import logger


class LLMJudge:
    """LLM-as-Judge 评估器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def evaluate(self, query: str, answer: str, expected_keywords: list[str] | None = None) -> dict:
        """多维度评估"""
        result: dict = {
            "overall": "FAIL",
            "dimensions": {},
            "reason": "",
            "keyword_recall": 0.0,
        }

        if expected_keywords:
            result["keyword_recall"] = self._keyword_recall(answer, expected_keywords)

        if self.llm:
            llm_r = await self._llm_score(query, answer, expected_keywords)
            result.update(llm_r)
        else:
            result["overall"] = "PASS" if result["keyword_recall"] >= 0.5 else "WEAK_PASS"
            result["reason"] = f"无LLM, 纯关键词: recall={result['keyword_recall']:.1%}"

        return result

    async def _llm_score(self, query: str, answer: str, expected_keywords: list[str] | None) -> dict:
        prompt = (
            f"用户问题: {query}\n系统回答: {answer}\n\n"
            + (f"预期关键词: {', '.join(expected_keywords)}\n" if expected_keywords else "")
            + "从 accuracy/completeness/relevance/conciseness 打分(0-10), 综合评判 PASS/WEAK_PASS/FAIL, 一句理由。\n"
            '输出 JSON: {"accuracy":8, "completeness":6, "relevance":9, "conciseness":7, "overall":"PASS", "reason":"..."}'
        )
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            if "```" in content:
                content = content.split("```")[1].replace("json", "", 1).split("```")[0]
            data = json.loads(content.strip())
            dims = {
                k: round(data.get(k, 0) / 10.0, 2) for k in ["accuracy", "completeness", "relevance", "conciseness"]
            }
            logger.info("LLM-Judge verdict={} accuracy={:.2f}", data.get("overall"), dims.get("accuracy", 0))
            return {"overall": data.get("overall", "FAIL"), "dimensions": dims, "reason": data.get("reason", "")}
        except Exception as e:
            logger.warning("LLM-Judge 失败: {}", e)
            return {"overall": "FAIL", "dimensions": {}, "reason": str(e)}

    def _keyword_recall(self, answer: str, keywords: list[str]) -> float:
        if not keywords:
            return 1.0
        return sum(1 for kw in keywords if kw.lower() in answer.lower()) / len(keywords)


# -- 工具调用评估 --


class ToolJudge:
    """工具调用正确性评估"""

    @staticmethod
    def compare(expected_tools: list[str], actual_tools: list[str]) -> dict:
        """比较期望工具 vs 实际工具调用"""
        exp_set = set(expected_tools)
        act_set = set(actual_tools)
        tp = len(exp_set & act_set)
        fp = len(act_set - exp_set)
        fn = len(exp_set - act_set)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.01)
        return {
            "precision": round(precision, 2),
            "recall": round(recall, 2),
            "f1": round(f1, 2),
            "expected": list(exp_set),
            "actual": list(act_set),
        }

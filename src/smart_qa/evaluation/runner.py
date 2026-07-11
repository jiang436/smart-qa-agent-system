"""Eval 评测运行器 — 批量跑测试用例并输出报告

评估维度:
  1. LLM-as-Judge 打分 (准确性/完整性/相关性/简洁性)
  2. 关键词召回率
  3. 工具调用正确率
  4. 意图分类准确率
  5. 延迟统计
"""

import json
import os
import time

from .dataset import get_stats, get_test_cases
from .judge import LLMJudge, ToolJudge
from .metrics import keyword_recall, summary


class EvalRunner:
    """自动化评估管线 — 每次改 Prompt 后跑一遍, 对比指标变化"""

    def __init__(self, agent, llm_client=None):
        self.agent = agent
        self.results: list[dict] = []
        self.judge = LLMJudge(llm_client=llm_client)
        self.tool_judge = ToolJudge()

    async def run_all(self, scenario=None, difficulty=None):
        """运行全部或筛选后的测试用例（异步）"""
        cases = get_test_cases(scenario, difficulty)
        print(f"[Eval] 开始评测: {len(cases)} 条用例")
        print(f"[Eval] 统计: {get_stats()}")

        for i, case in enumerate(cases):
            result = await self._run_single_async(case, i + 1, len(cases))
            self.results.append(result)

        report = summary(self.results)
        self._print_report(report)
        self._save_report(report)
        return report

    async def _run_single_async(self, case, index, total):
        """运行单条测试用例（含 LLM-as-Judge 打分）"""
        query = case["query"]
        expected_intent = case["expected_intent"]
        expected_keywords = case["expected_keywords"]
        expected_tools = case.get("expected_tools", [])

        print(f"  [{index}/{total}] {query[:30]}...", end=" ", flush=True)

        start = time.time()
        try:
            response = self.agent.process(query)
            latency = time.time() - start

            predicted_intent = response.get("intent", "")
            answer = response.get("answer", "")
            tools_used = response.get("tools_used", [])

            # 维度 1: LLM-as-Judge 打分
            judge_result = await self.judge.evaluate(query, answer, expected_keywords)

            # 维度 2: 关键词召回
            kw_recall = keyword_recall(answer, expected_keywords)

            # 维度 3: 工具调用正确率
            tool_result = self.tool_judge.compare(expected_tools, tools_used) if expected_tools else None

            # 维度 4: 意图分类
            intent_correct = predicted_intent == expected_intent

            # 综合: LLM-Judge + 关键词召回 + 意图
            passed = judge_result.get("overall") in ("PASS", "WEAK_PASS") and kw_recall >= 0.5 and intent_correct

            print(
                f"{'PASS' if passed else 'FAIL'} "
                f"(judge={judge_result.get('overall', '?')} "
                f"intent={intent_correct} "
                f"kw={kw_recall:.2f} "
                f"acc={judge_result.get('dimensions', {}).get('accuracy', 0):.2f} "
                f"{latency:.1f}s)"
            )

            return {
                "query": query,
                "expected_intent": expected_intent,
                "predicted_intent": predicted_intent,
                "intent_correct": intent_correct,
                "keyword_recall": kw_recall,
                "latency": latency,
                "judge_verdict": judge_result.get("overall"),
                "judge_dims": judge_result.get("dimensions", {}),
                "judge_reason": judge_result.get("reason", ""),
                "tool_eval": tool_result,
                "passed": passed,
            }
        except Exception as e:
            print(f"ERROR: {e}")
            return {
                "query": query,
                "expected_intent": expected_intent,
                "predicted_intent": "",
                "intent_correct": False,
                "keyword_recall": 0.0,
                "latency": time.time() - start,
                "judge_verdict": "ERROR",
                "judge_dims": {},
                "judge_reason": str(e),
                "tool_eval": None,
                "passed": False,
                "error": str(e),
            }

    def _print_report(self, report):
        """打印报告"""
        print("\n" + "=" * 50)
        print("评测报告")
        print("=" * 50)
        print(f"总用例:      {report.get('total_cases', 0)}")
        print(f"意图准确率:  {report.get('intent_accuracy', 0):.1%}")
        print(f"关键词召回率: {report.get('avg_keyword_recall', 0):.1%}")
        print(f"平均延迟:    {report.get('avg_latency_seconds', 0):.2f}s")
        print(f"通过率:      {report.get('pass_rate', 0):.1%}")

    def _save_report(self, report):
        """保存报告到文件"""
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(reports_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"summary": report, "details": self.results}, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {path}")

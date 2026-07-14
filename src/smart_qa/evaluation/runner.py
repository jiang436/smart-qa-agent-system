"""Eval 评测运行器 — 批量跑测试用例并输出报告

运行方式:
  1. 本地手工:
     uv run python -m smart_qa.evaluation.runner              # 跑全部 18 条
     uv run python -m smart_qa.evaluation.runner --scenario qa  # 只跑 QA
     uv run python -m smart_qa.evaluation.runner --difficulty easy  # 只跑简单

  2. pre-commit (git commit 前自动):
     pre-commit install
     git commit -m "..."   # 自动跑 11 条 easy 用例
     SKIP=eval-local git commit -m "..."   # 跳过

  3. GitLab CI (推送到 GitLab 时):
     .gitlab-ci.yml 中 eval job 自动触发。
     通过 CI/CD Variables 配置:
       LLM_API_KEY / LLM_BASE_URL  — LLM 提供商
       EVAL_SCENARIO               — 筛选场景 (默认空=全部)
       EVAL_DIFFICULTY             — 筛选难度 (默认空=全部)

输出:
  - 终端实时打印每条用例 PASS/FAIL
  - 报告写入 evaluation/reports/report_<timestamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from smart_qa.evaluation.dataset import get_stats, get_test_cases
from smart_qa.evaluation.judge import LLMJudge
from smart_qa.evaluation.metrics import keyword_recall, summary


class EvalRunner:
    """自动化评估管线 — 每次改 Prompt 后跑一遍, 对比指标变化"""

    def __init__(self, agent_graph=None, llm_client=None):
        self.graph = agent_graph
        self.results: list[dict] = []
        self.judge = LLMJudge(llm_client=llm_client)

    async def run_all(self, scenario=None, difficulty=None):
        """运行全部或筛选后的测试用例"""
        cases = get_test_cases(scenario, difficulty)
        print(f"[Eval] 开始评测: {len(cases)} 条用例")
        print(f"[Eval] 统计: {get_stats()}")

        for i, case in enumerate(cases):
            result = await self._run_single(case, i + 1, len(cases))
            self.results.append(result)

        report = summary(self.results)
        self._print_report(report)
        self._save_report(report)
        return report

    async def _run_single(self, case: dict, index: int, total: int) -> dict:
        """运行单条测试用例"""
        query = case["query"]
        expected_intent = case["expected_intent"]
        expected_keywords = case.get("expected_keywords", [])

        sys.stdout.write(f"  [{index}/{total}] {query[:30]}... ")
        sys.stdout.flush()

        start = time.time()
        try:
            predicted_intent, answer = await self._invoke_agent(query)
            latency = time.time() - start

            # 维度 1: LLM-as-Judge 打分
            judge_result = await self.judge.evaluate(query, answer, expected_keywords)

            # 维度 2: 关键词召回
            kw_recall = keyword_recall(answer, expected_keywords)

            # 维度 3: 意图分类
            intent_correct = predicted_intent == expected_intent

            # 综合
            judge_ok = judge_result.get("overall") in ("PASS", "WEAK_PASS")
            passed = judge_ok and kw_recall >= 0.5 and intent_correct

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
                "passed": False,
                "error": str(e),
            }

    async def _invoke_agent(self, query: str) -> tuple[str, str]:
        """调用 Agent 返回 (intent, answer)"""
        from smart_qa.agent.graph import get_agent

        graph = self.graph or get_agent()
        session_id = f"eval_{int(time.time())}_{id(query)}"
        state = {
            "messages": [{"role": "user", "content": query}],
            "user_id": "eval",
            "session_id": session_id,
            "intent": None,
            "scenario": None,
            "step": 0,
            "max_steps": 15,
            "max_execution_time": 60,
            "tool_calls_history": [],
            "final_answer": None,
            "error": None,
        }
        config = {"configurable": {"thread_id": state["session_id"]}}
        result = await graph.ainvoke(state, config=config)
        intent = result.get("intent", "general") or "general"
        answer = result.get("final_answer", "") or ""
        return intent, answer

    def _print_report(self, report: dict):
        print("\n" + "=" * 50)
        print("评测报告")
        print("=" * 50)
        print(f"总用例:      {report.get('total_cases', 0)}")
        print(f"意图准确率:  {report.get('intent_accuracy', 0):.1%}")
        print(f"关键词召回率: {report.get('avg_keyword_recall', 0):.1%}")
        print(f"平均延迟:    {report.get('avg_latency_seconds', 0):.2f}s")
        print(f"通过率:      {report.get('pass_rate', 0):.1%}")
        print(f"Judge分布:   {report.get('judge_breakdown', {})}")

    def _save_report(self, report: dict):
        """保存报告到文件"""
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(reports_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"summary": report, "details": self.results}, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {path}")


def cli():
    parser = argparse.ArgumentParser(description="Eval 评测运行器")
    parser.add_argument(
        "--scenario",
        type=str,
        default=os.environ.get("EVAL_SCENARIO"),
        help="筛选场景: qa/troubleshoot/consumables/...",
    )
    parser.add_argument(
        "--difficulty", type=str, default=os.environ.get("EVAL_DIFFICULTY"), help="筛选难度: easy/medium/hard"
    )
    args = parser.parse_args()

    async def main():
        runner = EvalRunner(llm_client=None)
        await runner.run_all(scenario=args.scenario, difficulty=args.difficulty)

    asyncio.run(main())


if __name__ == "__main__":
    cli()

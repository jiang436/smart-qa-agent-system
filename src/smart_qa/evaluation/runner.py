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
            predicted_intent, answer, contexts = await self._invoke_agent(query)
            latency = time.time() - start

            # 维度 1: LLM-as-Judge 打分
            judge_result = await self.judge.evaluate(query, answer, expected_keywords)

            # 维度 2: RAG Triad（context_relevance / faithfulness / answer_relevance）
            from smart_qa.evaluation.metrics import evaluate_rag_triad
            rag_triad = evaluate_rag_triad(query, answer, contexts, self.judge.llm) if contexts else {}

            # 维度 3: 关键词召回
            kw_recall = keyword_recall(answer, expected_keywords)

            # 维度 4: 意图分类
            intent_correct = predicted_intent == expected_intent

            # 综合判定
            judge_ok = judge_result.get("overall") in ("PASS", "WEAK_PASS")
            # device_control / sql_query 类型不依赖关键词召回（指令型查询）
            action_intents = ("device_control", "sql_query", "general")
            kw_pass = kw_recall >= 0.5 or expected_intent in action_intents
            passed = judge_ok and kw_pass and intent_correct

            # RAG Triad 单行显示
            triad_str = ""
            if rag_triad:
                triad_str = (
                    f" ctx={rag_triad.get('context_relevance', 0):.2f}"
                    f" faith={rag_triad.get('faithfulness', 0):.2f}"
                    f" ans={rag_triad.get('answer_relevance', 0):.2f}"
                )

            print(
                f"{'PASS' if passed else 'FAIL'} "
                f"(judge={judge_result.get('overall', '?')} "
                f"intent={intent_correct} "
                f"kw={kw_recall:.2f}{triad_str} "
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
                "rag_triad": rag_triad,
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
                "rag_triad": {},
                "passed": False,
                "error": str(e),
            }

    async def _invoke_agent(self, query: str) -> tuple[str, str, list[str]]:
        """调用 Agent 返回 (intent, answer, contexts)

        contexts: 检索到的文档列表，用于 RAG Triad 评测。
        """
        from smart_qa.agent.graph import get_agent

        graph = self.graph or get_agent()
        state = {
            "messages": [{"role": "user", "content": query}],
            "user_id": "eval",
            "session_id": f"eval_{int(time.time())}",
            "intent": None,
            "scenario": None,
            "step": 0,
            "max_steps": 15,
            "tool_calls_history": [],
            "final_answer": None,
            "retrieved_docs": [],
            "error": None,
        }
        config = {"configurable": {"thread_id": state["session_id"]}}
        result = await graph.ainvoke(state, config=config)
        intent = result.get("intent", "general") or "general"
        answer = result.get("final_answer", "") or ""
        # 提取检索上下文文本列表
        docs = result.get("retrieved_docs", []) or []
        contexts = []
        for d in docs:
            if isinstance(d, dict):
                contexts.append(d.get("content", ""))
            elif hasattr(d, "page_content"):
                contexts.append(d.page_content)
            elif isinstance(d, str):
                contexts.append(d)
        return intent, answer, contexts

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
    parser.add_argument(
        "--judge-llm", action="store_true", default=os.environ.get("EVAL_JUDGE_LLM") == "1",
        help="启用 LLM-as-Judge 打分（需要 LLM_API_KEY）"
    )
    args = parser.parse_args()

    async def main():
        # 确保 LLM 客户端注册到 DI 容器（eval 不走 web lifespan，需手动注册）
        from smart_qa.deps import get_llm_client
        from smart_qa.di import container

        try:
            llm = get_llm_client()
            container.register("llm", llm)
            print("[Eval] LLM 客户端已注册到 DI 容器")
        except Exception as e:
            print(f"[Eval] LLM 客户端注册失败（将用关键词降级）: {e}")

        # 若启用 LLM judge，使用同一个客户端
        judge_llm = container.get_optional("llm") if args.judge_llm else None
        if args.judge_llm and judge_llm:
            print("[Eval] LLM-as-Judge 已启用")
        elif args.judge_llm:
            print("[Eval] LLM-as-Judge 无可用客户端，降级为关键词模式")
        else:
            print("[Eval] 关键词模式（--judge-llm 可启用 LLM 评分）")

        runner = EvalRunner(llm_client=judge_llm)
        await runner.run_all(scenario=args.scenario, difficulty=args.difficulty)

    asyncio.run(main())


if __name__ == "__main__":
    cli()

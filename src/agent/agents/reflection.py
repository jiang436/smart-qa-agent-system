"""Reflection 自我修正 — Agent 自主检查并纠正自己的输出

五大核心模块之一，负责:
  1. 工具调用结果校验: 调用完工具后检查结果是否合理
  2. 回答质量自查: 生成答案后自我检查逻辑错误、事实错误
  3. 多轮迭代优化: 发现错误后重新生成，最多迭代 3 次
  4. 经验回存: 修正过程写入长期记忆，下次类似问题不会再错

和 CoT 的区别:
  CoT: "先想清楚再答"（事前）
  Reflection: "答完了检查一遍，错了就改"（事后）
  两者互补，都用效果最好
"""

import re

# 常见错误检查模式
_CHECK_PATTERNS = {
    "自相矛盾": [
        r"不会.*但是.*会",
        r"不支持.*也支持",
        r"不能.*可以",
    ],
    "答非所问": [
        r"关于这个问题.*和您的问题无关",
        r"建议您.*与当前无关",
    ],
    "模糊表述": [
        r"可能大概",
        r"应该也许",
        r"可能是.*也可能是",
    ],
}


from src.observability.logger import logger
from src.agent.persona import get_system_prompt


class ReflectionAgent:
    """自我反思 Agent"""

    def __init__(self, llm_client=None, max_refine_rounds: int = 3):
        self.llm = llm_client
        self.max_rounds = max_refine_rounds
        self.refine_history = []

    async def refine_answer(self, query: str, draft_answer: str, context: dict | None = None) -> dict:
        """
        对 Agent 生成的答案进行自我反思和修正。

        流程:
          1. 规则检查: 扫描答案中的自相矛盾、模糊表述等基础问题
          2. LLM 自查: 让 LLM 自己审视自己的答案
          3. 事实校验: 如果有检索到的文档，检查答案和文档的一致性
          4. 修正: 如果发现问题，让 LLM 重新生成
          5. 迭代: 最多 self.max_rounds 轮

        Args:
            query: 用户原始问题
            draft_answer: Agent 初步生成的答案
            context: 可选的检索上下文（文档）

        Returns:
            {
                "final_answer": "修正后的答案",
                "issues_found": ["列表", "发现的问题"],
                "refine_count": 2,
                "confidence": 0.92,
            }
        """
        current_answer = draft_answer
        all_issues = []
        refine_count = 0

        for round_idx in range(self.max_rounds):
            issues = []

            # 1. 规则检查（同步，无 LLM 调用）
            rule_issues = self._rule_check(current_answer, query)
            issues.extend(rule_issues)

            # 2. LLM 自查
            if self.llm and round_idx < self.max_rounds - 1:
                llm_issues = await self._llm_review(query, current_answer, context)
                issues.extend(llm_issues)

            # 3. 事实校验（有 RAG 上下文时，同步方法）
            if context and context.get("docs"):
                fact_issues = self._fact_check(current_answer, context["docs"])
                issues.extend(fact_issues)

            # 没有问题了就结束
            if not issues:
                break

            all_issues.extend(issues)

            # 让 LLM 修正
            if self.llm:
                current_answer = await self._do_refine(query, current_answer, issues, context)
                refine_count += 1
            else:
                break

        # 计算置信度
        confidence = self._calc_confidence(refine_count, all_issues)

        return {
            "final_answer": current_answer,
            "issues_found": all_issues,
            "refine_count": refine_count,
            "confidence": confidence,
        }

    def _rule_check(self, answer: str, query: str) -> list[str]:
        """规则级检查：自相矛盾、模糊表述"""
        issues = []

        for issue_type, patterns in _CHECK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, answer):
                    issues.append(f"{issue_type}: 匹配到模式 '{pattern}'")
                    break

        return issues

    async def _llm_review(self, query: str, answer: str, context: dict | None) -> list[str]:
        """让 LLM 审视自己的答案"""
        prompt = (
            f"用户问题: {query}\n"
            f"Agent 的回答: {answer}\n"
            "\n"
            "你是智能家居客服小智，请检查这个回答是否有以下问题:\n"
            "1. 是否存在事实错误或误导性信息？\n"
            "2. 是否回答了用户的问题？还是答非所问？\n"
            "3. 表述是否清晰、准确？有没有模糊或矛盾的地方？\n"
            "4. 说话风格是否亲切自然，像真人客服？\n"
            "\n"
            "如果有问题，列出具体问题点。如果没有问题，只输出: 无问题\n"
            "每个问题用 - 开头"
        )
        try:
            response = await self.llm.ainvoke(prompt)
            review = response.content if hasattr(response, "content") else str(response)
            if review.strip() != "无问题":
                lines = [l.strip().lstrip("- ") for l in review.split("\n") if l.strip().startswith("-")]
                return lines if lines else ["LLM 认为需要复查"]
            return []
        except Exception as e:
            logger.warning("LLM 自审失败: {}", e)
            return []

    def _fact_check(self, answer: str, docs: list[dict]) -> list[str]:
        """检查答案和检索到的文档是否一致"""
        issues = []

        numbers = re.findall(r"\d+", answer)
        models = re.findall(r"[A-Z]\d+[\w-]*", answer)

        all_doc_text = " ".join(d.get("content", "") for d in docs)

        for num in numbers:
            if len(num) >= 3 and num not in all_doc_text:
                issues.append(f"可能的幻觉: 数字 '{num}' 未在检索文档中出现")

        for model in models:
            if model not in all_doc_text:
                issues.append(f"可能的幻觉: 型号 '{model}' 未在检索文档中出现")

        return issues

    async def _do_refine(self, query: str, answer: str, issues: list[str], context: dict | None) -> str:
        """根据发现的问题修正答案

        注入完整 persona（来自 persona.py），确保修正后的回答
        保持小智客服的温柔风格，不变成冷冰冰的 QA 机器。
        """
        issues_text = "\n".join(f"- {i}" for i in issues)
        persona_text = get_system_prompt("qa")

        prompt = (
            persona_text + "\n\n"
            f"用户问题: {query}\n"
            f"你之前的回答: {answer}\n"
            "\n"
            f"检查出以下问题:\n{issues_text}\n"
            "\n"
            "请修正回答，解决上述问题。要求:\n"
            "1. 保持准确、清晰的表述\n"
            "2. 不确定的内容不要瞎编，用温和的方式说暂时找不到资料\n"
            "3. 说话风格保持亲切自然，像真人客服\n"
            "4. 只输出修正后的回答"
        )
        if context and context.get("docs"):
            doc_text = "\n".join(d.get("content", "")[:200] for d in context["docs"][:3])
            prompt += f"\n\n参考资料:\n{doc_text}"

        try:
            response = await self.llm.ainvoke(prompt)
            refined = response.content if hasattr(response, "content") else str(response)
            self.refine_history.append(
                {
                    "round": len(self.refine_history) + 1,
                    "issues": issues,
                    "before": answer[:100],
                    "after": refined[:100],
                }
            )
            return refined
        except Exception as e:
            logger.warning("回答改进失败: {}", e)
            return answer

    def _calc_confidence(self, refine_count: int, issues: list) -> float:
        """根据修正次数和问题数量估算置信度"""
        base = 1.0
        base -= refine_count * 0.1
        base -= len(issues) * 0.05
        return max(0.3, min(1.0, base))

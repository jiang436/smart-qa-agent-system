"""评测指标 — RAG Triad + 经典指标

RAG 三元组 (RAG Triad):
  1. 上下文相关性 (Context Relevance)  — 检索回来的文档是否与问题相关
  2. 忠实度 (Faithfulness)            — 答案是否基于检索文档，有无幻觉
  3. 答案相关性 (Answer Relevance)     — 答案是否直接、完整地回答了问题

Usage:
    from smart_qa.evaluation.metrics import evaluate_rag_triad
    scores = evaluate_rag_triad(query, answer, contexts, llm_client)
"""

from __future__ import annotations

import re

from smart_qa.observability.logger import logger


# ═══════════════════════════════════════════
# RAG Triad — LLM-as-Judge
# ═══════════════════════════════════════════


def context_relevance(query: str, contexts: list[str], llm_client=None) -> float:
    """评估检索回来的上下文与问题的相关性

    如果检索到的文档跟问题无关，再好的 LLM 也答不对。
    0-1 分，1 = 所有上下文高度相关。
    """
    if not contexts:
        return 0.0

    ctx_text = "\n---\n".join(c[:300] for c in contexts[:5])
    prompt = (
        "评估以下检索结果与用户问题的相关性。\n"
        f"用户问题：{query}\n\n"
        f"检索到的文档：\n{ctx_text}\n\n"
        "请给出 0-1 之间的相关性分数（1=高度相关，0=完全无关），只输出数字："
    )

    if llm_client:
        try:
            resp = llm_client.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
            nums = re.findall(r"(\d+\.?\d*)", text)
            return float(nums[0]) if nums else _keyword_overlap_score(query, contexts)
        except Exception as e:
            logger.debug("context_relevance LLM 评估失败: {}", e)

    return _keyword_overlap_score(query, contexts)


def faithfulness(answer: str, contexts: list[str], llm_client=None) -> float | None:
    """评估答案是否忠实于检索文档（有无幻觉）

    把答案拆成断言，逐一查证是否能在上下文中找到依据。
    0-1 分，1 = 完全没有编造。
    无检索文档时返回 None（不参与平均计算）。
    """
    if not answer or not contexts:
        return None  # 无文档可核对 → 不评分

    ctx_text = "\n---\n".join(c[:300] for c in contexts[:5])
    prompt = (
        "评估以下答案是否完全基于所给文档，有无编造事实。\n"
        f"参考文档：\n{ctx_text}\n\n"
        f"生成的答案：{answer}\n\n"
        "请给出 0-1 之间的忠实度分数（1=完全基于文档，0=全是编造），只输出数字："
    )

    if llm_client:
        try:
            import asyncio

            async def _call():
                return await llm_client.ainvoke(prompt)

            # 在已有 event loop 中安全调用
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(llm_client.invoke, prompt)
                    resp = future.result(timeout=15.0)
            except RuntimeError:
                resp = llm_client.invoke(prompt)

            text = resp.content if hasattr(resp, "content") else str(resp)
            nums = re.findall(r"(\d+\.?\d*)", text)
            if nums:
                return float(nums[0])
        except Exception as e:
            logger.debug("faithfulness LLM 评估失败: {}", e)

    # 无 LLM 时用关键词重叠估算
    return _keyword_faithfulness(answer, contexts)


def _keyword_faithfulness(answer: str, contexts: list[str]) -> float:
    """无 LLM 时用关键词重叠估算忠实度"""
    import re as _re
    # 提取答案中的中文词
    ans_words = set(_re.findall(r"[\w一-鿿]{2,}", answer.lower()))
    if not ans_words:
        return 0.5
    ctx_text = " ".join(contexts).lower()
    hits = sum(1 for w in ans_words if w in ctx_text)
    return round(hits / len(ans_words), 4)


def answer_relevance(query: str, answer: str, llm_client=None) -> float:
    """评估答案是否直接、完整地回答了用户问题

    0-1 分，1 = 完美回答了问题。
    """
    if not answer:
        return 0.0

    prompt = (
        "评估以下答案是否直接、完整地回答了用户的问题。\n"
        f"用户问题：{query}\n"
        f"生成的答案：{answer}\n\n"
        "请给出 0-1 之间的答案相关性分数（1=完美回答，0=答非所问），只输出数字："
    )

    if llm_client:
        try:
            resp = llm_client.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
            nums = re.findall(r"(\d+\.?\d*)", text)
            return float(nums[0]) if nums else 0.5
        except Exception as e:
            logger.debug("answer_relevance LLM 评估失败: {}", e)

    return _keyword_answer_overlap(query, answer)


def evaluate_rag_triad(query: str, answer: str, contexts: list[str], llm_client=None) -> dict:
    """一次评估 RAG 三个维度

    无文档时返回空 dict（不参与统计）。
    忠实度 = None 时 overall 仅用 context + answer 加权。

    Returns:
        {
            "context_relevance": 0.85,
            "faithfulness": 0.92,       # 无文档时为 None
            "answer_relevance": 0.78,
            "overall": 0.85,
        }
    """
    if not contexts:
        return {}  # 无检索文档 → 不评分

    cr = context_relevance(query, contexts, llm_client)
    fa = faithfulness(answer, contexts, llm_client)
    ar = answer_relevance(query, answer, llm_client)

    # 加权：检索 0.3 + 忠实 0.4 + 答案 0.3（忠实度缺失时调整为 0.5 + 0.5）
    if fa is not None:
        overall = round(cr * 0.3 + fa * 0.4 + ar * 0.3, 4)
    else:
        overall = round(cr * 0.5 + ar * 0.5, 4)

    logger.info(
        "RAG Triad: context={:.3f} faith={} answer={:.3f} overall={:.3f}",
        cr, f"{fa:.3f}" if fa is not None else "N/A", ar, overall,
    )

    return {
        "context_relevance": round(cr, 4),
        "faithfulness": round(fa, 4) if fa is not None else None,
        "answer_relevance": round(ar, 4),
        "overall": overall,
    }


# ═══════════════════════════════════════════
# 关键词指标（无 LLM 时快速降级）
# ═══════════════════════════════════════════


def keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """关键词召回率"""
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


def _keyword_overlap_score(query: str, contexts: list[str]) -> float:
    """关键词重叠率 — 无 LLM 时降级"""
    q_words = set(re.findall(r"[\w一-鿿]{2,}", query.lower()))
    if not q_words or not contexts:
        return 0.0
    ctx_text = " ".join(contexts).lower()
    hits = sum(1 for w in q_words if w in ctx_text)
    return round(hits / len(q_words), 4)


def _keyword_answer_overlap(query: str, answer: str) -> float:
    """答案与问题关键词重叠 — 无 LLM 时降级"""
    q_words = set(re.findall(r"[\w一-鿿]{2,}", query.lower()))
    if not q_words or not answer:
        return 0.0
    a_lower = answer.lower()
    hits = sum(1 for w in q_words if w in a_lower)
    return round(hits / len(q_words), 4)


# ═══════════════════════════════════════════
# 经典检索指标（需标注数据集）
# ═══════════════════════════════════════════


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """上下文精确率: 检索到的 top-K 文档中，有多少是真正相关的"""
    if not relevant_ids or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if str(doc_id) in relevant_ids)
    return round(hits / k, 4)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """上下文召回率: 所有相关文档中，top-K 检索召回了多少"""
    if not relevant_ids or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if str(doc_id) in relevant_ids)
    return round(hits / len(relevant_ids), 4)


def f1_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """P@k 与 R@k 的调和平均"""
    p = precision_at_k(retrieved_ids, relevant_ids, k)
    r = recall_at_k(retrieved_ids, relevant_ids, k)
    return round(2 * p * r / (p + r), 4) if (p + r) > 0 else 0.0


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """MRR (Mean Reciprocal Rank): 第一个相关文档的排名倒数"""
    if not relevant_ids:
        return 0.0
    for i, doc_id in enumerate(retrieved_ids, start=1):
        if str(doc_id) in relevant_ids:
            return round(1.0 / i, 4)
    return 0.0


def average_precision(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """单查询的 AP (Average Precision)"""
    if not relevant_ids:
        return 0.0
    hits, total = 0.0, 0.0
    for i, doc_id in enumerate(retrieved_ids[:k], start=1):
        if str(doc_id) in relevant_ids:
            hits += 1.0
            total += hits / i
    return round(total / len(relevant_ids), 4)


def mean_average_precision(queries_retrieved: list[tuple[list[str], set[str]]], k: int = 10) -> float:
    """MAP (Mean Average Precision): 所有查询 AP 的均值"""
    if not queries_retrieved:
        return 0.0
    aps = [average_precision(ret, rel, k) for ret, rel in queries_retrieved]
    return round(sum(aps) / len(aps), 4)


# ═══════════════════════════════════════════
# n-gram 答案质量指标（需参考答案）
# ═══════════════════════════════════════════


def rouge_l(answer: str, reference: str) -> float:
    """ROUGE-L: 最长公共子序列的 F1"""
    if not reference or not answer:
        return 0.0
    lcs_len = _lcs_length(answer, reference)
    p = lcs_len / max(len(answer), 1)
    r = lcs_len / max(len(reference), 1)
    return round(2 * p * r / (p + r), 4) if (p + r) > 0 else 0.0


def _lcs_length(a: str, b: str) -> int:
    """最长公共子序列长度"""
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, ca in enumerate(a, 1):
        for j, cb in enumerate(b, 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if ca == cb else max(dp[i - 1][j], dp[i][j - 1])
    return dp[len(a)][len(b)]


def bleu(answer: str, reference: str, n: int = 2) -> float:
    """BLEU-N: n-gram 精确率 + 长度惩罚"""
    if not reference or not answer:
        return 0.0

    def _ngrams(text: str, n: int) -> set[str]:
        chars = list(text)
        return {"".join(chars[i : i + n]) for i in range(len(chars) - n + 1)}

    precisions = []
    for ngram_n in range(1, n + 1):
        ref_ngrams = _ngrams(reference, ngram_n)
        ans_ngrams = _ngrams(answer, ngram_n)
        if not ans_ngrams:
            precisions.append(0.0)
        else:
            hits = len(ans_ngrams & ref_ngrams)
            precisions.append(hits / len(ans_ngrams))

    geo_mean = sum(p / n for p in precisions)
    # 长度惩罚
    bp = min(1.0, len(answer) / max(len(reference), 1)) if len(answer) < len(reference) else 1.0
    return round(bp * geo_mean, 4)


# ═══════════════════════════════════════════
# 汇总报告
# ═══════════════════════════════════════════


def summary(results: list[dict]) -> dict:
    """生成评测汇总报告"""
    if not results:
        return {
            "total_cases": 0, "pass_count": 0, "pass_rate": 0,
            "intent_accuracy": 0, "avg_keyword_recall": 0,
            "avg_latency_seconds": 0, "judge_breakdown": {},
            "rag_triad_avg": {},
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

    # RAG Triad 汇总（过滤 None 值，无文档的查询不参与平均）
    triad_keys = ["context_relevance", "faithfulness", "answer_relevance", "overall"]
    triad_avg = {}
    triad_count = 0
    for key in triad_keys:
        vals = [
            r.get("rag_triad", {}).get(key)
            for r in results
            if r.get("rag_triad") and r.get("rag_triad", {}).get(key) is not None
        ]
        triad_avg[key] = round(sum(vals) / len(vals), 4) if vals else 0
        if key == "overall":
            triad_count = len(vals)

    return {
        "total_cases": total,
        "pass_count": passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "intent_accuracy": round(correct_intent / len(results), 4),
        "avg_keyword_recall": round(sum(kw_recalls) / len(kw_recalls), 4) if kw_recalls else 0,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "judge_breakdown": judge_breakdown,
        "rag_triad_avg": triad_avg,
        "rag_triad_coverage": f"{triad_count}/{total}",
    }

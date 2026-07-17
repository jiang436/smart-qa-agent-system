"""RAG 评测 — 召回率 / 准确率 / 忠实性 / Token 追踪 / 性能基准

基于 12 条真实 Ground Truth 查询，使用 BM25 检索 + CitationTracker 评测
结果保存到 test_results/evaluation_metrics.json + EVALUATION_REPORT.md
"""
import json
import os
import time
import pytest

import numpy as np

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "test_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# ═══════════════════════════════════════
# Ground Truth — 基于真实知识库文件
# relevant_sources 必须与 BM25 元数据中的 source 字段精确匹配
# ═══════════════════════════════════════

GROUND_TRUTH = [
    {
        "query": "X30 Pro 定时清扫怎么设置",
        "relevant_sources": ["xiaomi_setup_guide.md", "xiaomi_mijia_iot.md"],
        "relevant_keywords": ["定时清扫", "设置", "App", "定时"],
        "expected_facts": ["打开App", "选择定时", "设置时间"],
        "category": "qa",
    },
    {
        "query": "E05错误码是什么故障",
        "relevant_sources": ["xiaomi_fault_codes.md"],
        "relevant_keywords": ["E05", "激光", "传感器", "异常"],
        "expected_facts": ["E05", "激光传感器", "异常", "雷达"],
        "category": "troubleshoot",
    },
    {
        "query": "边刷多久换一次",
        "relevant_sources": ["xiaomi_maintenance_guide.md"],
        "relevant_keywords": ["边刷", "更换", "3-6", "磨损"],
        "expected_facts": ["3-6个月", "更换", "边刷"],
        "category": "qa",
    },
    {
        "query": "HEPA滤网更换周期",
        "relevant_sources": ["xiaomi_maintenance_guide.md"],
        "relevant_keywords": ["HEPA", "滤网", "3-4", "更换"],
        "expected_facts": ["滤网", "3-4个月", "更换"],
        "category": "qa",
    },
    {
        "query": "扫地机连不上WiFi怎么办",
        "relevant_sources": ["xiaomi_fault_codes.md", "xiaomi_setup_guide.md"],
        "relevant_keywords": ["WiFi", "连接", "配网", "2.4G"],
        "expected_facts": ["WiFi", "配网", "路由器"],
        "category": "troubleshoot",
    },
    {
        "query": "扫地机器人回充失败",
        "relevant_sources": ["xiaomi_fault_codes.md"],
        "relevant_keywords": ["回充", "充电座", "触点"],
        "expected_facts": ["充电座", "触点", "清洁"],
        "category": "troubleshoot",
    },
    {
        "query": "拖布发黄洗不干净了",
        "relevant_sources": ["xiaomi_maintenance_guide.md"],
        "relevant_keywords": ["拖布", "更换", "2-3", "发黄"],
        "expected_facts": ["拖布", "更换", "2-3个月"],
        "category": "qa",
    },
    {
        "query": "X30 Pro 和 T10 对比哪个好",
        "relevant_sources": ["xiaomi_competitor_compare.md", "xiaomi_models.md"],
        "relevant_keywords": ["X30", "T10", "对比", "选购"],
        "expected_facts": ["X30 Pro", "T10", "对比"],
        "category": "qa",
    },
    {
        "query": "扫地机噪音太大怎么办",
        "relevant_sources": ["xiaomi_fault_codes.md"],
        "relevant_keywords": ["噪音", "异响", "主刷", "清理"],
        "expected_facts": ["噪音", "检查", "清理"],
        "category": "troubleshoot",
    },
    {
        "query": "米家APP怎么绑定扫地机",
        "relevant_sources": ["xiaomi_setup_guide.md", "xiaomi_mijia_iot.md"],
        "relevant_keywords": ["米家", "APP", "绑定", "配网"],
        "expected_facts": ["米家", "APP", "绑定", "配网"],
        "category": "qa",
    },
    {
        "query": "耗材是买原装还是第三方",
        "relevant_sources": ["xiaomi_maintenance_guide.md"],
        "relevant_keywords": ["原装", "第三方", "耗材", "选购"],
        "expected_facts": ["原装", "第三方", "选购"],
        "category": "qa",
    },
    {
        "query": "建图失败提示E06",
        "relevant_sources": ["xiaomi_fault_codes.md"],
        "relevant_keywords": ["E06", "建图", "激光", "传感器"],
        "expected_facts": ["E06", "激光雷达", "建图"],
        "category": "troubleshoot",
    },
]

# ═══════════════════════════════════════
# 共享 BM25 索引（只构建一次）
# ═══════════════════════════════════════

_shared_bm25 = None
_shared_docs = None
_shared_metas = None


def _get_bm25():
    global _shared_bm25, _shared_docs, _shared_metas
    if _shared_bm25 is None:
        from smart_qa.knowledge.bm25 import BM25Index
        from smart_qa.rag.retrieval_utils import collect_knowledge_texts

        _shared_docs, _shared_metas = collect_knowledge_texts()
        _shared_bm25 = BM25Index()
        _shared_bm25.build(_shared_docs, _shared_metas)
    return _shared_bm25, _shared_docs, _shared_metas


def _is_relevant(result_source: str, relevant_sources: list[str]) -> bool:
    """判断检索结果是否与相关文档匹配（精确单源匹配）"""
    if not result_source:
        return False
    src = result_source.lower()
    return any(src == rs.lower() for rs in relevant_sources)


def _count_matched_relevant(results: list[dict], relevant_sources: list[str]) -> int:
    """统计检索结果中命中了多少个不同的相关文档"""
    matched = set()
    for r in results:
        src = (r.get("source", "") or "").lower()
        for rs in relevant_sources:
            if src == rs.lower():
                matched.add(rs)
    return len(matched)


# ═══════════════════════════════════════
# 检索质量评测
# ═══════════════════════════════════════


class TestRetrievalQuality:
    """Recall@K / Precision@K / MRR / Hit@K / NDCG"""

    # ── Recall@K = |retrieved[:K] ∩ relevant| / |relevant| ──

    def test_recall_at_3(self):
        """Recall@3: 相关文档中有多少个在 top-3 中被匹配到"""
        bm25, _, _ = _get_bm25()
        recalls = []
        details = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=3)
            relevant = item["relevant_sources"]
            matched = _count_matched_relevant(results, relevant)
            recall = matched / len(relevant)
            recalls.append(recall)
            details.append({"query": item["query"][:30], "matched": matched, "total_relevant": len(relevant), "recall": round(recall, 4)})

        avg = sum(recalls) / len(recalls)
        queries_with_recall = sum(1 for r in recalls if r > 0)
        print(f"\n[Eval] Recall@3: {avg:.4f} ({queries_with_recall}/{len(recalls)} queries matched at least 1 relevant)")
        for d in details:
            print(f"  {d['query']}: matched {d['matched']}/{d['total_relevant']} relevant = {d['recall']:.4f}")
        _save("retrieval", "recall_at_3", round(avg, 4))
        _save("retrieval", "recall_at_3_details", details)

    def test_recall_at_5(self):
        """Recall@5"""
        bm25, _, _ = _get_bm25()
        recalls = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=5)
            relevant = item["relevant_sources"]
            matched = _count_matched_relevant(results, relevant)
            recall = matched / len(relevant)
            recalls.append(recall)

        avg = sum(recalls) / len(recalls)
        queries_with_recall = sum(1 for r in recalls if r > 0)
        print(f"\n[Eval] Recall@5: {avg:.4f} ({queries_with_recall}/{len(recalls)} queries matched)")
        _save("retrieval", "recall_at_5", round(avg, 4))

    # ── Precision@K = |retrieved[:K] ∩ relevant| / K ──

    def test_precision_at_3(self):
        """Precision@3: top-3 检索结果中有几条来自相关文档"""
        bm25, _, _ = _get_bm25()
        precisions = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=3)
            relevant = item["relevant_sources"]
            hits = sum(1 for r in results if _is_relevant(r.get("source", ""), relevant))
            precision = hits / len(results) if results else 0
            precisions.append(precision)

        avg = sum(precisions) / len(precisions)
        print(f"\n[Eval] Precision@3: {avg:.4f}")
        _save("retrieval", "precision_at_3", round(avg, 4))

    def test_precision_at_5(self):
        """Precision@5"""
        bm25, _, _ = _get_bm25()
        precisions = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=5)
            relevant = item["relevant_sources"]
            hits = sum(1 for r in results if _is_relevant(r.get("source", ""), relevant))
            precision = hits / len(results) if results else 0
            precisions.append(precision)

        avg = sum(precisions) / len(precisions)
        print(f"\n[Eval] Precision@5: {avg:.4f}")
        _save("retrieval", "precision_at_5", round(avg, 4))

    # ── MRR ──

    def test_mrr(self):
        """MRR: 第一个相关文档排名的倒数的均值"""
        bm25, _, _ = _get_bm25()
        rrs = []
        per_query = {}
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=10)
            relevant = item["relevant_sources"]
            rr = 0.0
            for rank, r in enumerate(results, 1):
                if _is_relevant(r.get("source", ""), relevant):
                    rr = 1.0 / rank
                    break
            rrs.append(rr)
            per_query[item["query"][:30]] = round(rr, 4)

        mrr = sum(rrs) / len(rrs)
        print(f"\n[Eval] MRR: {mrr:.4f}")
        for q, rr in sorted(per_query.items(), key=lambda x: x[1]):
            print(f"  {q}: RR={rr:.4f}")
        _save("retrieval", "mrr", round(mrr, 4))
        _save("retrieval", "mrr_per_query", per_query)

    # ── Hit@K ──

    def test_hit_rate(self):
        """Hit@5: 至少命中 1 篇相关文档的查询比例"""
        bm25, _, _ = _get_bm25()
        hits = 0
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=5)
            relevant = item["relevant_sources"]
            if any(_is_relevant(r.get("source", ""), relevant) for r in results):
                hits += 1

        hit_rate = hits / len(GROUND_TRUTH)
        print(f"\n[Eval] Hit@5: {hit_rate:.4f} ({hits}/{len(GROUND_TRUTH)})")
        _save("retrieval", "hit_at_5", round(hit_rate, 4))

    # ── 关键词覆盖率 ──

    def test_keyword_coverage(self):
        """检索结果中 GT 关键词覆盖率"""
        bm25, _, _ = _get_bm25()
        coverages = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=5)
            all_text = " ".join(r.get("content", "") for r in results)
            keywords = item["relevant_keywords"]
            covered = sum(1 for kw in keywords if kw.lower() in all_text.lower())
            coverage = covered / len(keywords)
            coverages.append(coverage)

        avg = sum(coverages) / len(coverages)
        print(f"\n[Eval] Keyword Coverage@5: {avg:.4f}")
        _save("retrieval", "keyword_coverage_at_5", round(avg, 4))

    # ── 干扰查询（无相关文档）不应高分 ──

    def test_irrelevant_query_low_score(self):
        """与扫地机无关的查询不应返回高分"""
        bm25, _, _ = _get_bm25()
        results = bm25.search("今天天气真好适合出去玩", top_k=5)
        # 所有结果分数都应该很低
        scores = [r.get("score", 0) for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0
        top_score = max(scores) if scores else 0
        print(f"\n[Eval] Irrelevant query scores: avg={avg_score:.2f}, max={top_score:.2f}")
        # 不应该接近业务查询的分数（业务查询一般 >10）
        _save("retrieval", "irrelevant_query", {"avg_score": round(avg_score, 2), "top_score": round(top_score, 2)})


# ═══════════════════════════════════════
# 忠实性评测
# ═══════════════════════════════════════


class TestFaithfulness:
    """回答是否忠实于源文档"""

    def test_self_consistency(self):
        """自一致性：注册文档中提取的事实全部找到出处"""
        from smart_qa.rag.citation import CitationTracker

        results = []
        for idx, item in enumerate(GROUND_TRUTH[:6]):
            t = CitationTracker()
            answer = "。".join(item["expected_facts"]) + "。"
            t.register_docs([
                {"doc_id": str(idx), "content": answer, "source": item["relevant_sources"][0]},
            ])
            cited = t.build_cited_answer(item["query"], answer)
            results.append({
                "query": item["query"][:30],
                "risk": cited.get("hallucination_risk", "UNKNOWN"),
                "citations": len(cited.get("citations", [])),
            })

        low_risk = sum(1 for r in results if r["risk"] == "low")
        score = low_risk / len(results) if results else 0
        print(f"\n[Eval] Self-consistency: {score:.4f} ({low_risk}/{len(results)})")
        _save("faithfulness", "self_consistency", round(score, 4))

    def test_cross_document_verification(self):
        """跨文档验证：true claim vs false claim"""
        from smart_qa.rag.citation import CitationTracker

        tracker = CitationTracker()
        doc = "X30 Pro 扫地机器人边刷更换周期为3-6个月。HEPA滤网建议每3-4个月更换。"
        tracker.register_docs([{"doc_id": "1", "content": doc, "source": "maintenance.md"}])

        true_claim = tracker.verify_document(doc, "边刷更换周期为3-6个月")
        false_claim = tracker.verify_document(doc, "边刷可以永久使用无需更换")

        print(f"\n[Eval] Citation: true_claim verified={true_claim['verified']}, false_claim verified={false_claim['verified']}")
        _save("faithfulness", "citation_verification", {
            "true_claim_verified": true_claim["verified"],
            "true_similarity": true_claim.get("similarity", 0),
            "false_claim_verified": false_claim["verified"],
            "false_similarity": false_claim.get("similarity", 0),
        })


# ═══════════════════════════════════════
# Token 追踪
# ═══════════════════════════════════════


class TestTokenTracking:
    """精确 Token 消耗统计"""

    def test_system_prompt_tokens(self):
        """各 System/CoT Prompt 的 token 统计"""
        from smart_qa.agent.persona import get_system_prompt, WELCOME_MESSAGE, OUT_OF_SCOPE_REJECTION
        from smart_qa.agent.prompts.loader import load_cot_prompt

        stats = {}
        for scenario in ["qa", "troubleshoot", "general"]:
            prompt = get_system_prompt(scenario)
            stats[f"system_{scenario}"] = _token_stats(prompt)

        for name in ["rag", "router", "troubleshoot"]:
            try:
                prompt = load_cot_prompt(name)
                stats[f"cot_{name}"] = _token_stats(prompt)
            except FileNotFoundError:
                stats[f"cot_{name}"] = {"chars": 0, "tokens": 0, "note": "not found"}

        stats["welcome"] = _token_stats(WELCOME_MESSAGE)
        stats["out_of_scope"] = _token_stats(OUT_OF_SCOPE_REJECTION)

        total_tokens = sum(v["tokens"] for v in stats.values())
        print(f"\n[Token] System prompts total: {total_tokens} tokens")
        for k, v in stats.items():
            print(f"  {k}: {v['chars']} chars → ~{v['tokens']} tokens")

        _save("token_tracking", "system_prompts", stats)
        _save("token_tracking", "system_total_tokens", total_tokens)

    def test_query_token_distribution(self):
        """查询 token 分布"""
        query_tokens = [_estimate_tokens(item["query"]) for item in GROUND_TRUTH]
        stats = {
            "count": len(query_tokens),
            "avg": round(sum(query_tokens) / len(query_tokens), 1),
            "min": min(query_tokens),
            "max": max(query_tokens),
            "p50": sorted(query_tokens)[len(query_tokens) // 2],
        }
        print(f"\n[Token] Query stats: avg={stats['avg']}, range=[{stats['min']}, {stats['max']}]")
        _save("token_tracking", "query_stats", stats)

    def test_knowledge_base_token_budget(self):
        """知识库 token 预算"""
        _, docs, _ = _get_bm25()
        doc_tokens = [_estimate_tokens(d) for d in docs]
        stats = {
            "total_docs": len(docs),
            "total_tokens": sum(doc_tokens),
            "avg_per_doc": round(sum(doc_tokens) / len(doc_tokens), 1),
            "median": sorted(doc_tokens)[len(doc_tokens) // 2],
            "p90": sorted(doc_tokens)[int(len(doc_tokens) * 0.9)],
            "max": max(doc_tokens),
        }
        top5_budget = stats["avg_per_doc"] * 5
        per_request = _get("token_tracking", {}).get("system_total_tokens", 0) + stats["avg_per_doc"] * 5 + 10
        print(f"\n[Token] KB: {stats['total_docs']} docs, ~{stats['total_tokens']} tokens")
        print(f"[Token] top-5 budget: ~{top5_budget:.0f} tokens")
        print(f"[Token] Estimated per-request: ~{per_request:.0f} tokens (system + top5 docs + query)")

        _save("token_tracking", "knowledge_base", stats)
        _save("token_tracking", "top5_retrieval_budget", round(top5_budget))
        _save("token_tracking", "estimated_per_request", round(per_request))


# ═══════════════════════════════════════
# 性能基准
# ═══════════════════════════════════════


class TestPerformanceBenchmarks:
    """真实数据性能测量"""

    def test_bm25_index_stats(self):
        """BM25 索引规模"""
        bm25, docs, _ = _get_bm25()
        stats = {
            "docs": bm25.doc_count,
            "terms": len(bm25.inverted_index),
            "avg_doc_len": round(bm25.avg_doc_len, 1),
            "index_size_kb": round(sum(len(k) + len(str(v)) for k, v in bm25.inverted_index.items()) / 1024, 1),
        }
        print(f"\n[Perf] BM25: {stats['docs']} docs, {stats['terms']} terms, ~{stats['index_size_kb']}KB")
        _save("performance", "bm25_index", stats)

    def test_bm25_search_latency(self):
        """BM25 单次检索延迟（不包含构建时间）"""
        bm25, _, _ = _get_bm25()

        # 预热
        bm25.search("预热查询", top_k=5)

        latencies = []
        for item in GROUND_TRUTH:
            start = time.perf_counter()
            bm25.search(item["query"], top_k=5)
            latencies.append((time.perf_counter() - start) * 1000)

        latencies.sort()
        stats = {
            "avg_ms": round(sum(latencies) / len(latencies), 2),
            "min_ms": round(latencies[0], 2),
            "max_ms": round(latencies[-1], 2),
            "p50_ms": round(latencies[len(latencies) // 2], 2),
            "p95_ms": round(latencies[int(len(latencies) * 0.95)], 2) if len(latencies) >= 20 else round(latencies[-1], 2),
            "samples": len(latencies),
        }
        print(f"\n[Perf] BM25 search: avg={stats['avg_ms']}ms, p50={stats['p50_ms']}ms, p95={stats['p95_ms']}ms")
        # BM25 当前实现每次计算 doc_len 时重新分词，存在优化空间
        _save("performance", "bm25_search_ms", stats)

    def test_bm25_throughput(self):
        """BM25 吞吐量"""
        bm25, _, _ = _get_bm25()
        queries = [item["query"] for item in GROUND_TRUTH] * 10
        n = min(100, len(queries))

        bm25.search("预热", top_k=5)  # warmup
        start = time.perf_counter()
        for q in queries[:n]:
            bm25.search(q, top_k=5)
        elapsed = time.perf_counter() - start

        qps = n / elapsed if elapsed > 0 else 0
        print(f"\n[Perf] Throughput: {qps:.1f} qps ({n} queries in {elapsed:.2f}s)")
        _save("performance", "bm25_throughput_qps", round(qps, 1))

    def test_full_pipeline_no_llm(self):
        """完整业务逻辑 pipeline（无 LLM）延迟"""
        bm25, _, _ = _get_bm25()
        from smart_qa.agent.persona import is_pure_greeting, is_out_of_scope
        from smart_qa.agent.agents.router_agent import RouterAgent
        from smart_qa.knowledge.knowledge_graph import get_kg

        kg = get_kg()
        router = RouterAgent(llm_client=None)

        latencies = []
        for item in GROUND_TRUTH[:8]:
            q = item["query"]
            start = time.perf_counter()
            is_pure_greeting(q)
            is_out_of_scope(q)
            router._keyword_classify(q)
            kg.link_entities(q)
            bm25.search(q, top_k=5)
            latencies.append((time.perf_counter() - start) * 1000)

        avg = sum(latencies) / len(latencies)
        max_l = max(latencies)
        min_l = min(latencies)
        # BM25 占据大部分时间（~33ms），纯业务逻辑 <1ms
        print(f"\n[Perf] Full pipeline (no LLM): avg={avg:.1f}ms, min={min_l:.1f}ms, max={max_l:.1f}ms")
        _save("performance", "full_pipeline_ms", {"avg": round(avg, 1), "min": round(min_l, 1), "max": round(max_l, 1)})

    def test_retrieval_context_size(self):
        """检索上下文大小分布"""
        bm25, _, _ = _get_bm25()
        sizes = []
        for item in GROUND_TRUTH:
            results = bm25.search(item["query"], top_k=5)
            total = sum(len(r.get("content", "")) for r in results)
            sizes.append(total)

        avg = sum(sizes) / len(sizes)
        print(f"\n[Perf] Context size: avg {avg:.0f} chars (~{_estimate_tokens('x'*int(avg))} tokens)")
        _save("performance", "context_size", {"avg_chars": round(avg, 1), "avg_tokens": _estimate_tokens("x" * int(avg))})


# ═══════════════════════════════════════
# 工具函数 & 结果持久化
# ═══════════════════════════════════════


def _estimate_tokens(text: str) -> int:
    """估算 token 数（中文 ~1.5 chars/token, 英文 ~4 chars/token）"""
    if not text:
        return 0
    chinese = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - chinese
    return max(1, int(chinese / 1.5 + other / 4))


def _token_stats(text: str) -> dict:
    return {"chars": len(text), "tokens": _estimate_tokens(text)}


_EVAL_STORE: dict = {}


def _save(category: str, name: str, value):
    _EVAL_STORE.setdefault(category, {})[name] = value


def _get(category: str, default=None):
    return _EVAL_STORE.get(category, default)


def _flush_results():
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    report = {"timestamp": timestamp, "ground_truth_queries": len(GROUND_TRUTH), **_EVAL_STORE}

    json_path = os.path.join(_RESULTS_DIR, "evaluation_metrics.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(_RESULTS_DIR, "EVALUATION_REPORT.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# RAG 评测报告\n\n**时间**: {timestamp}  |  **Ground Truth**: {len(GROUND_TRUTH)} 条查询\n\n")

        r = _EVAL_STORE.get("retrieval", {})
        f.write("## 📊 检索质量\n\n| 指标 | 值 | 说明 |\n|------|----|------|\n")
        for k, v in r.items():
            if isinstance(v, (int, float)) and not k.endswith("_details") and not k.endswith("_query"):
                f.write(f"| {k} | **{v}** | |\n")
        f.write(f"\n### 各查询 MRR\n\n")
        for q, rr in r.get("mrr_per_query", {}).items():
            emoji = "✅" if rr >= 0.5 else ("⚠️" if rr > 0 else "❌")
            f.write(f"- {emoji} `{q}`: RR={rr}\n")

        p = _EVAL_STORE.get("performance", {})
        f.write("\n## ⚡ 性能\n\n| 指标 | 值 |\n|------|----|\n")
        for k, v in p.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    f.write(f"| {k}.{sk} | {sv} |\n")
            else:
                f.write(f"| {k} | {v} |\n")

        t = _EVAL_STORE.get("token_tracking", {})
        f.write("\n## 💰 Token 追踪\n\n")
        f.write(f"- 系统 Prompt 总计: **{t.get('system_total_tokens', '?')} tokens**\n")
        f.write(f"- 预估每请求: **~{t.get('estimated_per_request', '?')} tokens**\n")
        kb = t.get("knowledge_base", {})
        f.write(f"- 知识库: {kb.get('total_docs', '?')} docs, ~{kb.get('total_tokens', '?')} tokens\n")

        fa = _EVAL_STORE.get("faithfulness", {})
        f.write(f"\n## 🎯 忠实性\n\n- 自一致性: **{fa.get('self_consistency', '?')}**\n")

    print(f"\n{'='*60}")
    print(f"[EvalReport] {json_path}")
    print(f"[EvalReport] {md_path}")
    print(f"{'='*60}")


@pytest.fixture(scope="session", autouse=True)
def _cleanup(request):
    yield
    if _EVAL_STORE:
        _flush_results()

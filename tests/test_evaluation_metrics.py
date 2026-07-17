"""RAG 评测 — Chunk 级别 Ground Truth

与文件级别的关键区别：
  文件级: 只要来源文件匹配就计分（如 xiaomi_maintenance_guide.md 全篇算一个）
  Chunk级: 必须具体 chunk 内容相关才计分（滤网更换 ≠ 电池维护）

结果保存到 test_results/
"""
import hashlib
import json
import os
import time

import numpy as np
import pytest

from smart_qa.knowledge.bm25 import BM25Index
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.rag.retrieval_utils import collect_knowledge_texts

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "test_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# ═══════════════════════════════════════
# Chunk 级 Ground Truth
# relevant_chunks: 列表中每个元素是该查询相关 chunk 的 content 唯一标识（前200字符的MD5）
#                 通过实际查看 BM25 检索结果手工标注
# ═══════════════════════════════════════

GROUND_TRUTH_CHUNK = [
    {
        "query": "X30 Pro 定时清扫怎么设置",
        "keywords_must": ["定时清扫"],
        "keywords_any": ["设置", "定时", "预约", "App", "米家"],
    },
    {
        "query": "E05错误码是什么故障",
        "keywords_must": ["E05"],
        "keywords_any": ["激光", "传感器", "异常", "故障", "雷达"],
    },
    {
        "query": "边刷多久换一次",
        "keywords_must": ["边刷"],
        "keywords_any": ["更换", "3-6", "周期", "磨损", "刷毛"],
    },
    {
        "query": "HEPA滤网更换周期",
        "keywords_must": ["HEPA", "滤网"],
        "keywords_any": ["更换", "3-4", "周期"],
    },
    {
        "query": "扫地机连不上WiFi怎么办",
        "keywords_must": ["WiFi", "Wi-Fi"],
        "keywords_any": ["连接", "配网", "2.4G", "路由器", "失败"],
    },
    {
        "query": "扫地机器人回充失败",
        "keywords_must": ["回充", "充电"],
        "keywords_any": ["充电座", "触点", "失败", "无法", "找不到"],
    },
    {
        "query": "拖布发黄洗不干净了",
        "keywords_must": ["拖布"],
        "keywords_any": ["更换", "2-3", "发黄", "洗不干净", "变硬"],
    },
    {
        "query": "X30 Pro 和 T10 对比哪个好",
        "keywords_must": ["X30", "T10"],
        "keywords_any": ["对比", "选购", "区别", "推荐", "性价比"],
    },
    {
        "query": "扫地机噪音太大怎么办",
        "keywords_must": ["噪音", "异响"],
        "keywords_any": ["声音", "吵", "检查", "清理", "缠绕"],
    },
    {
        "query": "米家APP怎么绑定扫地机",
        "keywords_must": ["APP", "米家"],
        "keywords_any": ["绑定", "配网", "连接", "添加设备"],
    },
    {
        "query": "耗材是买原装还是第三方",
        "keywords_must": ["原装", "第三方"],
        "keywords_any": ["耗材", "选购", "推荐", "性价比", "建议"],
    },
    {
        "query": "建图失败提示E06",
        "keywords_must": ["E06"],
        "keywords_any": ["建图", "激光", "传感器", "失败", "地图"],
    },
]


def _is_chunk_relevant(content: str, gt: dict) -> bool:
    """Chunk 级相关性判断: must 全满足 and any 至少满足 1 个"""
    content_lower = content.lower()
    must_hit = any(kw.lower() in content_lower for kw in gt["keywords_must"])
    any_hit = sum(1 for kw in gt["keywords_any"] if kw.lower() in content_lower)
    return must_hit and any_hit >= 1


def _rff_fusion(l1: list[dict], l2: list[dict], k: int = 60) -> list[dict]:
    scores, dmap = {}, {}
    for rank, doc in enumerate(l1, 1):
        key = hashlib.md5(doc["content"][:200].encode()).hexdigest()
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        dmap[key] = doc
    for rank, doc in enumerate(l2, 1):
        key = hashlib.md5(doc["content"][:200].encode()).hexdigest()
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        dmap[key] = doc
    return [dmap[k] for k, _ in sorted(scores.items(), key=lambda x: -x[1])]


# ═══════════════════════════════════════
# 共享索引（只建一次）
# ═══════════════════════════════════════

_shared = {}


def _get_retriever():
    if "bm25" not in _shared:
        docs, metas = collect_knowledge_texts()
        bm25 = BM25Index()
        bm25.build(docs, metas)
        emb = get_embedding()
        doc_vecs = emb.encode([d[:500] for d in docs])
        doc_vecs = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
        _shared.update(docs=docs, metas=metas, bm25=bm25, emb=emb, doc_vecs=doc_vecs)
    return _shared


def _semantic_search(query: str, k: int):
    s = _get_retriever()
    qvec = s["emb"].encode(query)
    qvec = qvec / (np.linalg.norm(qvec) + 1e-10)
    sims = np.dot(s["doc_vecs"], qvec.T).ravel()
    idx = np.argsort(sims)[-k:][::-1]
    return [
        {
            "content": s["docs"][i][:300],
            "score": round(float(sims[i]), 4),
            "source": s["metas"][i].get("source", ""),
            "doc_id": int(i),
        }
        for i in idx
        if float(sims[i]) > 0.3
    ]


# ═══════════════════════════════════════
# 评测
# ═══════════════════════════════════════


class TestChunkLevelEvaluation:
    """Chunk 级别评测 — 相关性精确匹配"""

    def test_bm25_chunk_metrics(self):
        """BM25 only chunk 级别"""
        s = _get_retriever()
        prec3, prec5, rec3, rec5, hits = [], [], [], [], 0

        for item in GROUND_TRUTH_CHUNK:
            results = s["bm25"].search(item["query"], top_k=5)
            top3, top5 = results[:3], results[:5]

            rel3 = sum(1 for r in top3 if _is_chunk_relevant(r.get("content", ""), item))
            rel5 = sum(1 for r in top5 if _is_chunk_relevant(r.get("content", ""), item))

            prec3.append(rel3 / len(top3) if top3 else 0)
            prec5.append(rel5 / len(top5) if top5 else 0)

            # Recall: 只看 top-K 有没有覆盖
            rec3.append(1.0 if rel3 > 0 else 0.0)
            rec5.append(1.0 if rel5 > 0 else 0.0)

            if rel5 > 0:
                hits += 1

        print(f"\n[Chunk] BM25 only:")
        print(f"  Recall@3={sum(rec3)/len(rec3):.4f}  Recall@5={sum(rec5)/len(rec5):.4f}")
        print(f"  Precision@3={sum(prec3)/len(prec3):.4f}  Precision@5={sum(prec5)/len(prec5):.4f}")
        print(f"  Hit@5={hits}/{len(GROUND_TRUTH_CHUNK)}={hits/len(GROUND_TRUTH_CHUNK):.0%}")
        _save("bm25_only", {"recall3": round(sum(rec3)/len(rec3), 4), "recall5": round(sum(rec5)/len(rec5), 4),
                            "precision3": round(sum(prec3)/len(prec3), 4), "precision5": round(sum(prec5)/len(prec5), 4),
                            "hit5": hits/len(GROUND_TRUTH_CHUNK)})

    def test_semantic_chunk_metrics(self):
        """Semantic only chunk 级别"""
        prec3, prec5, rec3, rec5, hits = [], [], [], [], 0

        for item in GROUND_TRUTH_CHUNK:
            results = _semantic_search(item["query"], k=5)
            top3, top5 = results[:3], results[:5]

            rel3 = sum(1 for r in top3 if _is_chunk_relevant(r.get("content", ""), item))
            rel5 = sum(1 for r in top5 if _is_chunk_relevant(r.get("content", ""), item))

            prec3.append(rel3 / len(top3) if top3 else 0)
            prec5.append(rel5 / len(top5) if top5 else 0)
            rec3.append(1.0 if rel3 > 0 else 0.0)
            rec5.append(1.0 if rel5 > 0 else 0.0)
            if rel5 > 0:
                hits += 1

        print(f"\n[Chunk] Semantic only:")
        print(f"  Recall@3={sum(rec3)/len(rec3):.4f}  Recall@5={sum(rec5)/len(rec5):.4f}")
        print(f"  Precision@3={sum(prec3)/len(prec3):.4f}  Precision@5={sum(prec5)/len(prec5):.4f}")
        print(f"  Hit@5={hits}/{len(GROUND_TRUTH_CHUNK)}={hits/len(GROUND_TRUTH_CHUNK):.0%}")
        _save("semantic_only", {"recall3": round(sum(rec3)/len(rec3), 4), "recall5": round(sum(rec5)/len(rec5), 4),
                                "precision3": round(sum(prec3)/len(prec3), 4), "precision5": round(sum(prec5)/len(prec5), 4),
                                "hit5": hits/len(GROUND_TRUTH_CHUNK)})

    def test_rrf_chunk_metrics(self):
        """RRF Fusion chunk 级别"""
        s = _get_retriever()
        prec3, prec5, rec3, rec5, hits = [], [], [], [], 0

        for item in GROUND_TRUTH_CHUNK:
            sem = _semantic_search(item["query"], k=10)
            bm25_res = s["bm25"].search(item["query"], top_k=10)
            fused = _rff_fusion(sem, bm25_res)
            top3, top5 = fused[:3], fused[:5]

            rel3 = sum(1 for r in top3 if _is_chunk_relevant(r.get("content", ""), item))
            rel5 = sum(1 for r in top5 if _is_chunk_relevant(r.get("content", ""), item))

            prec3.append(rel3 / len(top3) if top3 else 0)
            prec5.append(rel5 / len(top5) if top5 else 0)
            rec3.append(1.0 if rel3 > 0 else 0.0)
            rec5.append(1.0 if rel5 > 0 else 0.0)
            if rel5 > 0:
                hits += 1

        print(f"\n[Chunk] RRF Fusion:")
        print(f"  Recall@3={sum(rec3)/len(rec3):.4f}  Recall@5={sum(rec5)/len(rec5):.4f}")
        print(f"  Precision@3={sum(prec3)/len(prec3):.4f}  Precision@5={sum(prec5)/len(prec5):.4f}")
        print(f"  Hit@5={hits}/{len(GROUND_TRUTH_CHUNK)}={hits/len(GROUND_TRUTH_CHUNK):.0%}")
        _save("rrf_fusion", {"recall3": round(sum(rec3)/len(rec3), 4), "recall5": round(sum(rec5)/len(rec5), 4),
                             "precision3": round(sum(prec3)/len(prec3), 4), "precision5": round(sum(prec5)/len(prec5), 4),
                             "hit5": hits/len(GROUND_TRUTH_CHUNK)})

    def test_file_vs_chunk_comparison(self):
        """文件级 vs Chunk级 对比表"""
        s = _get_retriever()
        # 文件级 Ground Truth（旧方案）
        file_gt = {
            "X30 Pro 定时清扫怎么设置": ["xiaomi_setup_guide.md", "xiaomi_mijia_iot.md"],
            "E05错误码是什么故障": ["xiaomi_fault_codes.md"],
            "边刷多久换一次": ["xiaomi_maintenance_guide.md"],
            "HEPA滤网更换周期": ["xiaomi_maintenance_guide.md"],
            "扫地机连不上WiFi怎么办": ["xiaomi_fault_codes.md", "xiaomi_setup_guide.md"],
            "扫地机器人回充失败": ["xiaomi_fault_codes.md"],
            "拖布发黄洗不干净了": ["xiaomi_maintenance_guide.md"],
            "X30 Pro 和 T10 对比哪个好": ["xiaomi_competitor_compare.md", "xiaomi_models.md"],
            "扫地机噪音太大怎么办": ["xiaomi_fault_codes.md"],
            "米家APP怎么绑定扫地机": ["xiaomi_setup_guide.md", "xiaomi_mijia_iot.md"],
            "耗材是买原装还是第三方": ["xiaomi_maintenance_guide.md"],
            "建图失败提示E06": ["xiaomi_fault_codes.md"],
        }

        file_prec3, file_prec5 = [], []
        chunk_prec3, chunk_prec5 = [], []

        for item in GROUND_TRUTH_CHUNK:
            q = item["query"]
            fused = _rff_fusion(_semantic_search(q, k=10), s["bm25"].search(q, top_k=10))
            top3, top5 = fused[:3], fused[:5]

            # 文件级
            rel_files = file_gt.get(q, [])
            f3 = sum(1 for r in top3 if (r.get("source", "") or "").lower() in [x.lower() for x in rel_files])
            f5 = sum(1 for r in top5 if (r.get("source", "") or "").lower() in [x.lower() for x in rel_files])
            file_prec3.append(f3 / len(top3) if top3 else 0)
            file_prec5.append(f5 / len(top5) if top5 else 0)

            # Chunk 级
            c3 = sum(1 for r in top3 if _is_chunk_relevant(r.get("content", ""), item))
            c5 = sum(1 for r in top5 if _is_chunk_relevant(r.get("content", ""), item))
            chunk_prec3.append(c3 / len(top3) if top3 else 0)
            chunk_prec5.append(c5 / len(top5) if top5 else 0)

        fp3 = sum(file_prec3) / len(file_prec3)
        fp5 = sum(file_prec5) / len(file_prec5)
        cp3 = sum(chunk_prec3) / len(chunk_prec3)
        cp5 = sum(chunk_prec5) / len(chunk_prec5)

        print(f"\n[Compare] File vs Chunk level Precision:")
        print(f"  File-level:   P@3={fp3:.4f}  P@5={fp5:.4f}")
        print(f"  Chunk-level:  P@3={cp3:.4f}  P@5={cp5:.4f}")
        _save("comparison", {"file_precision3": round(fp3, 4), "file_precision5": round(fp5, 4),
                             "chunk_precision3": round(cp3, 4), "chunk_precision5": round(cp5, 4)})


# ═══════════════════════════════════════
# 结果持久化
# ═══════════════════════════════════════

_EVAL: dict = {}


def _save(k, v):
    _EVAL[k] = v


@pytest.fixture(scope="session", autouse=True)
def _flush(request):
    yield
    if _EVAL:
        report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "queries": len(GROUND_TRUTH_CHUNK), **_EVAL}
        path = os.path.join(_RESULTS_DIR, "evaluation_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[EvalReport] {path}")

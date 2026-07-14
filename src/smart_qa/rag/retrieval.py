"""四层召回兜底引擎 — 语义→改写→关键词→LLM

召回兜底不是简单的"搜不到就说不知道"，而是四层降级:
  语义搜不到就改写，改写还不行就用关键词，最后才降级到 LLM 自身知识。
  每一层都标注置信度和来源，让后续 LLM 知道"这是官方手册"还是"凭知识回答"。

面试要点:
  "为什么不一直用语义检索？语义检索依赖 Embedding 质量，遇到领域术语
   （如'E05故障码'）Embedding 可能偏离，这时关键词检索反而更准。"

Usage:
    retriever = MultiLayerRetriever(vector_store=milvus, llm=llm, bm25=bm25)
    result = retriever.retrieve("扫地机不走了")
    # result["source"]: "L1_semantic" | "L2_rewrite" | "L3_bm25" | "L4_llm"
    # result["confidence"]: "high" | "medium" | "low"
"""

import re
import threading

from smart_qa.knowledge.bm25 import BM25Index
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.observability.logger import logger
from smart_qa.rag.reranker import Reranker

# ── 停用词 ──
_STOP_WORDS: set[str] = {
    "的",
    "了",
    "是",
    "在",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "那",
    "些",
    "什么",
    "怎么",
    "如何",
    "为什么",
    "吗",
    "呢",
    "吧",
    "啊",
    "哦",
    "嗯",
}
_shared_bm25 = None
_doc_vectors = None  # 预计算的文档向量 (N x 512)
_load_lock = threading.Lock()


def _load_knowledge_bm25():
    """懒加载: 首次调用时构建 BM25 + 预计算 BGE 向量

    和 Milvus 使用完全相同的文档源 + 分块策略，
    确保两个索引的知识覆盖一致。

    Thread-safe: 使用双重检查锁（double-checked locking）。
    """
    global _shared_bm25, _doc_vectors
    if _shared_bm25 is not None:
        return _shared_bm25

    with _load_lock:
        if _shared_bm25 is not None:
            return _shared_bm25

        bm = BM25Index()
        docs = _collect_knowledge_texts()
        if docs:
            bm.build(docs)
            _shared_bm25 = bm
            emb = get_embedding()
            _doc_vectors = emb.encode(docs)
            logger.info("知识库 BM25 加载完成 docs={} vectors_shape={}", len(docs), _doc_vectors.shape)
    return _shared_bm25


def set_shared_bm25(bm25):
    """外部注入 BM25 实例（由 web.py lifespan 调用）"""
    with _load_lock:
        global _shared_bm25
        _shared_bm25 = bm25


def _collect_knowledge_texts() -> list[str]:
    """收集所有可索引知识文本 — 和 Milvus 使用完全相同的数据源

    来源:
      1. data/knowledge/ 下的 md/txt/pdf（DocumentParser + SmartDocumentSplitter）
      2. FAQ JSON 文件
      3. 内置默认知识（目录为空时兜底）
    """
    import json
    import os

    from smart_qa.knowledge.document_parser import DocumentParser
    from smart_qa.rag.chunking import SmartDocumentSplitter

    parser = DocumentParser()
    splitter = SmartDocumentSplitter(chunk_size=500, chunk_overlap=50)
    texts: list[str] = []

    # ── 1. data/knowledge/ 目录 ──
    if os.path.isdir("data/knowledge"):
        for root, _dirs, files in os.walk("data/knowledge"):
            for f in sorted(files):
                filepath = os.path.join(root, f)
                if not DocumentParser.is_supported(filepath):
                    continue
                try:
                    content = parser.extract_text(filepath)
                except Exception:
                    continue
                if not content.strip():
                    continue
                doc_type = SmartDocumentSplitter.detect_type(f, content)
                chunks = splitter.split(content, doc_type, {"source": f})
                for c in chunks:
                    txt = c.get("content", "").strip()
                    if len(txt) > 20:
                        texts.append(txt)

    # ── 2. FAQ JSON ──
    for faq_file in [
        "data/faq_knowledge_base.json",
        "data/faq_consumables.json",
        "data/faq_troubleshooting.json",
    ]:
        try:
            with open(faq_file, encoding="utf-8") as fh:
                faq_data = json.load(fh)
        except Exception:
            continue
        entries = faq_data if isinstance(faq_data, list) else faq_data.get("entries", [])
        for entry in entries:
            q = entry.get("question", "")
            a = entry.get("answer", "")
            if q and a and len(q + a) > 30:
                texts.append(f"问：{q}\n答：{a}")

    # ── 3. 默认知识（目录为空时兜底） ──
    if not texts:
        try:
            from smart_qa.scripts.init_vector_store import DEFAULT_KNOWLEDGE

            for category, content in DEFAULT_KNOWLEDGE.items():
                doc_type = SmartDocumentSplitter.detect_type(f"builtin/{category}.md", content)
                chunks = splitter.split(content, doc_type, {"source": f"builtin/{category}.md"})
                for c in chunks:
                    texts.append(c.get("content", ""))
        except ImportError:
            pass

    return texts


def _load_knowledge_bm25():
    """懒加载: 首次调用时构建 BM25 + 预计算 BGE 向量

    和 Milvus 使用完全相同的文档源 + 分块策略，
    确保两个索引的知识覆盖一致。
    """
    global _shared_bm25, _doc_vectors
    if _shared_bm25 is not None:
        return _shared_bm25

    bm = BM25Index()
    docs = _collect_knowledge_texts()
    if docs:
        bm.build(docs)
        _shared_bm25 = bm
        # 预计算所有文档的 BGE 向量（用于 L3 BM25 召回后的语义重排）
        emb = get_embedding()
        _doc_vectors = emb.encode(docs)
        logger.info("知识库 BM25 加载完成 docs={} vectors_shape={}", len(docs), _doc_vectors.shape)
    return _shared_bm25


class MultiLayerRetriever:
    """多层召回引擎: 语义→改写→关键词→LLM"""

    L1_THRESHOLD = 0.75
    L1_MIN_HITS = 3
    L2_THRESHOLD = 0.6
    L2_MIN_HITS = 2

    def __init__(self, milvus_client=None, llm_client=None, bm25_index=None):
        self.embedding = get_embedding()
        self.milvus = milvus_client
        self.llm = llm_client
        self.bm25 = bm25_index or _load_knowledge_bm25() or BM25Index()
        self._bm25_built = self.bm25.doc_count > 0
        self.reranker = Reranker()

    # ── 主入口 ──

    def retrieve(self, query: str, top_k: int = 10, mode: str = "cascade") -> dict:
        """检索主入口（带 Reranker 重排序）

        Args:
            query: 用户问题
            top_k: 返回文档数（reranker 从更多候选中精选）
            mode: "cascade" (串行降级) | "parallel" (并行+RRF融合)

        流程:
          1. 内部先取更多文档 (top_k * 3, 至少 20) 保证召回率
          2. Reranker Cross-Encoder 精确打分
          3. 返回精选的 top_k 条
        """
        # 内部多取一些, 供 reranker 精选
        retrieve_k = max(top_k * 3, 20)

        if mode == "parallel":
            result = self._parallel_retrieve(query, retrieve_k)
        else:
            result = self._cascade_retrieve(query, retrieve_k)

        # Reranker 重排序
        docs = result.get("docs", [])
        if len(docs) > top_k and self.reranker:
            docs = self.reranker.rerank(query, docs, top_k=top_k)
            result["docs"] = docs
            result["total"] = len(docs)
            result["note"] = (result.get("note", "") + f" | Reranker {len(docs)}/{retrieve_k}").lstrip(" |").strip()

        return result

    def _cascade_retrieve(self, query: str, top_k: int) -> dict:
        """四层召回，逐层降级

        Returns:
            {
                "docs": [...],
                "source": "L1_semantic" | "L2_rewrite" | "L3_bm25" | "L4_llm",
                "confidence": "high" | "medium" | "low",
                "query_used": str,
                "note": str,
                "total": int,
            }
        """
        # ═══ L1: 语义检索 ═══
        logger.info("L1 语义检索 query={}", query[:80])
        docs = self._semantic_search(query, top_k)

        if len(docs) >= self.L1_MIN_HITS and self._avg_score(docs) >= self.L1_THRESHOLD:
            logger.info("L1 命中 hits={} avg_score={:.3f}", len(docs), self._avg_score(docs))
            return self._build(
                docs, "L1_semantic", "high", query, f"语义检索命中 {len(docs)} 条, 平均分 {self._avg_score(docs):.2f}"
            )

        # ═══ L2: Query 改写 + Expansion ═══
        logger.info("L2 Query 改写 (L1 未命中, hits={})", len(docs))
        rewritten = self._rewrite_query(query) if self.llm else None
        expanded = self._expand_query(query) if not rewritten else rewritten

        if rewritten and rewritten != query:
            docs_rw = self._semantic_search(rewritten, top_k)
            if len(docs_rw) >= self.L2_MIN_HITS and self._avg_score(docs_rw) >= self.L2_THRESHOLD:
                logger.info("L2 命中 (改写) hits={} avg_score={:.3f}", len(docs_rw), self._avg_score(docs_rw))
                return self._build(
                    docs_rw, "L2_rewrite", "medium", rewritten, f"原始 query '{query[:40]}' → 改写为 '{rewritten[:40]}'"
                )

        # 改写没命中 → 用扩展后的 query 再试
        if expanded and expanded != query:
            docs_exp = self._semantic_search(expanded, top_k)
            if len(docs_exp) >= self.L2_MIN_HITS and self._avg_score(docs_exp) >= self.L2_THRESHOLD:
                logger.info("L2 命中 (扩展) hits={} avg_score={:.3f}", len(docs_exp), self._avg_score(docs_exp))
                return self._build(
                    docs_exp, "L2_rewrite", "medium", expanded, f"Query Expansion: '{query[:30]}' → '{expanded[:50]}'"
                )

        # 合并改写 + 扩展 + 原始结果中的高分段
        all_docs = docs + (docs_rw if rewritten else []) + (docs_exp if expanded else [])
        all_docs = self._dedup_and_sort(all_docs)[:top_k]
        if len(all_docs) >= self.L2_MIN_HITS:
            avg = sum(d.get("score", 0) for d in all_docs) / len(all_docs)
            if avg >= self.L2_THRESHOLD:
                return self._build(
                    all_docs, "L2_rewrite", "medium", query, f"合并多路召回 {len(all_docs)} 条, 平均分 {avg:.2f}"
                )

        # ═══ L3: BM25 关键词检索 ═══
        logger.info("L3 BM25 关键词检索")
        if self._bm25_built:
            keywords = self._extract_keywords(query)
            bm25_docs = self.bm25.search(" ".join(keywords), top_k=5)
            if bm25_docs:
                logger.info("L3 命中 (BM25) hits={} keywords={}", len(bm25_docs), keywords[:5])
                return self._build(
                    bm25_docs, "L3_bm25", "medium", query, f"语义检索未命中, 通过关键词 '{' '.join(keywords[:5])}' 召回"
                )

        # ═══ L4: LLM 自身知识 ═══
        logger.warning("L4 兜底 — 知识库无结果, 使用 LLM 自身知识")
        return self._build([], "L4_llm", "low", query, "以下内容基于模型自身知识, 非官方资料, 仅供参考")

    # ── L1: 语义检索 ──

    def _semantic_search(self, query: str, top_k: int) -> list[dict]:
        """向量检索: Milvus → 预计算 BGE 向量 → 空"""
        global _doc_vectors
        # 优先 Milvus
        if self.milvus:
            try:
                query_vec = self.embedding.encode(query)
                results = self.milvus.search(
                    data=[query_vec.tolist()],
                    anns_field="vector",
                    param={"metric_type": "IP", "params": {"nprobe": 10}},
                    limit=top_k,
                    output_fields=["content", "source"],
                    timeout=5,
                )
                return [
                    {
                        "content": hit.entity.get("content", ""),
                        "score": round(hit.score, 4),
                        "source": "L1_semantic",
                        "doc_id": hit.id,
                    }
                    for hits in results
                    for hit in hits
                ]
            except Exception as e:
                logger.warning("Milvus 检索异常: {}", e)

        # 降级: 预计算 BGE 向量做语义检索
        if self._bm25_built and _doc_vectors is not None and self.bm25.doc_count > 0:
            import numpy as _np

            query_vec = self.embedding.encode(query).ravel()  # (512,)
            # 矩阵乘法一次完成
            sims = _np.dot(_doc_vectors, query_vec) / (
                _np.linalg.norm(_doc_vectors, axis=1) * _np.linalg.norm(query_vec) + 1e-10
            )
            top_idx = _np.argsort(sims)[-top_k:][::-1]
            docs = []
            for idx in top_idx:
                sim = float(sims[idx])
                if sim > 0.35:
                    docs.append(
                        {
                            "content": self.bm25.documents[idx][:500],
                            "score": round(sim, 4),
                            "source": "L1_semantic",
                            "doc_id": int(idx),
                        }
                    )
            if docs:
                logger.info("语义检索 hits={} top={:.3f}", len(docs), docs[0]["score"])
            return docs
        return []

    # ── L2: Query 改写 + Expansion ──

    def _rewrite_query(self, query: str) -> str | None:
        """LLM Query 改写 — 将口语转为书面检索词

        例: "扫地机不走了" → "扫地机器人 停止工作 原因 排查"
        """
        if not self.llm:
            return None
        try:
            prompt = (
                "你是一个搜索查询改写器。将用户的口语问题改写为更规范的检索关键词。\n"
                "规则:\n"
                "1. 保持原意，不要添加或删除信息\n"
                "2. 用正式术语替换口语（如'不走了'→'停止工作'）\n"
                "3. 补充同义词, 用空格分隔关键词\n"
                "4. 去除语气词（'啊'、'呢'、'吗'）\n"
                "5. 只输出改写结果，不要解释\n\n"
                f"用户: {query}\n改写:"
            )
            response = self.llm.invoke(prompt)
            rewritten = response.content.strip() if hasattr(response, "content") else str(response).strip()
            return rewritten if rewritten and rewritten != query else None
        except Exception as e:
            logger.warning("L2 Query 改写失败: {}", e)
            return None

    def _expand_query(self, query: str) -> str | None:
        """Query Expansion — 添加同义词扩展

        例: "故障" → "故障 报错 异常 error"
        不使用 LLM，纯规则引擎，零延迟。
        """
        expansions = {
            "不工作": "停止工作 无法启动 没反应",
            "故障": "报错 异常 error 错误",
            "卡住": "卡死 无法移动 不动",
            "噪音": "异响 声音大 吵",
            "连不上": "连接失败 离线 断网 无法连接",
            "回充": "充电 回充座 找不到充电座",
            "边刷": "边刷 侧刷",
            "滤网": "滤网 HEPA 过滤网",
            "拖布": "拖布 抹布 拖地布",
            "耗材": "耗材 配件 耗材更换",
            "定时": "定时 预约 计划",
            "建图": "建图 地图 扫描 快速建图",
        }
        expanded_parts = [query]
        for key, exp in expansions.items():
            if key in query and key not in str(expanded_parts):
                expanded_parts.append(exp)
        result = " ".join(expanded_parts)
        return result if result != query else None

    # ── L3: BM25 关键词 ──

    def _extract_keywords(self, query: str) -> list[str]:
        """提取关键词 — 去停用词 + 保留型号/错误码

        优先用 jieba 分词，不可用时回退到基于正则的简单切分。
        """
        # 保留专用词: 型号 / 错误码 / 英文
        specials = re.findall(r"[A-Za-z]+\d+[\w-]*|[Ee]\d{2,3}", query)

        try:
            import jieba

            words = jieba.lcut(query)
        except ImportError:
            # 简单切分: 按停用词边界拆
            words = re.findall(r"[一-鿿]+|[A-Za-z\d]+", query)

        keywords = [w for w in words if len(w) > 1 and w not in _STOP_WORDS]
        return specials + keywords

    # ── 辅助方法 ──

    def _avg_score(self, docs: list[dict]) -> float:
        """计算文档列表的平均分"""
        if not docs:
            return 0.0
        return sum(d.get("score", 0) for d in docs) / len(docs)

    def _dedup_and_sort(self, docs: list[dict]) -> list[dict]:
        """去重并按分数降序排列"""
        seen = set()
        unique = []
        for d in sorted(docs, key=lambda x: x.get("score", 0), reverse=True):
            key = d.get("content", "")[:100]
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return unique

    # ── 并行检索 + RRF 融合 ──

    def _parallel_retrieve(self, query: str, top_k: int) -> dict:
        """并行检索 + RRF 融合排序

        流程:
          1. Query 改写 (LLM)
          2. 并行: 语义检索 (top_k=5) + BM25 关键词 (top_k=5)
          3. RRF (Reciprocal Rank Fusion) 融合排序
          4. 取最终 top_k

        RRF 公式:
          score(d) = Σ 1/(k + rank_i(d))
          其中 k=60 (经典配置), rank_i 是文档在第 i 路检索中的排名
        """
        logger.info("并行检索+RRF融合 query={}", query[:80])

        # 1. Query 改写
        rewritten = self._rewrite_query(query) if self.llm else None
        search_query = rewritten or query

        # 2. 并行检索
        semantic_docs = self._semantic_search(search_query, top_k=10)
        bm25_docs = self.bm25.search(query, top_k=10) if self._bm25_built else []

        logger.info("并行检索 semantic={} bm25={}", len(semantic_docs), len(bm25_docs))

        # 3. RRF 融合
        fused = self._rrf_fusion(
            [semantic_docs, bm25_docs],
            k=60,
            final_top_k=top_k,
        )

        if fused:
            return self._build(
                fused,
                "RRF_fusion",
                "high",
                search_query,
                f"RRF 融合 semantic({len(semantic_docs)}) + BM25({len(bm25_docs)}) → top_{len(fused)}",
            )

        # 融合无结果 → 降级 LLM
        logger.warning("RRF 融合无结果, 降级 LLM")
        return self._build([], "L4_llm", "low", query, "以下内容基于模型自身知识, 非官方资料, 仅供参考")

    def _rrf_fusion(
        self,
        ranked_lists: list[list[dict]],
        k: int = 60,
        final_top_k: int = 5,
    ) -> list[dict]:
        """RRF (Reciprocal Rank Fusion) 融合多路检索结果

        Args:
            ranked_lists: 多路检索结果, 每路已按 score 降序
            k: RRF 平滑参数 (经典值 60)
            final_top_k: 最终返回文档数

        Returns:
            融合后排好序的文档列表

        RRF 公式:
          score(d) = Σ 1/(k + rank_i(d))

        为什么用 RRF 而不是简单的分数加权?
          - 向量分数 (IP) 和 BM25 分数不在同一量纲, 不能直接加权
          - RRF 只关注排序位置, 不受量纲影响
          - k=60 对前 100 名区分度最好 (经典推荐配置)
        """
        if not ranked_lists or all(not lst for lst in ranked_lists):
            return []

        # doc_key → RRF 累计分数 + 文档内容
        rrf_scores: dict[str, dict] = {}

        for lst in ranked_lists:
            if not lst:
                continue
            for rank, doc in enumerate(lst, start=1):
                # 用 content 前 200 字符作为去重 key
                content = doc.get("content", "")
                key = content[:200].strip()

                rrf_score = 1.0 / (k + rank)

                if key in rrf_scores:
                    rrf_scores[key]["rrf_score"] += rrf_score
                    # 保留最高分的来源和分数
                    if doc.get("score", 0) > rrf_scores[key].get("orig_score", 0):
                        rrf_scores[key]["orig_score"] = doc["score"]
                        rrf_scores[key]["source"] = doc.get("source", "")
                else:
                    rrf_scores[key] = {
                        **doc,
                        "rrf_score": rrf_score,
                        "orig_score": doc.get("score", 0),
                    }

        # 按 RRF 分数降序
        sorted_docs = sorted(
            rrf_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        # 标注融合来源
        for d in sorted_docs[:final_top_k]:
            d["source"] = "RRF_fusion"

        return sorted_docs[:final_top_k]

    # ── 索引构建 ──

    def build_bm25_index(self, documents: list[str]):
        """构建 BM25 倒排索引"""
        self.bm25.build(documents)
        self._bm25_built = True

    def _build(self, docs, source, confidence, query_used, note):
        return {
            "docs": docs,
            "source": source,
            "confidence": confidence,
            "query_used": query_used or "",
            "note": note or "",
            "total": len(docs),
        }

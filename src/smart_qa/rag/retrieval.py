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

import asyncio
import hashlib
import json
import re

from smart_qa.config import settings
from smart_qa.di import container
from smart_qa.knowledge.bm25 import BM25Index
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.observability.logger import logger
from smart_qa.rag.retrieval_utils import (
    STOP_WORDS,
    collect_knowledge_texts,
    load_knowledge_bm25,
    register_bm25,
)

# ── 向后兼容别名 ──
_STOP_WORDS = STOP_WORDS
set_shared_bm25 = register_bm25
_load_knowledge_bm25 = load_knowledge_bm25
_collect_knowledge_texts = collect_knowledge_texts


class MultiLayerRetriever:
    """多层召回引擎: 语义→改写→关键词→LLM"""

    L1_THRESHOLD = 0.45
    L1_MIN_HITS = 2
    L2_THRESHOLD = 0.35
    L2_MIN_HITS = 1

    def __init__(self, milvus_client=None, llm_client=None, bm25_index=None, reranker=None):
        self.embedding = get_embedding()
        self.milvus = milvus_client
        self.llm = llm_client
        self.bm25 = bm25_index or _load_knowledge_bm25() or BM25Index()
        self._bm25_built = self.bm25.doc_count > 0
        self.reranker = reranker  # 可选：Reranker 实例

    # ── 主入口 ──

    def retrieve(self, query: str, top_k: int = 10, mode: str = "parallel") -> dict:
        """检索主入口

        流程:
          1. Multi-Query 复杂问题拆分
          2. 并行语义 + BM25 检索
          3. RRF 融合排序
          4. 句子窗口展开 → 拼接上下文
        """
        semantic_query = query

        # 0.5 Multi-Query: 仅复杂/长查询启用
        sub_queries = self._decompose_query(query) if (self.llm and len(query) > 15) else []
        if sub_queries:
            all_docs = []
            for sq in sub_queries:
                sub_result = self._parallel_retrieve(sq, sq, max(5, top_k))
                all_docs.extend(sub_result.get("docs", []))
            # 去重合并
            merged = self._dedup_and_sort(all_docs)[:top_k * 3]
            if merged:
                result = self._build(merged, "multi_query", "high", query,
                                     f"拆分为 {len(sub_queries)} 个子问题, 合并 {len(merged)} 条")
                logger.info("Multi-Query: {} → {} sub-queries, merged {} docs",
                             query[:60], len(sub_queries), len(merged))
                return result
            else:
                sub_queries = []  # 合并无结果 → 降级走正常检索

        if mode == "parallel":
            result = self._parallel_retrieve(query, semantic_query, top_k)
        else:
            result = self._cascade_retrieve(query, semantic_query, top_k)

        return result

    def _post_process(self, result, query, top_k, retrieve_k, meta_filter):
        """检索后处理: 元数据过滤 → ReRank → 窗口展开"""
        docs = result.get("docs", [])
        # Reranker 重排序
        if len(docs) > top_k and self.reranker:
            docs = self.reranker.rerank(query, docs, top_k=top_k)
            result["docs"] = docs
            result["total"] = len(docs)

        # 元数据过滤（Self-Query）
        docs = result.get("docs", [])
        if meta_filter and docs:
            before = len(docs)
            docs = self._apply_metadata_filter(docs, meta_filter)
            if docs:
                result["docs"] = docs
                result["total"] = len(docs)
                result["note"] = (result.get("note", "") + f" | MetaFilter {len(docs)}/{before}").strip()
                logger.info("元数据过滤: {} → {} docs filter={}", before, len(docs), meta_filter)

        # 句子窗口展开
        docs = result.get("docs", [])
        if docs:
            expanded = self._expand_context_window(docs)
            result["docs"] = expanded

        return result

    async def retrieve_async(self, query: str, top_k: int = 10, mode: str = "parallel") -> dict:
        """异步检索 — 在线程池中执行同步检索，避免阻塞事件循环

        用于 async 上下文中调用（如 RAGAgent.retrieve_and_generate）。
        底层 LLM 调用通过 asyncio.to_thread 在线程池执行。
        """
        return await asyncio.to_thread(self.retrieve, query, top_k, mode)

    def _cascade_retrieve(self, query: str, hyde_query: str = "", top_k: int = 10) -> dict:
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
        # ═══ L1: 语义检索（HyDE 优先）═══
        search_query = hyde_query if hyde_query else query
        source_tag = "L1_semantic" if search_query == query else "L1_semantic+hyde"
        logger.info("L1 语义检索 hyde={} query={}", hyde_query != "", search_query[:60])
        docs = self._semantic_search(search_query, top_k)

        if len(docs) >= self.L1_MIN_HITS and self._avg_score(docs) >= self.L1_THRESHOLD:
            logger.info("L1 命中 hits={} avg_score={:.3f}", len(docs), self._avg_score(docs))
            return self._build(
                docs, source_tag, "high", query,
                f"{'HyDE' if hyde_query else '语义'}检索命中 {len(docs)} 条, 平均分 {self._avg_score(docs):.2f}"
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
        doc_vectors = container.get_optional("doc_vectors")
        # 优先 Milvus
        if self.milvus:
            try:
                query_vec = self.embedding.encode(query)
                vec = [float(x) for x in query_vec.ravel()]
                results = self.milvus.search(
                    collection_name=settings.milvus_collection,
                    data=[vec],
                    anns_field="vector",
                    search_params={"metric_type": "COSINE", "params": {"ef": 128}},
                    limit=top_k,
                    output_fields=["content", "source"],
                )
                return [
                    {
                        "content": hit.entity.get("content", ""),
                        "score": round(hit.score, 4),
                        "source": hit.entity.get("source", "L1_semantic"),
                        "doc_id": hit.id,
                    }
                    for hits in results
                    for hit in hits
                ]
            except Exception as e:
                logger.warning("Milvus 检索异常: {}", e)

        # 降级: 预计算 BGE 向量做语义检索
        if self._bm25_built and doc_vectors is not None and self.bm25.doc_count > 0:
            import numpy as _np

            query_vec = self.embedding.encode(query).ravel()  # (512,)
            # 矩阵乘法一次完成
            sims = _np.dot(doc_vectors, query_vec) / (
                _np.linalg.norm(doc_vectors, axis=1) * _np.linalg.norm(query_vec) + 1e-10
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
            if key in query and exp not in expanded_parts:
                expanded_parts.append(exp)
        result = " ".join(expanded_parts)
        return result if result != query else None

    # ── Multi-Query: 复杂问题拆子问题 ──

    def _decompose_query(self, query: str) -> list[str]:
        """LLM 拆分复杂问题为多个简单子问题，分别检索后合并去重

        例:
          "X30 Pro和T10的边刷通用吗？分别多久换一次？"
          → ["X30 Pro边刷更换周期", "T10边刷更换周期", "X30 Pro与T10边刷兼容性"]
        """
        if not self.llm or len(query) < 15:
            return []

        prompt = (
            "判断用户问题是否包含多个子问题或对比多个事物。\n"
            "如果只有单个问题，输出 NONE。\n"
            "如果有多个子问题，拆分为独立的检索查询（每行一个），每个查询简洁明了，适合做关键词检索。\n\n"
            "规则:\n"
            "1. 保持原意，用正式术语（如'不走了'→'停止工作'）\n"
            "2. 涉及对比时，各方分别生成独立查询\n"
            "3. 最多拆成 4 个，每个不超过 30 字\n"
            "4. 先判断是否为多问题，单问题直接输出 NONE\n\n"
            f"用户问题: {query}\n"
            "输出（NONE 或每行一个子查询）:"
        )
        try:
            resp = self.llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
            text = text.strip()
            if "NONE" in text.upper() or not text:
                return []
            subs = [line.strip().lstrip("-0123456789. ").strip() for line in text.split("\n") if line.strip()]
            subs = [s for s in subs if len(s) > 3 and s != query]
            return subs[:4] if len(subs) > 1 else []
        except Exception as e:
            logger.debug("Multi-Query 分解失败: {}", e)
            return []

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

        keywords = [w for w in words if len(w) > 1 and w not in STOP_WORDS]
        return specials + keywords

    # ── 辅助方法 ──

    def _avg_score(self, docs: list[dict]) -> float:
        """计算文档列表的平均分"""
        if not docs:
            return 0.0
        return sum(d.get("score") or 0 for d in docs) / len(docs)

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

    def _parallel_retrieve(self, query: str, hyde_query: str = "", top_k: int = 10) -> dict:
        """并行检索 + RRF 融合排序（HyDE 增强语义检索）

        流程:
          1. HyDE 生成假设答案（可选）→ 替代 query 做语义检索
          2. 并行: 语义检索 + BM25 关键词
          3. RRF 融合排序
        """
        hyde_used = hyde_query and hyde_query != query
        logger.info("并行检索+RRF融合 query={} hyde={}", query[:60], hyde_used)

        # 语义检索用 HyDE 向量，BM25 用原始 query（保留精确匹配）
        semantic_query = hyde_query if hyde_query else query

        semantic_docs = self._semantic_search(semantic_query, top_k=10)
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
                query,
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
                # 用 content 前 300 字符的 MD5 作为去重 key，避免 hash randomization 和长文档误判
                content = doc.get("content", "")
                content_key = content[:300].strip()
                key = hashlib.md5(content_key.encode("utf-8")).hexdigest() if content_key else str(id(doc))

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

        return sorted_docs[:final_top_k]

    # ── 索引构建 ──

    def build_bm25_index(self, documents: list[str]):
        """构建 BM25 倒排索引"""
        self.bm25.build(documents)
        self._bm25_built = True

    def _expand_context_window(self, docs: list[dict], window: int = 1) -> list[dict]:
        """句子窗口展开 — 每个检索到的 chunk 拼接前后相邻 chunk

        原理（来自 Datawhale RAG 指南 §3.5）：
          检索用单句精确匹配 → 展开为上下文窗口 → 给 LLM 完整语境
          解决"搜到了但缺上下文"的问题。
        """
        if not self._bm25_built or not self.bm25.documents:
            return docs

        expanded = []
        for doc in docs:
            chunk_idx = doc.get("chunk_index")
            source = doc.get("source", "")
            if chunk_idx is None or source is None:
                expanded.append(doc)
                continue

            # 找同来源相邻 chunk
            neighbor_contents = []
            for offset in range(-window, window + 1):
                if offset == 0:
                    continue
                neighbor_idx = chunk_idx + offset
                if neighbor_idx < 0 or neighbor_idx >= len(self.bm25.documents):
                    continue
                # 通过 BM25 的 documents 列表按索引取（同次构建顺序与 chunk_index 一致）
                neighbor_doc = self.bm25.documents[neighbor_idx]
                if neighbor_doc and len(neighbor_doc) > 20:
                    neighbor_contents.append(neighbor_doc[:300])

            if neighbor_contents:
                new_doc = dict(doc)
                original = doc.get("content", "")
                # 前文 + 原文 + 后文
                prefix = "\n[上文]\n" + "\n".join(
                    neighbor_contents[:window]) if window > 0 else ""
                suffix = "\n[下文]\n" + "\n".join(
                    neighbor_contents[window:]) if len(neighbor_contents) > window else ""
                new_doc["content"] = prefix + "\n" + original + suffix
                new_doc["window_expanded"] = True
                expanded.append(new_doc)
            else:
                expanded.append(doc)

        return expanded

    # ── Self-Query: 元数据过滤 ──

    def _parse_metadata_filter(self, query: str) -> dict:
        """LLM 解析自然语言查询 → 提取元数据过滤条件

        例如:
          "X30 Pro的耗材怎么换" → {"header": "X30 Pro"}
          "故障E03怎么处理"     → {"category": "fault", "header": "E03"}
          "滤网多久换一次"      → {"header": "滤网"}    （header 模糊匹配）

        Returns:
            {"category": "fault", "header": "E03", "source": "xxx.md"}
            空 dict 表示不过滤
        """
        if not self.llm:
            return {}

        prompt = (
            "从用户问题中提取精确的检索过滤条件。只输出 JSON。\n\n"
            "可用过滤字段:\n"
            "  - category: \"consumables\"(耗材) / \"fault\"(故障) / \"manual\"(手册)\n"
            "  - header: 章节标题关键词，如\"X30 Pro\"、\"E03\"、\"边刷\"、\"滤网\"\n"
            "  - source: 文档文件名关键词\n\n"
            "规则:\n"
            "1. 只提取问题中明确提到的，不要猜测\n"
            "2. header 用短关键词（如\"边刷\"而非\"边刷怎么换\"）\n"
            "3. 如果没有明确过滤条件，输出 {}\n\n"
            f"用户问题: {query}\n"
            "JSON:"
        )
        try:
            resp = self.llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)

            json_match = re.search(r"\{[^{}]*\}", text)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            logger.debug("Self-Query 解析失败: {}", e)
        return {}

    def _apply_metadata_filter(self, docs: list[dict], meta_filter: dict) -> list[dict]:
        """对检索结果应用元数据过滤——宽松匹配，不满足的排到后面而不是删除

        策略: 命中的加分保持原位，未命中的降权但不丢弃（避免空结果）
        """
        if not meta_filter or not docs:
            return docs

        scored = []
        for doc in docs:
            bonus = 0.0
            doc_header = str(doc.get("header", "") or doc.get("section", ""))
            doc_category = str(doc.get("category", "") or "")
            doc_source = str(doc.get("source", "") or "")
            doc_content = str(doc.get("content", ""))

            # category 精确匹配
            if "category" in meta_filter:
                if meta_filter["category"] in doc_category:
                    bonus += 0.3
                elif meta_filter["category"] in doc_content:
                    bonus += 0.15

            # header 关键词匹配（模糊）
            if "header" in meta_filter:
                keyword = str(meta_filter["header"]).lower()
                if keyword in doc_header.lower():
                    bonus += 0.3
                elif keyword in doc_content.lower():
                    bonus += 0.1

            # source 匹配
            if "source" in meta_filter:
                if str(meta_filter["source"]).lower() in doc_source.lower():
                    bonus += 0.2

            doc["_meta_bonus"] = bonus
            scored.append(doc)

        # 按 bonus 降序：有元数据加分的排前面，没有的不删除
        scored.sort(key=lambda d: d.get("_meta_bonus", 0), reverse=True)
        return scored

    def _build(self, docs, source, confidence, query_used, note):
        return {
            "docs": docs,
            "source": source,
            "confidence": confidence,
            "query_used": query_used or "",
            "note": note or "",
            "total": len(docs),
        }

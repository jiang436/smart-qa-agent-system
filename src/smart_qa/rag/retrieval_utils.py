"""检索工具函数 — 停用词、BM25 加载、知识文本收集

从 retrieval.py 中提取，减少主文件体积，便于独立测试和维护。

Usage:
    from smart_qa.rag.retrieval_utils import STOP_WORDS, load_knowledge_bm25, collect_knowledge_texts
"""

from __future__ import annotations

import json
import os

from smart_qa.config import settings
from smart_qa.di import container
from smart_qa.knowledge.bm25 import BM25Index
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.observability.logger import logger

# ── 停用词 ──
STOP_WORDS: set[str] = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "它", "们", "那", "些", "什么", "怎么", "如何", "为什么",
    "吗", "呢", "吧", "啊", "哦", "嗯",
}


def register_bm25(bm25: BM25Index) -> None:
    """向 DI 容器注册共享 BM25 索引"""
    container.register("bm25", bm25)


def collect_knowledge_texts() -> list[str]:
    """收集所有可索引知识文本 — 与 Milvus 使用完全相同的数据源

    来源:
      1. data/knowledge/ 下的 md/txt/pdf（DocumentParser + SmartDocumentSplitter）
      2. FAQ JSON 文件
      3. 内置默认知识（目录为空时兜底）
    """
    from smart_qa.knowledge.document_parser import DocumentParser
    from smart_qa.rag.chunking import SmartDocumentSplitter

    parser = DocumentParser()
    splitter = SmartDocumentSplitter(chunk_size=500, chunk_overlap=50)
    texts: list[str] = []

    # ── 1. data/knowledge/ 目录 ──
    knowledge_dir = settings.get_knowledge_dir()
    if os.path.isdir(knowledge_dir):
        for root, _dirs, files in os.walk(knowledge_dir):
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
    for faq_file in settings.get_faq_file_list():
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


def load_knowledge_bm25() -> BM25Index:
    """懒加载: 首次调用时构建 BM25 + 预计算 BGE 向量

    和 Milvus 使用完全相同的文档源 + 分块策略，
    确保两个索引的知识覆盖一致。
    结果注册到 DI 容器，避免全局变量。
    """
    if container.has("bm25") and container.has("doc_vectors"):
        return container.get("bm25")

    bm = BM25Index()
    docs = collect_knowledge_texts()
    if docs:
        bm.build(docs)
        container.register("bm25", bm)
        # 预计算所有文档的 BGE 向量（用于 L3 BM25 召回后的语义重排）
        emb = get_embedding()
        doc_vectors = emb.encode(docs)
        container.register("doc_vectors", doc_vectors)
        logger.info("知识库 BM25 加载完成 docs={} vectors_shape={}", len(docs), doc_vectors.shape)
    return bm

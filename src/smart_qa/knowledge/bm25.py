"""BM25 关键词检索（L3 召回）—— 支持持久化到磁盘

BM25 和语义检索互补：
  - 语义检索: 理解"意思"（"怎么清尘盒" ↔ "如何清理集尘盒"）
  - BM25: 匹配"关键词"（"E05" ↔ "E05"）

为什么需要 BM25？
  1. 精确匹配: 错误码、型号名（X30 Pro）语义检索容易混淆
  2. 冷启动: 新文档刚加入时也能检索
  3. 互补性: 语义+BM25 混合召回效果 > 任何单一方式

持久化:
  BM25 索引保存到 data/bm25_index.pkl，启动时优先加载，
  知识库未变动时跳过重建。
"""

from __future__ import annotations

import math
import os
import pickle
import time
from collections import Counter
from datetime import datetime

from smart_qa.observability.logger import logger

_INDEX_PATH = "data/bm25_index.pkl"


class BM25Index:
    """BM25 倒排索引（带 save/load 持久化）"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[str] = []
        self.doc_count = 0
        self.avg_doc_len = 0.0
        self.inverted_index: dict[str, list[tuple[int, int]]] = {}
        self.built_at: float | None = None  # Unix 时间戳

    # ═══════════════════════════════════════
    # 构建
    # ═══════════════════════════════════════

    def build(self, documents: list[str]):
        """构建 BM25 倒排索引"""
        self.documents = documents
        self.doc_count = len(documents)
        total_len = 0
        self.inverted_index = {}

        for doc_id, doc in enumerate(documents):
            terms = self._tokenize(doc)
            term_counts = Counter(terms)
            total_len += len(terms)
            for term, count in term_counts.items():
                self.inverted_index.setdefault(term, []).append((doc_id, count))

        self.avg_doc_len = total_len / self.doc_count if self.doc_count > 0 else 1.0
        self.built_at = time.time()
        logger.info("BM25 索引构建完成 docs={} terms={}", self.doc_count, len(self.inverted_index))

    # ═══════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════

    def save(self, path: str = _INDEX_PATH):
        """序列化到磁盘"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "documents": self.documents,
            "doc_count": self.doc_count,
            "avg_doc_len": self.avg_doc_len,
            "inverted_index": self.inverted_index,
            "built_at": self.built_at,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logger.info("BM25 索引已保存 path={} docs={}", path, self.doc_count)

    def load(self, path: str = _INDEX_PATH) -> bool:
        """从磁盘加载，成功返回 True"""
        if not os.path.exists(path):
            return False
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.k1 = data["k1"]
            self.b = data["b"]
            self.documents = data["documents"]
            self.doc_count = data["doc_count"]
            self.avg_doc_len = data["avg_doc_len"]
            self.inverted_index = data["inverted_index"]
            self.built_at = data.get("built_at")
            logger.info("BM25 索引已加载 path={} docs={} terms={}", path, self.doc_count, len(self.inverted_index))
            return True
        except Exception as e:
            logger.warning("BM25 索引加载失败，将重建: {}", e)
            return False

    # ═══════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════

    @property
    def built_at_str(self) -> str:
        if self.built_at:
            return datetime.fromtimestamp(self.built_at).strftime("%Y-%m-%d %H:%M:%S")
        return ""

    @property
    def is_built(self) -> bool:
        return self.doc_count > 0

    def add_documents(self, new_docs: list[str]):
        """增量添加文档（上传文件后调用）"""
        start_count = self.doc_count
        total_len_so_far = self.avg_doc_len * self.doc_count

        for doc_id_offset, doc in enumerate(new_docs):
            terms = self._tokenize(doc)
            term_counts = Counter(terms)
            doc_id = self.doc_count + doc_id_offset
            total_len_so_far += len(terms)
            for term, count in term_counts.items():
                self.inverted_index.setdefault(term, []).append((doc_id, count))

        self.documents.extend(new_docs)
        self.doc_count = len(self.documents)
        self.avg_doc_len = total_len_so_far / self.doc_count if self.doc_count > 0 else 1.0
        self.built_at = time.time()
        logger.info("BM25 增量添加 docs={} 新增={}", self.doc_count, len(new_docs))

    # ═══════════════════════════════════════
    # 检索
    # ═══════════════════════════════════════

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.inverted_index:
            return []

        query_terms = self._tokenize(query)
        scores = [0.0] * self.doc_count

        for term in query_terms:
            if term not in self.inverted_index:
                continue
            df = len(self.inverted_index[term])
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)
            for doc_id, count in self.inverted_index[term]:
                doc_len = len(self._tokenize(self.documents[doc_id]))
                tf = (count * (self.k1 + 1)) / (count + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len))
                scores[doc_id] += idf * tf

        ranked = sorted(
            [(i, scores[i]) for i in range(self.doc_count) if scores[i] > 0],
            key=lambda x: -x[1],
        )[:top_k]

        return [
            {"doc_id": doc_id, "content": self.documents[doc_id][:200], "score": round(score, 4), "source": "BM25"}
            for doc_id, score in ranked
        ]

    # ═══════════════════════════════════════
    # 分词
    # ═══════════════════════════════════════

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        import re

        clean = re.sub(r"[^\w\s]", "", text)
        tokens = []
        for word in clean.split():
            if any("\u4e00" <= c <= "\u9fff" for c in word):
                chars = list(word)
                tokens.extend(chars)
                for i in range(len(chars) - 1):
                    tokens.append(chars[i] + chars[i + 1])
            else:
                tokens.append(word.lower())
        return tokens

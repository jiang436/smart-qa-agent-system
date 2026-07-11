"""BM25 关键词检索（L3 召回）

BM25 是传统信息检索的经典算法，和语义检索互补：
  - 语义检索: 理解"意思"（"怎么清尘盒" ? "如何清理集尘盒"）
  - BM25: 匹配"关键词"（"E05" ? "E05"）

为什么需要 BM25？
  1. 精确匹配: 错误码、型号名（X30 Pro）语义检索容易混淆
  2. 冷启动: 新文档刚加入时没有语义索引也能检索
  3. 互补性: 语义+BM25 的混合召回效果 > 任何单一方式
"""

import math
from collections import Counter

from smart_qa.observability.logger import logger


class BM25Index:
    """BM25 倒排索引"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1  # 词频饱和度参数
        self.b = b  # 文档长度归一化参数
        self.documents: list[str] = []
        self.doc_count = 0
        self.avg_doc_len = 0
        self.inverted_index: dict[str, list[tuple]] = {}  # term → [(doc_id, count)]

    def build(self, documents: list[str]):
        """构建 BM25 倒排索引

        流程:
          1. 对每篇文档分词
          2. 统计每个 term 在每篇文档中的出现次数
          3. 计算平均文档长度
        """
        self.documents = documents
        self.doc_count = len(documents)
        total_len = 0

        # 简单中文分词（按字+二字词组合，实际项目用 jieba）
        for doc_id, doc in enumerate(documents):
            terms = self._tokenize(doc)
            term_counts = Counter(terms)
            total_len += len(terms)

            for term, count in term_counts.items():
                if term not in self.inverted_index:
                    self.inverted_index[term] = []
                self.inverted_index[term].append((doc_id, count))

        self.avg_doc_len = total_len / self.doc_count if self.doc_count > 0 else 1
        logger.info("BM25 索引构建完成 docs={} terms={}", self.doc_count, len(self.inverted_index))

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """BM25 检索

        Args:
            query: 用户查询
            top_k: 返回前 k 篇文档

        Returns:
            [{"doc_id": id, "content": "...", "score": 0.85, "source": "BM25"}, ...]
        """
        if not self.inverted_index:
            return []

        query_terms = self._tokenize(query)
        scores = [0.0] * self.doc_count

        for term in query_terms:
            if term not in self.inverted_index:
                continue

            # IDF: 包含该 term 的文档数
            df = len(self.inverted_index[term])
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

            for doc_id, count in self.inverted_index[term]:
                doc_len = len(self._tokenize(self.documents[doc_id]))
                # BM25 评分公式
                tf = (count * (self.k1 + 1)) / (count + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len))
                scores[doc_id] += idf * tf

        # 排序取 top_k
        ranked = sorted(
            [(i, scores[i]) for i in range(self.doc_count) if scores[i] > 0],
            key=lambda x: -x[1],
        )[:top_k]

        return [
            {
                "doc_id": doc_id,
                "content": self.documents[doc_id][:200],
                "score": round(score, 4),
                "source": "BM25",
            }
            for doc_id, score in ranked
        ]

    def _tokenize(self, text: str) -> list[str]:
        """简单分词（中文按单字 + 二字组合）

        实际项目中应该用 jieba 分词，这里为了无依赖做简化。
        """
        if not text:
            return []
        # 去掉标点符号
        import re

        clean = re.sub(r"[^\w\s]", "", text)
        # 按空格/英文拆分 + 中文单字
        tokens = []
        for word in clean.split():
            if any("\u4e00" <= c <= "\u9fff" for c in word):
                # 中文: 单字 + 二字组合
                chars = list(word)
                tokens.extend(chars)
                for i in range(len(chars) - 1):
                    tokens.append(chars[i] + chars[i + 1])
            else:
                # 英文/数字: 整体
                tokens.append(word.lower())
        return tokens

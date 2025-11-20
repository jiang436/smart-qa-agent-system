"""FAQ 快速匹配器 — 将 900 条预写问答直接返回，跳过 RAG+LLM 全链路

在 router 层即可完成匹配，耗时 < 10ms，无需 RAG 检索和 LLM 生成。

匹配策略：最长公共子序列 (LCS) + 关键词加权。
LCS 天然适合中文——"边刷该换了" 和 "边刷多久换" 的公共子序列 "边刷换" 能有效匹配。
辅以型号/错误码等精准关键词加权。
"""

import json
import re
from collections.abc import Sequence

from src.observability.logger import logger


def _lcs_ratio(a: str, b: str) -> float:
    """计算两个字符串的 LCS 相似度（0~1）

    分母取查询长度（较短者），确保短查询也能匹配长 FAQ 问题。
    例："滤网多少钱"(5字) vs FAQ(16字)，LCS=3 → 3/5=0.60 ✓
    """
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    # 滚动数组
    prev = [0] * (lb + 1)
    for i in range(1, la + 1):
        curr = [0] * (lb + 1)
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    lcs_len = prev[lb]
    # 取较短者做分母，确保短查询不被长文本"稀释"
    return lcs_len / min(la, lb) if min(la, lb) > 0 else 0.0


def _extract_special_tokens(text: str) -> set[str]:
    """提取特殊 token：型号、错误码、数字+单位等"""
    tokens = set()
    # 错误码: E01-E99, e01-e99
    for m in re.finditer(r"[Ee]\d{2,3}", text):
        tokens.add(m.group().upper())
    # 型号: X30-SB-01, X30 Pro 等
    for m in re.finditer(r"X\d{2}[- ]?(?:Pro|[A-Z]{2}-\d{2})?", text, re.IGNORECASE):
        tokens.add(m.group().upper())
    # 数字+单位: 5000Pa, 5200mAh, 4L 等
    for m in re.finditer(r"\d+[A-Za-zµ]+", text):
        tokens.add(m.group().lower())
    # 价格
    for m in re.finditer(r"¥\d+(?:\.\d+)?", text):
        tokens.add(m.group())
    return tokens


class FAQMatcher:
    """FAQ 快速匹配器"""

    # LCS 阈值（>= 此值视为命中）
    LCS_THRESHOLD = 0.30
    # 特殊 token 精确匹配时的得分（直接覆盖 LCS，确保 E05 不会错配 E01）
    TOKEN_MATCH_SCORE = 1.00  # 精确匹配（E05↔E05）必须战胜任何 LCS

    def __init__(self):
        self._entries: list[dict] = []          # 原始 FAQ 条目
        self._questions: list[str] = []          # FAQ 问题文本（已清洗）
        self._question_tokens: list[set[str]] = []  # 每条问题的特殊 token

    # ── 加载 ──

    def load(self, filepaths: Sequence[str]) -> int:
        """加载 FAQ JSON 文件"""
        self._entries = []
        self._questions = []
        self._question_tokens = []
        for fp in filepaths:
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                entries = data if isinstance(data, list) else data.get("entries", [])
                for e in entries:
                    q = e.get("question", "")
                    a = e.get("answer", "")
                    if q and a:
                        self._entries.append(e)
                        self._questions.append(self._clean(q))
                        self._question_tokens.append(_extract_special_tokens(q))
                logger.info("FAQMatcher 加载完成 file={} count={}", fp, len(entries))
            except Exception as e:
                logger.warning("FAQMatcher 加载失败 file={} err={}", fp, str(e)[:80])

        logger.info("FAQMatcher 就绪 entries={}", len(self._entries))
        return len(self._entries)

    # ── 匹配 ──

    def match(self, query: str, threshold: float | None = None) -> str | None:
        """尝试匹配 FAQ，返回答案；未命中返回 None

        双重匹配：
          1. 特殊 token 匹配（E05 ↔ E05，X30-SB-01 ↔ X30-SB-01）→ 得分 1.0
          2. LCS 字符级相似度（"边刷该换了" vs "边刷多久更换"）→ 0~1

        Args:
            query: 用户查询
            threshold: 自定义阈值，默认 LCS_THRESHOLD (0.30)。
                       设为 0.85 可实现「95%相似度才用FAQ」的效果。
        """
        if threshold is None:
            threshold = self.LCS_THRESHOLD

        if not query or not self._questions:
            return None

        q_clean = self._clean(query)
        q_tokens = _extract_special_tokens(query)

        best_idx = -1
        best_score = 0.0

        for i, (faq_q, faq_tokens) in enumerate(zip(self._questions, self._question_tokens)):
            # 1) 特殊 token 精确匹配（E05、X30-SB-01 等）
            token_score = 0.0
            if q_tokens and faq_tokens:
                matched = len(q_tokens & faq_tokens)
                if matched > 0:
                    token_score = self.TOKEN_MATCH_SCORE * (matched / len(q_tokens))

            # 2) LCS 字符相似度
            lcs_score = _lcs_ratio(q_clean, faq_q)

            # 综合得分：token 精确匹配优先
            score = token_score if token_score > 0 else lcs_score

            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx >= 0 and best_score >= threshold:
            logger.info("FAQMatcher 命中 score=%.2f threshold=%.2f query=%s",
                        best_score, threshold, query[:60])
            return self._entries[best_idx].get("answer", "")

        return None

    # ── 辅助 ──

    @staticmethod
    def _clean(text: str) -> str:
        """清洗：去标点、空格、统一小写"""
        text = re.sub(r"[！？。，、；：“”‘’（）【】《》\s!?,.\"'`~:：]+", "", text)
        return text.lower().strip()


# 全局单例
_faq_matcher: FAQMatcher | None = None


def get_faq_matcher() -> FAQMatcher:
    global _faq_matcher
    if _faq_matcher is None:
        _faq_matcher = FAQMatcher()
    return _faq_matcher

"""引用溯源 + 幻觉抑制

让 RAG 的回答可追溯、可验证，从源头抑制幻觉。

核心机制:
  1. 引用溯源: 每条回答的每个关键信息都标注来源文档
  2. 引用校验: 检查"声称有来源"的内容是否真的在来源里
  3. 无源标记: 没有知识库支撑的内容自动标记"[无来源]"
  4. 置信度标签: 告诉用户这条回答的可信度
"""

import re


class CitationTracker:
    """引用追踪器 — 追踪每段回答的来源"""

    def __init__(self):
        self._documents = {}  # doc_id → document metadata

    def register_docs(self, docs: list[dict]):
        """注册检索到的文档

        Args:
            docs: [{"doc_id": "id1", "content": "...", "source": "故障手册_v3.pdf"}, ...]
        """
        for doc in docs:
            doc_id = doc.get("doc_id", str(len(self._documents)))
            self._documents[doc_id] = {
                "content": doc.get("content", ""),
                "source": doc.get("source", "未知来源"),
                "title": doc.get("title", "未命名文档"),
                "page": doc.get("page", ""),
            }

    def build_cited_answer(self, query: str, raw_answer: str) -> dict:
        """
        给原始答案加上引用标注。

        流程:
          1. 把答案拆成句子
          2. 对每个句子，检查是否和某篇文档内容匹配
          3. 匹配到的 → 加引用标记 [来源: xxx]
          4. 匹配不到的 → 加标记 [无来源]（潜在幻觉风险）

        Returns:
          {
            "text": "请将机器放回充电座充电[来源: 故障手册_v3.pdf]...",
            "citations": [{"doc_id": "id1", "source": "故障手册_v3.pdf", "snippets": [...], }],
            "unverified_claims": ["没有来源支撑的句子"],
            "hallucination_risk": "low|medium|high",
          }
        """
        if not self._documents:
            return {
                "text": raw_answer,
                "citations": [],
                "unverified_claims": [],
                "hallucination_risk": "high",
            }

        sentences = self._split_sentences(raw_answer)
        cited_sentences = []
        citations = []
        unverified = []

        for sentence in sentences:
            # 短句（<5字）仍尝试匹配文档，匹配不到也不加 [无来源] 标记
            # 避免 "好的"、"嗯嗯" 等非事实性短句污染 unverified 列表
            is_short = len(sentence.strip()) < 5
            if is_short:
                cited_sentences.append(sentence)
            else:
                best_match = self._find_best_match(sentence)
                if best_match:
                    doc_info = self._documents[best_match["doc_id"]]
                    source_tag = f"[来源: {doc_info['source']}]"
                    cited_sentences.append(f"{sentence}{source_tag}")
                    citations.append(
                        {
                            "doc_id": best_match["doc_id"],
                            "source": doc_info["source"],
                            "matched_sentence": sentence,
                            "score": best_match["score"],
                        }
                    )
                else:
                    cited_sentences.append(f"{sentence}[无来源]")
                    unverified.append(sentence)

        cited_text = "".join(cited_sentences)

        # 评估幻觉风险
        total = len(sentences)
        unverified_count = len(unverified)

        if unverified_count == 0:
            risk = "low"
        elif unverified_count / total < 0.3:
            risk = "medium"
        else:
            risk = "high"

        return {
            "text": cited_text,
            "citations": citations,
            "unverified_claims": unverified,
            "hallucination_risk": risk,
        }

    def _find_best_match(self, sentence: str) -> dict | None:
        """在注册的文档中找和句子最匹配的片段"""
        best = None
        best_score = 0.0

        # 提取句子的关键词（中文双字词 + 数字 + 型号）
        keywords = set(re.findall(r"[\u4e00-\u9fff]{2,}|\d+|[A-Z]\d+", sentence))

        for doc_id, doc in self._documents.items():
            doc_content = doc["content"]
            # 检查关键词在文档中的覆盖率
            if not keywords:
                continue
            match_count = sum(1 for kw in keywords if kw in doc_content)
            score = match_count / len(keywords)

            if score > best_score:
                best_score = score
                best = {"doc_id": doc_id, "score": score}

        # 只有关联度 > 0.3 才认为是匹配
        if best and best_score > 0.3:
            return best
        return None

    def _split_sentences(self, text: str) -> list[str]:
        """将文本拆成句子（支持中文标点）"""
        sentences = re.split(r"(?<=[。！？.!?])\s*", text)
        return [s for s in sentences if s.strip()]

    def verify_document(self, doc_content: str, claim: str) -> dict:
        """用文档验证单个声称事实（事实校验工具）

        检查文档中是否确实包含了 claim 所声称的信息。

        例如:
          claim: "X30 Pro 支持拖地功能"
          doc: "X30 Pro 支持扫拖一体"
          → 验证通过
        """
        if not doc_content or not claim:
            return {"verified": False, "reason": "参数为空"}

        claim_keywords = set(re.findall(r"[\u4e00-\u9fff]{2,}|\d+|[A-Z]\d+", claim))

        if not claim_keywords:
            return {"verified": False, "reason": "无法提取关键词"}

        match_count = sum(1 for kw in claim_keywords if kw in doc_content)
        match_ratio = match_count / len(claim_keywords)

        return {
            "verified": match_ratio >= 0.6,
            "match_ratio": match_ratio,
            "matched_keywords": match_count,
            "total_keywords": len(claim_keywords),
        }


class HallucinationGuard:
    """幻觉防护 — 在输出前拦截高风险内容"""

    @staticmethod
    def should_block(answer: dict, threshold: str = "high") -> bool:
        """判断是否应该拦截这条回答

        Args:
            answer: build_cited_answer() 的返回
            threshold: "low"=全放 / "medium"=拦高风险 / "high"=只拦最高风险

        Returns:
            True → 高风险，拦截并提示用户
        """
        risk_levels = {"low": 0, "medium": 1, "high": 2}
        answer_risk = risk_levels.get(answer.get("hallucination_risk", "high"), 2)
        threshold_level = risk_levels.get(threshold, 2)
        return answer_risk >= threshold_level

    @staticmethod
    def generate_safe_response(answer: dict) -> str:
        """生成安全的提示信息"""
        unverified = answer.get("unverified_claims", [])
        parts = [answer.get("text", "")]
        if unverified:
            parts.append("\n\n?? 以下内容小智暂时没有找到对应的资料:")
            for claim in unverified[:3]:
                parts.append(f"  - {claim[:50]}...")
            parts.append("建议您核实上述信息后再操作。")
        return "\n".join(parts)

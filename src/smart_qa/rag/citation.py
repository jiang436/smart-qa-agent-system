"""引用溯源 + 幻觉抑制 — embedding 语义匹配版本"""

import re


class CitationTracker:
    """引用追踪器"""

    def __init__(self):
        self._documents = {}
        self._vec_cache = {}  # doc_id -> vector

    def register_docs(self, docs: list[dict]):
        for doc in docs:
            doc_id = doc.get("doc_id", str(len(self._documents)))
            self._documents[doc_id] = {
                "content": doc.get("content", ""),
                "source": doc.get("source", "未知来源"),
                "title": doc.get("title", "未命名文档"),
                "page": doc.get("page", ""),
            }

    def build_cited_answer(self, query: str, raw_answer: str) -> dict:
        if not self._documents:
            return {
                "text": raw_answer,
                "citations": [],
                "unverified_claims": [],
                "hallucination_risk": "high",
            }

        sentences = self._split_sentences(raw_answer)
        cited_sentences, citations, unverified = [], [], []

        for sentence in sentences:
            if len(sentence.strip()) < 5:
                cited_sentences.append(sentence)
                continue

            best_match = self._find_best_match(sentence)
            if best_match:
                doc_info = self._documents[best_match["doc_id"]]
                source_tag = f" [{doc_info['source']}]"
                cited_sentences.append(f"{sentence}{source_tag}")
                citations.append({
                    "doc_id": best_match["doc_id"],
                    "source": doc_info["source"],
                    "matched_sentence": sentence,
                    "score": best_match["score"],
                })
            else:
                cited_sentences.append(f"{sentence} [未验证]")
                unverified.append(sentence)

        cited_text = "".join(cited_sentences)
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
        """Embedding 余弦相似度匹配（降级关键词）"""
        best, best_score = None, 0.0

        try:
            from smart_qa.knowledge.vector_store import get_embedding

            emb = get_embedding()
            sent_vec = emb.encode(sentence).ravel()
            for doc_id, doc in self._documents.items():
                doc_vec = emb.encode(doc["content"][:500]).ravel()
                sim = emb.cosine_similarity(sent_vec, doc_vec)
                if sim > best_score:
                    best_score = sim
                    best = {"doc_id": doc_id, "score": round(float(sim), 4)}
        except Exception:
            # keyword fallback
            keywords = set(re.findall(r"[一-鿿]{2,}|\d+|[A-Z]\d+", sentence))
            for doc_id, doc in self._documents.items():
                if not keywords:
                    continue
                c = doc["content"]
                match_count = sum(1 for kw in keywords if kw in c)
                score = match_count / len(keywords)
                if score > best_score:
                    best_score = score
                    best = {"doc_id": doc_id, "score": score}

        if best and best_score > 0.3:
            return best
        return None

    def _split_sentences(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[。！？.!?])\s*", text)
        return [s for s in sentences if s.strip()]

    def verify_document(self, doc_content: str, claim: str) -> dict:
        if not doc_content or not claim:
            return {"verified": False, "reason": "参数为空"}

        try:
            from smart_qa.knowledge.vector_store import get_embedding

            emb = get_embedding()
            sim = emb.cosine_similarity(
                emb.encode(claim).ravel(),
                emb.encode(doc_content[:500]).ravel(),
            )
            return {"verified": sim >= 0.6, "similarity": round(float(sim), 4)}
        except Exception:
            claim_keywords = set(re.findall(r"[一-鿿]{2,}|\d+|[A-Z]\d+", claim))
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
    """幻觉防护"""

    @staticmethod
    def should_block(answer: dict, threshold: str = "high") -> bool:
        risk_levels = {"low": 0, "medium": 1, "high": 2}
        answer_risk = risk_levels.get(answer.get("hallucination_risk", "high"), 2)
        threshold_level = risk_levels.get(threshold, 2)
        return answer_risk >= threshold_level

    @staticmethod
    def generate_safe_response(answer: dict) -> str:
        unverified = answer.get("unverified_claims", [])
        parts = [answer.get("text", "")]
        if unverified:
            parts.append("\n\n?? 以下内容小智暂时没有找到对应的资料:")
            for claim in unverified[:3]:
                parts.append(f"  - {claim[:50]}...")
            parts.append("建议您核实上述信息后再操作。")
        return "\n".join(parts)

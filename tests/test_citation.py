"""引用溯源 + 幻觉防护测试 — CitationTracker + HallucinationGuard"""
from smart_qa.rag.citation import CitationTracker, HallucinationGuard


class TestCitationTracker:
    def setup_method(self):
        self.tracker = CitationTracker()

    def test_split_sentences_chinese(self):
        text = "你好。今天天气不错！你去吗？"
        sentences = self.tracker._split_sentences(text)
        assert len(sentences) == 3
        assert "你好" in sentences[0]
        assert "今天天气不错" in sentences[1]
        assert "你去吗" in sentences[2]

    def test_split_sentences_mixed(self):
        text = "Hello world. 设置定时清扫！E05错误怎么解决？"
        sentences = self.tracker._split_sentences(text)
        assert len(sentences) >= 3

    def test_split_sentences_no_punctuation(self):
        text = "单一长句没有标点"
        sentences = self.tracker._split_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == text

    def test_split_sentences_empty(self):
        assert self.tracker._split_sentences("") == []

    def test_split_sentences_trailing_whitespace(self):
        text = "第一句。第二句。  "
        sentences = self.tracker._split_sentences(text)
        assert len(sentences) == 2

    def test_register_docs_and_build_no_docs_returns_high_risk(self):
        """没有文档时，build_cited_answer 返回 high hallucination_risk"""
        result = self.tracker.build_cited_answer("X30 Pro多大面积", "支持最大200平方米")
        assert result["text"] == "支持最大200平方米"
        assert result["hallucination_risk"] == "high"

    def test_register_docs_empty_list(self):
        self.tracker.register_docs([])
        assert len(self.tracker._documents) == 0

    def test_register_docs_then_build_with_sentence_hit(self):
        self.tracker.register_docs([
            {"content": "X30 Pro 支持最大200平方米的清扫面积", "source": "user_manual"},
        ])
        result = self.tracker.build_cited_answer("X30 Pro多大面积", "支持最大200平方米")
        # 句子过短(<5)会跳过，但这里有足够的匹配内容
        assert "text" in result
        assert result["hallucination_risk"] in ("low", "medium", "high")
        assert isinstance(result["citations"], list)


class TestHallucinationGuard:
    def test_should_block_high_risk_with_high_threshold(self):
        answer = {"text": "高风险内容", "hallucination_risk": "high", "unverified_claims": []}
        assert HallucinationGuard.should_block(answer, threshold="high") is True

    def test_should_block_medium_risk_with_medium_threshold(self):
        answer = {"text": "中等风险", "hallucination_risk": "medium", "unverified_claims": []}
        assert HallucinationGuard.should_block(answer, threshold="medium") is True

    def test_should_block_medium_risk_with_high_threshold(self):
        """high 阈值：answer_risk >= threshold_level, medium >= high → True"""
        answer = {"text": "中等风险", "hallucination_risk": "medium", "unverified_claims": []}
        # risk_levels = {"low": 0, "medium": 1, "high": 2}
        # medium(1) >= high(2) → False
        assert HallucinationGuard.should_block(answer, threshold="high") is False

    def test_should_block_low_risk_with_high_threshold(self):
        answer = {"text": "安全内容", "hallucination_risk": "low", "unverified_claims": []}
        assert HallucinationGuard.should_block(answer, threshold="high") is False

    def test_should_block_low_risk_with_low_threshold(self):
        answer = {"text": "安全内容", "hallucination_risk": "low", "unverified_claims": []}
        # low(0) >= low(0) → True — low threshold blocks everything
        assert HallucinationGuard.should_block(answer, threshold="low") is True

    def test_should_block_default_threshold_is_high(self):
        answer = {"text": "高风险", "hallucination_risk": "high", "unverified_claims": []}
        assert HallucinationGuard.should_block(answer) is True

    def test_generate_safe_response_with_unverified_claims(self):
        answer = {"text": "这是回答", "hallucination_risk": "high", "unverified_claims": ["没有来源的陈述"]}
        response = HallucinationGuard.generate_safe_response(answer)
        assert "这是回答" in response
        assert "小智" in response or "核实" in response

    def test_generate_safe_response_no_unverified(self):
        answer = {"text": "安全回答", "hallucination_risk": "low", "unverified_claims": []}
        response = HallucinationGuard.generate_safe_response(answer)
        assert response == "安全回答"

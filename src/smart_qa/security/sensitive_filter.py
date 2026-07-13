"""敏感词过滤 — AC 自动机 + 代码注入检测 + 输出脱敏"""

import re

try:
    import ahocorasick

    HAS_AHOCORASICK = True
except ImportError:
    HAS_AHOCORASICK = False

from .injection_guard import PromptInjectionDetector


class SensitiveFilter:
    DEFAULT_SENSITIVE_WORDS: list[str] = ["暴力", "色情", "赌博", "毒品", "转账", "验证码"]

    CODE_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL), "HTML script"),
        (re.compile(r"<\s*iframe[^>]*>", re.IGNORECASE), "HTML iframe"),
        (
            re.compile(r"(?:UNION|SELECT|INSERT|UPDATE|DELETE|DROP)\s+(?:ALL\s+)?(?:FROM|INTO|TABLE)", re.IGNORECASE),
            "SQL",
        ),
        (re.compile(r"(?:\||;|&&|\$\()\s*(?:ls|rm|cat|wget|curl|bash|sh)\b", re.IGNORECASE), "Shell"),
    ]

    PII_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"sk-[A-Za-z0-9]{32,}"), "[OPENAI_KEY_REDACTED]"),
        (re.compile(r"1[3-9]\d{9}"), "[PHONE_REDACTED]"),
        (re.compile(r"\d{6}[12]\d{3}[01]\d{3}\d{4}[0-9Xx]"), "[ID_REDACTED]"),
    ]

    def __init__(self):
        self._ac_built = False
        self._ac_automaton = None
        if HAS_AHOCORASICK:
            self._build_ac_automaton()
        self._injection_detector = PromptInjectionDetector()

    def _build_ac_automaton(self):
        self._ac_automaton = ahocorasick.Automaton()
        for idx, word in enumerate(self.DEFAULT_SENSITIVE_WORDS):
            self._ac_automaton.add_word(word, (idx, word))
        self._ac_automaton.make_automaton()
        self._ac_built = True

    def _check_sensitive_words(self, text: str) -> tuple[bool, list[str]]:
        if not text:
            return False, []
        if self._ac_built:
            matched = [word for _, (_, word) in self._ac_automaton.iter(text)]
            return len(matched) > 0, matched
        matched = [w for w in self.DEFAULT_SENSITIVE_WORDS if w.lower() in text.lower()]
        return len(matched) > 0, matched

    def _check_code_injection(self, text: str) -> tuple[bool, list[str]]:
        if not text:
            return False, []
        matched = [desc for p, desc in self.CODE_INJECTION_PATTERNS if p.search(text)]
        return len(matched) > 0, matched

    def check_input(self, text: str) -> dict:
        has_sensitive, words = self._check_sensitive_words(text)
        inj = self._injection_detector.detect(text)
        has_code, code_patterns = self._check_code_injection(text)
        reasons = []
        if has_sensitive:
            reasons.append(f"包含敏感词: {', '.join(words[:3])}")
        if inj["risk_level"] == "high":
            reasons.append("检测到 Prompt 注入")
        if has_code:
            reasons.append(f"检测到代码注入: {', '.join(code_patterns[:3])}")
        return {
            "allowed": len(reasons) == 0,
            "blocked_reason": "; ".join(reasons) if reasons else "",
            "details": {"sensitive_words": words, "injection_risk": inj["risk_level"], "code_injection": code_patterns},
        }

    def check_output(self, text: str) -> str:
        if not text:
            return text
        for pattern, replacement in self.PII_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

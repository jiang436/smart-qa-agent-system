"""核心安全 — 限流 + 敏感词过滤 + Prompt 注入防护

提供:
  - RateLimiter: 三层令牌桶限流 (全局 / 用户 / Token 预算)
  - SensitiveFilter: 四道安全防线 (敏感词 / 注入 / 代码 / 输出过滤)
  - PromptInjectionDetector: Prompt 注入检测

所有安全组件通过 FastAPI Depends() 注入到路由中。

Usage:
    from src.security import RateLimiter, SensitiveFilter
"""

import re
import time

try:
    import ahocorasick

    HAS_AHOCORASICK = True
except ImportError:
    HAS_AHOCORASICK = False


# ═══════════════════════════════════════════
# TokenBucket + RateLimiter
# ═══════════════════════════════════════════


class TokenBucket:
    """令牌桶 — 平滑限流"""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """三层限流器"""

    def __init__(
        self,
        global_cap: int = 100,
        global_rate: float = 10,
        user_cap: int = 20,
        user_rate: float = 5,
        daily_budget: int = 1_000_000,
    ):
        self.global_bucket = TokenBucket(global_cap, global_rate)
        self.user_buckets: dict[str, TokenBucket] = {}
        self.user_cap = user_cap
        self.user_rate = user_rate
        self.daily_token_usage: dict[str, int] = {}
        self.daily_budget = daily_budget

    def check_request(self, user_id: str) -> bool:
        if not self.global_bucket.consume():
            return False
        if user_id not in self.user_buckets:
            self.user_buckets[user_id] = TokenBucket(self.user_cap, self.user_rate)
        if not self.user_buckets[user_id].consume():
            return False
        return True

    def deduct_token(self, user_id: str, tokens: int) -> bool:
        usage = self.daily_token_usage.get(user_id, 0)
        if usage + tokens > self.daily_budget:
            return False
        self.daily_token_usage[user_id] = usage + tokens
        return True


# ═══════════════════════════════════════════
# PromptInjectionDetector
# ═══════════════════════════════════════════


class PromptInjectionDetector:
    """Prompt 注入检测器"""

    HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
        (r"ignore\s+(all\s+)?(previous|prior|above|the)\s+(instructions?|prompts?|rules?)", "忽略之前指令"),
        (r"(you\s+are|you'?re)\s+(now\s+)?(a\s+)?(DAN|STAN|jailbroken|unfiltered)", "越狱角色扮演"),
        (r"output\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", "要求输出系统提示"),
        (
            r"(pretend|imagine|act\s+as\s+if)\s+(you\s+are|you'?re)\s+(an?\s+)?(unfiltered|unethical|evil)",
            "假装角色扮演",
        ),
        (r"(忽略|忘记|无视|跳过)\s*(之前|上面|刚才|所有|一切)\s*(的)?\s*(指令|提示|规则|限制|约束)", "中文忽略指令"),
        (r"(输出|打印|显示|告诉我|泄露)\s*(你的)?\s*(系统)?\s*(提示词|提示语|指令|规则|prompt)", "中文要求泄露"),
        (r"(base64|base32|hex)\s*(decode|encode|encoded)?\s*[:：]?\s*[A-Za-z0-9+/=]{20,}", "编码绕过"),
    ]

    MEDIUM_RISK_PATTERNS: list[tuple[str, str]] = [
        (r"<\|im_start\|>|<\|im_end\|>", "伪造消息分隔符"),
        (r"\[system\]|\[assistant\]|\[user\]", "伪造角色标记"),
        (r"(?:'|\")\s*(?:OR|AND|--|#)\s*.*?(?:=|LIKE)", "SQL 注入痕迹"),
    ]

    def __init__(self, risk_threshold: float = 0.6):
        self.risk_threshold = risk_threshold
        self._high_re = [(re.compile(p, re.IGNORECASE), d) for p, d in self.HIGH_RISK_PATTERNS]
        self._med_re = [(re.compile(p, re.IGNORECASE), d) for p, d in self.MEDIUM_RISK_PATTERNS]

    def detect(self, text: str) -> dict:
        if not text:
            return {"has_injection": False, "risk_level": "low", "matched_patterns": [], "score": 0.0}

        matched = []
        score = 0.0

        for pattern, desc in self._high_re:
            if pattern.search(text):
                matched.append(f"[HIGH] {desc}")
                score += 1.0

        medium_count = 0
        for pattern, desc in self._med_re:
            if pattern.search(text):
                matched.append(f"[MEDIUM] {desc}")
                medium_count += 1
                score += 0.3

        if medium_count >= 3:
            score = max(score, 0.9)

        score = min(score, 1.0)
        if score >= 0.8:
            risk_level = "high"
        elif score >= self.risk_threshold:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "has_injection": risk_level != "low",
            "risk_level": risk_level,
            "matched_patterns": matched,
            "score": round(score, 2),
        }


# ═══════════════════════════════════════════
# SensitiveFilter — 四道安全防线
# ═══════════════════════════════════════════


class SensitiveFilter:
    """四道安全防线"""

    DEFAULT_SENSITIVE_WORDS: list[str] = ["暴力", "色情", "赌博", "毒品", "转账", "验证码"]

    CODE_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL), "HTML script"),
        (re.compile(r"<\s*iframe[^>]*>", re.IGNORECASE), "HTML iframe"),
        (
            re.compile(r"(?:UNION|SELECT|INSERT|UPDATE|DELETE|DROP)\s+(?:ALL\s+)?(?:FROM|INTO|TABLE)", re.IGNORECASE),
            "SQL 关键字",
        ),
        (re.compile(r"(?:\||;|&&|\$\()\s*(?:ls|rm|cat|wget|curl|bash|sh)\b", re.IGNORECASE), "Shell 命令注入"),
    ]

    PII_PATTERNS: list[tuple[re.Pattern, str, str]] = [
        (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI Key", "[OPENAI_KEY_REDACTED]"),
        (re.compile(r"1[3-9]\d{9}"), "手机号", "[PHONE_REDACTED]"),
        (re.compile(r"\d{6}[12]\d{3}[01]\d{3}\d{4}[0-9Xx]"), "身份证号", "[ID_REDACTED]"),
    ]

    def __init__(self):
        self._ac_built = False
        self._ac_automaton = None
        if HAS_AHOCORASICK:
            self._build_ac_automaton()
        self._injection_detector = PromptInjectionDetector()

    def _build_ac_automaton(self):
        if not HAS_AHOCORASICK:
            return
        self._ac_automaton = ahocorasick.Automaton()
        for idx, word in enumerate(self.DEFAULT_SENSITIVE_WORDS):
            self._ac_automaton.add_word(word, (idx, word))
        self._ac_automaton.make_automaton()
        self._ac_built = True

    def _check_sensitive_words(self, text: str) -> tuple[bool, list[str]]:
        if not text:
            return False, []
        if self._ac_built and self._ac_automaton:
            matched = [word for _, (_, word) in self._ac_automaton.iter(text)]
            return len(matched) > 0, matched
        text_lower = text.lower()
        matched = [w for w in self.DEFAULT_SENSITIVE_WORDS if w.lower() in text_lower]
        return len(matched) > 0, matched

    def _check_code_injection(self, text: str) -> tuple[bool, list[str]]:
        if not text:
            return False, []
        matched = [desc for p, desc in self.CODE_INJECTION_PATTERNS if p.search(text)]
        return len(matched) > 0, matched

    def check_input(self, text: str) -> dict:
        """检查用户输入"""
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
            "details": {
                "sensitive_words": words,
                "injection_risk": inj["risk_level"],
                "injection_score": inj["score"],
                "code_injection": code_patterns,
            },
        }

    def check_output(self, text: str) -> str:
        """过滤输出中的敏感信息"""
        if not text:
            return text
        filtered = text
        for pattern, _, replacement in self.PII_PATTERNS:
            if pattern.search(filtered):
                filtered = pattern.sub(replacement, filtered)
        return filtered

"""Prompt 注入检测 — 正则 + 语义双通道"""

import re


class PromptInjectionDetector:
    HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
        (r"ignore\s+(all\s+)?(previous|prior|above|the)\s+(instructions?|prompts?|rules?)", "忽略指令"),
        (r"(you\s+are|you'?re)\s+(now\s+)?(a\s+)?(DAN|STAN|jailbroken|unfiltered)", "越狱角色"),
        (r"output\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", "要求输出系统提示"),
        (r"(忽略|忘记|无视|跳过)\s*(之前|上面|刚才|所有|一切)\s*(的)?\s*(指令|提示|规则|限制)", "中文忽略指令"),
        (r"(输出|打印|显示|告诉我|泄露)\s*(你的)?\s*(系统)?\s*(提示词|提示语|指令|规则|prompt)", "中文要求泄露"),
        (r"(base64|base32|hex)\s*(decode|encode)?\s*[:：]?\s*[A-Za-z0-9+/=]{20,}", "编码绕过"),
    ]

    MEDIUM_RISK_PATTERNS: list[tuple[str, str]] = [
        (r"<\|im_start\|>|<\|im_end\|>", "伪造消息分隔符"),
        (r"\[system\]|\[assistant\]|\[user\]", "伪造角色标记"),
    ]

    def __init__(self, risk_threshold: float = 0.6):
        self.risk_threshold = risk_threshold
        self._high_re = [(re.compile(p, re.IGNORECASE), d) for p, d in self.HIGH_RISK_PATTERNS]
        self._med_re = [(re.compile(p, re.IGNORECASE), d) for p, d in self.MEDIUM_RISK_PATTERNS]

    def detect(self, text: str) -> dict:
        if not text:
            return {"has_injection": False, "risk_level": "low", "matched_patterns": [], "score": 0.0}
        matched, score = [], 0.0
        for pattern, desc in self._high_re:
            if pattern.search(text):
                matched.append(f"[HIGH] {desc}")
                score += 1.0
        mc = 0
        for pattern, desc in self._med_re:
            if pattern.search(text):
                matched.append(f"[MEDIUM] {desc}")
                mc += 1
                score += 0.3
        if mc >= 3:
            score = max(score, 0.9)
        score = min(score, 1.0)
        risk = "high" if score >= 0.8 else ("medium" if score >= self.risk_threshold else "low")
        return {
            "has_injection": risk != "low",
            "risk_level": risk,
            "matched_patterns": matched,
            "score": round(score, 2),
        }

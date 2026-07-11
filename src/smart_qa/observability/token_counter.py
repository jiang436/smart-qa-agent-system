"""可观测 — Token 消耗统计

追踪每个用户 / 每个会话的 LLM Token 消耗量，配合限流系统使用。

统计维度:
  - 按用户: 每日 / 每月 Token 消耗总量
  - 按会话: 单次会话 Token 消耗
  - 按模型: 轻量模型 vs 重量模型的消耗分布

限流告警:
  - 日预算 100 万 token / 用户
  - 月预算 2000 万 token / 用户
  - 超预算时自动降级到轻量模型
"""

import time
from dataclasses import dataclass, field

try:
    import tiktoken

    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


# ── 各模型的 Token 估算 (approximate, char-based fallback) ──
_MODEL_CHAR_RATIOS = {
    "gpt-4o": 0.25,  # ~4 chars per token (English), ~1.5 chars (Chinese)
    "gpt-4o-mini": 0.25,
    "gpt-4": 0.25,
    "gpt-3.5-turbo": 0.25,
    "deepseek-chat": 0.3,  # DeepSeek uses slightly more tokens per char
    "qwen-turbo": 0.3,
    "default": 0.3,
}


@dataclass
class UsageRecord:
    """单次 LLM 调用的用量记录"""

    model: str
    prompt_tokens: int
    completion_tokens: int
    timestamp: float = field(default_factory=time.time)


class TokenCounter:
    """Token 消耗统计器

    提供:
      - 精确的 Token 计数（tiktoken）或字符估算
      - 按用户/会话的累计追踪
      - 日/月预算检查

    用法:
      counter = TokenCounter()
      tokens = counter.count_tokens("你好，怎么设置定时清扫？", model="gpt-4o")

      counter.track_usage("U1001", "session_abc", prompt_tokens=150, completion_tokens=300, model="gpt-4o")
      ok = counter.check_budget("U1001")  # True if within daily budget
    """

    def __init__(self, daily_budget: int = 1_000_000, monthly_budget: int = 20_000_000):
        """
        Args:
            daily_budget: 每日 Token 预算上限
            monthly_budget: 每月 Token 预算上限
        """
        self.daily_budget = daily_budget
        self.monthly_budget = monthly_budget

        # user_id → [UsageRecord, ...]
        self._user_records: dict[str, list] = {}
        # session_id → [UsageRecord, ...]
        self._session_records: dict[str, list] = {}

        # tiktoken 编码器缓存
        self._encoders: dict[str, object] = {}

    def count_tokens(self, text: str, model: str = "gpt-4o") -> int:
        """计算文本的 Token 数量

        优先使用 tiktoken 精确计算，
        不可用时使用字符数估算（中文约 1.5 char/token, 英文约 4 char/token）

        Args:
            text: 输入文本
            model: 模型名称

        Returns:
            Token 数量（估计值）
        """
        if not text:
            return 0

        # 尝试 tiktoken
        if HAS_TIKTOKEN:
            try:
                enc = self._get_tiktoken_encoder(model)
                return len(enc.encode(text))
            except Exception:
                pass

        # 字符估算
        _MODEL_CHAR_RATIOS.get(model, _MODEL_CHAR_RATIOS["default"])

        # 中文字符权重更大（UTF-8 编码更长）
        chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
        other_chars = len(text) - chinese_chars

        # 中文约 0.5-1.5 token/char，英文约 0.2-0.3 token/char
        estimated = int(chinese_chars * 0.8 + other_chars * 0.25)
        return max(1, estimated)

    def _get_tiktoken_encoder(self, model: str):
        """获取或缓存 tiktoken 编码器"""
        if model in self._encoders:
            return self._encoders[model]

        try:
            # 尝试模型专用编码
            enc = tiktoken.encoding_for_model(model)
        except (KeyError, Exception):
            # 回退到 cl100k_base (GPT-4/GPT-3.5 系列)
            try:
                enc = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                raise RuntimeError("无法获取 tiktoken 编码器") from e

        self._encoders[model] = enc
        return enc

    def track_usage(
        self, user_id: str, session_id: str, prompt_tokens: int = 0, completion_tokens: int = 0, model: str = "gpt-4o"
    ):
        """记录一次 LLM 调用的 Token 消耗

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            prompt_tokens: 输入 Token 数
            completion_tokens: 输出 Token 数
            model: 使用的模型
        """
        record = UsageRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # 按用户记录
        if user_id not in self._user_records:
            self._user_records[user_id] = []
        self._user_records[user_id].append(record)

        # 按会话记录
        if session_id not in self._session_records:
            self._session_records[session_id] = []
        self._session_records[session_id].append(record)

    def get_user_daily_usage(self, user_id: str) -> int:
        """获取用户今日 Token 消耗"""
        records = self._user_records.get(user_id, [])
        now = time.time()
        today_start = now - (now % 86400)  # 今日零点

        total = 0
        for r in records:
            if r.timestamp >= today_start:
                total += r.prompt_tokens + r.completion_tokens
        return total

    def get_user_monthly_usage(self, user_id: str) -> int:
        """获取用户本月 Token 消耗"""
        records = self._user_records.get(user_id, [])
        now = time.time()
        month_start = now - (now % 2592000)  # 近似30天

        total = 0
        for r in records:
            if r.timestamp >= month_start:
                total += r.prompt_tokens + r.completion_tokens
        return total

    def get_session_usage(self, session_id: str) -> int:
        """获取会话 Token 消耗"""
        records = self._session_records.get(session_id, [])
        return sum(r.prompt_tokens + r.completion_tokens for r in records)

    def check_budget(self, user_id: str) -> dict:
        """检查用户 Token 预算

        Returns:
            {
                "within_budget": bool,
                "daily_used": int,
                "daily_limit": int,
                "daily_remaining": int,
                "monthly_used": int,
                "monthly_limit": int,
                "should_degrade": bool,  # 是否应降级到轻量模型
            }
        """
        daily = self.get_user_daily_usage(user_id)
        monthly = self.get_user_monthly_usage(user_id)

        daily_remaining = max(0, self.daily_budget - daily)
        within_budget = daily < self.daily_budget and monthly < self.monthly_budget

        # 超过 80% 预算时建议降级
        should_degrade = daily > self.daily_budget * 0.8 or monthly > self.monthly_budget * 0.8

        return {
            "within_budget": within_budget,
            "daily_used": daily,
            "daily_limit": self.daily_budget,
            "daily_remaining": daily_remaining,
            "monthly_used": monthly,
            "monthly_limit": self.monthly_budget,
            "should_degrade": should_degrade,
        }

    def get_stats(self, user_id: str) -> dict:
        """获取用户用量统计摘要"""
        records = self._user_records.get(user_id, [])

        if not records:
            return {"total_calls": 0, "total_tokens": 0, "by_model": {}}

        by_model = {}
        total_tokens = 0
        for r in records:
            tokens = r.prompt_tokens + r.completion_tokens
            total_tokens += tokens
            by_model.setdefault(r.model, 0)
            by_model[r.model] += tokens

        return {
            "total_calls": len(records),
            "total_tokens": total_tokens,
            "by_model": by_model,
            "daily_used": self.get_user_daily_usage(user_id),
            "monthly_used": self.get_user_monthly_usage(user_id),
        }

    def reset_user(self, user_id: str):
        """重置用户统计"""
        self._user_records.pop(user_id, None)

    def cleanup_old_records(self, max_age_days: int = 30):
        """清理超过 max_age_days 天的记录"""
        now = time.time()
        cutoff = now - max_age_days * 86400

        for uid in list(self._user_records.keys()):
            self._user_records[uid] = [r for r in self._user_records[uid] if r.timestamp >= cutoff]
            if not self._user_records[uid]:
                del self._user_records[uid]

        for sid in list(self._session_records.keys()):
            self._session_records[sid] = [r for r in self._session_records[sid] if r.timestamp >= cutoff]
            if not self._session_records[sid]:
                del self._session_records[sid]

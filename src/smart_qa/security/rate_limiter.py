"""限流 — 令牌桶 + 三层限流"""

import time


class TokenBucket:
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
    def __init__(self, global_cap=100, global_rate=10, user_cap=20, user_rate=5, daily_budget=1_000_000):
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
        return self.user_buckets[user_id].consume()

    def deduct_token(self, user_id: str, tokens: int) -> bool:
        usage = self.daily_token_usage.get(user_id, 0)
        if usage + tokens > self.daily_budget:
            return False
        self.daily_token_usage[user_id] = usage + tokens
        return True

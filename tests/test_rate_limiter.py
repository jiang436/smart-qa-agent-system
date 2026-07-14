"""限流器测试 — TokenBucket + RateLimiter"""
import time

from smart_qa.security import RateLimiter, TokenBucket


class TestTokenBucket:
    def setup_method(self):
        self.bucket = TokenBucket(capacity=5, refill_rate=10)

    def test_consume_within_capacity(self):
        self.bucket.consume()
        self.bucket.consume()
        # 每 consume 一次，tokens 减少 1（浮点数精度影响）
        assert self.bucket.tokens > 2.5

    def test_consume_exceeds_capacity(self):
        for _ in range(5):
            self.bucket.consume()
        # 第 6 次应失败（容量 5，refill_rate 10/s，时间太短不足回填）
        assert self.bucket.consume() is False

    def test_initial_tokens_at_capacity(self):
        assert self.bucket.tokens == 5
        assert self.bucket.capacity == 5

    def test_consume_negative_not_allowed(self):
        bucket = TokenBucket(capacity=0, refill_rate=10)
        assert bucket.consume() is False

    def test_refill_after_waiting(self):
        """等待足够时间后，令牌应重新可用"""
        bucket = TokenBucket(capacity=1, refill_rate=10)
        bucket.consume()  # 0
        assert bucket.consume() is False  # 满负荷
        # 等待至少 0.1 秒（1 个令牌 / 10 个每秒 = 0.1s）
        time.sleep(0.15)
        assert bucket.consume() is True

    def test_cannot_exceed_capacity(self):
        """等待后 tokens 不能超过 capacity"""
        bucket = TokenBucket(capacity=5, refill_rate=100)
        time.sleep(0.1)
        assert bucket.tokens <= 5


class TestRateLimiter:
    def setup_method(self):
        self.limiter = RateLimiter(
            global_cap=10,
            global_rate=100,
            user_cap=3,
            user_rate=10,
            daily_budget=1000,
        )

    def test_within_global_and_user_limits(self):
        assert self.limiter.check_request("user_a") is True
        assert self.limiter.check_request("user_b") is True

    def test_user_rate_limit_exceeded(self):
        lim = self.limiter
        assert lim.check_request("user_a") is True
        assert lim.check_request("user_a") is True
        assert lim.check_request("user_a") is True
        assert lim.check_request("user_a") is False

    def test_different_users_independent(self):
        lim = self.limiter
        for _ in range(3):
            lim.check_request("user_a")
        assert lim.check_request("user_a") is False  # user_a 耗尽

        # user_b 仍可通行
        assert lim.check_request("user_b") is True

    def test_global_rate_limit_exceeded(self):
        lim = RateLimiter(global_cap=2, global_rate=10, user_cap=10, user_rate=100, daily_budget=1000)
        assert lim.check_request("user_a") is True
        assert lim.check_request("user_b") is True
        assert lim.check_request("user_c") is False  # global 耗尽

    def test_daily_deduct_token(self):
        lim = RateLimiter(global_cap=100, global_rate=100, user_cap=100, user_rate=100, daily_budget=10)
        assert lim.deduct_token("user_a", 5) is True
        assert lim.deduct_token("user_a", 5) is True
        assert lim.deduct_token("user_a", 1) is False  # 超过 daily budget

    def test_deduct_token_across_multiple_users(self):
        lim = RateLimiter(global_cap=100, global_rate=100, user_cap=100, user_rate=100, daily_budget=10)
        assert lim.deduct_token("user_a", 7) is True
        assert lim.deduct_token("user_b", 3) is True
        assert lim.deduct_token("user_a", 4) is False  # 7+4 > 10

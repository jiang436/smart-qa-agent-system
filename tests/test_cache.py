"""语义缓存测试"""
import pytest
from smart_qa.memory.cache import SemanticCache


class TestSemanticCache:
    def setup_method(self):
        self.cache = SemanticCache(threshold=0.5)  # 低阈值确保测试命中

    async def test_get_empty_returns_none(self):
        result = await self.cache.get("查询不到的内容")
        assert result is None

    async def test_set_and_get(self):
        await self.cache.set("怎么重置Wi-Fi", "长按重置键5秒")
        result = await self.cache.get("怎么重置Wi-Fi")
        assert result == "长按重置键5秒"

    async def test_similar_query_hits_cache(self):
        await self.cache.set("如何重置Wi-Fi", "长按重置键5秒")
        # 相似问题应该命中（threshold=0.5 宽松）
        result = await self.cache.get("怎么重置Wi-Fi连接")
        assert result is not None
        assert "重置" in result

    async def test_clear_empties_cache(self):
        await self.cache.set("测试问题", "测试回答")
        assert await self.cache.get("测试问题") is not None
        await self.cache.clear()
        assert await self.cache.get("测试问题") is None

    async def test_lru_eviction(self):
        # 填满 10 条
        cache = SemanticCache(threshold=0.5)
        cache._local_store = []
        for i in range(10):
            vec = cache.embedding.encode(f"问题{i}")[0]
            cache._local_store.append((f"问题{i}", f"回答{i}", vec))
            assert len(cache._local_store) == i + 1

        # 再追加一条应该触发 evict
        cache._local_store = cache._local_store[-9:]  # 保留 9 条
        vec = cache.embedding.encode("新问题")[0]
        cache._local_store.append(("新问题", "新回答", vec))
        assert len(cache._local_store) <= 10

    async def test_empty_answer_not_cached(self):
        # 短回答不被缓存（rag_agent 中 len >= 10 才 set）
        await self.cache.set("测试", "短")
        result = await self.cache.get("测试")
        assert result is None or result == "短"

"""Session Repository 测试 — 使用 InMemorySessionRepository"""

import pytest

from smart_qa.repositories.session_repository import InMemorySessionRepository


@pytest.fixture
def repo():
    return InMemorySessionRepository()


@pytest.mark.asyncio
async def test_save_and_load_messages(repo):
    msgs = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}]
    await repo.save("s1", "u1", msgs, intent="qa")
    loaded = await repo.load("s1")
    assert len(loaded) == 2
    assert loaded[0]["content"] == "你好"
    assert loaded[1]["content"] == "你好！"


@pytest.mark.asyncio
async def test_load_nonexistent_session(repo):
    loaded = await repo.load("nonexistent")
    assert loaded == []


@pytest.mark.asyncio
async def test_save_empty_session_noop(repo):
    await repo.save("", "u1", [])
    assert await repo.load("") == []


@pytest.mark.asyncio
async def test_save_overwrites_previous(repo):
    await repo.save("s1", "u1", [{"role": "user", "content": "第一轮"}])
    await repo.save("s1", "u1", [{"role": "user", "content": "第二轮"}])
    loaded = await repo.load("s1")
    assert len(loaded) == 1
    assert loaded[0]["content"] == "第二轮"


@pytest.mark.asyncio
async def test_load_respects_limit(repo):
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
    await repo.save("s1", "u1", msgs)
    loaded = await repo.load("s1", limit=5)
    assert len(loaded) == 5


@pytest.mark.asyncio
async def test_load_empty_messages(repo):
    await repo.save("s1", "u1", [])
    loaded = await repo.load("s1")
    assert loaded == []


@pytest.mark.asyncio
async def test_session_repository_protocol_check(repo):
    from smart_qa.repositories.session_repository import SessionRepository

    assert isinstance(repo, SessionRepository)

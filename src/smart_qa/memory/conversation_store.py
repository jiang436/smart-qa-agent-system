"""对话持久化存储 — 委托到 SessionRepository

保持向后兼容的函数式 API：

    from smart_qa.memory.conversation_store import save_messages, load_messages

底层实现见 smart_qa.repositories.session_repository:
    - PostgresSessionRepository  → 生产用（PostgreSQL 存储）
    - InMemorySessionRepository  → 测试用（内存存储）

模块级单例 _repo 默认为 PostgresSessionRepository，测试时可替换为 InMemorySessionRepository。

典型用法:
    保存: save_messages(session_id, user_id, messages, intent="qa")
    读取: messages = await load_messages(session_id, limit=50)
"""

from smart_qa.repositories.session_repository import PostgresSessionRepository

# 模块级 Repository 实例（单例）
# 生产环境使用 PostgreSQL；测试时可替换为 InMemorySessionRepository
_repo = PostgresSessionRepository()


async def save_messages(
    session_id: str,
    user_id: str,
    messages: list,
    intent: str | None = None,
):
    """持久化对话消息到 PostgreSQL

    委托到 PostgresSessionRepository.save() 执行 UPSERT 操作。
    同一 session_id 的消息会覆盖之前的记录。

    参数:
        session_id: 会话唯一标识（由 chat.py 中的 uuid 生成）
        user_id: 用户 ID
        messages: 对话消息列表，每个元素为 {"role": ..., "content": ...}
        intent: 本轮对话识别出的意图（qa / troubleshoot / consumables / ...）

    注意:
        此函数可能抛异常，调用方（chat.py / stream_handler.py）负责 try/except。
        异常不会阻塞主流程，仅记录 debug 日志后静默忽略。

    性能:
        每次保存完整消息列表，适合单轮保存。
        高频场景应考虑增量追加。
    """
    await _repo.save(session_id, user_id, messages, intent=intent)


async def load_messages(session_id: str, limit: int = 50) -> list[dict]:
    """从 PostgreSQL 加载对话历史

    委托到 PostgresSessionRepository.load() 执行 SELECT 查询。
    返回最近 limit 条消息，按时间升序排列。

    参数:
        session_id: 会话 ID
        limit: 最大返回消息数（默认 50）

    返回值:
        list[dict] — 对话消息列表，每个元素为 {"role": ..., "content": ...}
        会话不存在时返回空列表。

    使用场景:
        - 服务重启后恢复对话上下文
        - 前端查询会话历史（GET /session/{id}/history）
    """
    return await _repo.load(session_id, limit=limit)

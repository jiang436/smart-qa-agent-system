"""数据库集成测试 — ORM 模型的 CRUD Smoke Test

需要 PostgreSQL 实例。通过 POSTGRES_DSN 环境变量配置，CI 中由 GitHub Actions
自动提供 pgvector/pgvector:pg17 服务。

本地运行:
    POSTGRES_DSN=postgresql+asyncpg://user:password@localhost:5432/agent uv run pytest tests/test_database_integration.py -v

无 POSTGRES_DSN 时自动跳过。
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# ── 获取测试数据库 DSN ──
def _get_test_dsn() -> str | None:
    """从环境变量获取测试数据库连接串"""
    dsn = os.environ.get("POSTGRES_DSN", "")
    if dsn:
        return dsn
    # 兼容本地 Docker Compose 环境
    for candidate in [
        "postgresql+asyncpg://user:password@localhost:5432/agent",
        "postgresql+asyncpg://test:test@localhost:5432/test_agent",
    ]:
        return candidate  # 第一个候选作为默认
    return None


TEST_DSN = _get_test_dsn()
_requires_db = pytest.mark.skipif(
    os.environ.get("POSTGRES_DSN") is None,
    reason="POSTGRES_DSN 未设置，跳过数据库集成测试",
)


# ── Fixtures ──


@pytest.fixture
async def engine():
    """创建独立测试引擎（每次测试结束后销毁表）"""
    if not TEST_DSN:
        pytest.skip("无 POSTGRES_DSN")
    eng = create_async_engine(TEST_DSN, echo=False)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    """创建测试 schema → 提供会话 → 清理"""
    from smart_qa.models import Base

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ═══════════════════════════════════════════
# 引擎生命周期
# ═══════════════════════════════════════════


class TestEngineLifecycle:
    """测试 init_db / close_db 生命周期"""

    @_requires_db
    async def test_init_db_creates_tables(self):
        """init_db 应创建所有 ORM 表"""
        from smart_qa.database.engine import _engine as global_engine

        # 不使用全局引擎，独立测试
        eng = create_async_engine(TEST_DSN, echo=False)
        try:
            from smart_qa.models import Base

            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 验证所有表存在
            async with eng.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                    )
                )
                tables = {row[0] for row in await result.fetchall()}
                assert "sessions" in tables
                assert "user_devices" in tables
                assert "consumable_orders" in tables
                assert "device_usage_logs" in tables
                assert "knowledge_files" in tables
                assert "user_profiles" in tables
        finally:
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await eng.dispose()

    @_requires_db
    async def test_engine_ping(self, engine):
        """引擎应该能成功 ping"""
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert (await result.fetchone())[0] == 1


# ═══════════════════════════════════════════
# Session 表 CRUD
# ═══════════════════════════════════════════


class TestSessionCRUD:
    """会话记录 CRUD"""

    @_requires_db
    async def test_create_session(self, db_session: AsyncSession):
        """创建会话记录"""
        from smart_qa.database.postgres import PostgresClient
        from smart_qa.models.session import Session

        sid = str(uuid.uuid4())[:12]
        rec = await PostgresClient.create_session(db_session, sid, "user_a")
        assert rec.session_id == sid
        assert rec.user_id == "user_a"
        assert rec.message_count == 0

    @_requires_db
    async def test_get_session(self, db_session: AsyncSession):
        """读取会话记录"""
        from smart_qa.database.postgres import PostgresClient

        sid = str(uuid.uuid4())[:12]
        await PostgresClient.create_session(db_session, sid, "user_a")
        rec = await PostgresClient.get_session(db_session, sid)
        assert rec is not None
        assert rec.session_id == sid

    @_requires_db
    async def test_get_nonexistent_session(self, db_session: AsyncSession):
        """读取不存在的会话返回 None"""
        from smart_qa.database.postgres import PostgresClient

        rec = await PostgresClient.get_session(db_session, "no_such_session")
        assert rec is None

    @_requires_db
    async def test_session_messages_serialization(self, db_session: AsyncSession):
        """会话消息 JSON 序列化/反序列化"""
        from smart_qa.database.postgres import PostgresClient

        sid = str(uuid.uuid4())[:12]
        await PostgresClient.create_session(db_session, sid, "user_a")

        rec = await PostgresClient.get_session(db_session, sid)
        test_msgs = [
            {"role": "user", "content": "边刷怎么换"},
            {"role": "assistant", "content": "您可以参考说明书第3页..."},
        ]
        rec.set_messages(test_msgs)

        # 重新查询验证
        rec2 = await PostgresClient.get_session(db_session, sid)
        restored = rec2.get_messages()
        assert len(restored) == 2
        assert restored[0]["role"] == "user"
        assert restored[0]["content"] == "边刷怎么换"


# ═══════════════════════════════════════════
# UserDevice 表 CRUD
# ═══════════════════════════════════════════


class TestUserDeviceCRUD:
    """用户设备绑定 CRUD"""

    @_requires_db
    async def test_bind_device(self, db_session: AsyncSession):
        """绑定设备"""
        from smart_qa.database.postgres import PostgresClient

        dev = await PostgresClient.bind_device(db_session, "user_a", "客厅机器人", "X30 Pro")
        assert dev.user_id == "user_a"
        assert dev.device_model == "X30 Pro"
        assert dev.is_active is True

    @_requires_db
    async def test_get_user_device(self, db_session: AsyncSession):
        """获取用户活跃设备"""
        from smart_qa.database.postgres import PostgresClient

        await PostgresClient.bind_device(db_session, "user_a", "主卧机器人", "X20 Pro")
        dev = await PostgresClient.get_user_device(db_session, "user_a")
        assert dev is not None
        assert dev.device_model == "X20 Pro"

    @_requires_db
    async def test_get_user_device_no_binding(self, db_session: AsyncSession):
        """无设备绑定的用户返回 None"""
        from smart_qa.database.postgres import PostgresClient

        dev = await PostgresClient.get_user_device(db_session, "unknown_user")
        assert dev is None

    @_requires_db
    async def test_bind_new_device_deactivates_old(self, db_session: AsyncSession):
        """绑定新设备应停用旧设备"""
        from smart_qa.database.postgres import PostgresClient

        await PostgresClient.bind_device(db_session, "user_a", "旧设备", "T10")
        await PostgresClient.bind_device(db_session, "user_a", "新设备", "X30 Pro")

        dev = await PostgresClient.get_user_device(db_session, "user_a")
        assert dev.device_name == "新设备"
        assert dev.device_model == "X30 Pro"


# ═══════════════════════════════════════════
# ConsumableOrder 表 CRUD
# ═══════════════════════════════════════════


class TestConsumableOrderCRUD:
    """耗材订单 CRUD"""

    @_requires_db
    async def test_create_order(self, db_session: AsyncSession):
        """创建耗材订单"""
        from smart_qa.database.postgres import PostgresClient

        order = await PostgresClient.create_order(
            db_session, "user_a", "X30 Pro", "side_brush", "边刷", quantity=2, price=49.9
        )
        assert order.user_id == "user_a"
        assert order.part_type == "side_brush"
        assert order.part_name == "边刷"
        assert order.quantity == 2
        assert order.price == 49.9
        assert len(order.order_id) == 12

    @_requires_db
    async def test_get_last_order(self, db_session: AsyncSession):
        """获取最近订单"""
        from smart_qa.database.postgres import PostgresClient

        await PostgresClient.create_order(db_session, "user_a", "X30 Pro", "side_brush", "边刷", quantity=1)
        await PostgresClient.create_order(db_session, "user_a", "side_brush", "边刷", quantity=3)

        order = await PostgresClient.get_last_order(db_session, "user_a", "side_brush")
        assert order is not None
        assert order.quantity == 3  # 最新的

    @_requires_db
    async def test_get_last_order_none(self, db_session: AsyncSession):
        """无订单历史返回 None"""
        from smart_qa.database.postgres import PostgresClient

        order = await PostgresClient.get_last_order(db_session, "user_a", "main_brush")
        assert order is None


# ═══════════════════════════════════════════
# DeviceUsageLog 表 CRUD
# ═══════════════════════════════════════════


class TestDeviceUsageLogCRUD:
    """设备使用日志 CRUD"""

    @_requires_db
    async def test_log_usage(self, db_session: AsyncSession):
        """记录使用日志"""
        from smart_qa.database.postgres import PostgresClient

        log = await PostgresClient.log_usage(
            db_session, "user_a", "客厅机器人", "X30 Pro", clean_area=80.5, duration_minutes=45.0
        )
        assert log.user_id == "user_a"
        assert log.clean_area == 80.5
        assert log.duration_minutes == 45.0
        assert log.status == "completed"

    @_requires_db
    async def test_log_usage_with_error(self, db_session: AsyncSession):
        """记录带错误码的使用日志"""
        from smart_qa.database.postgres import PostgresClient

        log = await PostgresClient.log_usage(
            db_session, "user_a", "厨房机器人", "T10", error_code="E05", status="error"
        )
        assert log.error_code == "E05"
        assert log.status == "error"

    @_requires_db
    async def test_get_usage_stats(self, db_session: AsyncSession):
        """获取使用统计"""
        from smart_qa.database.postgres import PostgresClient

        await PostgresClient.log_usage(db_session, "user_a", "A", "X30 Pro", clean_area=50, duration_minutes=30)
        await PostgresClient.log_usage(db_session, "user_a", "A", "X30 Pro", clean_area=30, duration_minutes=20)
        await PostgresClient.log_usage(
            db_session, "user_a", "A", "X30 Pro", clean_area=20, duration_minutes=10, error_code="E01"
        )

        stats = await PostgresClient.get_usage_stats(db_session, "user_a", days=30)
        assert stats["total_cleans"] == 3
        assert stats["total_area"] == 100.0
        assert stats["total_duration"] == 60.0
        assert stats["avg_area_per_clean"] == pytest.approx(33.3, abs=0.1)
        assert stats["error_count"] == 1

    @_requires_db
    async def test_get_usage_stats_no_data(self, db_session: AsyncSession):
        """无使用数据时返回零值统计"""
        from smart_qa.database.postgres import PostgresClient

        stats = await PostgresClient.get_usage_stats(db_session, "no_history_user", days=30)
        assert stats["total_cleans"] == 0
        assert stats["total_area"] == 0


# ═══════════════════════════════════════════
# KnowledgeFile 表 CRUD
# ═══════════════════════════════════════════


class TestKnowledgeFileCRUD:
    """知识文件记录 CRUD"""

    @_requires_db
    async def test_insert_knowledge_file(self, db_session: AsyncSession):
        """插入知识文件记录"""
        from smart_qa.models.knowledge_file import KnowledgeFile

        kf = KnowledgeFile(filename="test_manual.pdf", file_type="pdf", chunks=15, dimension=512)
        db_session.add(kf)
        await db_session.commit()

        # 查询验证
        from sqlalchemy import select

        result = await db_session.execute(select(KnowledgeFile).where(KnowledgeFile.filename == "test_manual.pdf"))
        saved = result.scalar_one_or_none()
        assert saved is not None
        assert saved.file_type == "pdf"
        assert saved.chunks == 15
        assert saved.dimension == 512


# ═══════════════════════════════════════════
# UserProfile 表 CRUD
# ═══════════════════════════════════════════


class TestUserProfileCRUD:
    """用户画像 CRUD"""

    @_requires_db
    async def test_insert_user_profile(self, db_session: AsyncSession):
        """插入用户画像"""
        from smart_qa.models.user_profile import UserProfile

        profile = UserProfile(
            user_id="user_a", device_model="X30 Pro", preferred_mode="quiet", home_layout="三室一厅"
        )
        db_session.add(profile)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(select(UserProfile).where(UserProfile.user_id == "user_a"))
        saved = result.scalar_one_or_none()
        assert saved is not None
        assert saved.device_model == "X30 Pro"
        assert saved.preferred_mode == "quiet"
        assert saved.home_layout == "三室一厅"

    @_requires_db
    async def test_user_profile_unique_constraint(self, db_session: AsyncSession):
        """同一用户多次插入应报唯一约束冲突"""
        from smart_qa.models.user_profile import UserProfile
        from sqlalchemy.exc import IntegrityError

        db_session.add(UserProfile(user_id="dup_user", device_model="T10"))
        await db_session.commit()

        db_session.add(UserProfile(user_id="dup_user", device_model="X20 Pro"))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    @_requires_db
    async def test_user_profile_defaults(self, db_session: AsyncSession):
        """用户画像默认值"""
        from smart_qa.models.user_profile import UserProfile
        from sqlalchemy import select

        db_session.add(UserProfile(user_id="minimal_user"))
        await db_session.commit()

        result = await db_session.execute(select(UserProfile).where(UserProfile.user_id == "minimal_user"))
        saved = result.scalar_one_or_none()
        assert saved.conversation_count == 1
        assert saved.first_seen_at is not None
        assert saved.updated_at is not None

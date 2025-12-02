"""L3 长期记忆 — 用户画像 & 事实提取

核心问题: 不是所有信息都值得永久存储。需要判断:
  "这条信息是事实还是观点？被后续查询命中的概率多大？"

判断规则:
  ✅ 事实性信息 → 永久保留:
     - 设备型号 "我家是 X30 Pro"
     - 家庭环境 "三室两厅"、"有宠物"
     - 地板材质 "客厅是大理石"
     - 偏好设置 "喜欢安静模式"

  ❌ 非事实 → 不写入:
     - 情绪表达 "今天心情不好"
     - 一次性请求 "帮我查一下天气"
     - 重复信息 (覆盖旧记录)
     - 模糊表达 "可能是"、"大概"

Usage:
    from src.memory.long_term import LongTermMemory
    ltm = LongTermMemory(db_session)
    facts = ltm.extract_facts("我家是三室两厅，有只猫")
    await ltm.update_profile("U1001", facts)
"""

import re
from datetime import datetime
from typing import Any

from src.observability.logger import logger

# ── 事实模式: (正则, 类别, 置信度) ──
FACT_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # 设备型号 (必须在户型之前匹配，避免 X30 被当成其他)
    (
        re.compile(r"(?:是|买|用)(?:了|的|的是一台)?\s*([A-Za-z]+\d{1,2}\s*(?:Pro|Max|Ultra)?)", re.IGNORECASE),
        "device_model",
        0.95,
    ),
    (
        re.compile(r"(?:我家|家里|设备)(?:是|用|有)(?:一台)?\s*([A-Za-z]+\d{1,2}\s*(?:Pro|Max|Ultra)?)", re.IGNORECASE),
        "device_model",
        0.90,
    ),
    # 户型 (支持中文数字: 三室两厅, 3室2厅)
    (re.compile(r"([\d一二三四五六七八九十两]+室[\d一二三四五六七八九十两]+厅)"), "floor_plan", 0.90),
    # 面积 (支持多种表述)
    (re.compile(r"(\d{2,4})\s*(?:平|平米|平方|m²|平方米)"), "area_sqm", 0.85),
    (re.compile(r"(?:面积|大概|约|大约)\s*(\d{2,4})\s*(?:平|平米)?"), "area_sqm", 0.80),
    # 宠物
    (re.compile(r"(?:有|养|家里有)(?:一?只|条)?\s*(猫|狗|宠物|仓鼠|兔子)"), "has_pet", 0.90),
    (re.compile(r"(?:没有|无)(?:宠物|猫|狗)"), "has_pet", 0.90),
    # 地板材质
    (re.compile(r"(?:地板|地面).{0,5}?(木地板|瓷砖|大理石|地毯|复合地板|实木)"), "floor_type", 0.85),
    # 偏好
    (
        re.compile(r"(?:喜欢|偏好|习惯|一般|通常)(?:用|开|使用)?\s*(安静模式|标准模式|强力模式|拖地模式)"),
        "preferred_mode",
        0.80,
    ),
    (re.compile(r"(?:每天|每周|每\w)(?:打扫|清扫|清洁)\s*(\d+)?\s*次?"), "cleaning_frequency", 0.75),
    # 家庭成员
    (re.compile(r"(?:家里|有)(?:小孩|宝宝|婴儿|老人)"), "has_children_or_elderly", 0.80),
]

# ── 非事实模式: 不写入 LTM ──
NON_FACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:可能|大概|也许|好像|应该|感觉|觉得|不知道)"),
    re.compile(r"(?:心情|情绪|今天|昨天|刚才).{0,10}(?:不好|很差|不错|很好)"),
    re.compile(r"(?:帮我|给我|查一下|看一下|搜一下)"),
    re.compile(r"(?:嗯|哦|好的|知道了|明白了|谢谢|再见)"),
]


class LongTermMemory:
    """L3 长期记忆 — 用户画像管理

    职责:
      1. 从对话中提取事实性信息
      2. 判断该信息是否值得永久存储
      3. 写入 PostgreSQL user_profile
      4. 生成用户摘要供下次对话使用
    """

    def __init__(self, db_session=None):
        self.db = db_session

    # ── 事实提取 ──

    def extract_facts(self, text: str) -> list[dict[str, Any]]:
        """从文本中提取事实性信息

        Args:
            text: 用户输入文本

        Returns:
            [{"category": "device_model", "value": "X30 Pro", "confidence": 0.95}, ...]
        """
        if not text:
            return []

        # 检查非事实信号: 纯主观语句才大幅降权
        transient_count = sum(1 for p in NON_FACT_PATTERNS if p.search(text))
        # 每命中一个非事实模式，置信度降低 0.15 (最多降 0.45)
        penalty = min(0.45, transient_count * 0.15)

        facts = []
        for pattern, category, confidence in FACT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = match.group(1) if match.lastindex else match.group(0)
                value = value.strip()
                confidence = confidence - penalty

                if confidence >= 0.6:  # 低置信度不写入
                    facts.append(
                        {
                            "category": category,
                            "value": value,
                            "confidence": round(confidence, 2),
                            "source": "extraction",
                            "extracted_at": datetime.utcnow().isoformat(),
                        }
                    )

        # 去重: 同一 category 只保留置信度最高的一条
        seen: dict[str, dict[str, Any]] = {}
        for f in facts:
            key = f["category"]
            if key not in seen or f["confidence"] > seen[key]["confidence"]:
                seen[key] = f
        facts = list(seen.values())

        if facts:
            logger.info("L3 提取事实 count={} text={}", len(facts), text[:80])

        return facts

    def is_fact_worth_storing(self, category: str, value: str, existing_value: str | None) -> bool:
        """判断是否值得写入 LTM

        规则:
          1. 新信息 > 旧信息 (覆盖)
          2. 高置信度 (>0.8) > 低置信度
          3. 相同信息不重复写入
        """
        if existing_value is None:
            return True  # 新信息总是值得写
        if existing_value == value:
            return False  # 完全相同，不重复写
        return True  # 不同的值 (比如更新了户型) → 覆盖

    # ── 用户画像读写 ──

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户画像

        优先查 PostgreSQL，降级到 Redis 缓存。
        """
        profile = {}

        # 从 PostgreSQL 查
        if self.db:
            try:
                from src.database.postgres import PostgresClient

                device = await PostgresClient.get_user_device(self.db, user_id)
                if device:
                    profile["device_model"] = device.device_model
                    profile["device_name"] = device.device_name
                    profile["firmware_version"] = device.firmware_version
                    profile["bound_at"] = str(device.bound_at)
            except Exception as e:
                logger.warning("L3 获取设备失败 user={}: {}", user_id, e)

        # 从 Redis 查补充信息
        try:
            from src.database.redis import RedisClient

            cached = await RedisClient.get_json(f"profile:{user_id}")
            if cached:
                profile.update(cached)
        except Exception:
            pass

        return profile

    async def update_profile(self, user_id: str, facts: list[dict[str, Any]]):
        """将提取的事实写入用户画像

        不是全量写入，只有"确信不会变"的才写入。

        Args:
            user_id: 用户 ID
            facts: extract_facts() 的输出
        """
        if not facts:
            return

        # 获取现有画像
        existing = await self.get_profile(user_id)

        # 逐条判断是否值得写入
        updates = {}
        stored_count = 0
        for fact in facts:
            category = fact["category"]
            value = fact["value"]
            confidence = fact["confidence"]

            existing_value = existing.get(category)
            if not self.is_fact_worth_storing(category, value, existing_value):
                continue
            if confidence < 0.7:  # 低于 0.7 不进 LTM
                continue

            updates[category] = {
                "value": value,
                "confidence": confidence,
                "updated_at": fact["extracted_at"],
            }
            stored_count += 1

        if not updates:
            return

        # 写入 Redis (持久化)
        try:
            from src.database.redis import RedisClient

            await RedisClient.set_json(f"profile:{user_id}", {**existing, **updates})
        except Exception as e:
            logger.warning("L3 写入 Redis 失败 user={}: {}", user_id, e)

        logger.info("L3 更新画像 user={} stored={}/{} facts", user_id, stored_count, len(facts))

    async def generate_summary(self, user_id: str) -> str:
        """生成用户摘要字符串，注入 LLM 上下文

        Returns:
            "用户设备: X30 Pro, 户型: 三室两厅, 有宠物: 猫, 偏好: 安静模式"
        """
        profile = await self.get_profile(user_id)
        parts = []
        if "device_model" in profile:
            parts.append(f"设备: {profile['device_model']}")
        if "floor_plan" in profile:
            parts.append(f"户型: {profile['floor_plan']}")
        if "has_pet" in profile:
            parts.append(f"有宠物: {profile['has_pet']}")
        if "floor_type" in profile:
            parts.append(f"地板: {profile['floor_type']}")
        if "preferred_mode" in profile:
            parts.append(f"偏好: {profile['preferred_mode']}")
        return ", ".join(parts) if parts else ""

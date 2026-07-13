"""记忆写入器 — 从对话中提取用户画像并持久化到 PostgreSQL

并非所有对话都写入，只写入 LTM 层级的信息:
  - 设备型号（"我的 X30 Pro 不工作了" → device_model="X30 Pro"）
  - 偏好模式（"我喜欢安静模式" → preferred_mode="quiet"）
  - 居住环境（"我家三室一厅" → home_layout="三室一厅"）

设计原则:
  1. 轻量 — 纯模式匹配，不调 LLM
  2. 安全 — 写入失败不抛异常，不阻塞主流程
  3. 幂等 — UPSERT，重复对话不产生重复记录
"""

from __future__ import annotations

import json
import re

from smart_qa.observability.logger import logger

# ── 设备型号识别 ──
_DEVICE_MODELS = ["X30 Pro", "X20 Pro", "T10", "X30", "X20", "R10", "R20"]

# ── 偏好关键词 → 字段值 ──
_MODE_KEYWORDS: dict[str, str] = {
    "安静模式": "quiet",
    "静音模式": "quiet",
    "安静": "quiet",
    "强力模式": "strong",
    "强力": "strong",
    "标准模式": "standard",
    "标准": "standard",
}
_MOPPING_KEYWORDS: dict[str, str] = {
    "拖地": "yes",
    "拖地模式": "yes",
    "扫拖": "yes",
    "不拖地": "no",
    "不要拖地": "no",
    "不用拖": "no",
}

# ── 户型识别 ──
_HOME_LAYOUT_PATTERN = re.compile(
    r"([一二两三四五六七八九十\d]+)[室房](?:[一二两三四五六七八九十\d]+厅)?"
)

# ── 序列号 ──
_SN_PATTERN = re.compile(r"(?:SN[：:]\s*|序列号[：:]\s*|sn[：:]\s*)([A-Za-z0-9]{6,20})", re.IGNORECASE)


def _extract_device(text: str) -> str | None:
    """提取设备型号"""
    for model in _DEVICE_MODELS:
        if model.lower() in text.lower():
            return model
    return None


def _extract_preferred_mode(text: str) -> str | None:
    """提取偏好模式"""
    for keyword, value in _MODE_KEYWORDS.items():
        if keyword in text:
            return value
    return None


def _extract_mopping(text: str) -> str | None:
    """提取拖地偏好"""
    for keyword, value in _MOPPING_KEYWORDS.items():
        if keyword in text:
            return value
    return None


def _extract_home_layout(text: str) -> str | None:
    """提取户型"""
    m = _HOME_LAYOUT_PATTERN.search(text)
    if m:
        return m.group(0)
    return None


def _extract_sn(text: str) -> str | None:
    """提取序列号"""
    m = _SN_PATTERN.search(text)
    if m:
        return m.group(1)
    return None


def _extract_user_query(state: dict) -> str:
    """从 state 中提取用户最后一条消息"""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "") or getattr(msg, "role", "")
            content = getattr(msg, "content", "")
        if role in ("human", "user") and content:
            return content
    return ""


def _build_tags(*extracted_values: str | None) -> str:
    """构建 JSON 标签数组"""
    tags = [v for v in extracted_values if v is not None]
    # 去重保序
    seen: set[str] = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return json.dumps(unique, ensure_ascii=False)


async def memory_writer_node(state: dict) -> dict:
    """记忆写入节点 — LangGraph node

    在 guard_check 之后、END 之前执行。
    从当前对话中提取确定性信息，写入 PostgreSQL user_profiles 表。

    写入条件:
      - user_id 存在（非 anonymous）
      - 对话中有实质内容（final_answer 存在）
      - 提取到新的确定性信息

    Args:
        state: AgentState

    Returns:
        不变的 state（本节点不修改对话逻辑）
    """
    user_id = state.get("user_id", "anonymous")
    if not user_id or user_id in ("anonymous", "", "default"):
        return state

    # 对话无实质内容 → 跳过
    if not state.get("final_answer"):
        return state

    query = _extract_user_query(state)
    if not query:
        return state

    # ── 从用户消息中提取信息 ──
    device_model = _extract_device(query)
    preferred_mode = _extract_preferred_mode(query)
    mopping = _extract_mopping(query)
    home_layout = _extract_home_layout(query)
    sn = _extract_sn(query)

    # 没有任何可提取的信息 → 跳过
    if not any([device_model, preferred_mode, mopping, home_layout, sn]):
        return state

    # ── 写入数据库 ──
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from smart_qa.config import settings

        engine = create_async_engine(settings.postgres_dsn, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            # 检查现有记录
            existing = await session.execute(
                text("SELECT * FROM user_profiles WHERE user_id = :uid"),
                {"uid": user_id},
            )
            row = existing.fetchone()

            if row:
                # UPDATE — 只更新非空字段，不覆盖已有值
                updates = []
                params: dict[str, object] = {"uid": user_id}

                if device_model:
                    updates.append("device_model = :device_model")
                    params["device_model"] = device_model
                if preferred_mode:
                    updates.append("preferred_mode = :preferred_mode")
                    params["preferred_mode"] = preferred_mode
                if mopping:
                    updates.append("mopping_enabled = :mopping_enabled")
                    params["mopping_enabled"] = mopping
                if home_layout:
                    updates.append("home_layout = :home_layout")
                    params["home_layout"] = home_layout

                # 标签合并
                existing_tags = json.loads(row.tags) if row.tags else []
                new_tag = _build_tags(device_model, preferred_mode, home_layout)
                if new_tag:
                    merged = list(set(existing_tags + json.loads(new_tag)))
                    updates.append("tags = :tags")
                    params["tags"] = json.dumps(merged, ensure_ascii=False)

                updates.append("conversation_count = conversation_count + 1")
                updates.append("updated_at = NOW()")

                if len(updates) > 2:  # 有实质性变化（不仅仅是 conversation_count）
                    sql = f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = :uid"
                    await session.execute(text(sql), params)
                    await session.commit()
                    logger.info(
                        "LTM 更新 user={} device={} mode={} layout={}",
                        user_id, device_model, preferred_mode, home_layout,
                    )
            else:
                # INSERT
                tags = _build_tags(device_model, preferred_mode, home_layout)
                await session.execute(
                    text("""
                        INSERT INTO user_profiles
                            (user_id, device_model, device_sn, preferred_mode,
                             mopping_enabled, home_layout, tags,
                             conversation_count, first_seen_at, updated_at)
                        VALUES
                            (:uid, :device_model, :device_sn, :preferred_mode,
                             :mopping, :home_layout, :tags,
                             1, NOW(), NOW())
                    """),
                    {
                        "uid": user_id,
                        "device_model": device_model,
                        "device_sn": sn,
                        "preferred_mode": preferred_mode,
                        "mopping": mopping,
                        "home_layout": home_layout,
                        "tags": tags,
                    },
                )
                await session.commit()
                logger.info(
                    "LTM 创建 user={} device={} mode={} layout={}",
                    user_id, device_model, preferred_mode, home_layout,
                )

        await engine.dispose()

    except Exception as e:
        logger.warning("LTM 写入失败 user={} err={}", user_id, e)
        # 静默失败 — 不阻塞主流程

    return state

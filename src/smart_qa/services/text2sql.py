"""Text2SQL — 自然语言查询转 SQL + 执行

三层架构:
  Text2SQLKb      → DDL + Q-SQL 示例 + 表/字段描述
  SQLGenerator    → LLM 生成 SQL + 错误修正
  Text2SQLAgent   → 协调检索/生成/执行 完整流程

Usage:
    agent = Text2SQLAgent()
    result = await agent.query("X30 Pro用户今年买了多少边刷")
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from smart_qa.database.engine import get_session
from smart_qa.observability.logger import logger


# ═══════════════════════════════════════════
# 知识库（DDL + 示例 + 描述）
# ═══════════════════════════════════════════

DATABASE_KNOWLEDGE = {
    "ddl": [
        """CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    intent VARCHAR(32),          -- qa/troubleshoot/consumables/general
    scenario VARCHAR(32),
    message_count INTEGER DEFAULT 0,
    messages TEXT,               -- JSON array of conversation
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);""",
        """CREATE TABLE user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) UNIQUE NOT NULL,
    device_model VARCHAR(64),    -- X30 Pro / T10 / R20 / ...
    device_sn VARCHAR(64),
    preferred_mode VARCHAR(32),  -- quiet/standard/strong
    mopping_enabled VARCHAR(8),
    home_layout VARCHAR(64),     -- 三室一厅 / ...
    tags TEXT,
    conversation_count INTEGER DEFAULT 1,
    first_seen_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);""",
        """CREATE TABLE knowledge_files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(256) NOT NULL,
    file_type VARCHAR(16) NOT NULL,   -- pdf / md / txt
    chunks INTEGER DEFAULT 0,
    dimension INTEGER DEFAULT 512,
    uploaded_at TIMESTAMP DEFAULT NOW()
);""",
        """CREATE TABLE consumable_orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(64) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    device_model VARCHAR(64) NOT NULL,
    part_type VARCHAR(64) NOT NULL,   -- 边刷/滤网/主刷/拖布/尘盒
    part_name VARCHAR(128) NOT NULL,
    quantity INTEGER DEFAULT 1,
    price FLOAT,
    source VARCHAR(32),               -- official/tmall/jd/third_party
    ordered_at TIMESTAMP DEFAULT NOW()
);""",
        """CREATE TABLE user_devices (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    device_name VARCHAR(128) NOT NULL,
    device_model VARCHAR(64) NOT NULL,
    firmware_version VARCHAR(32),
    is_active BOOLEAN DEFAULT TRUE,
    bound_at TIMESTAMP DEFAULT NOW()
);""",
        """CREATE TABLE device_usage_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    device_name VARCHAR(128) NOT NULL,
    device_model VARCHAR(64) NOT NULL,
    clean_area FLOAT DEFAULT 0.0,
    duration_minutes FLOAT DEFAULT 0.0,
    battery_consumed INTEGER DEFAULT 0,
    error_code VARCHAR(8),
    status VARCHAR(32) DEFAULT 'completed',
    recorded_at TIMESTAMP DEFAULT NOW()
);""",
    ],
    "qsql": [
        {
            "question": "今天有多少次对话",
            "sql": "SELECT COUNT(*) AS count FROM sessions WHERE DATE(created_at) = CURRENT_DATE"
        },
        {
            "question": "最近7天各意图的对话数量",
            "sql": "SELECT intent, COUNT(*) AS count FROM sessions WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY intent ORDER BY count DESC"
        },
        {
            "question": "X30 Pro用户有多少",
            "sql": "SELECT COUNT(*) AS count FROM user_devices WHERE device_model = 'X30 Pro' AND is_active = TRUE"
        },
        {
            "question": "3月份卖了多少边刷",
            "sql": "SELECT SUM(quantity) AS total FROM consumable_orders WHERE part_type = '边刷' AND ordered_at >= '2026-03-01' AND ordered_at < '2026-04-01'"
        },
        {
            "question": "用户最多的型号排行",
            "sql": "SELECT device_model, COUNT(*) AS count FROM user_devices WHERE is_active = TRUE GROUP BY device_model ORDER BY count DESC"
        },
    ],
    "descriptions": {
        "sessions": "用户对话记录表，包含每次AI会话的意图、场景和完整对话历史。messages字段为JSON数组。",
        "user_profiles": "用户画像表，存储从对话中提取的设备型号、清扫偏好、户型等信息。tags字段为逗号分隔。",
        "knowledge_files": "知识库文件表，记录上传到系统的文档信息。",
        "consumable_orders": "耗材订单表，记录用户购买边刷、滤网等耗材的订单。part_type: 边刷/滤网/主刷/拖布/尘盒。source: official/tmall/jd/third_party。",
        "user_devices": "用户设备绑定表，每人可绑定多台设备。is_active表示当前使用的设备。",
        "device_usage_logs": "设备使用日志表，记录每次清扫的面积、时长、耗电和故障信息。error_code如E01-E10。",
        "age": "user_profiles表中无age字段。sessions.created_at的时间差可推算用户活跃天数。",
    },
}


# ═══════════════════════════════════════════
# SQL 生成器
# ═══════════════════════════════════════════

class SQLGenerator:
    """LLM 生成 SQL + 错误自动修正"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.max_retries = 3

    def _build_context(self, query: str) -> str:
        """构建 LLM 上下文 — DDL + Q-SQL 示例 + 表描述 + 匹配策略"""

        # 简单的关键词匹配选出相关示例
        qsql_examples = []
        query_lower = query.lower()
        for item in DATABASE_KNOWLEDGE["qsql"]:
            keywords = item["question"].lower().split()
            if any(kw in query_lower for kw in keywords):
                qsql_examples.append(f"Q: {item['question']}\nSQL: {item['sql']}")

        # 如果没匹配到任何示例，取全部（最多3条）
        if not qsql_examples:
            for item in DATABASE_KNOWLEDGE["qsql"][:3]:
                qsql_examples.append(f"Q: {item['question']}\nSQL: {item['sql']}")

        parts = []
        parts.append("=== 数据库表结构 ===")
        parts.append("\n".join(DATABASE_KNOWLEDGE["ddl"]))
        parts.append("\n=== 表和字段描述 ===")
        parts.extend(f"{k}: {v}" for k, v in DATABASE_KNOWLEDGE["descriptions"].items())
        parts.append("\n=== 相似查询示例 ===")
        parts.append("\n---\n".join(qsql_examples[:3]))

        return "\n".join(parts)

    def generate_sql(self, query: str) -> str:
        """LLM 生成 SQL"""
        context = self._build_context(query)
        prompt = (
            "你是PostgreSQL SQL专家。根据数据库结构和查询示例，将用户问题转为PostgreSQL SQL。\n\n"
            f"{context}\n\n"
            "规则:\n"
            "1. 只输出 SQL，不要解释\n"
            "2. 用 PostgreSQL 语法\n"
            "3. 字段名严格使用 DDL 中定义的\n"
            "4. 查询始终加 LIMIT 100\n"
            "5. 时间查询用 CURRENT_DATE 和 INTERVAL\n\n"
            f"用户问题: {query}\nSQL:"
        )
        try:
            resp = self.llm.invoke(prompt)
            sql = resp.content if hasattr(resp, "content") else str(resp)
            return self._clean_sql(sql)
        except Exception as e:
            logger.error("SQL生成 LLM 调用失败: {}", e)
            return ""

    def fix_sql(self, query: str, original_sql: str, error_msg: str) -> str:
        """错误修正 — 将报错和原始SQL回给LLM修正"""
        context = self._build_context(query)
        prompt = (
            "你生成的SQL执行报错，请修正。\n\n"
            f"用户问题: {query}\n"
            f"原始SQL: {original_sql}\n"
            f"错误信息: {error_msg}\n\n"
            f"参考结构:\n{context[:2000]}\n\n"
            "只输出修正后的 SQL:"
        )
        try:
            resp = self.llm.invoke(prompt)
            sql = resp.content if hasattr(resp, "content") else str(resp)
            return self._clean_sql(sql)
        except Exception as e:
            logger.error("SQL修正失败: {}", e)
            return ""

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """清洗 LLM 输出 — 去掉 markdown 包装和注释"""
        raw = raw.strip()
        # 去掉 ```sql ... ``` 包装
        raw = re.sub(r"^```(?:sql)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        # 去掉 SQL 注释
        raw = re.sub(r"--.*$", "", raw, flags=re.MULTILINE)
        # 确保以分号结尾
        raw = raw.strip().rstrip(";")
        # 加 LIMIT
        if raw.upper().startswith("SELECT") and "LIMIT" not in raw.upper():
            raw += " LIMIT 100"
        return raw.strip()


# ═══════════════════════════════════════════
# Text2SQL 代理
# ═══════════════════════════════════════════

class Text2SQLAgent:
    """Text2SQL — 协调检索/生成/执行"""

    def __init__(self, llm_client=None):
        self.generator = SQLGenerator(llm_client)
        self.max_retries = 3

    async def query(self, user_question: str) -> dict[str, Any]:
        """执行自然语言 → SQL → 结构化结果

        Returns:
            {"success": bool, "sql": str, "columns": [...], "rows": [...]}
        """
        t0 = time.time()
        sql = self.generator.generate_sql(user_question)
        if not sql:
            return {"success": False, "error": "SQL 生成失败", "sql": ""}

        logger.info("Text2SQL 生成: {} → {}", user_question[:60], sql[:120])

        for attempt in range(self.max_retries):
            success, result = await self._execute_sql(sql)
            if success:
                elapsed = time.time() - t0
                logger.info("Text2SQL 成功: {} rows, {:.1f}s", result.get("count", 0), elapsed)
                return {
                    "success": True,
                    "sql": sql,
                    "retry_count": attempt,
                    "elapsed": round(elapsed, 2),
                    **result,
                }
            # 失败 → 修正重试
            logger.warning("Text2SQL 执行失败 (attempt={}/{}): {}", attempt + 1, self.max_retries, result)
            sql = self.generator.fix_sql(user_question, sql, str(result))
            if not sql:
                break

        return {"success": False, "error": "SQL 执行多次失败", "sql": sql}

    @staticmethod
    async def _execute_sql(sql: str) -> tuple[bool, Any]:
        """执行 SQL 并返回结构化结果"""
        import asyncio

        from sqlalchemy import text

        try:
            session_gen = get_session()
            # get_session 可能是 async generator，需要适配
            if hasattr(session_gen, "__aiter__"):
                db = await session_gen.__anext__()
            else:
                db = session_gen

            result_proxy = await db.execute(text(sql))
            if sql.strip().upper().startswith("SELECT"):
                columns = list(result_proxy.keys())
                rows_raw = await result_proxy.fetchall()
                rows = [dict(zip(columns, row)) for row in rows_raw]
                # 日期序列化
                for row in rows:
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            row[k] = v.isoformat()

                try:
                    if hasattr(db, "close"):
                        await db.close()
                except Exception:
                    pass

                return True, {"columns": columns, "rows": rows, "count": len(rows)}
            else:
                return True, {"columns": [], "rows": [], "count": 0}

        except Exception as e:
            return False, str(e)[:300]

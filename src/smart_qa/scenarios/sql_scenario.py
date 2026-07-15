"""SQL 场景 — Text2SQL 自然语言查数据库"""

from smart_qa.observability.logger import logger


class SQLScenario:
    """SQL 查询场景"""

    @staticmethod
    async def run(state: dict) -> dict:
        query = _extract_query(state)

        if not query:
            state["final_answer"] = "请提供您要查询的问题。"
            return state

        try:
            from smart_qa.services.text2sql import Text2SQLAgent
            from smart_qa.di import container

            agent = Text2SQLAgent(llm_client=container.get("llm"))
            result = await agent.query(query)

            if result["success"]:
                answer = _format_sql_result(query, result)
            else:
                answer = f"查询失败: {result.get('error', '未知错误')}\n执行的SQL: {result.get('sql', 'N/A')}"
        except Exception as e:
            logger.error("SQLScenario 异常: {}", e)
            answer = f"查询执行时出现错误: {str(e)[:200]}"

        state["final_answer"] = answer
        state["intent"] = "sql_query"
        return state


def _extract_query(state: dict) -> str:
    from smart_qa.agent.state_utils import extract_user_query
    return extract_user_query(state)


def _format_sql_result(query: str, result: dict) -> str:
    """格式化 SQL 结果为人可读的回答"""
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    sql = result.get("sql", "")

    if not rows:
        return f"查询完成，但没有找到符合条件的记录。\n执行的SQL: `{sql}`"

    # 单行单列 → 简洁数字
    if len(rows) == 1 and len(columns) == 1:
        key = columns[0]
        val = rows[0][key]
        return f"根据查询结果，**{val}**。\n执行的SQL: `{sql}`"

    # 多行 → 表格
    header = " | ".join(columns)
    sep = " | ".join("---" for _ in columns)
    body = "\n".join(
        " | ".join(str(row.get(c, "")) for c in columns)
        for row in rows[:20]
    )
    more = f"\n... 共 {len(rows)} 条记录（仅显示前20条）" if len(rows) > 20 else ""
    return (
        f"查询结果（共 {len(rows)} 条）：\n\n"
        f"| {header} |\n| {sep} |\n{body}{more}\n\n"
        f"执行的SQL: `{sql}`"
    )

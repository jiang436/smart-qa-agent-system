"""AgentState 工具函数 — 安全的消息提取（兼容 dict 和 LangChain 对象）"""
from typing import Any


def get_messages(state: dict) -> list[dict[str, Any]]:
    """获取消息列表，兼容 dict 和 LangChain 消息对象"""
    msgs = state.get("messages", [])
    if not msgs:
        return []
    result = []
    for m in msgs:
        if isinstance(m, dict):
            result.append(m)
        else:
            # LangChain 消息对象 → 转为 dict
            role = getattr(m, "type", "unknown")
            content = getattr(m, "content", "")
            result.append({"role": role, "content": content})
    return result


def extract_user_query(state: dict) -> str:
    """从 state 提取最新用户消息，安全处理 dict 和 LangChain 对象"""
    messages = state.get("messages", [])
    if not messages:
        return ""

    for msg in reversed(messages):
        # LangChain 消息对象
        if hasattr(msg, "type") and hasattr(msg, "content"):
            if msg.type in ("human", "user"):
                return msg.content
        # dict
        elif isinstance(msg, dict):
            if msg.get("role") in ("user", "human"):
                return msg.get("content", "")

    # 取最后一条
    last = messages[-1]
    if isinstance(last, dict):
        return last.get("content", "")
    return getattr(last, "content", str(last))

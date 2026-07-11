"""记忆压缩 — 滑动窗口 + 摘要压缩

短期记忆不能无限增长（上下文窗口有限），需要两种压缩手段：

1. 滑动窗口:
   - 只保留最近的 N 轮对话
   - 超出部分直接丢弃
   - 适合简单问答场景，用户不太会往回翻

2. 摘要压缩:
   - 将早期的对话内容压缩成一句话摘要
   - "用户问过重置方法和耗材更换，设备是 X30 Pro"
   - 保留关键信息，丢弃细节
   - 适合多轮复杂场景，需要完整上下文

什么时候用哪个？
  滑动窗口: N 轮以内 -> 保留完整历史
  摘要压缩: 超过 N 轮 -> 旧轮压缩成摘要 + 新轮保留完整
"""

from dataclasses import dataclass, field

from smart_qa.observability.logger import logger


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = 0.0


@dataclass
class CompressedMemory:
    """压缩后的记忆"""

    summary: str = ""
    recent_messages: list[Message] = field(default_factory=list)
    user_profile_snapshot: dict = field(default_factory=dict)

    def to_context(self) -> str:
        """转为 LLM 上下文字符串"""
        parts = []
        if self.summary:
            parts.append(f"[历史摘要] {self.summary}")
        if self.user_profile_snapshot:
            parts.append(f"[用户信息] {self.user_profile_snapshot}")
        for msg in self.recent_messages:
            prefix = "用户" if msg.role == "user" else "助手"
            parts.append(f"{prefix}: {msg.content}")
        return "\n".join(parts)


class MemoryCompressor:
    """记忆压缩器"""

    def __init__(self, llm_client=None, window_size: int = 6):
        """
        Args:
            llm_client: LLM 客户端（用于生成摘要）
            window_size: 保留的完整消息轮数（一对问答算一轮）
        """
        self.llm = llm_client
        self.window_size = window_size

    async def compress(self, messages: list[Message], existing_summary: str = "") -> CompressedMemory:
        """
        对对话历史做压缩。

        策略:
          - 如果消息总数 <= window_size: 全部保留，不压缩
          - 如果消息总数 > window_size:
              前 (total - window_size) 轮 -> 摘要压缩
              后 window_size 轮 -> 保留完整

        Args:
            messages: 按时间排序的消息列表
            existing_summary: 已有的历史摘要（上一次压缩的结果）

        Returns:
            CompressedMemory
        """
        total = len(messages)

        if total <= self.window_size:
            return CompressedMemory(
                summary=existing_summary,
                recent_messages=messages,
            )

        compress_count = total - self.window_size
        to_compress = messages[:compress_count]
        to_keep = messages[-self.window_size :]

        if self.llm:
            new_summary = await self._generate_summary(to_compress, existing_summary)
        else:
            new_summary = self._simple_summary(to_compress, existing_summary)

        profile = self._extract_profile(to_compress)

        return CompressedMemory(
            summary=new_summary,
            recent_messages=to_keep,
            user_profile_snapshot=profile,
        )

    async def _generate_summary(self, messages: list[Message], existing: str) -> str:
        """用 LLM 生成对话摘要"""
        dialog = "\n".join(f"{'用户' if m.role == 'user' else '助手'}: {m.content[:100]}" for m in messages)

        prompt = (
            f"已有摘要: {existing or '无'}\n"
            f"新增对话:\n{dialog}\n"
            "\n"
            "请将以上对话内容压缩为一句话摘要，保留关键信息:\n"
            "- 用户提到过的设备型号\n"
            "- 用户遇到过的故障\n"
            "- 用户购买过的耗材\n"
            "- 用户做过的设置\n"
            "只输出摘要，不要解释。"
        )
        try:
            response = await self.llm.ainvoke(prompt)
            summary = response.content if hasattr(response, "content") else str(response)
            return summary.strip()[:200]
        except Exception as e:
            logger.warning("LLM 摘要生成失败: {}", e)
            return self._simple_summary(messages, existing)

    def _simple_summary(self, messages: list[Message], existing: str) -> str:
        """无 LLM 时的简单压缩（关键词提取）"""
        import re

        keywords = set()
        for m in messages:
            found = re.findall(r"[A-Z]\d+[\w-]*|[Xx]\d+[\w-]*", m.content)
            keywords.update(found)

        summary_parts = [existing] if existing else []
        if keywords:
            summary_parts.append(f"提及设备: {', '.join(keywords)}")
        summary_parts.append(f"共 {len(messages)} 轮对话已归档")
        return " | ".join(summary_parts)

    def _extract_profile(self, messages: list[Message]) -> dict:
        """从对话中提取用户画像信息"""
        profile = {}
        import re

        for m in messages:
            models = re.findall(r"[A-Z]\d+[\w-]*", m.content)
            if models:
                profile.setdefault("devices", set()).update(models)

            problem_keywords = {
                "故障": "fault",
                "重置": "reset",
                "充电": "charging",
                "耗材": "consumables",
                "购买": "purchase",
            }
            for kw, tag in problem_keywords.items():
                if kw in m.content:
                    profile.setdefault("topics", set()).add(tag)

        return {k: list(v) if isinstance(v, set) else v for k, v in profile.items()}

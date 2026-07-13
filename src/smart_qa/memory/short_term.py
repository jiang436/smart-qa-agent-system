"""短期记忆 — 对话上下文压缩与状态管理

用于 RAGAgent:
  1. 压缩对话历史为摘要
  2. 保留最近 N 条消息原文
  3. 提取用户画像快照（可选）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from smart_qa.observability.logger import logger


@dataclass
class Message:
    """对话消息"""
    role: str  # user / assistant / system
    content: str
    metadata: dict | None = None


@dataclass
class CompressedResult:
    """记忆压缩结果"""
    summary: str = ""
    recent_messages: list[Message] = field(default_factory=list)
    user_profile_snapshot: dict | None = None


class MemoryCompressor:
    """记忆压缩器 — 压缩对话历史为摘要

    用法:
        compressor = MemoryCompressor(llm_client=llm)
        result = await compressor.compress(messages)
    """

    def __init__(self, llm_client=None, window_size: int = 6):
        self.llm = llm_client
        self.window_size = window_size

    async def compress(self, messages: list[Message]) -> CompressedResult:
        """压缩消息列表

        Args:
            messages: 按时间顺序的消息列表

        Returns:
            CompressedResult 包含摘要和最近消息
        """
        if not messages:
            return CompressedResult()

        recent = messages[-self.window_size:] if len(messages) > self.window_size else messages

        # 尝试用 LLM 生成摘要
        summary = ""
        if self.llm and len(messages) > self.window_size:
            try:
                summary = await self._summarize(messages[:-self.window_size])
            except Exception as e:
                logger.debug("记忆压缩失败: {}", e)

        return CompressedResult(
            summary=summary,
            recent_messages=recent,
            user_profile_snapshot=None,
        )

    async def _summarize(self, messages: list[Message]) -> str:
        """用 LLM 生成摘要"""
        text = "\n".join(f"{m.role}: {m.content[:100]}" for m in messages)
        prompt = f"请将以下对话压缩为一句话摘要：\n\n{text}\n\n摘要："
        response = await self.llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return content.strip()[:200] or "（摘要生成失败）"

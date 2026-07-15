"""HyDE — 假设性文档嵌入

原理（Datawhale RAG 指南 §1.4 / Luyu Gao et al. 2022）:
  用户查询通常简短、关键词有限，而知识库文档内容详实。
  直接用查询向量去搜 → 存在"语义鸿沟"。

  HyDE 绕开这个问题:
    1. LLM 生成假设性答案（不要求事实正确，只需语义相关）
    2. 将假设答案向量化
    3. 用假设答案的向量去搜真实文档
    → 把"查询→文档"匹配转为"文档→文档"匹配

Usage:
    from smart_qa.rag.hyde import HyDE
    hyde = HyDE(llm_client)
    hyde_query = hyde.generate("边刷不转了")
"""

from __future__ import annotations

import concurrent.futures

from smart_qa.observability.logger import logger


class HyDE:
    """假设性文档嵌入生成器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def generate(self, query: str, timeout: float = 10.0) -> str | None:
        """为查询生成假设性答案文档

        短查询（≤8字）自动跳过以节省 LLM 调用。
        LLM 调用带超时保护，超时或失败降级为直接使用原查询。
        """
        if not self.llm or len(query) < 3:
            return None

        skip_patterns = ["你好", "谢谢", "再见", "在吗", "hi", "hello", "好的", "ok"]
        if any(query.strip().lower() == p for p in skip_patterns):
            return None
        if len(query) <= 2:
            return None
        # 短查询：embedding 已足够精确，跳过 HyDE
        if len(query) <= 8:
            return None

        prompt = (
            "你是扫地机器人技术支持。请用100-300字简要回答用户问题，"
            "包含具体型号、参数或步骤。\n"
            f"问题: {query}\n回答:"
        )
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.invoke, prompt)
                resp = future.result(timeout=timeout)
            text = resp.content if hasattr(resp, "content") else str(resp)
            text = text.strip()
            if 30 < len(text) < 2000:
                logger.debug("HyDE 生成成功 query={} len={}", query[:40], len(text))
                return text
            else:
                logger.debug("HyDE 长度异常 len={}", len(text))
                return None
        except concurrent.futures.TimeoutError:
            logger.debug("HyDE 超时 query={}", query[:40])
            return None
        except Exception as e:
            logger.debug("HyDE 生成失败: {}", e)
            return None

"""智能文档分片器 — 根据文档类型选择切分策略

不同格式的文档需要不同的切分策略:

分片策略选择:
  - TXT / Markdown → 递归字符切分 (chunk_size=500, overlap=50)
  - PDF（文字版）→ 按标题层级切分，保留结构
  - PDF（扫描件）→ OCR → 递归字符切分
  - PDF（表格）→ 结构化存储，独立 chunk + headers 元数据
  - PDF（图文混排）→ 布局分析 → 按阅读顺序切分

设计原则: 按语义边界切分比按固定字数切分效果好 20-30%，
因为固定长度会导致标题与内容分离，检索时丢失上下文。
"""

import re
from typing import Any

from smart_qa.observability.logger import logger

# ── 中文分句 ──
_SENTENCE_END = re.compile(r"[。！？.!?\n]")


class SmartDocumentSplitter:
    """智能文档分片器

    支持策略:
      - recursive:     递归字符切分 (TXT / Markdown)
      - header:        按标题层级切分 (有结构的 PDF)
      - semantic:      按语义边界切分 (需提供 embedding_model，通过相邻句相似度找断点)
      - table:         表格结构化提取
      - ocr:           OCR 结果按句子切分
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        embedding_model=None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_model = embedding_model

        # 递归切分分隔符（按优先级递减）
        self.separators = ["\n\n", "\n", "。", ". ", "！", "？", "；", ";", " ", ""]

    # ── 主入口 ──

    def split(self, text: str, doc_type: str = "txt", metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """自动选择分片策略

        Args:
            text: 文档原文
            doc_type: txt / markdown / pdf_text / pdf_scan / table
            metadata: 附加元数据 (source, title, category)

        Returns:
            [{"content": "...", "chunk_index": 0, "strategy": "...", **metadata}, ...]
        """
        meta = metadata or {}

        if doc_type in ("markdown", "pdf_text"):
            chunks = self._split_markdown_structured(text, meta)
        elif doc_type == "semantic" and self.embedding_model is not None:
            chunks = self._semantic_split(text, meta)
        elif doc_type in ("txt", "ocr"):
            chunks = self._split_recursive(text, meta)
        elif doc_type == "table":
            chunks = self._split_table(text, meta)
        else:
            chunks = self._split_recursive(text, meta)

        avg_size = 0
        if chunks:
            total = sum(len(c.get("content", "")) for c in chunks)
            avg_size = round(total / len(chunks), 1)
        logger.info(
            "文档分片 type={} len={} chunks={} avg_size={}",
            doc_type,
            len(text),
            len(chunks),
            avg_size,
        )
        return chunks

    # ── 策略 1: 递归字符切分 (TXT / Markdown / OCR 结果) ──

    def _split_recursive(self, text: str, meta: dict) -> list[dict]:
        """递归字符切分 — 按分隔符优先级依次尝试

        分隔符优先级:
          段落 (\\n\\n) > 换行 (\\n) > 句号 (。) > 感叹号 (！) > 问号 (？) > 空格 > 字符
        """
        chunks = self._recursive_split(text, self.separators)
        return [
            {"content": c.strip(), "chunk_index": i, "strategy": "recursive", **meta}
            for i, c in enumerate(chunks)
            if c.strip()
        ]

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """递归地按分隔符切分，确保每段不超过 chunk_size"""
        if not separators or len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        sep = separators[0]
        remaining = separators[1:]

        if sep == "":
            # 最后手段: 硬切字符
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        # 按分隔符拆分
        parts = text.split(sep)

        # 保留分隔符（补回去，避免丢信息）
        parts_with_sep = []
        for i, p in enumerate(parts):
            if i > 0:
                parts_with_sep.append(sep + p)
            else:
                parts_with_sep.append(p)

        # 合并短片段，拆分长片段
        result = []
        current = ""
        for part in parts_with_sep:
            if len(current) + len(part) <= self.chunk_size:
                current += part
            else:
                if current.strip():
                    result.append(current)
                # 当前片段本身超过 chunk_size → 用下一级分隔符再切
                if len(part) > self.chunk_size:
                    sub = self._recursive_split(part, remaining)
                    result.extend(sub)
                    current = ""
                else:
                    current = part

        if current.strip():
            result.append(current)

        return result

    # ── 策略 2: Markdown 结构化分块（两阶段）──

    def _split_markdown_structured(self, text: str, meta: dict) -> list[dict]:
        """Markdown 文档两阶段分块

        Stage 1: 按 ## 标题切分为逻辑章节，保留 Header1/Header2 元数据
        Stage 2: 章节过长 (>chunk_size) → 递归切分，子块继承标题路径
        """
        chunks = self._split_by_headers(text, meta)

        # 对每个章节检查是否需要 Stage 2 细切
        final = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if len(content) <= self.chunk_size:
                final.append(chunk)
            else:
                # Stage 2: 递归切分，保留标题元数据
                sub_meta = {**meta, "header": chunk.get("header", ""), "level": chunk.get("level", 0)}
                sub_chunks = self._split_recursive(content, sub_meta)
                # 子块继承 Header 元数据
                for _i, sc in enumerate(sub_chunks):
                    final.append({
                        **sc,
                        "chunk_index": len(final),
                        "strategy": "markdown_header+recursive",
                        "section": chunk.get("header", ""),
                    })

        logger.info("Markdown 结构化分块: sections={} chunks={}", len(chunks), len(final))
        return final

    # ── 策略 3: 按标题层级切分 ──

    def _split_by_headers(self, text: str, meta: dict) -> list[dict]:
        """按 Markdown 标题层级切分

        先按 # / ## / ### 切分，保留标题作为上下文。
        切分后过长的段落再递归细切。
        """
        # 识别标题行
        header_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

        # 按标题边界切分
        sections = []
        last_pos = 0
        current_header = ""

        for match in header_re.finditer(text):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.start()

            # 前面那段是一个 section
            if last_pos < start:
                section_text = text[last_pos:start].strip()
                if section_text:
                    sections.append(
                        {
                            "content": section_text,
                            "header": current_header,
                            "level": level,
                        }
                    )

            current_header = title
            last_pos = match.end()

        # 最后一个 section
        if last_pos < len(text):
            section_text = text[last_pos:].strip()
            if section_text:
                sections.append(
                    {
                        "content": section_text,
                        "header": current_header,
                        "level": 0,
                    }
                )

        # 对每个 section 检查是否需要递归细切
        chunks = []
        for idx, sec in enumerate(sections):
            section_meta = {**meta, "header": sec["header"], "section_index": idx}

            if len(sec["content"]) <= self.chunk_size:
                chunks.append(
                    {
                        "content": sec["content"],
                        "chunk_index": len(chunks),
                        "strategy": "header",
                        **section_meta,
                    }
                )
            else:
                # 过长 → 用分句切分
                sub = self._split_by_sentences(sec["content"])
                for sub_text in sub:
                    chunks.append(
                        {
                            "content": sub_text.strip(),
                            "chunk_index": len(chunks),
                            "strategy": "header+recursive",
                            **section_meta,
                        }
                    )

        return chunks

    # ── 策略 3: 按句子语义边界切分 ──

    def _split_by_sentences(self, text: str) -> list[str]:
        """按句子边界切分，保持 chunk 在合理范围内

        合并短句，在语义边界（句号/换行）处自然断开。
        """
        sentences = _SENTENCE_END.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) <= self.chunk_size:
                current += sent + "。"
            else:
                if current:
                    chunks.append(current)
                if len(sent) > self.chunk_size:
                    # 单句超长 → 硬切
                    for i in range(0, len(sent), self.chunk_size - self.chunk_overlap):
                        chunks.append(sent[i : i + self.chunk_size])
                else:
                    current = sent + "。"
        if current.strip():
            chunks.append(current)
        return chunks

    def _semantic_split(self, text: str, meta: dict) -> list[dict]:
        """按语义边界切分 — 通过相邻句子 embedding 相似度判断断点

        原理: 当相邻句子的 embedding 相似度突然下降时，
              说明话题转换了，这里就是自然断点。
        """
        sentences = _SENTENCE_END.split(text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        if len(sentences) <= 2 or not self.embedding_model:
            # 退化为分句切分
            return [
                {"content": c, "chunk_index": i, "strategy": "semantic_fallback", **meta}
                for i, c in enumerate(self._split_by_sentences(text))
            ]

        # 计算相邻句子相似度
        embeddings = self.embedding_model.encode(sentences)
        similarities = []
        for i in range(len(sentences) - 1):
            sim = self.embedding_model.cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append(float(sim))

        # 找到语义断点（相似度低于均值 - 0.5 标准差）
        import statistics

        mean_sim = statistics.mean(similarities) if similarities else 0.5
        std_sim = statistics.stdev(similarities) if len(similarities) > 1 else 0.1
        threshold = max(0.3, mean_sim - 0.5 * std_sim)

        # 按断点合并句子
        chunks = []
        current = sentences[0]
        for i in range(1, len(sentences)):
            sim = similarities[i - 1] if i - 1 < len(similarities) else 1.0
            combined = current + "。" + sentences[i]

            if sim < threshold or len(combined) > self.chunk_size:
                chunks.append(
                    {
                        "content": current.strip(),
                        "chunk_index": len(chunks),
                        "strategy": "semantic",
                        **meta,
                    }
                )
                current = sentences[i]
            else:
                current = combined

        if current.strip():
            chunks.append(
                {
                    "content": current.strip(),
                    "chunk_index": len(chunks),
                    "strategy": "semantic",
                    **meta,
                }
            )

        return chunks

    # ── 策略 4: 表格结构化 ──

    def _split_table(self, text: str, meta: dict) -> list[dict]:
        """表格结构化提取

        将 Markdown/CSV 表格解析为结构化片段:
          - 每个表格作为一个独立 chunk
          - 元数据记录表格 headers
          - content 包含表格描述 + 数据
        """
        # 检测 Markdown 表格
        lines = text.strip().split("\n")
        table_chunks = []

        current_table = []
        in_table = False
        headers = []

        for line in lines:
            stripped = line.strip()
            is_table_line = stripped.startswith("|") and "|" in stripped[1:]

            if is_table_line and not in_table:
                # 开始新表格
                in_table = True
                current_table = [stripped]
                # 提取表头
                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                headers = cells
            elif is_table_line and in_table:
                current_table.append(stripped)
            elif not is_table_line and in_table:
                # 表格结束
                in_table = False
                if current_table:
                    table_text = "\n".join(current_table)
                    table_chunks.append(
                        {
                            "content": f"[表格]\n表头: {', '.join(headers)}\n{table_text}",
                            "chunk_index": len(table_chunks),
                            "strategy": "table",
                            "table_headers": headers,
                            "table_rows": len(current_table) - 1,  # minus header row
                            **meta,
                        }
                    )
                current_table = []
                headers = []

        # 最后一个表格
        if in_table and current_table:
            table_text = "\n".join(current_table)
            table_chunks.append(
                {
                    "content": f"[表格]\n表头: {', '.join(headers)}\n{table_text}",
                    "chunk_index": len(table_chunks),
                    "strategy": "table",
                    "table_headers": headers,
                    "table_rows": len(current_table) - 1,
                    **meta,
                }
            )

        # 如果没有检测到表格 → 用递归切分兜底
        return table_chunks if table_chunks else self._split_recursive(text, meta)

    # ── 文档类型检测 ──

    @staticmethod
    def detect_type(filepath: str, content: str = "") -> str:
        """检测文档类型

        Returns:
            txt / markdown / pdf_text / table / ocr
        """
        ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

        if ext in ("md", "markdown"):
            return "markdown"
        elif ext == "csv":
            return "table"

        # 检查内容特征
        if content:
            # Markdown 表格
            if content.count("|") > 10 and "---" in content:
                return "table"
            # Markdown 标题判断
            if re.search(r"^#{1,3}\s+", content, re.MULTILINE):
                return "markdown"
            # PDF 文字版（经过提取后有标题结构）
            if re.search(r"^(?:第[一二三四五六七八九十\d]+[章节]|\d+[\.\)、])", content, re.MULTILINE):
                return "pdf_text"

        return "txt"

"""文档解析器 — 统一转 LangChain Document（元素级语义标签）

后端:
  1. Unstructured fast（首选，自动检测） — 版面分析 + 语义元素标签
  2. PyMuPDF Markdown 模式（降级）       — PDF 保留标题/粗体/列表
  3. 内置 Markdown 结构解析器（兜底）    — 纯 Python，零依赖

所有后端统一输出:
  list[Document] — 每个 Document 为一个语义元素
  metadata.element_type: Title / Header / NarrativeText / ListItem / Table

使用方式:
    parser = DocumentParser()
    docs = parser.load("manual.pdf")
    # → [Document(page_content="# 标题", metadata={"element_type": "Title"}), ...]
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.documents import Document

from smart_qa.observability.logger import logger

_SUPPORTED = {".txt", ".md", ".markdown", ".pdf", ".csv", ".html", ".json"}


class DocumentParser:
    """文档解析器 — 自动选择后端

    优先级:
      1. Unstructured fast（已安装时）
      2. PyMuPDF Markdown（PDF）
      3. 内置 Markdown 解析（MD/TXT/CSV/HTML）
    """

    def __init__(self, strategy: str = "fast"):
        self.strategy = strategy
        self._unstructured_ok: bool | None = None

    def _check_unstructured(self) -> bool:
        if self._unstructured_ok is not None:
            return self._unstructured_ok
        try:
            from unstructured.partition.auto import partition  # noqa: F401

            # 冒烟测试: 解析一段简单文本确认不 crash
            partition(text="test", strategy="fast", content_type="text/plain")
            self._unstructured_ok = True
            logger.info("Unstructured 已就绪")
        except Exception:
            self._unstructured_ok = False
        return self._unstructured_ok

    # ── 主入口 ──

    def load(self, filepath: str) -> list[Document]:
        ext = Path(filepath).suffix.lower()
        if ext not in _SUPPORTED:
            logger.warning("不支持的文档类型: {}", ext)
            return []

        # 1. Unstructured
        if self._check_unstructured():
            docs = self._load_with_unstructured(filepath, ext)
            if docs:
                return docs

        # 2. PyMuPDF (PDF)
        if ext == ".pdf":
            return self._load_with_pymupdf(filepath)

        # 3. 内置 Markdown 解析
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self._parse_markdown_elements(content, Path(filepath).name)

    def extract_text(self, filepath: str) -> str:
        """兼容旧接口：提取全部文本"""
        docs = self.load(filepath)
        return "\n\n".join(d.page_content for d in docs if d.page_content.strip())

    # ── Unstructured ──

    def _load_with_unstructured(self, filepath: str, ext: str) -> list[Document]:
        from unstructured.partition.auto import partition

        fmt_map = {
            ".txt": "text/plain", ".md": "text/markdown", ".pdf": "application/pdf",
            ".csv": "text/csv", ".html": "text/html", ".json": "application/json",
        }
        content_type = fmt_map.get(ext)

        try:
            elements = partition(
                filename=filepath, content_type=content_type,
                strategy=self.strategy, languages=["chi_sim", "eng"],
            )
        except Exception as e:
            logger.warning("Unstructured 解析失败: {}", e)
            return []

        docs = []
        for el in elements:
            text = str(el).strip()
            if not text:
                continue
            category = type(el).__name__
            md_text = _apply_markdown_tag(category, text)
            docs.append(Document(page_content=md_text, metadata={
                "source": Path(filepath).name, "element_type": category,
            }))

        logger.info("Unstructured: {} ({} elements)", filepath, len(docs))
        return docs

    # ── PyMuPDF (PDF 降级) ──

    def _load_with_pymupdf(self, filepath: str) -> list[Document]:
        import fitz

        docs = []
        doc = fitz.open(filepath)
        num_pages = doc.page_count
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": Path(filepath).name, "element_type": "NarrativeText",
                              "page_number": i + 1},
                ))
        doc.close()
        logger.info("PyMuPDF: {} ({} pages, {} elements)", filepath, num_pages, len(docs))
        return docs

    # ── 内置 Markdown 结构解析 ──

    def _parse_markdown_elements(
        self, text: str, source: str, page_num: int | None = None
    ) -> list[Document]:
        """纯 Python Markdown 元素解析 — 按行识别标题/列表/段落/表格"""
        docs = []
        lines = text.split("\n")
        buf: list[str] = []
        buf_type = "NarrativeText"

        def _flush():
            nonlocal buf, buf_type
            content = "\n".join(buf).strip()
            if content:
                docs.append(Document(page_content=content, metadata={
                    "source": source, "element_type": buf_type, "page_number": page_num,
                }))
            buf, buf_type = [], "NarrativeText"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                _flush()
                continue

            # 标题
            if m := re.match(r"^(#{1,6})\s+(.+)", stripped):
                _flush()
                level = len(m.group(1))
                docs.append(Document(page_content=f"{'#' * level} {m.group(2)}", metadata={
                    "source": source,
                    "element_type": "Title" if level == 1 else "Header",
                    "page_number": page_num,
                }))
                continue

            # 有序/无序列表
            if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
                if buf_type != "ListItem":
                    _flush()
                    buf_type = "ListItem"
                buf.append(stripped)
                continue

            # Markdown 表格
            if "|" in stripped and stripped.count("|") >= 2:
                if buf_type != "Table":
                    _flush()
                    buf_type = "Table"
                buf.append(stripped)
                continue

            # 普通段落
            if buf_type not in ("NarrativeText", "Text"):
                _flush()
            buf.append(stripped)

        _flush()
        return docs

    @staticmethod
    def is_supported(filepath: str) -> bool:
        return Path(filepath).suffix.lower() in _SUPPORTED


# ── Markdown 标签映射 ──

_MD_TAG_MAP = {
    "Title": "# ",
    "Header": "## ",
    "ListItem": "- ",
}


def _apply_markdown_tag(category: str, text: str) -> str:
    prefix = _MD_TAG_MAP.get(category)
    return prefix + text if prefix and not text.startswith(prefix) else text

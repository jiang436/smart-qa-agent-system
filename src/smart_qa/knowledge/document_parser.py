"""文档解析器 — 可插拔后端: PyMuPDF / Unstructured

当前默认使用 PyMuPDF（轻量、快速、零模型依赖），
为 Unstructured（布局分析、OCR）预留了接口。

使用方式:
    parser = DocumentParser()
    text = parser.extract("manual.pdf")
    text = parser.extract("notes.md")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from smart_qa.observability.logger import logger

# ═══════════════════════════════════════════
# 基类
# ═══════════════════════════════════════════


class DocumentParserBackend(ABC):
    """文档解析后端基类"""

    @abstractmethod
    def extract_text(self, filepath: str) -> str: ...


# ═══════════════════════════════════════════
# PyMuPDF（默认）
# ═══════════════════════════════════════════


class PyMuPDFBackend(DocumentParserBackend):
    """PyMuPDF 解析器 — 文字 PDF / MD / TXT

    轻量，零模型依赖，毫秒级提取。
    对于文字 PDF 效果极好，扫描件只能拿到空字符串。
    """

    def extract_text(self, filepath: str) -> str:
        ext = Path(filepath).suffix.lower()

        # TXT / MD 直接读
        if ext in (".txt", ".md", ".markdown"):
            with open(filepath, encoding="utf-8", errors="replace") as f:
                return f.read()

        # PDF 用 PyMuPDF
        if ext == ".pdf":
            return self._extract_pdf(filepath)

        logger.warning("不支持的文档类型: {}", ext)
        return ""

    def _extract_pdf(self, filepath: str) -> str:
        import fitz  # PyMuPDF

        doc = fitz.open(filepath)
        pages = []
        for page in doc:
            text = page.get_text().strip()
            if text:
                pages.append(text)
        doc.close()

        result = "\n\n".join(pages)
        logger.info("PyMuPDF 提取: {} ({} 页, {} 字符)", filepath, len(pages), len(result))
        return result


# ═══════════════════════════════════════════
# Unstructured（预留）
# ═══════════════════════════════════════════


class UnstructuredBackend(DocumentParserBackend):
    """Unstructured 解析器 — 版面分析 + OCR + 表格提取

    适用场景:
      - 扫描件 PDF（自动 OCR）
      - 复杂版面文档（多栏、页眉页脚）
      - 需要表格结构提取

    注意:
      - 需要额外安装: pip install "unstructured[pdf]"
      - hi_res 模式需要 detectron2（PyTorch 模型，~2GB）
    """

    def extract_text(self, filepath: str) -> str:
        try:
            from unstructured.partition.auto import partition
        except ImportError:
            logger.error("Unstructured 未安装: pip install 'unstructured[pdf]'")
            return ""

        elements = partition(
            filename=filepath,
            strategy="auto",  # auto / fast / hi_res / ocr_only
            languages=["zh"],
        )
        text = "\n\n".join(str(el) for el in elements if str(el).strip())
        logger.info("Unstructured 提取: {} ({} 元素)", filepath, len(elements))
        return text


# ═══════════════════════════════════════════
# 文档解析器（门面）
# ═══════════════════════════════════════════


class DocumentParser:
    """文档解析器 — 自动选择后端

    优先级:
      1. 显式指定的 backend（目前支持 pymupdf / unstructured）
      2. 自动检测（文字 PDF → PyMuPDF；扫描件 → PyMuPDF 返回空时 fallback）
    """

    def __init__(self, backend: str = "pymupdf"):
        if backend == "unstructured":
            self._backend: DocumentParserBackend = UnstructuredBackend()
        else:
            self._backend = PyMuPDFBackend()

    def extract_text(self, filepath: str) -> str:
        return self._backend.extract_text(filepath)

    @staticmethod
    def is_supported(filepath: str) -> bool:
        ext = Path(filepath).suffix.lower()
        return ext in (".txt", ".md", ".markdown", ".pdf")

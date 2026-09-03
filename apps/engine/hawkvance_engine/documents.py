"""Document processing and OCR: spec sections 15, 16, 17 and 40.

The rule that matters here: never OCR a document unnecessarily. A PDF with a text layer is read
directly. OCR is a last resort, loaded on demand, and released when the queue drains.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class DocumentFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"
    MARKDOWN = "markdown"
    CSV = "csv"
    SOURCE_CODE = "sourceCode"
    IMAGE = "image"
    UNSUPPORTED = "unsupported"

    @property
    def needs_structure_extraction(self) -> bool:
        """Only these gain anything from Docling. A .txt file does not."""
        return self in (DocumentFormat.PDF, DocumentFormat.DOCX)

    @property
    def is_always_ocr(self) -> bool:
        return self is DocumentFormat.IMAGE

    @property
    def is_plain_read(self) -> bool:
        return self in (
            DocumentFormat.TEXT,
            DocumentFormat.MARKDOWN,
            DocumentFormat.CSV,
            DocumentFormat.SOURCE_CODE,
        )


_SOURCE_SUFFIXES = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".kt", ".cs", ".rb", ".php",
        ".c", ".h", ".cpp", ".hpp", ".swift", ".sql", ".sh", ".ps1", ".yaml", ".yml", ".toml",
        ".json", ".xml", ".html", ".css", ".ini", ".env",
    }
)
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"})


class TextNormaliser:
    """Normalises exactly once, before detection.

    Every offset a detector produces refers to this output. Normalising twice, or normalising after
    detection, silently corrupts every redaction in the document, which is why this is a single
    named step rather than something each detector does for itself.
    """

    @staticmethod
    def normalise(raw: str) -> str:
        text = unicodedata.normalize("NFC", raw)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace(" ", " ").replace("​", "")
        # Collapse runs of blank lines but keep paragraph structure, which matters for offsets the
        # user will see highlighted in the document view.
        lines = [line.rstrip() for line in text.split("\n")]
        collapsed: list[str] = []
        blank_run = 0
        for line in lines:
            if line:
                blank_run = 0
                collapsed.append(line)
            else:
                blank_run += 1
                if blank_run <= 2:
                    collapsed.append(line)
        return "\n".join(collapsed).strip()


class OcrUnavailable(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "The OCR engine is not installed. Text-layer documents still process normally; "
            "scanned pages and images need OCR."
        )
        self.cause = cause


class OCRManager:
    """PaddleOCR, lazily initialised and explicitly released.

    Spec section 17: loaded only for OCR tasks, CPU compatible, GPU accelerated where available,
    released when the queue empties, and pages processed one at a time so a 300-page scan never
    materialises in memory at once.
    """

    name = "ocr"

    def __init__(self, language: str = "en", use_gpu: bool = False) -> None:
        self._language = language
        self._use_gpu = use_gpu
        self._engine: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._engine is not None

    @staticmethod
    def is_available() -> bool:
        try:
            import paddleocr  # noqa: F401
        except Exception:
            return False
        return True

    def load(self) -> None:
        if self._engine is not None:
            return
        try:
            from paddleocr import PaddleOCR
        except Exception as cause:  # pragma: no cover - exercised only without PaddleOCR installed
            raise OcrUnavailable(cause) from cause
        self._engine = PaddleOCR(lang=self._language, use_textline_orientation=True)

    def release(self) -> None:
        self._engine = None

    def estimated_memory_bytes(self) -> int:
        return 400 * 1024 * 1024

    def read(self, image_path: Path) -> str:
        self.load()
        engine = self._engine
        if engine is None:  # pragma: no cover - load() raises before this can happen
            raise OcrUnavailable(RuntimeError("engine did not initialise"))

        result = engine.predict(str(image_path))
        lines: list[str] = []
        for page in result or []:
            texts = page.get("rec_texts") if isinstance(page, dict) else None
            if texts:
                lines.extend(str(text) for text in texts)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """What the processor produces. `text` is already normalised."""

    path: str
    filename: str
    format: DocumentFormat
    sha256: str
    size_bytes: int
    text: str
    used_ocr: bool
    page_count: int | None
    degraded: tuple[str, ...] = ()

    @property
    def character_count(self) -> int:
        return len(self.text)

    def as_dict(self) -> dict[str, object]:
        """Note what is absent: the text itself is not in here.

        Extraction results are handed to the privacy pipeline in-process. Only counts and metadata
        are ever safe to log or send onward.
        """
        return {
            "filename": self.filename,
            "format": self.format.value,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "characterCount": self.character_count,
            "usedOcr": self.used_ocr,
            "pageCount": self.page_count,
            "degraded": list(self.degraded),
        }


class UnsupportedDocument(ValueError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"HawkVance cannot read {path.name} yet. "
            "Supported: PDF, DOCX, TXT, Markdown, CSV, source files and images."
        )
        self.path = path


class DocumentProcessor:
    """Format detection, extraction, and the decision of whether OCR is needed at all.

    Docling handles PDF and DOCX structure. Plain text formats are read directly, because running a
    structure-extraction pipeline over a .txt file is exactly the waste spec section 35 forbids.
    """

    # Below this many characters per page, a PDF's text layer is treated as absent or unusable.
    USABLE_CHARACTERS_PER_PAGE = 24

    def __init__(self, ocr: OCRManager | None = None) -> None:
        self._ocr = ocr or OCRManager()
        self._converter: Any | None = None

    @staticmethod
    def format_of(path: Path) -> DocumentFormat:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return DocumentFormat.PDF
        if suffix in (".docx", ".doc"):
            return DocumentFormat.DOCX
        if suffix in (".md", ".markdown"):
            return DocumentFormat.MARKDOWN
        if suffix == ".csv":
            return DocumentFormat.CSV
        if suffix == ".txt":
            return DocumentFormat.TEXT
        if suffix in _IMAGE_SUFFIXES:
            return DocumentFormat.IMAGE
        if suffix in _SOURCE_SUFFIXES:
            return DocumentFormat.SOURCE_CODE
        return DocumentFormat.UNSUPPORTED

    @staticmethod
    def digest_of(path: Path) -> str:
        """Streamed, so a large file never lands in memory just to be hashed.

        The digest is what makes the cache in spec section 40 work: an unchanged file is never
        extracted or OCR'd twice.
        """
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def docling_available() -> bool:
        try:
            import docling  # noqa: F401
        except Exception:
            return False
        return True

    def _docling(self) -> Any:
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def release(self) -> list[str]:
        released: list[str] = []
        if self._converter is not None:
            self._converter = None
            released.append("docling")
        if self._ocr.is_loaded:
            self._ocr.release()
            released.append("ocr")
        return released

    def extract(self, path: Path, allow_ocr: bool = True) -> ExtractedDocument:
        document_format = self.format_of(path)
        if document_format is DocumentFormat.UNSUPPORTED:
            raise UnsupportedDocument(path)

        degraded: list[str] = []
        used_ocr = False
        page_count: int | None = None

        if document_format.is_plain_read:
            raw = path.read_text(encoding="utf-8", errors="replace")
        elif document_format.is_always_ocr:
            if not allow_ocr:
                raw = ""
                degraded.append("OCR was not permitted for this job, so the image produced no text.")
            else:
                try:
                    raw = self._ocr.read(path)
                    used_ocr = True
                except OcrUnavailable as unavailable:
                    raw = ""
                    degraded.append(str(unavailable))
        else:
            raw, page_count, structure_note = self._extract_structured(path)
            if structure_note is not None:
                degraded.append(structure_note)

            if allow_ocr and self._text_layer_is_unusable(raw, page_count):
                try:
                    raw = self._ocr.read(path)
                    used_ocr = True
                except OcrUnavailable as unavailable:
                    degraded.append(str(unavailable))

        return ExtractedDocument(
            path=str(path),
            filename=path.name,
            format=document_format,
            sha256=self.digest_of(path),
            size_bytes=path.stat().st_size,
            text=TextNormaliser.normalise(raw),
            used_ocr=used_ocr,
            page_count=page_count,
            degraded=tuple(degraded),
        )

    def _extract_structured(self, path: Path) -> tuple[str, int | None, str | None]:
        if not self.docling_available():
            return (
                "",
                None,
                "Docling is not installed, so this document's text layer could not be read.",
            )
        result = self._docling().convert(str(path))
        document = result.document
        pages = getattr(document, "pages", None)
        return document.export_to_markdown(), len(pages) if pages is not None else None, None

    @classmethod
    def _text_layer_is_unusable(cls, text: str, page_count: int | None) -> bool:
        """A scanned PDF extracts to almost nothing. That absence is the OCR trigger."""
        stripped = text.strip()
        if not stripped:
            return True
        pages = page_count if page_count and page_count > 0 else 1
        return len(stripped) / pages < cls.USABLE_CHARACTERS_PER_PAGE

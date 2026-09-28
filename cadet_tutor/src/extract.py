"""PDF text extraction with PyMuPDF, falling back to offline Tesseract OCR per page."""
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from src import config


@dataclass
class Page:
    number: int  # 1-based
    text: str
    ocr: bool  # True if the text came from Tesseract


class OcrUnavailable(RuntimeError):
    """Raised when a page needs OCR but Tesseract or its language data is missing."""


def _clean(text: str) -> str:
    """Fold Arabic presentation forms and ligatures that some PDFs emit into normal
    letters (NFKC), and trim trailing whitespace. Words and order are unchanged."""
    text = unicodedata.normalize("NFKC", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _ocr(page: pymupdf.Page) -> str:
    """Render the page and run the Tesseract CLI on it. (PyMuPDF's built-in OCR
    text page reverses some right-to-left lines, so it is not used.)"""
    png = page.get_pixmap(dpi=config.OCR_DPI).tobytes("png")
    cmd = [config.TESSERACT_CMD, "stdin", "stdout", "-l", config.OCR_LANGUAGES]
    try:
        res = subprocess.run(cmd, input=png, capture_output=True, timeout=300, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise OcrUnavailable(
            f"OCR needed on page {page.number + 1} but Tesseract failed: "
            f"{detail.decode(errors='replace').strip()[:200]}. Install Tesseract with the Arabic "
            "and French language data (see README)."
        ) from exc
    return res.stdout.decode("utf-8", errors="replace")


def extract_pages(pdf_path: Path) -> list[Page]:
    """Text of every page; pages with (almost) no text layer are OCR'd.

    Text is read in the PDF's own order: sorting by position breaks right-to-left lines.
    """
    pages = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            text = _clean(page.get_text())
            ocr = len(text) < config.OCR_MIN_CHARS
            if ocr:
                text = _clean(_ocr(page))
            if text:
                pages.append(Page(page.number + 1, text, ocr))
    return pages

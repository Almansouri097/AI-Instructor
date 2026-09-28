"""Phase 12: PyMuPDF extraction and Tesseract OCR on French and Arabic PDFs."""
import re
import shutil
from pathlib import Path

import pytest

from src import config
from src.extract import OcrUnavailable, extract_pages

FIXTURES = Path(__file__).parent / "fixtures"
needs_tesseract = pytest.mark.skipif(shutil.which(config.TESSERACT_CMD) is None, reason="Tesseract not installed")


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def test_french_text_layer():
    [page] = extract_pages(FIXTURES / "fr_geneve.pdf")
    assert not page.ocr
    assert "prisonniers de guerre doivent être traités en tout temps avec" in " ".join(page.text.split())


def test_arabic_text_layer_is_logical_order_and_normal_letters():
    [page] = extract_pages(FIXTURES / "ar_geneve.pdf")
    assert not page.ocr
    assert "يجب معاملة أسرى الحرب معاملة إنسانية" in page.text
    # No presentation forms (U+FB50-U+FEFF) survive: they break search and embeddings.
    assert not any("ﭐ" <= c <= "﻿" for c in page.text)


@needs_tesseract
@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_scanned_page_is_ocrd_accurately(lang):
    [truth] = extract_pages(FIXTURES / f"{lang}_geneve.pdf")
    [scan] = extract_pages(FIXTURES / f"{lang}_geneve_scanned.pdf")
    assert scan.ocr
    expected, got = words(truth.text), words(scan.text)
    same = sum(a == b for a, b in zip(expected, got))
    assert same / len(expected) > 0.95


def test_missing_tesseract_gives_clear_error(monkeypatch):
    monkeypatch.setattr(config, "TESSERACT_CMD", "/nonexistent/tesseract")
    with pytest.raises(OcrUnavailable, match="Install Tesseract"):
        extract_pages(FIXTURES / "ar_geneve_scanned.pdf")

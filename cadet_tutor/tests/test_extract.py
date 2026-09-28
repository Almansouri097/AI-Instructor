"""Phase 12: PyMuPDF extraction and Tesseract OCR on French and Arabic PDFs."""
import re
import shutil
from pathlib import Path

import pymupdf
import pytest

from src import config, extract
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


def test_repeated_headers_are_removed():
    header = "GESTION DE LA SÉCURITÉ  •  DR. X  •  ACADÉMIE"
    pages = [f"{header}\nContenu {i}" for i in range(6)] + ["Page sans en-tête"]
    drop = extract.repeated_lines(pages)
    assert extract._norm_line(header) in drop
    assert not any("contenu" in line for line in drop)


def test_broken_arabic_text_layer_is_detected():
    # Pattern seen in real course PDFs: ligatures stored with letters swapped or dropped.
    broken = ("احلمد هلل الذي جعل العربية وعاء لكتابه الكرمي يلهج هبا املؤمن يف معراج صلواته "
              "والصاة والسام على من أويت جوامع الكلم فا خيفى على كل يقظان ما متر به األمة "
              "إىل غر ذلك من األفكار الرعناء اليت تنبئ بقبح النوايا")
    correct = ("الحمد لله الذي جعل العربية وعاء لكتابه الكريم يلهج بها المؤمن في معراج صلواته "
               "والصلاة والسلام على من أوتي جوامع الكلم فلا يخفى على كل يقظان ما تمر به الأمة "
               "إلى غير ذلك من الأفكار الرعناء التي تنبئ بقبح النوايا")
    assert extract.broken_arabic(broken)
    assert not extract.broken_arabic(correct)


def test_arabic_comma_fix_and_bidi_marks():
    assert extract._clean("‎Lex‏ نص") == "Lex نص"


@needs_tesseract
def test_scanned_arabic_uses_arabic_only_ocr():
    [scan] = extract_pages(FIXTURES / "ar_geneve_scanned.pdf")
    assert scan.reason.endswith("OCR ara")  # script detected, no ara+fra mixing
    assert not re.search(r"[A-Za-z]", scan.text)


@needs_tesseract
def test_short_text_page_is_kept_when_ocr_finds_nothing(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Thank you")
    doc.save(tmp_path / "short.pdf")
    [page] = extract_pages(tmp_path / "short.pdf")
    assert page.text == "Thank you" and not page.ocr


def _position(text: str, phrase: str) -> int:
    pos = " ".join(text.split()).find(phrase)
    assert pos >= 0, f"{phrase!r} not found in OCR text"
    return pos


@needs_tesseract
def test_qa_rows_keep_each_answer_after_its_question():
    # Plain Tesseract reads all questions, then all answers.
    [page] = extract_pages(FIXTURES / "fr_rows_scanned.pdf")
    order = [_position(page.text, p) for p in
             ["QUESTIONS DE RÉVISION", "Question un", "Réponse un", "Question deux", "Réponse deux",
              "Question trois", "Réponse trois"]]
    assert order == sorted(order)
    assert "RÉPONSES — QUESTIONS DE RÉVISION" in page.text  # one-line title not split


@needs_tesseract
def test_arabic_columns_read_right_to_left():
    # Plain Tesseract reads straight across both columns.
    [page] = extract_pages(FIXTURES / "ar_columns_scanned.pdf")
    right = _position(page.text, "العمود الأيمن. يجب معاملة أسرى الحرب معاملة إنسانية")
    left = _position(page.text, "العمود الأيسر. لا يلتزم أسير الحرب")
    assert right < left


def test_missing_tesseract_gives_clear_error(monkeypatch):
    monkeypatch.setattr(config, "TESSERACT_CMD", "/nonexistent/tesseract")
    with pytest.raises(OcrUnavailable, match="Install Tesseract"):
        extract_pages(FIXTURES / "ar_geneve_scanned.pdf")

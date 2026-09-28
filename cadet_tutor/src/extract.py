"""PDF text extraction with PyMuPDF, falling back to offline Tesseract OCR per page.

A page is OCR'd when, after removing running headers/footers, it has almost no text
(scans, slides exported as pictures) or when its Arabic text layer is corrupted
(some Arabic fonts store ligatures with letters swapped or dropped).
"""
import csv
import io
import re
import subprocess
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from src import config

ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ſ]")
BIDI_CONTROLS = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩"))

# Forms produced by Arabic fonts whose ligatures extract with letters swapped or dropped
# (e.g. "في" -> "يف", "الله" -> "اهلل", "المؤمن" -> "املؤمن"). Rare in correct Arabic.
BROKEN_AR_WORDS = {"يف", "إىل", "عىل", "هلل", "اهلل", "حى", "إال"}
BROKEN_AR_PREFIXES = ("امل", "احل", "األ", "اإل", "اجل", "اخل", "اهل", "اآل", "واحل", "واأل", "واإل", "بامل", "باحل", "باأل")


@dataclass
class Page:
    number: int  # 1-based
    text: str
    ocr: bool  # True if the text came from Tesseract
    reason: str = ""  # why the page was OCR'd, and in which language


class OcrUnavailable(RuntimeError):
    """Raised when a page needs OCR but Tesseract or its language data is missing."""


def _clean(text: str) -> str:
    """Fold Arabic presentation forms and ligatures (NFKC), drop invisible direction
    marks, trim trailing spaces. Words and their order are unchanged."""
    text = unicodedata.normalize("NFKC", text).translate(BIDI_CONTROLS)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _norm_line(line: str) -> str:
    return " ".join(line.split()).casefold()


def repeated_lines(page_texts: list[str]) -> set[str]:
    """Lines (normalised) that recur on at least half the pages: headers and footers."""
    if len(page_texts) < 3:
        return set()
    counts = Counter(l for t in page_texts for l in {_norm_line(x) for x in t.splitlines() if x.strip()})
    return {l for l, n in counts.items() if n >= max(3, len(page_texts) / 2)}


def _strip_lines(text: str, drop: set[str]) -> str:
    return "\n".join(l for l in text.splitlines() if _norm_line(l) not in drop).strip()


def arabic_share(text: str) -> float:
    """Fraction of letters that are Arabic (0 when there are no letters)."""
    ar, la = len(ARABIC_RE.findall(text)), len(LATIN_RE.findall(text))
    return ar / (ar + la) if ar + la else 0.0


def broken_arabic(text: str) -> bool:
    """True if an Arabic text layer shows the swapped/dropped-ligature corruption."""
    words = [w.replace("ـ", "") for w in re.findall(r"[؀-ۿ]+", text)]
    if len(words) < 20:
        return False
    bad = sum(1 for w in words if w in BROKEN_AR_WORDS or w.startswith(BROKEN_AR_PREFIXES))
    return bad / len(words) > config.BROKEN_ARABIC_THRESHOLD


def _tesseract(args: list[str], png: bytes, page_no: int) -> str:
    try:
        res = subprocess.run([config.TESSERACT_CMD, "stdin", "stdout", *args], input=png,
                             capture_output=True, timeout=300, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise OcrUnavailable(
            f"OCR needed on page {page_no} but Tesseract failed: "
            f"{detail.decode(errors='replace').strip()[:200]}. Install Tesseract with the Arabic "
            "and French language data (see README)."
        ) from exc
    return res.stdout.decode("utf-8", errors="replace")


def detect_script(png: bytes, page_no: int) -> str | None:
    """'ara', 'fra' or None, using Tesseract's script detection (needs enough text)."""
    try:
        out = _tesseract(["--psm", "0", "-l", "osd"], png, page_no)
    except OcrUnavailable:
        return None  # "too few characters" is reported as a failure
    script = re.search(r"^Script: (\w+)", out, re.M)
    return {"Arabic": "ara", "Latin": "fra"}.get(script.group(1)) if script else None


def ocr_png(png: bytes, lang: str, page_no: int = 0) -> str:
    """OCR one page image; drop low-confidence words (icons and photos read as text)."""
    min_conf = min(config.OCR_MIN_WORD_CONF.get(l, 30) for l in lang.split("+"))
    tsv = _tesseract(["-l", lang, "tsv"], png, page_no)
    lines: dict[tuple[str, str, str], list[str]] = {}
    for r in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["level"] == "5" and r["text"].strip() and float(r["conf"]) >= min_conf:
            lines.setdefault((r["block_num"], r["par_num"], r["line_num"]), []).append(r["text"])
    out = []
    for words in lines.values():
        line = " ".join(words)
        if "ara" in lang and "«" not in line:  # Tesseract reads the Arabic comma as »
            line = line.replace("»", "،")
        out.append(line)
    return "\n".join(out)


def _ocr_page(page: pymupdf.Page, layer_text: str) -> tuple[str, str]:
    """OCR in the page's own language: mixing ara+fra turns some Arabic words into
    Latin gibberish. Returns (text, language used)."""
    png = page.get_pixmap(dpi=config.OCR_DPI).tobytes("png")
    if len(ARABIC_RE.findall(layer_text)) + len(LATIN_RE.findall(layer_text)) >= 20:
        lang = "ara" if arabic_share(layer_text) > 0.5 else "fra"
    else:
        lang = detect_script(png, page.number + 1) or config.OCR_LANGUAGES
    return ocr_png(png, lang, page.number + 1), lang


def extract_pages(pdf_path: Path) -> list[Page]:
    """Text of every page, without running headers/footers; OCR where needed.

    The text layer is read in the PDF's own order: sorting by position breaks
    right-to-left lines.
    """
    with pymupdf.open(pdf_path) as doc:
        layers = [_clean(p.get_text()) for p in doc]
        drop = repeated_lines(layers)
        pages = []
        for page, layer in zip(doc, layers):
            body = _strip_lines(layer, drop)
            reason = ""
            if len(body) < config.OCR_MIN_CHARS:
                reason = "little or no text"
            elif arabic_share(body) > 0.5 and broken_arabic(body):
                reason = "corrupted Arabic text layer"
            if reason:
                text, lang = _ocr_page(page, layer)
                ocr_body = _strip_lines(_clean(text), drop)
                if len(ocr_body) > len(body) or reason.startswith("corrupted"):
                    body, reason = ocr_body, f"{reason}, OCR {lang}"
                else:  # OCR found nothing more than the short text layer: keep it
                    reason = ""
            if body:
                pages.append(Page(page.number + 1, body, bool(reason), reason))
    return pages

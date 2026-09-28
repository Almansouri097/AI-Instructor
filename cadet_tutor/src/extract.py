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
# OCR "words" with no letters or digits that are not sentence punctuation: box edges,
# arrows and icon fragments read as text (e.g. "|", "—}", "[").
JUNK_SYMBOLS_RE = re.compile(r"[^\w?!:;.,،؛؟«»%()\"'’\-–—•]+")
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


def _strip_lines(text: str, drop: set[str], fragments: bool = False) -> str:
    """Remove header/footer lines. With fragments=True (OCR output, where a header may be
    split or slightly misread) also remove lines that are a piece of a header line."""
    def is_header(line: str) -> bool:
        n = _norm_line(line)
        return n in drop or (fragments and len(n) >= 8 and any(n in d for d in drop))
    return "\n".join(l for l in text.splitlines() if not is_header(l)).strip()


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


@dataclass
class Word:
    text: str
    line: tuple[str, str, str]  # Tesseract (block, paragraph, line)
    index: int  # position in Tesseract's output (logical order within a line)
    x0: int
    y0: int
    x1: int
    y1: int


def _gaps(words: list[Word], vertical: bool, min_gap: float) -> list[tuple[int, int]]:
    """Empty bands between words, as (start, end) along x (vertical=True) or y."""
    spans = sorted((w.x0, w.x1) if vertical else (w.y0, w.y1) for w in words)
    gaps, reach = [], spans[0][1]
    for start, end in spans[1:]:
        if start - reach >= min_gap:
            gaps.append((reach, start))
        reach = max(reach, end)
    return gaps


def _median_height(words: list[Word]) -> int:
    return sorted(w.y1 - w.y0 for w in words)[len(words) // 2]


def _xy_cut(words: list[Word], rtl: bool) -> list[list[Word]]:
    """Recursive XY-cut: split at a full-height gutter into columns (right to left for
    Arabic), else at wide horizontal gaps into bands (top to bottom). Gap thresholds
    scale with the region's own text size. Returns regions in reading order."""
    content = [w for w in words if any(c.isalnum() for c in w.text)]  # symbols don't block gutters
    if len(content) > 1:
        height = _median_height(content)
        columns = _gaps(content, vertical=True, min_gap=config.COLUMN_GAP * height)
        if columns and len({w.line for w in content}) > 1:  # a single line is never split
            cut = sum(max(columns, key=lambda g: g[1] - g[0])) / 2
            parts = [[w for w in words if (w.x0 + w.x1) / 2 < cut], [w for w in words if (w.x0 + w.x1) / 2 >= cut]]
            if rtl:
                parts.reverse()
            return [r for p in parts if p for r in _xy_cut(p, rtl)]
        bands = _gaps(content, vertical=False, min_gap=config.BAND_GAP * height)
        if bands:
            edges = [-1] + [(a + b) / 2 for a, b in bands] + [float("inf")]
            parts = [[w for w in words if lo <= (w.y0 + w.y1) / 2 < hi] for lo, hi in zip(edges, edges[1:])]
            return [r for p in parts if p for r in _xy_cut(p, rtl)]
    return [words]


def _region_lines(words: list[Word]) -> list[str]:
    """Lines of one region: Tesseract's lines, top to bottom, words in logical order."""
    lines: dict[tuple[str, str, str], list[Word]] = {}
    for w in words:
        lines.setdefault(w.line, []).append(w)
    ordered = sorted(lines.values(), key=lambda ws: min(w.y0 for w in ws))
    return [" ".join(w.text for w in sorted(ws, key=lambda w: w.index)) for ws in ordered]


def ocr_png(png: bytes, lang: str, page_no: int = 0) -> str:
    """OCR one page image: drop low-confidence words (icons and photos read as text) and
    rebuild the reading order so columns are not read straight across."""
    min_conf = min(config.OCR_MIN_WORD_CONF.get(l, 30) for l in lang.split("+"))
    tsv = _tesseract(["-l", lang, "tsv"], png, page_no)
    words = []
    for i, r in enumerate(csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)):
        text = r["text"].strip()
        if r["level"] == "5" and text and float(r["conf"]) >= min_conf and not JUNK_SYMBOLS_RE.fullmatch(text):
            x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            words.append(Word(text, (r["block_num"], r["par_num"], r["line_num"]), i, x, y, x + w, y + h))
    if not words:
        return ""
    regions = _xy_cut(words, rtl=lang == "ara")
    out = []
    for region in regions:
        for line in _region_lines(region):
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
                ocr_body = _strip_lines(_clean(text), drop, fragments=True)
                if len(ocr_body) > len(body) or reason.startswith("corrupted"):
                    body, reason = ocr_body, f"{reason}, OCR {lang}"
                else:  # OCR found nothing more than the short text layer: keep it
                    reason = ""
            if body:
                pages.append(Page(page.number + 1, body, bool(reason), reason))
    return pages

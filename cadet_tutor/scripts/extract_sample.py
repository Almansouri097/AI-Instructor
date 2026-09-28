"""Show what text extraction produces, so it can be checked before ingesting.

Usage (from the project root):
    python -m scripts.extract_sample                         # every PDF in data/docs
    python -m scripts.extract_sample data/docs/a.pdf b.pdf   # specific files
    python -m scripts.extract_sample --chars 1200 --pages 3  # longer samples
"""
import argparse
import sys
from pathlib import Path

from src import config
from src.extract import OcrUnavailable, extract_pages


def script_mix(text: str) -> str:
    """Share of Arabic vs Latin letters, e.g. 'Arabic 97% / Latin 3%'."""
    arabic = sum(1 for c in text if "؀" <= c <= "ۿ")
    latin = sum(1 for c in text if c.isalpha() and c.isascii() or "À" <= c <= "ſ")
    total = arabic + latin or 1
    return f"Arabic {100 * arabic // total}% / Latin {100 * latin // total}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdfs", nargs="*", type=Path)
    parser.add_argument("--chars", type=int, default=600, help="characters shown per page")
    parser.add_argument("--pages", type=int, default=2, help="pages shown per document")
    args = parser.parse_args()

    pdfs = args.pdfs or sorted(config.DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {config.DOCS_DIR}.")
    for pdf in pdfs:
        print("=" * 80)
        try:
            pages = extract_pages(pdf)
        except OcrUnavailable as exc:
            print(f"{pdf.name}: {exc}")
            continue
        ocr_pages = [p.number for p in pages if p.ocr]
        text = "\n".join(p.text for p in pages)
        print(f"{pdf.name}: {len(pages)} pages with text, {len(text)} characters, {script_mix(text)}")
        print(f"OCR'd pages: {ocr_pages or 'none'}")
        for p in pages:
            if p.ocr:
                print(f"  page {p.number}: {p.reason}")
        for p in pages[: args.pages]:
            print(f"\n--- page {p.number} ({p.reason if p.ocr else 'text layer'}) ---")
            print(p.text[: args.chars])


if __name__ == "__main__":
    main()

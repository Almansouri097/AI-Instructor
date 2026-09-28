"""Demo mode: load sample documents and orders so the app can be shown offline."""
import contextlib
import csv
import io
import shutil

from scripts import make_sample_docs
from src import config, ingest

SAMPLE_ORDERS_DIR = config.DATA_DIR / "sample_orders"
# French and Arabic sample documents, each on a topic found only in that language, so
# cross-lingual retrieval is visible. The Arabic guide's page 2 is a scan (needs OCR).
SAMPLE_DOCS_DIR = config.DATA_DIR / "sample_docs"
MULTILINGUAL_LEVELS: dict[str, int] = {
    "manuel_transmissions_fr.pdf": 0,
    "guide_secourisme_ar.pdf": 0,
    # Public document with an embedded prompt-injection attack (en/fr/ar), to show
    # that it is flagged and cannot unlock restricted content.
    "injection_test.pdf": 0,
}
SAMPLE_ORDERS: dict[str, str] = {
    "Excellent": "excellent.txt",
    "Average": "average.txt",
    "Missing sections": "incomplete.txt",
}


class DemoError(RuntimeError):
    """Raised with a readable message when the demo data cannot be loaded."""


def sample_order(name: str) -> str:
    """Text of one sample order by display name."""
    return (SAMPLE_ORDERS_DIR / SAMPLE_ORDERS[name]).read_text(encoding="utf-8")


def ensure_levels() -> None:
    """Make levels.csv list every demo document at its demo level; keep other rows."""
    rows: dict[str, str] = {}
    if config.LEVELS_CSV.exists():
        with config.LEVELS_CSV.open(newline="", encoding="utf-8") as f:
            rows = {r["filename"]: r["level"] for r in csv.DictReader(f) if r.get("filename")}
    demo_levels = {**make_sample_docs.LEVELS, **MULTILINGUAL_LEVELS}
    rows.update({name: str(level) for name, level in demo_levels.items()})
    with config.LEVELS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["filename", "level"])
        writer.writerows(rows.items())


def load() -> str:
    """Write the sample PDFs, register their levels and ingest. Returns the ingest log."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        make_sample_docs.main()
        config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
        for name in MULTILINGUAL_LEVELS:
            shutil.copy2(SAMPLE_DOCS_DIR / name, config.DOCS_DIR / name)
        ensure_levels()
        try:
            ingest.run()
        except SystemExit as exc:  # ingest reports fatal problems via sys.exit
            raise DemoError(str(exc.code)) from None
    return out.getvalue()

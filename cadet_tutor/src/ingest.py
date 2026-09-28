"""CLI: parse PDFs in data/docs, chunk, embed with Ollama and store in ChromaDB.

Usage (from the project root):
    python -m src.ingest            # incremental: only new/changed documents
    python -m src.ingest --reset    # wipe the collection and rebuild
"""
import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import chromadb
from pypdf import PdfReader

from src import config, llm


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int


def get_collection(reset: bool = False) -> chromadb.Collection:
    """Open (or create) the persistent Chroma collection."""
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if reset:
        try:
            client.delete_collection(config.COLLECTION_NAME)
        except Exception:  # noqa: BLE001 - collection did not exist
            pass
    return client.get_or_create_collection(
        config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}, embedding_function=None
    )


def load_levels(path: Path = config.LEVELS_CSV) -> dict[str, int]:
    """Read filename -> clearance level from levels.csv (missing file = all public)."""
    if not path.exists():
        return {}
    levels: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, level = (row.get("filename") or "").strip(), (row.get("level") or "").strip()
            if not name:
                continue
            try:
                levels[name] = int(level)
            except ValueError:
                print(f"  ! levels.csv: invalid level '{level}' for {name}, using {config.DEFAULT_LEVEL}")
    return levels


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Return (1-based page number, text) for every page that has text."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i, text))
    return pages


def chunk_pages(
    pages: list[tuple[int, str]],
    size: int = config.CHUNK_WORDS,
    overlap: int = config.CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split page texts into ~size-word windows with overlap.

    Every word keeps its page number, so a chunk that crosses a page break
    records the exact page range it covers (page_start..page_end).
    """
    words: list[tuple[str, int]] = [(w, num) for num, text in pages for w in text.split()]
    if not words:
        return []
    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        chunks.append(
            Chunk(" ".join(w for w, _ in window), window[0][1], window[-1][1])
        )
        if start + size >= len(words):
            break
    return chunks


def page_label(doc: str, page_start: int, page_end: int) -> str:
    """Citation label used everywhere: [DocName, p.X] or [DocName, p.X-Y]."""
    pages = f"{page_start}" if page_start == page_end else f"{page_start}-{page_end}"
    return f"[{Path(doc).stem}, p.{pages}]"


def fingerprint(pdf_path: Path, level: int) -> str:
    """Hash of file content + level + chunk settings; changes trigger re-ingestion."""
    h = hashlib.sha256(pdf_path.read_bytes())
    h.update(f"|{level}|{config.CHUNK_WORDS}|{config.CHUNK_OVERLAP}|{config.EMBED_MODEL}".encode())
    return h.hexdigest()[:16]


def stored_fingerprint(col: chromadb.Collection, doc: str) -> str | None:
    """Fingerprint of a document already in the store, if any."""
    res = col.get(where={"doc": doc}, limit=1, include=["metadatas"])
    return res["metadatas"][0]["fingerprint"] if res["ids"] else None


def ingest_file(col: chromadb.Collection, pdf_path: Path, level: int) -> str:
    """Ingest one PDF; replaces previous chunks of that document. Returns a status line."""
    doc = pdf_path.name
    fp = fingerprint(pdf_path, level)
    if stored_fingerprint(col, doc) == fp:
        return f"= {doc}: unchanged, skipped"

    chunks = chunk_pages(extract_pages(pdf_path))
    if not chunks:
        return f"! {doc}: no extractable text (scanned PDF?), skipped"

    embeddings = llm.embed([c.text for c in chunks])
    col.delete(where={"doc": doc})  # drop stale chunks from an older version
    col.add(
        ids=[f"{doc}::{i}" for i in range(len(chunks))],
        documents=[c.text for c in chunks],
        embeddings=embeddings,
        metadatas=[
            {
                "doc": doc,
                "page": c.page_start,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "level": level,
                "label": page_label(doc, c.page_start, c.page_end),
                "fingerprint": fp,
            }
            for c in chunks
        ],
    )
    return f"+ {doc}: {len(chunks)} chunks, level {level} ({config.LEVEL_NAMES.get(level, '?')})"


def remove_missing(col: chromadb.Collection, present: set[str]) -> list[str]:
    """Delete chunks of documents no longer in data/docs."""
    stored = {m["doc"] for m in col.get(include=["metadatas"])["metadatas"]}
    gone = sorted(stored - present)
    for doc in gone:
        col.delete(where={"doc": doc})
    return gone


def run(reset: bool = False, only: str | None = None) -> None:
    """Ingest all PDFs (or one file with `only`) from data/docs."""
    pdfs = sorted(config.DOCS_DIR.glob("*.pdf"))
    if only:
        pdfs = [p for p in pdfs if p.name == only]
        if not pdfs:
            sys.exit(f"No PDF named '{only}' in {config.DOCS_DIR}")
    if not pdfs:
        sys.exit(f"No PDFs found in {config.DOCS_DIR}. Add documents and retry.")

    problems = llm.check_ollama(models=(config.EMBED_MODEL,))
    if problems:
        sys.exit("\n".join(problems))

    levels = load_levels()
    col = get_collection(reset=reset)
    for pdf in pdfs:
        level = levels.get(pdf.name, config.DEFAULT_LEVEL)
        if pdf.name not in levels:
            print(f"  ! {pdf.name} not in levels.csv, defaulting to level {config.DEFAULT_LEVEL}")
        try:
            print(ingest_file(col, pdf, level))
        except llm.OllamaError as exc:
            sys.exit(str(exc))
        except Exception as exc:  # noqa: BLE001 - keep going on a bad PDF
            print(f"! {pdf.name}: failed ({exc})")
    if not only:
        for doc in remove_missing(col, {p.name for p in pdfs}):
            print(f"- {doc}: removed (file no longer in data/docs)")
    print(f"Collection '{config.COLLECTION_NAME}' now holds {col.count()} chunks.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDFs into the local vector store.")
    parser.add_argument("--reset", action="store_true", help="wipe the collection first")
    parser.add_argument("--file", help="ingest only this PDF (file name in data/docs)")
    args = parser.parse_args()
    run(reset=args.reset, only=args.file)


if __name__ == "__main__":
    main()

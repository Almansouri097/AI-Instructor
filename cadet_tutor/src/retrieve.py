"""Clearance-aware retrieval from the Chroma store, plus citation helpers."""
import re
from dataclasses import dataclass

from src import audit, config, guard, llm
from src.ingest import get_collection
from src.text import normalize_arabic

CITATION_RE = re.compile(r"\[([^\[\],]+), p\.(\d+)(?:-(\d+))?\]")


@dataclass
class Hit:
    text: str
    doc: str
    label: str
    level: int
    score: float  # cosine similarity, higher is better
    lang: str = "en"
    suspicious: bool = False  # text looks like instructions aimed at the AI


def level_filter(level: int) -> dict:
    """Chroma `where` clause: only chunks at or below the user's clearance."""
    return {"level": {"$lte": level}}


def search(query: str, level: int, k: int = config.TOP_K) -> list[Hit]:
    """Return the top-k chunks the user is cleared to see, in any language.

    bge-m3 embeds French, Arabic and English in one space, so a question in one
    language finds passages in the others. The query is normalised like the index.
    Every call is written to the audit log, including ones that return nothing.
    """
    hits = []
    col = get_collection()
    if col.count() > 0:
        [vector] = llm.embed([normalize_arabic(query)])
        res = col.query(
            query_embeddings=[vector],
            n_results=k,
            where=level_filter(level),
            include=["documents", "metadatas", "distances"],
        )
        for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            # Defence in depth: never trust the store filter alone.
            if int(meta["level"]) > level:
                continue
            hits.append(Hit(text, meta["doc"], meta["label"], int(meta["level"]), 1.0 - dist,
                            meta.get("lang", "en"), guard.looks_like_injection(text)))
    flags = [f"possible prompt injection in {h.label}" for h in hits if h.suspicious]
    audit.record(query, level, hits, flags)
    return hits


def format_context(hits: list[Hit]) -> str:
    """Render hits as fenced, labelled excerpts for the prompt (see guard.py)."""
    return "\n\n".join(guard.fence_document(h.label, h.text) for h in hits)


def extract_citations(text: str) -> list[str]:
    """All citation labels in a reply, normalised to the [Doc, p.X(-Y)] form."""
    out = []
    for doc, start, end in CITATION_RE.findall(text):
        out.append(f"[{doc.strip()}, p.{start}{'-' + end if end else ''}]")
    return out


def invalid_citations(text: str, hits: list[Hit]) -> list[str]:
    """Citations in `text` that do not match any retrieved excerpt."""
    allowed = {h.label for h in hits}
    return [c for c in extract_citations(text) if c not in allowed]

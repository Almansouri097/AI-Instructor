# Read this first

Rules for anyone (human or AI) working on Cadet Tutor. The full brief is in
[SPEC.md](SPEC.md); these rules override convenience.

## 1. Offline only
Everything runs locally with no internet at runtime. No cloud APIs, no telemetry,
no remote model calls, no CDN assets. Documents and questions never leave the machine.

## 2. The stack is fixed
Do not add, swap or remove any of these:

| Part          | Choice                                  |
|---------------|-----------------------------------------|
| LLM           | Ollama `qwen2.5:7b` (`format="json"` for structured output) |
| Embeddings    | Ollama `bge-m3`                         |
| Vector store  | ChromaDB, persistent local folder       |
| PDF parsing   | PyMuPDF, with Tesseract OCR (ara+fra) for scanned pages (phase 12; was pypdf) |
| UI            | Streamlit                               |
| Language      | Python 3.11, minimal dependencies in `requirements.txt` |

## 3. Build in phases
Work through the phases in order, and verify each one before starting the next:

1. Structure, config, ingestion, then test on one PDF.
2. Retrieval with clearance filtering, then prove a Cadet cannot retrieve level-2 chunks.
3. Ask mode.
4. Socratic mode.
5. Order grader.
6. UI.
7. Evaluation.
8. Demo mode: sample orders, a level-2 test document, a Demo button, `DEMO.md`,
   verified with networking off.
9. Security: SQLite audit log with an Instructor-only Audit tab, prompt-injection
   defence, tests proving a Cadet never receives level-1 or level-2 chunks in any mode.
10. Retrieval upgrades: BM25 + vector hybrid search with reciprocal rank fusion,
    cross-encoder reranking (top 20 to best 5), streamed responses.
11. Progress tracking: per-cadet results in SQLite, Instructor dashboard, quiz from
    a chosen document, PDF feedback report for graded orders.

12. Multilingual documents (French and Arabic): PyMuPDF extraction with Tesseract OCR
    fallback, per-chunk language, Arabic normalisation for indexing, cross-lingual
    retrieval, right-to-left display, configurable model, per-language evaluation.
    **Built next, before phases 9-11**, starting with an extraction check on real
    French and Arabic documents.

Phases 8-12 are specified at the end of [SPEC.md](SPEC.md). The packages they name
(`rank_bm25`, the `bge-reranker-v2-m3` reranker, SQLite, and for phase 12 PyMuPDF
replacing pypdf plus Tesseract OCR with Arabic and French) are approved changes to the stack.

## 4. Wait for confirmation after each phase
At the end of every phase, report:
- what was built,
- how to test it,

then **stop and wait for the owner's confirmation** before starting the next phase.

## 5. Keep all prompts in one place
Every LLM prompt lives as a named constant in a single module, so prompts can be tuned
without touching logic. Modes import prompts from there; no prompt strings are defined
inline anywhere else.

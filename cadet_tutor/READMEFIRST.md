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
| PDF parsing   | pypdf                                   |
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

## 4. Wait for confirmation after each phase
At the end of every phase, report:
- what was built,
- how to test it,

then **stop and wait for the owner's confirmation** before starting the next phase.

## 5. Keep all prompts in one place
Every LLM prompt lives as a named constant in a single module, so prompts can be tuned
without touching logic. Modes import prompts from there; no prompt strings are defined
inline anywhere else.

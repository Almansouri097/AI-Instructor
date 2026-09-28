# Cadet Tutor

A fully local AI instructor for officer cadets. It answers questions from your own
PDF documents with page citations, generates quizzes, and grades five-paragraph
orders against a rubric. Everything runs on your machine through
[Ollama](https://ollama.com): no document or question leaves the computer.

Documents carry a clearance level, and users only ever retrieve chunks at or
below their own level:

| User       | Level | Sees                                  |
|------------|-------|---------------------------------------|
| Cadet      | 0     | Public                                |
| Officer    | 1     | Public, Restricted                    |
| Instructor | 2     | Public, Restricted, Confidential      |

## Setup

```bash
# 1. Ollama models
ollama pull qwen2.5:7b
ollama pull bge-m3

# 2. Tesseract OCR with Arabic and French (for scanned pages)
#    Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra
#    macOS:         brew install tesseract tesseract-lang
#    Windows:       install from https://github.com/UB-Mannheim/tesseract/wiki, tick
#                   Arabic and French, then set TESSERACT_CMD to the full path of tesseract.exe
tesseract --list-langs   # must list ara and fra

# 3. Python environment (from this folder)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Documents: put PDFs in data/docs and list them in data/levels.csv
#    (or generate the fictional sample set)
python -m scripts.make_sample_docs

# 5. Check extraction (see below), then index
python -m scripts.extract_sample
python -m src.ingest            # incremental: only new/changed files
python -m src.ingest --reset    # full rebuild

# 6. Launch
streamlit run app.py
```

## Checking text extraction

`python -m scripts.extract_sample` prints, for every PDF in `data/docs` (or the files
you name), the page count, which pages were OCR'd, the Arabic/Latin letter mix, and
a text sample per page. Run it on new documents before ingesting them: broken words,
reversed Arabic lines or garbled OCR show up here first.

## Demo

Click **Demo** in the sidebar to load the sample documents (including a level-2
test document) and reset the app. Three sample orders (excellent, average, missing
sections) can be loaded in the **Order review** tab. [DEMO.md](DEMO.md) is a
3-minute presentation script that works with Wi-Fi off.

## Languages

Documents and questions can be in French, Arabic or English.

- **Extraction:** PyMuPDF reads the text layer. Tesseract OCRs pages that have little or
  no text (scans, slides saved as pictures) or a corrupted Arabic text layer, in the
  page's own language, and restores the reading order of columns.
  `python -m src.ingest` lists every OCR'd page and why.
- **Indexing:** each chunk stores its language (`fr`, `ar`, `en`). Arabic is normalised
  for indexing only (alef variants, ى→ي, ة→ه, no diacritics or tatweel); the original
  text is what is shown and cited.
- **Cross-lingual search:** `bge-m3` puts all three languages in one vector space, so a
  French question finds Arabic passages and vice versa.
- **Answers** are written in the question's language and quote passages in their
  original language. Arabic is displayed right to left.
- **Model:** set `LLM_MODEL` in `src/config.py`, or run with
  `CADET_LLM_MODEL=qwen2.5:14b` (pull it first). The 14b model follows the language
  and citation rules more reliably but needs about 10 GB of memory.

## Security

- **Clearance is enforced before the model.** Retrieval filters by level inside the
  vector query and re-checks every result, so the model never receives a chunk above
  the user's clearance. Nothing the model does, or is tricked into doing, can reveal
  text it never saw. Switching user clears the conversation.
- **Prompt injection.** Retrieved text and pasted orders are fenced in
  `<document>` / `<cadet_order>` tags that the text cannot close, and the system
  prompts say fenced text is data, never instructions (`src/prompts.py`). Passages
  that look like instructions to the AI (English, French, Arabic) are flagged in the
  answer and in the audit log. `data/sample_docs/injection_test.pdf` is a Public
  document carrying such an attack, loaded by the Demo button.
- **Audit log.** Every query (Ask, Quiz, Order review, evaluation) is recorded in the
  local SQLite file `audit/audit.sqlite`: UTC time, user, clearance level, mode, query,
  documents and citations retrieved, and flags. Instructors see it in the **Audit**
  tab; for other users the tab is not created and the log is not read.
- **Tests.** `tests/test_security.py` runs Cadet and Officer through every mode with
  attack queries in three languages and fails if any restricted text reaches the model.

**Limitation:** there is no login. The "Signed in as" selector is trusted, so anyone
at the keyboard can choose Instructor. Clearance filtering, the Audit tab and the log's
user names are only as reliable as that choice. Add authentication before letting
people use the app unsupervised.

## Modes

- **Ask** – grounded Q&A. Every sentence cites `[Document, p.X]`; citations that
  don't match a retrieved excerpt are flagged. If the answer isn't in the cleared
  documents, the tutor says so instead of guessing.
- **Quiz** – multiple-choice questions on a topic, generated only from documents
  the user may see, with explanations and sources.
- **Order review** – scores a pasted five-paragraph order per criterion in
  `data/order_rubric.json`, with feedback grounded in doctrine excerpts.

## Configuration

`src/config.py` holds models, chunk size, `TOP_K`, users and level names.
Set `OLLAMA_HOST` to use a non-default Ollama address.

`data/levels.csv` maps each file name to a level (0/1/2). Files not listed default
to level 0 with a warning; changing a level re-ingests that file on the next run.

## Evaluation and tests

```bash
python -m scripts.evaluate            # hit rate@5 and clearance leaks, per language
python -m scripts.evaluate --answers  # also correct refusals, keywords, answer language, latency
pip install pytest && pytest -q       # offline unit tests (no Ollama needed)
```

The sample documents are fictional training material; replace them with your own.

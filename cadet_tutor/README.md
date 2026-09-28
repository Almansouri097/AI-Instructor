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

# 2. Python environment (from this folder)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Documents: put PDFs in data/docs and list them in data/levels.csv
#    (or generate the fictional sample set)
python -m scripts.make_sample_docs

# 4. Index them
python -m src.ingest            # incremental: only new/changed files
python -m src.ingest --reset    # full rebuild

# 5. Launch
streamlit run app.py
```

## Demo

Click **Demo** in the sidebar to load the sample documents (including a level-2
test document) and reset the app. Three sample orders (excellent, average, missing
sections) can be loaded in the **Order review** tab. [DEMO.md](DEMO.md) is a
3-minute presentation script that works with Wi-Fi off.

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
python -m scripts.evaluate            # retrieval accuracy + clearance-leak checks
python -m scripts.evaluate --answers  # also checks generated answers and citations
pip install pytest && pytest -q       # offline unit tests (no Ollama needed)
```

The sample documents are fictional training material; replace them with your own.

# Cadet Tutor: Project Spec

Original project brief, saved verbatim.

---

You are a senior Python engineer. Build a complete, working hackathon project called "Cadet Tutor": an offline AI instructor for military officer cadets. Everything must run locally with no internet at runtime.
Stack (do not change)

* LLM: Ollama with qwen2.5:7b (use format="json" when structured output is needed)
* Embeddings: Ollama with bge-m3
* Vector store: ChromaDB (persistent, local folder)
* PDF parsing: pypdf
* UI: Streamlit
* Python 3.11, keep dependencies minimal, include requirements.txt

Project structure
cadet_tutor/
data/docs/ # PDFs go here
data/levels.csv # filename,level (0=public,1=restricted,2=confidential)
data/order_rubric.json
data/eval_questions.json
src/config.py # model names, paths, chunk size, top_k
src/ingest.py # CLI: parse PDFs, chunk, embed, store
src/retrieval.py # clearance-filtered search
src/llm.py # Ollama wrapper with retries
src/modes/ask.py
src/modes/socratic.py
src/modes/grader.py
src/evaluate.py # CLI evaluation script
app.py # Streamlit app
README.md
Feature 1: Ingestion

* Read every PDF in data/docs, extract text per page.
* Chunk into ~500 words with 80-word overlap, never mixing pages without recording them.
* Metadata per chunk: doc name, page number, level (from levels.csv, default 0).
* Re-running ingestion must not create duplicates.

Feature 2: Clearance-aware retrieval

* Users: "Cadet" (level 0), "Officer" (level 1), "Instructor" (level 2).
* Filter in the vector query itself: where={"level": {"$lte": user_level}}.
* The LLM must never receive chunks above the user's level.
* Each chunk is labeled in the prompt as [DocName, p.X].

Feature 3: Ask mode

* Answer only from retrieved chunks, cite a label for every claim.
* If the chunks don't contain the answer, reply exactly: "Not covered in the documents available at your clearance level."
* Show the sources used in an expandable section under the answer.
* Support questions in French, Arabic and English; answer in the question's language.

Feature 4: Socratic mode

* Never give the answer directly. Ask one guiding question at a time based on retrieved doctrine.
* Evaluate each cadet reply (correct / partially correct / wrong) and guide further.
* Reveal the full answer with citations after 3 failed attempts or if the cadet types "reveal".
* Keep conversation state in st.session_state.

Feature 5: Order grader

* order_rubric.json defines the five-paragraph order (Situation, Mission, Execution, Sustainment, Command and Signal) with required elements for each.
* Cadet pastes an order. The LLM returns JSON:
{"sections":[{"name":..., "score":0-10, "missing":[...], "feedback":..., "citations":[...]}], "overall_score":..., "summary":...}
* Validate the JSON; retry once if invalid.
* Display a color-coded table (green >=7, orange 4-6, red <=3) and the overall score.

Feature 6: UI

* Sidebar: user selector showing their clearance level, plus a status indicator "Offline: no data leaves this machine".
* Three tabs: Ask, Train (Socratic), Grade my order.
* Clean, professional military-style look (dark theme, simple).

Feature 7: Evaluation

* evaluate.py reads eval_questions.json (question, expected_doc, expected_page, answerable true/false).
* Reports: retrieval hit rate@5, correct-refusal rate on unanswerable questions, and average latency.
* Include 10 example questions based on the Geneva Conventions so it runs out of the box.

Quality rules

* Clear error messages if Ollama is not running or a model is missing.
* Type hints and short docstrings, no unnecessary abstractions.
* All prompts stored as constants in one place so I can tune them.
* README: setup steps, how to add documents, how to run the demo, how to run evaluation.

How to work
Build in phases and verify each before moving on:

1. Structure, config, ingestion, then test on one PDF.
2. Retrieval with filtering, then prove a Cadet cannot retrieve level-2 chunks.
3. Ask mode, 4. Socratic mode, 5. Grader, 6. UI, 7. Evaluation.
After each phase, tell me what you built, how to test it, and wait for my confirmation.

"""Offline tests: no Ollama needed (embeddings and chat are faked)."""
import hashlib
import json

import pytest

from scripts import make_sample_docs
from src import config, extract, ingest, llm, retrieve
from src.modes import order, quiz


def fake_embed(texts):
    """Deterministic bag-of-words embedding, good enough for keyword retrieval."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in t.lower().split():
            v[int(hashlib.md5(w.strip(".,:;()").encode()).hexdigest(), 16) % 64] += 1.0
        out.append(v)
    return out


@pytest.fixture()
def store(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(config, "DOCS_DIR", docs)
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(llm, "embed", fake_embed)
    monkeypatch.setattr(llm, "check_ollama", lambda models=(): [])
    for name, pages in make_sample_docs.DOCS.items():
        make_sample_docs.write_pdf(docs / name, pages)
    ingest.run(reset=True)
    return docs


def test_chunk_pages_tracks_page_ranges():
    pages = [extract.Page(1, "a " * 300, False), extract.Page(2, "b " * 300, True)]
    chunks = ingest.chunk_pages(pages, size=400, overlap=50)
    assert chunks[0].page_start == 1 and chunks[0].page_end == 2
    assert chunks[-1].page_end == 2
    assert chunks[0].ocr  # covers the OCR'd page 2
    assert all(len(c.text.split()) <= 400 for c in chunks)


def test_page_label():
    assert ingest.page_label("x.pdf", 3, 3) == "[x, p.3]"
    assert ingest.page_label("x.pdf", 3, 4) == "[x, p.3-4]"


def test_sample_pdfs_are_readable(tmp_path):
    path = tmp_path / "t.pdf"
    make_sample_docs.write_pdf(path, ["Hello (world) " * 5, "Second page " * 5])
    pages = extract.extract_pages(path)
    assert [p.number for p in pages] == [1, 2]
    assert "Hello (world)" in pages[0].text


def test_ingest_is_incremental(store, capsys):
    ingest.run()
    assert "unchanged, skipped" in capsys.readouterr().out


@pytest.mark.parametrize("user", list(config.USERS))
def test_retrieval_never_exceeds_clearance(store, user):
    level = config.USERS[user]
    for q in ["H-hour Iron Cedar", "challenge and reply sentry", "prisoner of war"]:
        for h in retrieve.search(q, level, k=10):
            assert h.level <= level


def test_instructor_sees_confidential(store):
    hits = retrieve.search("Iron Cedar H-hour 0530", config.USERS["Instructor"], k=10)
    assert any(h.doc == "exercise_iron_cedar_opord.pdf" for h in hits)


def test_removed_file_is_dropped(store):
    (store / "platoon_sop_restricted.pdf").unlink()
    ingest.run()
    hits = retrieve.search("challenge reply", 2, k=20)
    assert all(h.doc != "platoon_sop_restricted.pdf" for h in hits)


def test_citation_checks():
    hit = retrieve.Hit("t", "a.pdf", "[a, p.1]", 0, 1.0)
    text = "Fact one [a, p.1]. Fact two [b, p.9-10]."
    assert retrieve.extract_citations(text) == ["[a, p.1]", "[b, p.9-10]"]
    assert retrieve.invalid_citations(text, [hit]) == ["[b, p.9-10]"]


def test_quiz_parse_drops_bad_questions():
    raw = json.dumps({"questions": [
        {"question": "Q1", "options": ["a", "b", "c", "d"], "answer": 2, "explanation": "e", "source": "[a, p.1]"},
        {"question": "Q2", "options": ["a", "b"], "answer": 0},
        {"question": "Q3", "options": ["a", "b", "c", "d"], "answer": 7},
        {"question": "Q4", "options": ["a", "b", "c", "d"], "answer": "1", "source": "[fake, p.99]"},
    ]})
    qs = quiz._parse(raw, {"[a, p.1]"})
    assert [q.question for q in qs] == ["Q1", "Q4"]
    assert qs[1].answer == 1 and qs[1].source == "unverified source"
    assert quiz._parse("not json", set()) == []
    assert quiz.score(qs, [2, 0]) == 1


def test_order_parse_clamps_and_fills():
    rubric = order.load_rubric()
    raw = json.dumps({"criteria": [{"id": "mission", "score": 999, "feedback": "ok"},
                                   {"id": "situation", "score": -5}], "overall": "fine"})
    results, overall = order._parse(raw, rubric)
    by_id = {r.id: r for r in results}
    assert by_id["mission"].score == by_id["mission"].max
    assert by_id["situation"].score == 0
    assert by_id["execution"].score == 0
    assert len(results) == len(rubric) and overall == "fine"

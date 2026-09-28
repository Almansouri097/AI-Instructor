"""Phase 12: language-aware answers, multilingual ingestion and per-language evaluation."""
import pytest

from scripts import evaluate
from src import config, demo, ingest, llm, prompts, retrieve
from src.modes import ask
from tests.fake_ollama import bow_vector


@pytest.fixture()
def captured(monkeypatch):
    """Fake retrieval and chat; record the messages sent to the model."""
    calls = []
    hit = retrieve.Hit("توضع العاصبة فوق الجرح", "guide.pdf", "[guide, p.1]", 0, 0.9, "ar")
    monkeypatch.setattr(retrieve, "search", lambda q, level, k=5: [hit])
    monkeypatch.setattr(llm, "chat", lambda messages, json_mode=False: calls.append(messages) or "ok [guide, p.1]")
    return calls


@pytest.mark.parametrize("question,lang,name", [
    ("Où faut-il placer le garrot ?", "fr", "French"),
    ("أين توضع العاصبة؟", "ar", "Arabic"),
    ("Where is the tourniquet placed?", "en", "English"),
])
def test_answer_language_follows_question(captured, question, lang, name):
    out = ask.answer(question, level=0)
    system = captured[0][0]["content"]
    assert f"Write your whole answer in {name}" in system
    assert prompts.NO_ANSWER[lang] in system  # refusal wording in the same language
    assert "ORIGINAL language" in system  # quotes stay untranslated
    assert out.language == lang


def test_refusal_recognised_in_every_language():
    for text in prompts.NO_ANSWER.values():
        assert ask.is_refusal(text)
    assert not ask.is_refusal("Le SITREP est transmis toutes les six heures [manuel, p.1].")


def test_ingest_stores_language_and_ocr_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "LEVELS_CSV", tmp_path / "levels.csv")
    embedded = []
    monkeypatch.setattr(llm, "embed", lambda texts: embedded.extend(texts) or [bow_vector(t) for t in texts])
    monkeypatch.setattr(llm, "check_ollama", lambda models=(): [])
    log = demo.load()
    metas = {m["doc"]: m for m in ingest.get_collection().get(include=["metadatas"])["metadatas"]}
    assert metas["guide_secourisme_ar.pdf"]["lang"] == "ar"
    assert metas["guide_secourisme_ar.pdf"]["ocr"] is True  # page 2 is a scan
    assert metas["manuel_transmissions_fr.pdf"]["lang"] == "fr"
    assert metas["geneva_conventions_extracts.pdf"]["lang"] == "en"
    assert "OCR p.2" in log
    # Arabic is normalised for indexing only: the stored text keeps the original spelling.
    stored = ingest.get_collection().get(where={"doc": "guide_secourisme_ar.pdf"})["documents"][0]
    assert "الإسعاف" in stored
    assert not any("الإسعاف" in t for t in embedded) and any("الاسعاف" in t for t in embedded)


def test_eval_categories_and_checks():
    assert evaluate.category({"lang": "fr", "doc_lang": "ar"}) == "cross-lingual"
    assert evaluate.category({"lang": "ar", "doc_lang": None}) == "ar"
    assert evaluate.keywords_found("Toutes les 6 heures", ["six heures|6 heures"]) == []
    assert evaluate.keywords_found("توضع فوق الجرح", ["فوق الجرح", "المفصل"]) == ["المفصل"]
    # A French answer quoting Arabic is still French.
    assert evaluate.answer_language("Le texte dit « توضع العاصبة فوق الجرح » [guide, p.1].") == "fr"


def test_eval_summary_reports_per_language():
    rs = [evaluate.Result("fr", True, hit=True, refusal_ok=True, keywords_ok=True, language_ok=True, latency=1),
          evaluate.Result("ar", True, hit=False, refusal_ok=True, keywords_ok=False, language_ok=True, latency=2),
          evaluate.Result("cross-lingual", True, hit=True, refusal_ok=True, keywords_ok=True, language_ok=False, latency=3)]
    table = evaluate.summarize(rs, with_answers=True).splitlines()
    assert table[0].split()[0] == "category"
    assert [line.split()[0] for line in table[1:]] == ["fr", "ar", "cross-lingual"]
    assert "0% (0/1)" in table[2]

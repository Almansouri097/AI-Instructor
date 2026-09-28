"""Phase 12: language detection, Arabic normalisation, BM25 tokens."""
import pytest

from src.text import detect_language, normalize_arabic, tokenize


def test_normalize_arabic_as_specified():
    assert normalize_arabic("أإآٱ") == "اااا"  # alef variants
    assert normalize_arabic("على") == "علي"  # ى → ي
    assert normalize_arabic("مدرسة") == "مدرسه"  # ة → ه
    assert normalize_arabic("الحَرْبُ") == "الحرب"  # diacritics
    assert normalize_arabic("الحــرب") == "الحرب"  # tatweel
    assert normalize_arabic("Sécurité 13") == "Sécurité 13"  # non-Arabic untouched


@pytest.mark.parametrize("text,lang", [
    ("يجب معاملة أسرى الحرب معاملة إنسانية", "ar"),
    ("Les prisonniers de guerre doivent être traités avec humanité.", "fr"),
    ("L'objectif est de préserver les ressources critiques", "fr"),
    ("Prisoners of war must at all times be humanely treated.", "en"),
    ("Quelle est la procédure radio ?", "fr"),
    ("What is the H-hour?", "en"),
    ("", "en"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_tokenize_french_elisions_accents_and_stopwords():
    assert tokenize("L’organisation et la sécurité d'un système") == ["organisation", "securite", "systeme"]


def test_tokenize_arabic_matches_across_spelling_variants():
    # Article, diacritics, hamza on alef, taa marbuta and tatweel must not block a match.
    assert tokenize("الحَرْب") == tokenize("حرب") == ["حرب"]
    assert tokenize("والأسرى") == tokenize("اسري")
    assert tokenize("المعاملــة") == tokenize("معامله")
    assert tokenize("في الحرب") == ["حرب"]  # stopword dropped


def test_tokenize_keeps_numbers_and_acronyms():
    assert tokenize("Article 17 du SITREP") == ["article", "17", "sitrep"]
    assert tokenize("المادة 17") == ["ماده", "17"]

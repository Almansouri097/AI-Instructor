"""Language detection, Arabic normalisation and search tokens for fr / ar / en.

Normalised text is used only for indexing (embeddings, BM25). The original text is
always what gets stored, displayed and cited.
"""
import re
import unicodedata

ARABIC_LETTER_RE = re.compile(r"[ء-يٱ-ۓ]")
LATIN_LETTER_RE = re.compile(r"[A-Za-zÀ-ſ]")

# Arabic normalisation (as specified): unify alef variants, ى→ي, ة→ه,
# remove diacritics (harakat, tanwin, shadda, sukun, dagger alef) and tatweel.
_ARABIC_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
_ARABIC_STRIP_RE = re.compile(r"[ً-ْٰـ]")

FR_WORDS = {"le", "la", "les", "des", "du", "de", "et", "est", "une", "un", "dans", "pour", "par",
            "que", "qui", "sur", "au", "aux", "ne", "pas", "sont", "avec", "ou", "ces", "cette"}
EN_WORDS = {"the", "and", "of", "to", "is", "in", "for", "are", "with", "that", "on", "be", "by",
            "this", "must", "what", "which", "how", "from", "or", "an", "as", "at", "it"}
AR_STOPWORDS = {"في", "من", "علي", "الي", "عن", "ان", "او", "ما", "لا", "هذا", "هذه", "ذلك", "التي",
                "الذي", "كل", "مع", "هو", "هي", "قد", "ثم", "كان", "بين", "عند", "اي", "لم", "لن"}
FR_STOPWORDS = FR_WORDS | {"se", "sa", "son", "ses", "il", "elle", "en", "a", "y", "l", "d", "qu"}
EN_STOPWORDS = EN_WORDS

LANGUAGE_NAMES = {"fr": "French", "ar": "Arabic", "en": "English"}

# French elided articles/pronouns: l'organisation, d'un, qu'il, j'ai...
_ELISION_RE = re.compile(r"\b(?:[ldjmnstc]|qu)['’]", re.I)
# Arabic definite article, with optional preceding conjunction/preposition.
_AR_ARTICLE_RE = re.compile(r"^(?:وال|فال|بال|كال|لل|ال)(?=\w{2,})")


def normalize_arabic(text: str) -> str:
    """Arabic normalisation for indexing only. Leaves non-Arabic text unchanged."""
    return _ARABIC_STRIP_RE.sub("", text.translate(_ARABIC_MAP))


def detect_language(text: str) -> str:
    """'ar', 'fr' or 'en' (default 'en' when there is nothing to go on)."""
    arabic, latin = len(ARABIC_LETTER_RE.findall(text)), len(LATIN_LETTER_RE.findall(text))
    if arabic and arabic >= latin:
        return "ar"
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    fr = sum(w in FR_WORDS for w in words) + 2 * len(re.findall(r"[àâçéèêëîïôûùœ]", text.lower()))
    fr += 2 * len(_ELISION_RE.findall(text))
    en = sum(w in EN_WORDS for w in words)
    return "fr" if fr > en else "en"


def _fold_latin_accents(text: str) -> str:
    """sécurité -> securite (Latin letters only, so Arabic is left to normalize_arabic)."""
    out = []
    for ch in text:
        if LATIN_LETTER_RE.match(ch):
            ch = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        out.append(ch)
    return "".join(out)


def tokenize(text: str) -> list[str]:
    """Search tokens for BM25 in any of fr / ar / en.

    Lowercased, accent-folded (Latin) and Arabic-normalised; French elisions split off;
    Arabic definite article (with و/ف/ب/ك/ل) removed; stopwords dropped. Numbers are
    kept because article numbers and acronyms matter.
    """
    text = _ELISION_RE.sub(" ", normalize_arabic(text).casefold())
    text = _fold_latin_accents(text)
    tokens = []
    for tok in re.findall(r"\w+", text):
        if ARABIC_LETTER_RE.match(tok):
            if tok in AR_STOPWORDS:
                continue
            tok = _AR_ARTICLE_RE.sub("", tok)
        elif tok in FR_STOPWORDS or tok in EN_STOPWORDS:
            continue
        tokens.append(tok)
    return tokens

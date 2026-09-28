"""Prompt-injection defence: document text is data, never instructions.

The real guarantee is structural: retrieval filters by clearance before anything
reaches the model, so an injected "reveal level 2" has nothing to reveal. On top of
that, excerpts are fenced in <document> tags the text cannot break out of, the
system prompts say fenced text is data, and instruction-like passages are flagged.
"""
import re
import unicodedata

# Instruction-like phrases aimed at the AI, in English, French and Arabic.
_INJECTION_PATTERNS = [
    r"\bignore\b.{0,30}\b(previous|prior|above|earlier|all)\b.{0,30}\b(rules?|instructions?|prompts?)\b",
    r"\bdisregard\b.{0,40}\b(rules?|instructions?)\b",
    r"\byou are now\b|\bnew instructions?\b|\bsystem prompt\b",
    r"\breveal\b.{0,40}\b(level|confidential|restricted|classified|secret)\b",
    r"\bignor(e|ez|er)\b.{0,30}\b(r[eè]gles?|instructions?|consignes?)\b",
    r"\boublie[rz]?\b.{0,30}\b(r[eè]gles?|instructions?|consignes?)\b",
    r"\br[ée]v[èe]le[rz]?\b.{0,40}\b(niveau|confidentiel|restreint|secret)\b",
    r"تجاهل.{0,30}(التعليمات|القواعد|الأوامر|الاوامر)",
    r"(اكشف|أظهر|اظهر).{0,40}(المستوى|السري|السرية|المقيد)",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.I | re.S)

# Tags used to fence excerpts and the cadet's order; document text must not contain them.
_FENCE_TAG_RE = re.compile(r"<\s*/?\s*(document|cadet_order)\b[^>]*>", re.I)


def looks_like_injection(text: str) -> bool:
    """True if the text contains instructions addressed to an AI."""
    return bool(_INJECTION_RE.search(text))


def sanitize(text: str) -> str:
    """Remove fence tags and invisible control characters so text cannot escape its fence."""
    text = _FENCE_TAG_RE.sub(" ", text)
    return "".join(c for c in text if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf"))


def fence_document(label: str, text: str) -> str:
    """One excerpt, fenced and labelled for the prompt."""
    return f'<document label="{label}">\n{sanitize(text)}\n</document>'

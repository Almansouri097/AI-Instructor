"""Mode 1: grounded question answering with page citations, in the question's language."""
from dataclasses import dataclass, field

from src import llm, prompts, retrieve
from src.text import LANGUAGE_NAMES, detect_language


@dataclass
class Answer:
    text: str
    sources: list[retrieve.Hit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    language: str = "en"


def is_refusal(text: str) -> bool:
    """True if the reply is the 'not covered' answer, in any language."""
    return any(msg in text for msg in prompts.NO_ANSWER.values())


def answer(question: str, level: int, history: list[dict[str, str]] | None = None) -> Answer:
    """Retrieve cleared excerpts (any language) and answer in the question's language."""
    lang = detect_language(question)
    no_answer = prompts.NO_ANSWER[lang]
    hits = retrieve.search(question, level)
    if not hits:
        return Answer(no_answer, language=lang)

    system = prompts.ASK_SYSTEM.format(language=LANGUAGE_NAMES[lang], no_answer=no_answer)
    messages = [{"role": "system", "content": system}]
    messages += (history or [])[-4:]  # short memory for follow-up questions
    messages.append({"role": "user", "content": prompts.ASK_USER.format(
        context=retrieve.format_context(hits), question=question)})
    text = llm.chat(messages).strip()

    warnings = [f"{h.label} contains text that looks like instructions to the AI. "
                "It was treated as reference material only." for h in hits if h.suspicious]
    bad = retrieve.invalid_citations(text, hits)
    if bad:
        warnings.append("Unverified citations (not in retrieved excerpts): " + ", ".join(bad))
    if not is_refusal(text) and not retrieve.extract_citations(text):
        warnings.append("The answer contains no citations; verify it against the sources.")
    return Answer(text, hits, warnings, lang)

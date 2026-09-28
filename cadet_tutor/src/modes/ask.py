"""Mode 1: grounded question answering with page citations."""
from dataclasses import dataclass, field

from src import llm, retrieve

NO_ANSWER = "I can't find this in the documents available at your clearance level."

SYSTEM = f"""You are a military instructor tutoring officer cadets.
Answer ONLY from the excerpts provided. Each excerpt starts with its citation label,
e.g. [DocName, p.3]. After every factual sentence, add the label of the excerpt it
comes from, copied exactly. Never invent labels, documents or page numbers.
If the excerpts do not contain the answer, reply exactly:
"{NO_ANSWER}"
Be concise and precise; use short paragraphs or bullet points."""


@dataclass
class Answer:
    text: str
    sources: list[retrieve.Hit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def answer(question: str, level: int, history: list[dict[str, str]] | None = None) -> Answer:
    """Retrieve cleared excerpts and answer with citations."""
    hits = retrieve.search(question, level)
    if not hits:
        return Answer(NO_ANSWER)

    messages = [{"role": "system", "content": SYSTEM}]
    messages += (history or [])[-4:]  # short memory for follow-up questions
    messages.append(
        {
            "role": "user",
            "content": f"Excerpts:\n{retrieve.format_context(hits)}\n\nQuestion: {question}",
        }
    )
    text = llm.chat(messages).strip()

    warnings = []
    bad = retrieve.invalid_citations(text, hits)
    if bad:
        warnings.append("Unverified citations (not in retrieved excerpts): " + ", ".join(bad))
    if NO_ANSWER not in text and not retrieve.extract_citations(text):
        warnings.append("The answer contains no citations; verify it against the sources.")
    return Answer(text, hits, warnings)

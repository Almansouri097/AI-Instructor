"""Mode 2: multiple-choice quiz generated from the cadet's cleared documents."""
import json
import random
from dataclasses import dataclass

from src import llm, retrieve

SYSTEM = """You write multiple-choice questions for officer cadets.
Use ONLY facts stated in the excerpts. Return JSON of the form:
{"questions": [{"question": str, "options": [str, str, str, str],
"answer": int (0-3, index of the correct option), "explanation": str,
"source": str (the exact citation label of the excerpt used)}]}
Exactly one option must be correct. Distractors must be plausible but clearly wrong
according to the excerpts."""


@dataclass
class Question:
    question: str
    options: list[str]
    answer: int
    explanation: str
    source: str


def _parse(raw: str, allowed_labels: set[str]) -> list[Question]:
    """Validate the model's JSON; silently drop malformed questions."""
    try:
        items = json.loads(raw).get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    out = []
    for q in items if isinstance(items, list) else []:
        try:
            options = [str(o) for o in q["options"]]
            idx = int(q["answer"])
            if len(options) != 4 or not 0 <= idx < 4 or not str(q["question"]).strip():
                continue
            source = str(q.get("source", "")).strip()
            if source not in allowed_labels:
                source = "unverified source"
            out.append(Question(str(q["question"]), options, idx, str(q.get("explanation", "")), source))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def generate(topic: str, level: int, n: int = 5) -> list[Question]:
    """Generate up to n questions on a topic from cleared excerpts."""
    hits = retrieve.search(topic or "key rules and procedures", level, k=max(n, 5))
    if not hits:
        return []
    random.shuffle(hits)
    prompt = f"Excerpts:\n{retrieve.format_context(hits)}\n\nWrite {n} questions on: {topic or 'the excerpts'}"
    raw = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], json_mode=True)
    return _parse(raw, {h.label for h in hits})[:n]


def score(questions: list[Question], picks: list[int | None]) -> int:
    """Number of correct picks."""
    return sum(1 for q, p in zip(questions, picks) if p == q.answer)

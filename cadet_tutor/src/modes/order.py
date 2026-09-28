"""Mode 3: assess a cadet's five-paragraph order against the rubric."""
import json
from dataclasses import dataclass
from pathlib import Path

from src import config, llm, retrieve

SYSTEM = """You are a military instructor grading a cadet's five-paragraph order.
Grade each rubric criterion strictly from what the cadet actually wrote.
Use the doctrine excerpts (if any) to justify feedback and cite their labels exactly.
Return JSON: {"criteria": [{"id": str, "score": int, "feedback": str}],
"overall": str (3-5 sentences: strengths, main gaps, one priority to fix)}.
Each score must be an integer between 0 and that criterion's max."""


@dataclass
class CriterionResult:
    id: str
    title: str
    score: int
    max: int
    feedback: str


@dataclass
class Assessment:
    criteria: list[CriterionResult]
    overall: str
    sources: list[retrieve.Hit]

    @property
    def total(self) -> int:
        return sum(c.score for c in self.criteria)

    @property
    def max_total(self) -> int:
        return sum(c.max for c in self.criteria)


def load_rubric(path: Path = config.RUBRIC_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["criteria"]


def _parse(raw: str, rubric: list[dict]) -> tuple[list[CriterionResult], str]:
    """Map model output onto the rubric; clamp scores; fill gaps with 0."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    given = {
        str(c.get("id")): c
        for c in data.get("criteria", [])
        if isinstance(c, dict)
    }
    results = []
    for crit in rubric:
        got = given.get(crit["id"], {})
        try:
            s = int(got.get("score", 0))
        except (TypeError, ValueError):
            s = 0
        s = max(0, min(crit["max"], s))
        fb = str(got.get("feedback") or "No feedback returned for this criterion.")
        results.append(CriterionResult(crit["id"], crit["title"], s, crit["max"], fb))
    return results, str(data.get("overall", ""))


def assess(order_text: str, level: int) -> Assessment:
    """Grade an order; doctrine retrieval respects the cadet's clearance."""
    rubric = load_rubric()
    hits = retrieve.search("five paragraph order situation mission execution sustainment command signal", level)
    rubric_txt = "\n".join(
        f"- {c['id']} ({c['title']}, max {c['max']}): {c['description']}" for c in rubric
    )
    prompt = (
        f"Rubric:\n{rubric_txt}\n\n"
        f"Doctrine excerpts:\n{retrieve.format_context(hits) or '(none)'}\n\n"
        f"Cadet's order:\n\"\"\"\n{order_text}\n\"\"\""
    )
    raw = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], json_mode=True)
    criteria, overall = _parse(raw, rubric)
    return Assessment(criteria, overall, hits)

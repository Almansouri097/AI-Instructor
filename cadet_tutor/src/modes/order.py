"""Mode 3: assess a cadet's five-paragraph order against the rubric."""
import json
from dataclasses import dataclass
from pathlib import Path

from src import config, llm, prompts, retrieve
from src.text import LANGUAGE_NAMES, detect_language

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
    hits = retrieve.search(prompts.ORDER_DOCTRINE_QUERY, level)
    rubric_txt = "\n".join(
        f"- {c['id']} ({c['title']}, max {c['max']}): {c['description']}" for c in rubric
    )
    system = prompts.ORDER_SYSTEM.format(language=LANGUAGE_NAMES[detect_language(order_text)])
    prompt = prompts.ORDER_USER.format(rubric=rubric_txt, context=retrieve.format_context(hits) or "(none)", order=order_text)
    raw = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}], json_mode=True)
    criteria, overall = _parse(raw, rubric)
    return Assessment(criteria, overall, hits)

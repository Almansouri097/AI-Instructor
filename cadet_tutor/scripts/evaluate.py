"""Evaluate retrieval, answers and clearance on data/eval_questions.json, per language.

Usage (from the project root, after ingesting):
    python -m scripts.evaluate              # retrieval + clearance checks only
    python -m scripts.evaluate --answers    # also generate answers with the LLM

Each question is scored in a category: its language (en / fr / ar), or
"cross-lingual" when the expected document is in another language.
"""
import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

from src import config, llm, retrieve
from src.modes import ask
from src.text import detect_language, normalize_arabic

CATEGORIES = ("en", "fr", "ar", "cross-lingual")


@dataclass
class Result:
    category: str
    answerable: bool
    hit: bool | None = None  # expected document in the top 5 (answerable questions)
    leak: bool = False  # a chunk above the user's clearance, or a forbidden document
    refusal_ok: bool | None = None  # refused exactly when it should (with --answers)
    keywords_ok: bool | None = None
    language_ok: bool | None = None  # answered in the question's language
    latency: float = 0.0
    errors: list[str] = field(default_factory=list)


def category(case: dict) -> str:
    doc_lang = case.get("doc_lang")
    return "cross-lingual" if doc_lang and doc_lang != case["lang"] else case["lang"]


def _norm(text: str) -> str:
    return normalize_arabic(text).casefold()


def answer_language(text: str) -> str:
    """Language of an answer, ignoring quoted passages and citation labels."""
    text = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|\[[^\]]*\]", " ", text)
    return detect_language(text)


def keywords_found(text: str, keywords: list[str]) -> list[str]:
    """Missing keywords; 'a|b' means either is fine."""
    low = _norm(text)
    return [k for k in keywords if not any(_norm(alt) in low for alt in k.split("|"))]


def evaluate_case(case: dict, with_answers: bool) -> Result:
    level = config.USERS[case["user"]]
    answerable = case.get("expected_doc") is not None
    res = Result(category(case), answerable)

    start = time.perf_counter()
    hits = retrieve.search(case["question"], level)
    docs = [h.doc for h in hits]
    leaked = sorted({d for d in docs if d in case.get("forbidden_docs", [])})
    if leaked or any(h.level > level for h in hits):
        res.leak = True
        res.errors.append(f"CLEARANCE LEAK: {leaked}")
    if answerable:
        res.hit = case["expected_doc"] in docs[:5]
        if not res.hit:
            res.errors.append(f"expected {case['expected_doc']} in top 5, got {docs}")

    if with_answers:
        out = ask.answer(case["question"], level)
        refused = ask.is_refusal(out.text)
        res.refusal_ok = refused != answerable
        if not res.refusal_ok:
            res.errors.append("refused an answerable question" if refused else "answered instead of refusing")
        missing = keywords_found(out.text, case.get("keywords", []))
        res.keywords_ok = not missing
        if missing:
            res.errors.append(f"answer missing {missing}")
        got = answer_language(out.text)
        res.language_ok = got == case["lang"]
        if not res.language_ok:
            res.errors.append(f"answered in {got}, asked in {case['lang']}")
        res.errors += out.warnings
    res.latency = time.perf_counter() - start
    return res


def _rate(values: list[bool | None]) -> str:
    vals = [v for v in values if v is not None]
    return f"{100 * sum(vals) / len(vals):5.0f}% ({sum(vals)}/{len(vals)})" if vals else "    -"


def summarize(results: list[Result], with_answers: bool) -> str:
    """Per-category table: hit rate@5, leaks, and with answers refusal/keywords/language."""
    groups = defaultdict(list)
    for r in results:
        groups[r.category].append(r)
    cols = ["hit@5", "leaks"] + (["correct refusal", "keywords", "language"] if with_answers else []) + ["avg s"]
    lines = [f"{'category':<14}" + "".join(f"{c:>18}" for c in cols)]
    for cat in [c for c in CATEGORIES if c in groups] + [c for c in groups if c not in CATEGORIES]:
        rs = groups[cat]
        row = [_rate([r.hit for r in rs]), str(sum(r.leak for r in rs))]
        if with_answers:
            row += [_rate([r.refusal_ok for r in rs]), _rate([r.keywords_ok for r in rs]),
                    _rate([r.language_ok for r in rs])]
        row.append(f"{sum(r.latency for r in rs) / len(rs):.1f}")
        lines.append(f"{cat:<14}" + "".join(f"{v:>18}" for v in row))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", action="store_true", help="also run the LLM and check answers")
    args = parser.parse_args()

    models = (config.LLM_MODEL, config.EMBED_MODEL) if args.answers else (config.EMBED_MODEL,)
    problems = llm.check_ollama(models=models)
    if problems:
        sys.exit("\n".join(problems))

    cases = json.loads(config.EVAL_PATH.read_text(encoding="utf-8"))
    results = []
    for i, case in enumerate(cases, start=1):
        r = evaluate_case(case, args.answers)
        results.append(r)
        print(f"[{'PASS' if not r.errors else 'FAIL'}] {i:>2}. ({case['user']}, {r.category}) {case['question']}")
        for e in r.errors:
            print(f"        - {e}")
    print(f"\nModel: {config.LLM_MODEL if args.answers else '(retrieval only)'} · embeddings: {config.EMBED_MODEL}\n")
    print(summarize(results, args.answers))
    passed = sum(not r.errors for r in results)
    print(f"\n{passed}/{len(results)} questions passed every check")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

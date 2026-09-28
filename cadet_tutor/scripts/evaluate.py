"""Evaluate retrieval, citations and clearance enforcement on data/eval_questions.json.

Usage (from the project root, after ingesting):
    python -m scripts.evaluate              # retrieval + clearance checks only
    python -m scripts.evaluate --answers    # also generate answers with the LLM
"""
import argparse
import json
import sys

from src import config, llm, retrieve
from src.modes import ask


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", action="store_true", help="also run the LLM and check answers")
    args = parser.parse_args()

    models = (config.LLM_MODEL, config.EMBED_MODEL) if args.answers else (config.EMBED_MODEL,)
    problems = llm.check_ollama(models=models)
    if problems:
        sys.exit("\n".join(problems))

    cases = json.loads(config.EVAL_PATH.read_text(encoding="utf-8"))
    passed = 0
    for i, case in enumerate(cases, start=1):
        level = config.USERS[case["user"]]
        hits = retrieve.search(case["question"], level)
        docs = [h.doc for h in hits]
        errors = []

        leaked = [d for d in docs if d in case.get("forbidden_docs", [])]
        if leaked or any(h.level > level for h in hits):
            errors.append(f"CLEARANCE LEAK: {sorted(set(leaked))}")
        if case.get("expected_doc") and case["expected_doc"] not in docs[:3]:
            errors.append(f"expected {case['expected_doc']} in top 3, got {docs[:3]}")

        if args.answers:
            res = ask.answer(case["question"], level)
            low = res.text.lower()
            missing = [k for k in case.get("keywords", []) if k.lower() not in low]
            if missing:
                errors.append(f"answer missing keywords {missing}")
            errors += res.warnings

        ok = not errors
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {i:>2}. ({case['user']}) {case['question']}")
        for e in errors:
            print(f"        - {e}")
    print(f"\n{passed}/{len(cases)} passed")
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()

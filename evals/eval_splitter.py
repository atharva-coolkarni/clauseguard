"""Measure the clause splitter against the generated labels.

Real agreements rarely look as tidy as the generated ones, so each agreement is
also reformatted in ways that mimic real documents (PDF line wrapping, other
numbering styles, missing blank lines, no numbering) and scored again.

A predicted clause counts as correct when its text matches a labelled clause
exactly, ignoring whitespace and words broken across lines at a hyphen.

Usage:
    python evals/eval_splitter.py
    python evals/eval_splitter.py --data data/generated --out evals/results/splitter.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard.graph.nodes.split import split_clauses  # noqa: E402
from clauseguard.text import normalize as norm  # noqa: E402


def wrap(doc: str, width: int = 80) -> str:
    return "\n\n".join(textwrap.fill(p, width) for p in doc.split("\n\n"))


def renumber(doc: str, fmt: str) -> str:
    return re.sub(r"(?m)^(\d{1,2})\. ", lambda m: fmt.format(n=m.group(1)), doc)


def no_blank_lines(doc: str) -> str:
    return re.sub(r"\n\s*\n", "\n", doc)


# name -> (description, transform)
FORMATS = {
    "original": ("As generated", lambda d: d),
    "pdf_wrapped": ("Lines wrapped at 80 characters, as text copied from a PDF", wrap),
    "paren_numbers": ('Numbered "1)" instead of "1."', lambda d: renumber(d, "{n}) ")),
    "clause_prefix": ('Numbered "Clause 1:"', lambda d: renumber(d, "Clause {n}: ")),
    "no_blank_lines": ("No blank lines between clauses", no_blank_lines),
    "pdf_combined": ("Wrapped + \"1)\" numbering + no blank lines",
                     lambda d: no_blank_lines(renumber(wrap(d), "{n}) "))),
    "unnumbered": ("Clause numbers removed", lambda d: renumber(d, "")),
}


def evaluate(data_dir: Path) -> dict:
    gold: dict[str, list[dict]] = defaultdict(list)
    for line in open(data_dir / "labels.jsonl", encoding="utf-8"):
        row = json.loads(line)
        if row["clause_number"] is not None:
            gold[row["agreement_id"]].append(row)

    results = {}
    for name, (description, transform) in FORMATS.items():
        tp = n_pred = n_gold = exact_docs = 0
        risky_found = risky_total = 0
        methods: dict[str, int] = defaultdict(int)
        for agreement_id, rows in gold.items():
            doc = transform((data_dir / "agreements" / f"{agreement_id}.txt").read_text(encoding="utf-8"))
            result = split_clauses(doc)
            methods[result["method"]] += 1
            predicted = [norm(c["text"]) for c in result["clauses"]]
            expected = [norm(r["text"]) for r in rows]
            hits = set(predicted) & set(expected)

            tp += len(hits)
            n_pred += len(predicted)
            n_gold += len(expected)
            exact_docs += predicted == expected
            risky = [norm(r["text"]) for r in rows if r["label"] == "risky"]
            risky_total += len(risky)
            risky_found += sum(t in hits for t in risky)

        results[name] = {
            "description": description,
            "precision": round(tp / n_pred, 4) if n_pred else 0.0,
            "recall": round(tp / n_gold, 4) if n_gold else 0.0,
            "risky_clause_recall": round(risky_found / risky_total, 4) if risky_total else 0.0,
            "agreements_split_exactly": round(exact_docs / len(gold), 4),
            "methods": dict(methods),
        }
    return {"agreements": len(gold), "formats": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "generated")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "results" / "splitter.json")
    args = parser.parse_args()

    report = evaluate(args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Clause splitter on {report['agreements']} agreements\n")
    print(f"{'Format':<16}{'Precision':>10}{'Recall':>9}{'Risky recall':>14}{'Exact docs':>12}")
    for name, r in report["formats"].items():
        print(f"{name:<16}{r['precision']:>10.1%}{r['recall']:>9.1%}"
              f"{r['risky_clause_recall']:>14.1%}{r['agreements_split_exactly']:>12.1%}")
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()

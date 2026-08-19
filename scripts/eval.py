#!/usr/bin/env python
"""Run the ragas evaluation and print a report.

    uv run python scripts/eval.py
    uv run python scripts/eval.py --top-k 8
    uv run python scripts/eval.py --json results.json

Makes real OpenAI calls: embeddings to index the fixture corpus, one answer per
question, and several judge calls per metric.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.eval.harness import THRESHOLDS, evaluate_rag  # noqa: E402


def print_report(report: dict) -> bool:
    """Print scores. Returns True if every metric cleared its floor."""
    print()
    print(f"Corpus: {report['chunks_indexed']} chunks, top_k={report['top_k']}")

    hit_rate = report["retrieval_hit_rate"]
    if hit_rate is not None:
        print(f"Retrieval hit rate: {hit_rate:.1%} (expected postings present in context)")

    print()
    print(f"{'metric':<40} {'score':>7}  {'floor':>6}")
    print("-" * 58)

    passed = True
    for metric, score in sorted(report["scores"].items()):
        floor = THRESHOLDS.get(metric)
        if floor is None:
            print(f"{metric:<40} {score:>7.3f} {'—':>7}")
            continue
        ok = score >= floor
        passed = passed and ok
        print(f"{metric:<40} {score:>7.3f} {floor:>7.2f}  {'PASS' if ok else 'FAIL'}")

    print()
    for case in report["cases"]:
        print(f"Q: {case.question}")
        print(f"A: {case.answer}")
        print(f"   contexts={len(case.contexts)} jobs={len(case.retrieved_job_urls)}")
        print()

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Scout's RAG pipeline with ragas.")
    parser.add_argument("--top-k", type=int, default=None, help="chunks retrieved per question")
    parser.add_argument("--json", type=Path, default=None, help="write scores to this file")
    args = parser.parse_args()

    report = asyncio.run(evaluate_rag(top_k=args.top_k))
    passed = print_report(report)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "top_k": report["top_k"],
                    "chunks_indexed": report["chunks_indexed"],
                    "retrieval_hit_rate": report["retrieval_hit_rate"],
                    "scores": report["scores"],
                    "thresholds": THRESHOLDS,
                    "cases": [
                        {
                            "question": c.question,
                            "answer": c.answer,
                            "reference": c.reference,
                            "expected_job_urls": c.expected_job_urls,
                            "retrieved_job_urls": c.retrieved_job_urls,
                        }
                        for c in report["cases"]
                    ],
                },
                indent=2,
            )
        )
        print(f"Wrote {args.json}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

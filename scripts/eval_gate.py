"""Eval gate script for CI/CD.

Runs regression tests and blocks deploy if scores drop below thresholds.

The gate has two tiers, because they differ in cost by orders of magnitude:

    # Cheap tier: retrieval only. Embeddings and nothing else — no answer
    # generation, no LLM judge. Fast enough to run on every change.
    python scripts/eval_gate.py --retrieval-only

    # Full tier: agent regressions plus the judged RAG metrics. Generates an
    # answer per question and judges each on four metrics. Run on a schedule.
    python scripts/eval_gate.py --ragas

Usage:
    # Run all evals
    python scripts/eval_gate.py

    # Run specific agent eval
    python scripts/eval_gate.py --agent cover_letter

    # Output JSON for CI
    python scripts/eval_gate.py --json
"""

import argparse
import asyncio
import json
import sys


async def main():
    parser = argparse.ArgumentParser(description="Scout eval gate")
    parser.add_argument(
        "--agent",
        choices=["cover_letter", "research", "matching"],
        help="Specific agent to test",
    )
    parser.add_argument("--ragas", action="store_true", help="Also run RAGAS eval")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Cheap tier: gate retrieval only, skipping every LLM-judged check",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON for CI")
    parser.add_argument("--threshold", type=float, help="Override threshold for all metrics")
    args = parser.parse_args()

    results = []
    all_passed = True

    # The cheap tier returns early on purpose. The agent regressions below judge
    # every case with an LLM, so running them would defeat the point of the flag.
    if args.retrieval_only:
        print("Running retrieval-only evaluation...", file=sys.stderr)
        from tests.eval.harness import evaluate_retrieval

        report = await evaluate_retrieval()
        hit_rate = report["retrieval_hit_rate"]
        floor = report["retrieval_floor"]
        passed = hit_rate is not None and hit_rate >= floor

        failures = []
        if hit_rate is None:
            failures.append({"metric": "retrieval_hit_rate", "reason": "no grounded questions"})
        elif not passed:
            failures.append(
                {"metric": "retrieval_hit_rate", "score": hit_rate, "threshold": floor}
            )

        payload = {
            "passed": passed,
            "results": [
                {
                    "agent": "retrieval",
                    "passed": passed,
                    "scores": {
                        "retrieval_hit_rate": hit_rate,
                        "chunks_indexed": report["chunks_indexed"],
                    },
                    "failures": failures,
                }
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            status = "PASSED" if passed else "FAILED"
            rate = "n/a" if hit_rate is None else f"{hit_rate:.1%}"
            print(f"retrieval: {status} — hit rate {rate} (floor {floor:.0%})")
        sys.exit(0 if passed else 1)

    # Run regression tests
    from app.eval.regression import check_eval_gate, run_regression_test

    print("Running regression tests...", file=sys.stderr)
    regression_results = await run_regression_test(args.agent)
    results.extend(regression_results)

    if not check_eval_gate(regression_results):
        all_passed = False

    # Run RAGAS eval if requested
    if args.ragas:
        print("Running RAGAS evaluation...", file=sys.stderr)
        from tests.eval.harness import evaluate_rag

        rag_result = await evaluate_rag()
        rag_scores = rag_result["scores"]

        # RAG floors come from the harness that calibrated them. Importing them
        # rather than restating them is what keeps the metric *keys* honest:
        # ragas reports context precision as "llm_context_precision_with_reference",
        # and a hand-written key that misses is indistinguishable from a pass.
        from tests.eval.harness import THRESHOLDS as RAG_THRESHOLDS

        rag_failures = []
        for metric, threshold in RAG_THRESHOLDS.items():
            score = rag_scores.get(metric)
            if score is None:
                # Not "no news is good news" — ragas scoring nothing for a
                # gated metric means the gate did not run, so it fails.
                rag_failures.append({
                    "metric": metric,
                    "score": None,
                    "threshold": threshold,
                    "reason": "ragas returned no score for this metric",
                })
                all_passed = False
            elif score < threshold:
                rag_failures.append({
                    "metric": metric,
                    "score": score,
                    "threshold": threshold,
                })
                all_passed = False

        results.append({
            "agent": "rag",
            "passed": len(rag_failures) == 0,
            "scores": rag_scores,
            "failures": rag_failures,
        })

    # Output results
    if args.json:
        output = {
            "passed": all_passed,
            "results": [
                {
                    "agent": r.agent if hasattr(r, "agent") else r["agent"],
                    "passed": r.passed if hasattr(r, "passed") else r["passed"],
                    "scores": r.scores if hasattr(r, "scores") else r["scores"],
                    "failures": r.failures if hasattr(r, "failures") else r["failures"],
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "=" * 60)
        print("EVAL GATE RESULTS")
        print("=" * 60)

        for result in results:
            agent = result.agent if hasattr(result, "agent") else result["agent"]
            passed = result.passed if hasattr(result, "passed") else result["passed"]
            scores = result.scores if hasattr(result, "scores") else result["scores"]
            failures = result.failures if hasattr(result, "failures") else result["failures"]

            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"\n{agent}: {status}")
            print(f"  Scores: {scores}")

            if failures:
                print("  Failures:")
                for f in failures:
                    print(f"    - {f}")

        print("\n" + "=" * 60)
        if all_passed:
            print("✅ ALL EVALS PASSED - Deploy allowed")
        else:
            print("❌ EVALS FAILED - Deploy blocked")
        print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())

"""Eval gate script for CI/CD.

Runs regression tests and blocks deploy if scores drop below thresholds.

Usage:
    # Run all evals
    python scripts/eval_gate.py

    # Run specific agent eval
    python scripts/eval_gate.py --agent cover_letter

    # Run with RAGAS eval
    python scripts/eval_gate.py --ragas

    # Output JSON for CI
    python scripts/eval_gate.py --json
"""

import argparse
import asyncio
import json
import sys


async def main():
    parser = argparse.ArgumentParser(description="Scout eval gate")
    parser.add_argument("--agent", choices=["cover_letter", "research", "matching"], help="Specific agent to test")
    parser.add_argument("--ragas", action="store_true", help="Also run RAGAS eval")
    parser.add_argument("--json", action="store_true", help="Output JSON for CI")
    parser.add_argument("--threshold", type=float, help="Override threshold for all metrics")
    args = parser.parse_args()

    results = []
    all_passed = True

    # Run regression tests
    from app.eval.regression import run_regression_test, check_eval_gate

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
                print(f"  Failures:")
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

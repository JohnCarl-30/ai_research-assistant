"""Run Scout against companies with known answers and report how often it's right.

    uv run python extension/evals/run_eval.py                 # live, keyless
    uv run python extension/evals/run_eval.py --record DIR    # live, saving every response
    uv run python extension/evals/run_eval.py --replay DIR    # offline, from saved responses
    uv run python extension/evals/run_eval.py --only Linear   # some companies only

Writes a Markdown report to stdout (and to $GITHUB_STEP_SUMMARY on GitHub
Actions) and a JSON report to --out. It exits non-zero only when Scout
crashes or, with --min-accuracy, when accuracy falls below it: real
companies change, so a mismatch is something to look at, not a build break.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from scoring import CRITICAL, ERROR, FAIL, PASS, score_case, summarize

from scout_mcp.company import research_company
from scout_mcp.sources import dnsinfo
from scout_mcp.sources.http import Cache, Fetcher, FetchError, Response

HERE = Path(__file__).parent
MARK = {PASS: "✅", FAIL: "❌", CRITICAL: "🚨", ERROR: "⚠️"}


class Tape(Fetcher):
    """Counts requests per host and records or replays every response."""

    def __init__(self, inner: Fetcher | None, tape: dict | None = None, record: bool = False):
        super().__init__(cache=None)
        self.inner = inner
        self.tape = tape if tape is not None else {}
        self.record = record
        self.hosts: Counter = Counter()

    async def get(self, url, *, ttl, headers=None, max_bytes=0):
        self.hosts[urlparse(url).hostname] += 1
        if self.inner is None:  # replay
            saved = self.tape.get(url)
            if saved is None:
                raise FetchError(url, 599, f"not in the saved responses: {url}")
            if not 200 <= saved["status"] < 300:
                raise FetchError(url, saved["status"], saved.get("error") or "")
            return Response(**saved["response"])
        try:
            response = await self.inner.get(url, ttl=ttl, headers=headers)
        except FetchError as e:
            if self.record:
                self.tape[url] = {"status": e.status, "error": str(e)}
            raise
        if self.record:
            self.tape[url] = {"status": response.status, "response": response.__dict__}
        return response


def dns_lookup_for(tape: dict, mode: str):
    async def lookup(domain: str) -> dnsinfo.DnsInfo:
        key = f"dns:{domain}"
        if mode == "replay":
            if key not in tape:
                raise RuntimeError(f"DNS for {domain} not in the saved responses")
            return dnsinfo.DnsInfo(**tape[key])
        info = await dnsinfo.lookup(domain)
        if mode == "record":
            tape[key] = info.to_dict()
        return info

    return lookup


def case_name(c: dict) -> str:
    return f"{c['name']} ({c['domain'] or 'no domain'})"


def report_markdown(results: list, summary: dict, hosts: Counter, seconds: float, mode: str) -> str:
    lines = ["# Scout accuracy eval", ""]
    acc = summary["overall_accuracy"]
    lines.append(f"**Overall accuracy: {acc:.0%}** · errors (unreachable): {summary['errors']}"
                 f" · critical: {len(summary['critical'])} · {mode} · {seconds:.0f}s")
    lines += ["", "| Field | Pass | Fail | Critical | Error | Accuracy |",
              "|---|---|---|---|---|---|"]
    for name, f in summary["fields"].items():
        acc = f"{f['accuracy']:.0%}" if f["accuracy"] is not None else "-"
        lines.append(f"| {name} | {f[PASS]} | {f[FAIL]} | {f[CRITICAL]} | {f[ERROR]} | {acc} |")
    if summary["critical"]:
        lines += ["", "## Critical (confident and wrong)", ""]
        lines += [f"- {c}" for c in summary["critical"]]
    lines += ["", "## Cases", ""]
    for case, dossier, score in results:
        marks = " ".join(f"{MARK[s.outcome]} {s.field}" for s in score.scores)
        lines.append(f"- **{case}**: {marks}")
        for s in score.scores:
            if s.outcome != PASS:
                lines.append(f"  - {s.field}: expected `{s.expected}`, got `{s.got}`"
                             + (f" ({s.detail})" if s.detail else ""))
        if dossier.get("gaps"):
            lines.append(f"  - gaps: {'; '.join(dossier['gaps'])}")
    github_api = hosts.get("api.github.com", 0)
    companies = len(results) or 1
    lines += ["", "## Requests", "",
              f"GitHub API calls: {github_api} ({github_api / companies:.1f} per company); "
              f"raw.githubusercontent.com: {hosts.get('raw.githubusercontent.com', 0)}.", ""]
    lines += [f"- {host}: {n}" for host, n in hosts.most_common()]
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--golden", default=HERE / "companies.json", type=Path)
    parser.add_argument("--record", type=Path, help="save every response to DIR/tape.json")
    parser.add_argument("--replay", type=Path, help="answer from DIR/tape.json, offline")
    parser.add_argument("--only", action="append", help="company name (repeatable)")
    parser.add_argument("--pace", type=float, default=8.0,
                        help="seconds between companies (GitHub search allows 10 a minute)")
    parser.add_argument("--out", type=Path, default=Path("eval-report.json"))
    parser.add_argument("--min-accuracy", type=float, default=None)
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text())["companies"]
    if args.only:
        wanted = {n.lower() for n in args.only}
        golden = [c for c in golden if c["name"].lower() in wanted]

    if args.replay:
        mode, tape = "replay", json.loads((args.replay / "tape.json").read_text())
        fetcher = Tape(None, tape)
    else:
        mode = "record" if args.record else "live"
        tape = {}
        # A fresh cache, so a run measures the sources rather than old answers.
        cache = Cache(Path(tempfile.mkdtemp()) / "cache.db")
        fetcher = Tape(Fetcher(cache), tape, record=bool(args.record))

    started = time.monotonic()
    results = []
    for i, case in enumerate(golden):
        if i and mode != "replay":
            await asyncio.sleep(args.pace)
        dossier = (await research_company(
            case["name"], domain=case["domain"], fetcher=fetcher, notebook=None,
            github_token=None, dns_lookup=dns_lookup_for(tape, mode),
        )).to_dict()
        score = score_case(case_name(case), case["expect"], dossier)
        results.append((case_name(case), dossier, score))
        print(f"{case_name(case)}: " + " ".join(f"{s.field}={s.outcome}" for s in score.scores),
              file=sys.stderr, flush=True)

    summary = summarize([s for _, _, s in results])
    markdown = report_markdown(results, summary, fetcher.hosts, time.monotonic() - started, mode)
    print(markdown)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a") as f:
            f.write(markdown)
    args.out.write_text(json.dumps({
        "summary": summary,
        "requests": dict(fetcher.hosts),
        "cases": [{"case": c, "dossier": d, **s.to_dict()} for c, d, s in results],
    }, indent=1))
    if args.record:
        args.record.mkdir(parents=True, exist_ok=True)
        (args.record / "tape.json").write_text(json.dumps(tape))

    if args.min_accuracy is not None and (summary["overall_accuracy"] or 0) < args.min_accuracy:
        print(f"Accuracy {summary['overall_accuracy']} is below {args.min_accuracy}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

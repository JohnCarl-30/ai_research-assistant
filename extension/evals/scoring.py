"""Score a Scout dossier against a known answer.

Each expectation scores one of:

- pass: the dossier has the expected answer.
- fail: the dossier has a different answer, or none.
- critical: a confident wrong answer (a "high" or "medium" GitHub match to the
  wrong org). Worse than no answer, because Claude would trust it.
- error: the source could not be reached (network, rate limit), so the
  answer is unknown. Reported separately and not counted as wrong.

Accuracy is pass / (pass + fail + critical); errors are excluded.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field

PASS, FAIL, CRITICAL, ERROR = "pass", "fail", "critical", "error"


@dataclass
class FieldScore:
    field: str
    outcome: str
    expected: object
    got: object
    detail: str = ""


@dataclass
class CaseScore:
    case: str
    scores: list[FieldScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"case": self.case, "scores": [asdict(s) for s in self.scores]}


def _failed(gaps: list[str], prefix: str) -> str | None:
    """The gap saying a source failed outright (unreachable, rate-limited), if any.

    "No public GitHub organisation found." is an answer, not a failure: only
    gaps that start with the source's name count.
    """
    return next((gap for gap in gaps if gap.startswith(prefix)), None)


def _norm(value):
    return value.lower() if isinstance(value, str) else value


def score_case(name: str, expect: dict, dossier: dict) -> CaseScore:
    gaps = dossier.get("gaps") or []
    result = CaseScore(case=name)

    def add(fld, outcome, expected, got, detail=""):
        result.scores.append(FieldScore(fld, outcome, expected, got, detail))

    if "domain" in expect:
        got = dossier.get("domain")
        failure = _failed(gaps, "Wikidata lookup failed")
        if dossier.get("domain_source") != "given" and got is None and failure:
            # Finding no website proves nothing if the source couldn't be asked.
            add("domain", ERROR, expect["domain"], None, failure)
        else:
            add("domain", PASS if _norm(got) == _norm(expect["domain"]) else FAIL,
                expect["domain"], got, dossier.get("domain_source") or "")

    if "wikidata" in expect:
        facts = dossier.get("facts") or {}
        got = facts.get("wikidata_id")
        failure = _failed(gaps, "Wikidata lookup failed")
        if got is None and failure:
            add("wikidata", ERROR, expect["wikidata"], None, failure)
        else:
            add("wikidata", PASS if got == expect["wikidata"] else FAIL, expect["wikidata"], got)

    if "github_org" in expect:
        gh = dossier.get("github") or {}
        got, confidence = gh.get("org"), gh.get("confidence")
        failure = _failed(gaps, "GitHub")
        detail = f"{confidence or '-'} confidence, org from {gh.get('org_source') or '-'}"
        if got is None and failure:
            add("github_org", ERROR, expect["github_org"], None, failure)
        elif _norm(got) == _norm(expect["github_org"]):
            add("github_org", PASS, expect["github_org"], got, detail)
        elif got is not None and confidence in ("high", "medium"):
            add("github_org", CRITICAL, expect["github_org"], got, detail)
        else:
            add("github_org", FAIL, expect["github_org"], got, detail)

    if "job_board" in expect:
        hiring = dossier.get("hiring") or {}
        got = [hiring["board"], hiring["slug"]] if hiring else None
        expected = expect["job_board"]
        failure = _failed(gaps, "Job board lookup failed")
        if got is None and failure:
            add("job_board", ERROR, expected, None, failure)
        else:
            same = got is not None and expected is not None and [_norm(x) for x in got] == [
                _norm(x) for x in expected]
            same = same or (got is None and expected is None)
            add("job_board", PASS if same else FAIL, expected, got,
                f"{hiring.get('open_roles')} roles, board from {hiring.get('board_source')}"
                if hiring else "")

    if "tech" in expect:
        found = tech_found(dossier)
        missing = [t for t in expect["tech"] if t.lower() not in found]
        failures = [g for p in ("Website could not be read", "Job board lookup failed", "GitHub")
                    if (g := _failed(gaps, p))]
        if missing and failures:
            add("tech", ERROR, expect["tech"], sorted(found), "; ".join(failures))
        else:
            add("tech", PASS if not missing else FAIL, expect["tech"], sorted(found),
                f"missing {missing}" if missing else "")

    return result


def tech_found(dossier: dict) -> set[str]:
    """Every technology the dossier names, from any source, lowercased."""
    found: set[str] = set()
    for labels in ((dossier.get("website") or {}).get("tech") or {}).values():
        found.update(label.lower() for label in labels)
    for label, _ in (dossier.get("hiring") or {}).get("tech_mentions") or []:
        found.add(label.lower())
    gh = dossier.get("github") or {}
    found.update(f.lower() for f in gh.get("frameworks") or [])
    found.update(lang.lower() for lang, _ in gh.get("top_languages") or [])
    return found


def summarize(cases: list[CaseScore]) -> dict:
    """Per-field counts and accuracy, plus the critical misses."""
    by_field: dict[str, Counter] = {}
    critical = []
    for case in cases:
        for s in case.scores:
            by_field.setdefault(s.field, Counter())[s.outcome] += 1
            if s.outcome == CRITICAL:
                critical.append(
                    f"{case.case}: {s.field} expected {s.expected}, got {s.got} ({s.detail})"
                )
    fields = {}
    for name, counts in by_field.items():
        scored = counts[PASS] + counts[FAIL] + counts[CRITICAL]
        fields[name] = {**{k: counts[k] for k in (PASS, FAIL, CRITICAL, ERROR)},
                        "accuracy": round(counts[PASS] / scored, 3) if scored else None}
    total = Counter(s.outcome for c in cases for s in c.scores)
    scored = total[PASS] + total[FAIL] + total[CRITICAL]
    return {
        "fields": fields,
        "overall_accuracy": round(total[PASS] / scored, 3) if scored else None,
        "errors": total[ERROR],
        "critical": critical,
    }

"""The eval's scoring and record/replay, offline."""

import pytest
from run_eval import Tape, dns_lookup_for
from scoring import CRITICAL, ERROR, FAIL, PASS, score_case, summarize, tech_found

from scout_mcp.sources.http import FetchError, Response

GOOD = {
    "domain": "linear.app", "domain_source": "given",
    "facts": None,
    "website": {"tech": {"framework": ["Next.js"]}},
    "hiring": {"board": "ashby", "slug": "linear", "board_source": "website", "open_roles": 31,
               "tech_mentions": [["TypeScript", 4]]},
    "github": {"org": "linear", "confidence": "high", "org_source": "website",
               "frameworks": [], "top_languages": [["TypeScript", 5]]},
    "gaps": ["No Wikidata entry matched this company."],
}
EXPECT = {"wikidata": None, "github_org": "linear", "job_board": ["ashby", "linear"],
          "tech": ["Next.js", "TypeScript"]}


def outcomes(score):
    return {s.field: s.outcome for s in score.scores}


def test_a_correct_dossier_passes_everything():
    assert set(outcomes(score_case("Linear", EXPECT, GOOD)).values()) == {PASS}


def test_confident_wrong_org_is_critical_and_unsure_wrong_org_is_a_fail():
    wrong = {**GOOD, "github": {"org": "linear-labs", "confidence": "high"}}
    assert outcomes(score_case("x", EXPECT, wrong))["github_org"] == CRITICAL
    guessed = {**GOOD, "github": {"org": "linear-labs", "confidence": "low"}}
    assert outcomes(score_case("x", EXPECT, guessed))["github_org"] == FAIL


def test_unreachable_sources_are_errors_not_wrong_answers():
    down = {**GOOD, "github": None, "hiring": None, "facts": None, "gaps": [
        "GitHub's search limit for requests without a token is used up (10 a minute).",
        "Job board lookup failed: HTTP 500",
        "Wikidata lookup failed: timeout",
    ]}
    result = outcomes(score_case("x", {**EXPECT, "wikidata": "Q1"}, down))
    assert result["github_org"] == result["job_board"] == result["wikidata"] == ERROR


def test_no_answer_from_unreachable_sources_is_an_error_not_a_pass():
    down = {"domain": None, "domain_source": None, "gaps": ["Wikidata lookup failed: 403"]}
    assert outcomes(score_case("x", {"domain": None}, down))["domain"] == ERROR
    blind = {**GOOD, "website": None, "hiring": None, "github": None,
             "gaps": ["Website could not be read: 403", "Job board lookup failed: 403"]}
    assert outcomes(score_case("x", {"tech": ["Rust"]}, blind))["tech"] == ERROR


def test_not_found_is_a_fail_not_an_error():
    missing = {**GOOD, "github": None, "gaps": ["No public GitHub organisation found."]}
    assert outcomes(score_case("x", EXPECT, missing))["github_org"] == FAIL


def test_case_and_null_expectations():
    assert outcomes(score_case("x", {"github_org": "LINEAR"}, GOOD))["github_org"] == PASS
    no_domain = {"domain": None, "gaps": []}
    assert outcomes(score_case("x", {"domain": None}, no_domain))["domain"] == PASS
    guessed = {"domain": "linear.com", "gaps": []}
    assert outcomes(score_case("x", {"domain": None}, guessed))["domain"] == FAIL
    assert outcomes(score_case("x", {"job_board": None}, {**GOOD, "hiring": None}))[
        "job_board"] == PASS


def test_tech_is_found_across_sources():
    assert tech_found(GOOD) == {"next.js", "typescript"}
    result = score_case("x", {"tech": ["Rust"]}, GOOD).scores[0]
    assert result.outcome == FAIL and "Rust" in result.detail


def test_summary_excludes_errors_from_accuracy():
    cases = [score_case("a", EXPECT, GOOD),
             score_case("b", {"github_org": "x"}, {"github": {"org": "y", "confidence": "high"},
                                                  "gaps": []}),
             score_case("c", {"github_org": "x"}, {"github": None,
                                                  "gaps": ["GitHub research failed: boom"]})]
    s = summarize(cases)
    assert s["fields"]["github_org"] == {PASS: 1, FAIL: 0, CRITICAL: 1, ERROR: 1, "accuracy": 0.5}
    assert s["errors"] == 1 and len(s["critical"]) == 1


class Live:
    def __init__(self):
        self.calls = 0

    async def get(self, url, *, ttl, headers=None, max_bytes=0):
        self.calls += 1
        if "missing" in url:
            raise FetchError(url, 404)
        return Response(url=url, status=200, headers={}, text="ok")


async def test_record_then_replay_offline():
    tape = {}
    recorder = Tape(Live(), tape, record=True)
    assert (await recorder.get("https://a.io/x", ttl=0)).text == "ok"
    with pytest.raises(FetchError):
        await recorder.get("https://a.io/missing", ttl=0)

    replay = Tape(None, tape)
    assert (await replay.get("https://a.io/x", ttl=0)).text == "ok"
    with pytest.raises(FetchError) as e:
        await replay.get("https://a.io/missing", ttl=0)
    assert e.value.status == 404
    with pytest.raises(FetchError, match="not in the saved responses"):
        await replay.get("https://a.io/never-seen", ttl=0)
    assert replay.hosts["a.io"] == 3


async def test_dns_replay_needs_a_recording():
    with pytest.raises(RuntimeError):
        await dns_lookup_for({}, "replay")("acme.io")
    tape = {"dns:acme.io": {"email_provider": ["Google Workspace"], "email_senders": [],
                            "verified_services": [], "unavailable": []}}
    info = await dns_lookup_for(tape, "replay")("acme.io")
    assert info.email_provider == ["Google Workspace"]

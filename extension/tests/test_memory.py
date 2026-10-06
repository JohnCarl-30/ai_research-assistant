"""Snapshots of past research, what changed between them, and the watchlist."""

from datetime import UTC, date, datetime

from scout_mcp.memory import History, company_key, compare, signals


def _dossier(roles=40, teams=None, job_tech=("Go", "Rust"), site_tech=("React",),
             last_push="2026-09-01T00:00:00Z", hn=("Launch",), employees=500):
    teams = teams if teams is not None else [("Engineering", 30), ("Sales", 10)]
    return {
        "company": "Acme", "domain": "acme.com",
        "facts": {"employees": employees},
        "website": {"tech": {"framework": list(site_tech)}},
        "hiring": {"board": "greenhouse", "slug": "acme", "open_roles": roles,
                   "by_department": teams, "remote_share": 0.5,
                   "tech_mentions": [(t, 3) for t in job_tech]},
        "github": {"org": "acme", "last_pushed_at": last_push},
        "hacker_news": {"recent": [{"title": t} for t in hn]},
    }


def test_company_key_prefers_the_domain():
    assert company_key("Acme Inc.", "Acme.com") == "acme.com"
    assert company_key("Acme Inc.", None) == "acme-inc"


def test_nothing_changed_is_quiet():
    s = signals(_dossier())
    assert compare(s, s, date(2026, 9, 15)) == []


def test_hiring_changes_are_reported():
    old = signals(_dossier())
    new = signals(_dossier(roles=12, teams=[("Sales", 6), ("Support", 6)],
                           job_tech=("Go", "Kotlin")))
    changes = compare(old, new, date(2026, 9, 15))
    assert changes[0] == "Open roles fell from 40 to 12 (-70%)."
    assert "Engineering hiring stopped (had 30 open roles)." in changes
    assert "New hiring in Support (6 open roles)." in changes
    assert "New in job posts: Kotlin." in changes
    assert "No longer in job posts: Rust." in changes


def test_small_role_changes_are_noise():
    assert compare(signals(_dossier(roles=40)), signals(_dossier(roles=44)),
                   date(2026, 9, 15)) == []


def test_a_team_pushed_out_of_a_full_list_has_not_stopped():
    full = [(f"Team {i}", 10 - i) for i in range(8)]
    old = signals(_dossier(teams=full))
    new = signals(_dossier(teams=[("New team", 20), *full[:7]]))
    changes = compare(old, new, date(2026, 9, 15))
    assert not any("stopped" in c for c in changes)


def test_a_section_missing_this_time_is_not_reported_as_emptied():
    old = signals(_dossier())
    unreachable = _dossier()
    unreachable["website"] = None
    unreachable["hacker_news"] = None
    assert compare(old, signals(unreachable), date(2026, 9, 15)) == []
    # ...and a section that is back is not all "new".
    assert compare(signals(unreachable), old, date(2026, 9, 15)) == []


def test_board_appearing_moving_and_vanishing():
    with_board = signals(_dossier())
    no_board = signals({**_dossier(), "hiring": None})
    moved = {**with_board, "job_board": "ashby/acme"}
    assert compare(no_board, with_board)[0] == (
        "A job board appeared (greenhouse/acme) with 40 open roles.")
    assert compare(with_board, no_board)[0].startswith("No job board found this time")
    assert "The job board moved from greenhouse/acme to ashby/acme." in compare(
        with_board, moved)


def test_github_going_quiet_and_news():
    old = signals(_dossier(last_push="2026-03-01T00:00:00Z"))
    new = signals(_dossier(last_push="2026-03-01T00:00:00Z", hn=("Launch", "Layoffs")))
    changes = compare(old, new, date(2026, 9, 15))
    assert "No public GitHub activity for 198 days (since 2026-03-01)." in changes
    assert "New Hacker News story: Layoffs" in changes


def test_history_compares_with_an_earlier_day(tmp_path):
    h = History(tmp_path / "history.db")
    first = h.record("Acme", "acme.com", _dossier(), now=datetime(2026, 9, 1, tzinfo=UTC))
    assert first.to_dict() == {"previous_snapshot": None,
                               "changes": ["First time Scout has researched this company."]}
    # A second look the same day replaces that day's snapshot.
    same_day = h.record("Acme", "acme.com", _dossier(roles=10),
                        now=datetime(2026, 9, 1, 18, tzinfo=UTC))
    assert same_day.previous_snapshot is None
    later = h.record("Acme", "acme.com", _dossier(roles=10),
                     now=datetime(2026, 9, 20, tzinfo=UTC))
    assert later.previous_snapshot == "2026-09-01"
    assert later.to_dict()["changes"] == ["Nothing notable changed."]


def test_watchlist(tmp_path):
    h = History(tmp_path / "history.db")
    assert h.watch("Acme", "acme.com") is True
    assert h.watch("Acme", "acme.com") is False
    h.watch("Beta", None)
    assert [w["company"] for w in h.watchlist()] == ["Acme", "Beta"]
    assert h.unwatch("acme") is True  # by name, without the domain
    assert h.unwatch("Nobody") is False
    assert [w["company"] for w in h.watchlist()] == ["Beta"]


def test_a_run_that_reached_nothing_is_not_kept(tmp_path):
    h = History(tmp_path / "history.db")
    h.record("Acme", "acme.com", _dossier(roles=40), now=datetime(2026, 9, 1, tzinfo=UTC))
    offline = {"company": "Acme", "domain": "acme.com"}
    h.record("Acme", "acme.com", offline, now=datetime(2026, 9, 10, tzinfo=UTC))
    later = h.record("Acme", "acme.com", _dossier(roles=10),
                     now=datetime(2026, 9, 20, tzinfo=UTC))
    assert later.previous_snapshot == "2026-09-01"
    assert later.changes[0].startswith("Open roles fell from 40 to 10")

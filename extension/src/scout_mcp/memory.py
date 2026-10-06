"""What changed since last time: dossier snapshots and a watchlist.

Every dossier leaves a snapshot of its signals (hiring by team, technologies,
GitHub activity, Hacker News stories, headcount), at most one per company per
day. The next dossier for that company is compared with the latest snapshot
from an earlier day, so Claude can say "open roles fell from 40 to 12 and
engineering hiring stopped": the kind of change a web search can't show.

All of it lives in one SQLite file in the user's notes folder.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    company_key TEXT NOT NULL,
    day TEXT NOT NULL,
    company TEXT NOT NULL,
    domain TEXT,
    taken_at TEXT NOT NULL,
    signals TEXT NOT NULL,
    PRIMARY KEY (company_key, day)
);
CREATE TABLE IF NOT EXISTS watchlist (
    company_key TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    domain TEXT,
    added_at TEXT NOT NULL
);
"""

# A change in open roles smaller than this is noise, not news.
ROLE_CHANGE_THRESHOLD = 0.2
# GitHub silence is only worth mentioning once it's this long.
QUIET_DAYS = 90
# Dossiers list only the top teams and technologies, so one missing from a
# full list may just have been pushed out of it, not gone.
TEAMS_LISTED = 8
TECH_LISTED = 15


def company_key(company: str, domain: str | None) -> str:
    """One key per company: the domain when known, else the normalised name."""
    if domain:
        return domain.lower()
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def signals(dossier: dict) -> dict:
    """The parts of a dossier worth comparing over time.

    A section that is missing (not found, or unreachable this time) is None,
    so it is never compared as if it were empty.
    """
    hiring = dossier.get("hiring") or {}
    github = dossier.get("github") or {}
    hn = dossier.get("hacker_news") or {}
    website = dossier.get("website") or {}
    facts = dossier.get("facts") or {}
    return {
        "open_roles": hiring.get("open_roles"),
        "job_board": f"{hiring['board']}/{hiring['slug']}" if hiring else None,
        "by_department": dict(hiring.get("by_department") or []),
        "remote_share": hiring.get("remote_share"),
        "job_tech": sorted(t for t, _ in hiring["tech_mentions"]) if hiring else None,
        "site_tech": sorted({t for labels in (website.get("tech") or {}).values()
                             for t in labels}) if website else None,
        "github_org": github.get("org"),
        "github_last_push": github.get("last_pushed_at"),
        "hn_recent": [s.get("title") for s in hn.get("recent") or [] if s.get("title")]
        if hn else None,
        "employees": facts.get("employees"),
    }


def _pct(old: int, new: int) -> str:
    return f"{(new - old) / old:+.0%}" if old else "new"


def compare(old: dict, new: dict, today: date | None = None) -> list[str]:
    """Plain-language changes between two snapshots' signals, most important first."""
    today = today or datetime.now(UTC).date()
    changes: list[str] = []
    o, n = old.get("open_roles"), new.get("open_roles")
    if o is not None and n is not None:
        if o and abs(n - o) / o >= ROLE_CHANGE_THRESHOLD:
            verb = "rose" if n > o else "fell"
            changes.append(f"Open roles {verb} from {o} to {n} ({_pct(o, n)}).")
    elif o and n is None and new.get("job_board") is None:
        changes.append(f"No job board found this time; last time {old.get('job_board')} "
                       f"listed {o} open roles.")
    elif n and o is None:
        changes.append(f"A job board appeared ({new.get('job_board')}) with {n} open roles.")

    old_board, new_board = old.get("job_board"), new.get("job_board")
    if old_board and new_board and old_board != new_board:
        changes.append(f"The job board moved from {old_board} to {new_board}.")
    elif new_board:
        changes += _team_changes(old.get("by_department") or {},
                                 new.get("by_department") or {})

    for label, key in (("job posts", "job_tech"), ("its website", "site_tech")):
        if old.get(key) is None or new.get(key) is None:
            continue
        before, after = set(old[key]), set(new[key])
        added = sorted(after - before) if len(before) < TECH_LISTED else []
        dropped = sorted(before - after) if len(after) < TECH_LISTED else []
        if added:
            changes.append(f"New in {label}: {', '.join(added)}.")
        if dropped:
            changes.append(f"No longer in {label}: {', '.join(dropped)}.")

    last_push = new.get("github_last_push")
    if last_push and last_push == old.get("github_last_push"):
        quiet = (today - date.fromisoformat(last_push[:10])).days
        if quiet >= QUIET_DAYS:
            changes.append(f"No public GitHub activity for {quiet} days (since {last_push[:10]}).")
    for title in new.get("hn_recent") or []:
        if old.get("hn_recent") is not None and title not in old["hn_recent"]:
            changes.append(f"New Hacker News story: {title}")

    oe, ne = old.get("employees"), new.get("employees")
    if oe and ne and oe != ne:
        changes.append(f"Headcount on Wikidata changed from {oe} to {ne} ({_pct(oe, ne)}).")
    return changes


def _team_changes(old: dict, new: dict) -> list[str]:
    changes = []
    for team in sorted(set(old) | set(new)):
        before, after = old.get(team, 0), new.get(team, 0)
        if before and not after and len(new) < TEAMS_LISTED:
            changes.append(f"{team} hiring stopped (had {before} open roles).")
        elif after and not before and old and len(old) < TEAMS_LISTED:
            changes.append(f"New hiring in {team} ({after} open roles).")
    return changes


@dataclass
class Comparison:
    previous_snapshot: str | None
    changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.previous_snapshot is None:
            return {"previous_snapshot": None,
                    "changes": ["First time Scout has researched this company."]}
        return {"previous_snapshot": self.previous_snapshot,
                "changes": self.changes or ["Nothing notable changed."]}


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def record(self, company: str, domain: str | None, dossier: dict,
               now: datetime | None = None) -> Comparison:
        """Save today's snapshot and compare it with the latest from an earlier day."""
        now = now or datetime.now(UTC)
        key, day = company_key(company, domain), now.date().isoformat()
        current = signals(dossier)
        previous = self.db.execute(
            "SELECT taken_at, signals FROM snapshots WHERE company_key = ? AND day < ? "
            "ORDER BY day DESC LIMIT 1", (key, day),
        ).fetchone()
        # A run where nothing could be reached (offline, say) isn't kept: it
        # would hide the real snapshot from the next comparison.
        if any(v not in (None, [], {}) for v in current.values()):
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                    (key, day, company, domain, now.isoformat(timespec="seconds"),
                     json.dumps(current)),
                )
        if previous is None:
            return Comparison(previous_snapshot=None)
        return Comparison(previous_snapshot=previous["taken_at"][:10],
                          changes=compare(json.loads(previous["signals"]), current, now.date()))

    def watch(self, company: str, domain: str | None) -> bool:
        """Add to the watchlist; False if it was already there."""
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO watchlist VALUES (?, ?, ?, ?)",
                (company_key(company, domain), company, domain,
                 datetime.now(UTC).isoformat(timespec="seconds")),
            )
        return cur.rowcount > 0

    def unwatch(self, company: str, domain: str | None = None) -> bool:
        keys = {company_key(company, domain), company_key(company, None)}
        with self.db:
            cur = self.db.execute(
                f"DELETE FROM watchlist WHERE company_key IN ({','.join('?' * len(keys))}) "
                "OR lower(company) = lower(?)", (*keys, company),
            )
        return cur.rowcount > 0

    def watchlist(self) -> list[dict]:
        rows = self.db.execute("SELECT company, domain, added_at FROM watchlist ORDER BY company")
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.db.close()

"""A local research notebook: notes in one SQLite file, searchable with BM25.

Search uses SQLite's built-in FTS5 index, the same sparse (BM25) ranking the
backend's hybrid retriever uses for its keyword arm. It needs no embedding
model or API key, so it works offline for anyone.
"""

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    url TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, content, tags, content='notes', content_rowid='id',
    tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
END;
"""


@dataclass
class Note:
    id: int
    title: str
    content: str
    url: str | None
    tags: list[str]
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def fts_query(text: str) -> str | None:
    """A safe FTS5 query: every word quoted (no operator injection), OR-ed for recall."""
    words = re.findall(r"\w+", text)
    return " OR ".join(f'"{w}"' for w in words) or None


class Notebook:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def _note(self, row: sqlite3.Row) -> Note:
        return Note(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            tags=json.loads(row["tags"]),
            created_at=row["created_at"],
        )

    def save(
        self, title: str, content: str, url: str | None = None, tags: list[str] | None = None
    ) -> Note:
        tags = sorted({t.strip().lower() for t in tags or [] if t.strip()})
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO notes (title, content, url, tags, created_at) VALUES (?, ?, ?, ?, ?)",
                (title.strip(), content, url, json.dumps(tags), created_at),
            )
        return self.get(cur.lastrowid)

    def get(self, note_id: int) -> Note | None:
        row = self.db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self._note(row) if row else None

    def delete(self, note_id: int) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0

    def recent(self, limit: int = 20, tag: str | None = None) -> list[Note]:
        rows = self.db.execute(
            """
            SELECT * FROM notes
            WHERE ?1 IS NULL OR EXISTS (SELECT 1 FROM json_each(notes.tags) WHERE value = ?1)
            ORDER BY id DESC LIMIT ?2
            """,
            (tag.strip().lower() if tag else None, limit),
        ).fetchall()
        return [self._note(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[tuple[Note, str]]:
        """Best-matching notes with a highlighted snippet of each."""
        match = fts_query(query)
        if not match:
            return []
        rows = self.db.execute(
            """
            SELECT notes.*, snippet(notes_fts, 1, '**', '**', ' … ', 24) AS snip
            FROM notes_fts JOIN notes ON notes.id = notes_fts.rowid
            WHERE notes_fts MATCH ?
            ORDER BY bm25(notes_fts, 5.0, 1.0, 2.0)
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [(self._note(r), r["snip"]) for r in rows]

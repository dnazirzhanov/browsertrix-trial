"""The frontier: where discovered URLs live, deduplicated.

For a single-site trial this is intentionally a plain SQLite table, not Redis or
a message queue. The url_hash is the primary key, so INSERT OR IGNORE gives us
the dedup "gate" for free: adding a URL we've already seen is a no-op.

We store discovery provenance (source, discovered_from) so the report can prove
which source found what — the evidence your project plan asks for.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash        TEXT PRIMARY KEY,
    normalized_url  TEXT NOT NULL,
    raw_url         TEXT,
    url_type        TEXT,
    source          TEXT,          -- which sitemap/feed/crawl found it
    discovered_from TEXT,          -- the exact sitemap/page URL it appeared in
    robots_allowed  INTEGER,       -- 1 / 0: may the crawler fetch it later?
    lastmod         TEXT,          -- from sitemap <lastmod> if present
    title           TEXT,          -- from news sitemap / feed if present
    discovered_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_urls_source ON urls(source);
CREATE INDEX IF NOT EXISTS idx_urls_type   ON urls(url_type);
"""


class Frontier:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def add(
        self,
        url_hash: str,
        normalized_url: str,
        raw_url: str,
        url_type: str,
        source: str,
        discovered_from: str,
        robots_allowed: bool,
        lastmod: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        """Insert a URL. Returns True if it was new, False if already present."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO urls
               (url_hash, normalized_url, raw_url, url_type, source, discovered_from,
                robots_allowed, lastmod, title, discovered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                url_hash, normalized_url, raw_url, url_type, source, discovered_from,
                1 if robots_allowed else 0, lastmod, title,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return cur.rowcount > 0

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]

    def counts_by(self, column: str) -> Dict[str, int]:
        assert column in {"source", "url_type"}   # avoid SQL injection on identifiers
        rows = self.conn.execute(
            f"SELECT {column}, COUNT(*) FROM urls GROUP BY {column} ORDER BY COUNT(*) DESC"
        ).fetchall()
        return {(k if k is not None else "?"): v for k, v in rows}

    def robots_blocked_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM urls WHERE robots_allowed=0").fetchone()[0]

    def iter_rows(self) -> Iterable[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        yield from self.conn.execute(
            "SELECT * FROM urls ORDER BY url_type, normalized_url"
        )

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

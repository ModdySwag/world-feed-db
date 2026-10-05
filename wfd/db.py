"""wfd.db — SQLite (+FTS5) registry storage.

Working database: ``data/worldfeed.db`` (gitignored — code travels, data stays put).

Usage:
    from wfd import db
    conn = db.connect()
    db.init_db(conn)
    db.upsert_many(conn, rows)
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Iterable, Optional, Union

from .schema import CameraRow

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "worldfeed.db"

_COLUMNS = [
    "camera_id", "url", "source_family", "provenance", "name", "country", "city",
    "lat", "lon", "protocol", "status", "snapshot_date", "fetch_date", "last_verified",
    "geo_confidence", "was_redacted", "credential_present", "attribution", "official_url",
    "tags", "meta",
]
# NOTE: ``fail_count`` (the health engine's consecutive-failure streak) is
# deliberately NOT part of _COLUMNS: ingest upserts must never clobber the
# streak, so a re-ingest leaves the column untouched and fresh inserts take
# its column default (0). The health write-back (wfd.health.apply_result)
# owns it; ensure_health_columns() migrates the column into older DBs.

_DDL = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id          TEXT PRIMARY KEY,
    url                TEXT NOT NULL,
    source_family      TEXT NOT NULL,
    provenance         TEXT NOT NULL,
    name               TEXT NOT NULL DEFAULT '',
    country            TEXT NOT NULL DEFAULT '',
    city               TEXT NOT NULL DEFAULT '',
    lat                REAL,
    lon                REAL,
    protocol           TEXT NOT NULL DEFAULT 'unknown',
    status             TEXT NOT NULL DEFAULT 'unknown',
    snapshot_date      TEXT NOT NULL DEFAULT '',
    fetch_date         TEXT NOT NULL DEFAULT '',
    last_verified      TEXT NOT NULL DEFAULT '',
    geo_confidence     TEXT NOT NULL DEFAULT '',
    was_redacted       INTEGER NOT NULL DEFAULT 0,
    credential_present INTEGER NOT NULL DEFAULT 0,
    attribution        TEXT NOT NULL DEFAULT '',
    official_url       TEXT NOT NULL DEFAULT '',
    tags               TEXT NOT NULL DEFAULT '[]',
    meta               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cameras_provenance    ON cameras(provenance);
CREATE INDEX IF NOT EXISTS idx_cameras_status        ON cameras(status);
CREATE INDEX IF NOT EXISTS idx_cameras_source_family ON cameras(source_family);
CREATE VIRTUAL TABLE IF NOT EXISTS cameras_fts USING fts5(
    camera_id UNINDEXED, name, city, country, source_family, tags
);
"""


def connect(path: Optional[Union[pathlib.Path, str]] = None,
            check_same_thread: bool = False) -> sqlite3.Connection:
    """Open the registry. Thread-usable by default (check_same_thread=False):
    multi-threaded callers (e.g. health sweeps) MUST serialize their writes
    with their own lock — as wfd.health does."""
    p = pathlib.Path(path) if path else DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    ensure_health_columns(conn)
    conn.commit()


def ensure_health_columns(conn: sqlite3.Connection) -> bool:
    """Idempotent migration: add health write-back columns when missing.

    ``cameras.fail_count`` (A1 self-heal: consecutive-failure streak) is owned
    by the health engine, not by ingest, so it is added via this migration
    rather than baked into ``_DDL``/``_COLUMNS`` (see the note at ``_COLUMNS``).
    Covers both fresh tables (created by ``_DDL`` without the column) and
    pre-existing databases.
    Returns True when this call added the column.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cameras)")}
    if "fail_count" in cols:
        return False
    conn.execute(
        "ALTER TABLE cameras ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0"
    )
    return True


def _row_values(row: CameraRow) -> tuple:
    row.finalize()
    return (
        row.camera_id, row.url, row.source_family, row.provenance, row.name,
        row.country, row.city, row.lat, row.lon, row.protocol, row.status,
        row.snapshot_date, row.fetch_date, row.last_verified, row.geo_confidence,
        int(row.was_redacted), int(row.credential_present), row.attribution,
        row.official_url, json.dumps(row.tags, ensure_ascii=False),
        json.dumps(row.meta, ensure_ascii=False),
    )


def upsert(conn: sqlite3.Connection, row: CameraRow) -> None:
    """Idempotent by camera_id (stable hash of source_family|url).

    FTS maintenance is rowid-keyed: a ``WHERE camera_id`` delete on the FTS
    table would scan it per row (O(n^2) on bulk loads).
    """
    values = _row_values(row)
    placeholders = ", ".join("?" for _ in _COLUMNS)
    # Health-owned columns (status, last_verified) survive re-ingest: only a
    # fresh INSERT takes the ingest values; live sweeps own them afterwards.
    # A full rebuild is what `wfd db load --reset` is for.
    updates = ", ".join(
        f"{c}=excluded.{c}" for c in _COLUMNS
        if c not in ("camera_id", "status", "last_verified"))
    conn.execute(
        f"INSERT INTO cameras ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(camera_id) DO UPDATE SET {updates}",
        values,
    )
    rid = conn.execute(
        "SELECT rowid FROM cameras WHERE camera_id = ?", (row.camera_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM cameras_fts WHERE rowid = ?", (rid,))
    conn.execute(
        "INSERT INTO cameras_fts (rowid, camera_id, name, city, country, source_family, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rid, row.camera_id, row.name, row.city, row.country, row.source_family, " ".join(row.tags)),
    )


def upsert_many(conn: sqlite3.Connection, rows: Iterable[CameraRow]) -> int:
    n = 0
    for r in rows:
        upsert(conn, r)
        n += 1
    conn.commit()
    return n


def counts(conn: sqlite3.Connection) -> dict:
    out = {"total": conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]}
    out["by_provenance"] = {
        r[0]: r[1] for r in conn.execute("SELECT provenance, COUNT(*) FROM cameras GROUP BY provenance")
    }
    out["by_status"] = {
        r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM cameras GROUP BY status")
    }
    return out


def get(conn: sqlite3.Connection, camera_id: str) -> Optional[CameraRow]:
    r = conn.execute("SELECT * FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
    return _row_from_sql(r) if r else None


def _row_from_sql(r: sqlite3.Row) -> CameraRow:
    return CameraRow(
        camera_id=r["camera_id"], url=r["url"], source_family=r["source_family"],
        provenance=r["provenance"], name=r["name"], country=r["country"], city=r["city"],
        lat=r["lat"], lon=r["lon"], protocol=r["protocol"], status=r["status"],
        snapshot_date=r["snapshot_date"], fetch_date=r["fetch_date"],
        last_verified=r["last_verified"], geo_confidence=r["geo_confidence"],
        was_redacted=bool(r["was_redacted"]), credential_present=bool(r["credential_present"]),
        attribution=r["attribution"], official_url=r["official_url"],
        tags=json.loads(r["tags"] or "[]"), meta=json.loads(r["meta"] or "{}"),
    )


def search(conn: sqlite3.Connection, query: str, limit: int = 50) -> list:
    """FTS search over name/city/country/source_family/tags. Returns list of dicts."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        rows = conn.execute(
            "SELECT f.camera_id, f.name, f.city, f.country, f.source_family "
            "FROM cameras_fts f WHERE cameras_fts MATCH ? ORDER BY rank LIMIT ?",
            (q, int(limit)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]

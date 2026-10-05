"""wfd.registry — build + inspect the registry database from ingest outputs.

The ingest modules write normalized JSONL (wfd.schema.CameraRow dicts) under
``data/ingest/``. This module loads those files into the SQLite registry
(``data/worldfeed.db``) — idempotent by ``camera_id`` — and answers
summary / overlap / search questions over the result.

CLI (registered via wfd.cli):
    py -3.11 -m wfd db load [--dir data/ingest] [--reset]
    py -3.11 -m wfd db stats
    py -3.11 -m wfd db search <query> [--limit N]

Loading is idempotent (upsert by camera_id): re-running a load after re-running
an ingester refreshes rows in place; it never duplicates them.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib

from . import db as dbmod
from .ingest.base import DATA_DIR
from .schema import CameraRow

DEFAULT_DIR = DATA_DIR / "ingest"
_FIELDS = {f.name for f in dataclasses.fields(CameraRow)}


def load_jsonl_file(conn, path) -> dict:
    """Load one JSONL file of CameraRow dicts. Tolerant of bad lines / extra keys."""
    path = pathlib.Path(path)
    rows = []
    bad_lines = 0
    unknown_keys = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        extra = set(data) - _FIELDS
        if extra:
            unknown_keys += len(extra)
            data = {k: v for k, v in data.items() if k in _FIELDS}
        rows.append(CameraRow(**data))
    loaded = dbmod.upsert_many(conn, rows)
    return {"file": path.name, "rows": loaded, "bad_lines": bad_lines, "unknown_keys": unknown_keys}


def load_dir(conn, directory=None, pattern: str = "*.jsonl") -> dict:
    """Load every matching JSONL file in ``directory`` (sorted, deterministic)."""
    directory = pathlib.Path(directory) if directory else DEFAULT_DIR
    files = sorted(directory.glob(pattern))
    out = {"dir": str(directory), "files": [], "total": 0}
    for f in files:
        entry = load_jsonl_file(conn, f)
        out["files"].append(entry)
        out["total"] += entry["rows"]
    return out


def stats(conn) -> dict:
    """Registry summary: totals, family split, top countries, cross-family URL overlaps."""
    counts = dbmod.counts(conn)
    by_family = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT source_family, COUNT(*) FROM cameras GROUP BY source_family ORDER BY COUNT(*) DESC"
        )
    }
    top_countries = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT country, COUNT(*) FROM cameras WHERE country != '' "
            "GROUP BY country ORDER BY COUNT(*) DESC LIMIT 12"
        )
    }
    overlap_urls = conn.execute(
        "SELECT COUNT(*) FROM (SELECT url FROM cameras GROUP BY url HAVING COUNT(DISTINCT source_family) > 1)"
    ).fetchone()[0]
    overlap_examples = [
        {"url": r[0], "families": r[1]}
        for r in conn.execute(
            "SELECT url, COUNT(DISTINCT source_family) AS c FROM cameras "
            "GROUP BY url HAVING c > 1 ORDER BY c DESC, url LIMIT 10"
        )
    ]
    return {
        "total": counts["total"],
        "by_provenance": counts["by_provenance"],
        "by_status": counts["by_status"],
        "by_family": by_family,
        "top_countries": top_countries,
        "overlap_urls": overlap_urls,
        "overlap_examples": overlap_examples,
    }


def search(conn, query: str, limit: int = 20) -> list:
    """FTS search, enriched with provenance/status/protocol for display."""
    base = dbmod.search(conn, query, limit=limit)
    if not base:
        return []
    ids = [r["camera_id"] for r in base]
    marks = ", ".join("?" for _ in ids)
    detail = {
        r["camera_id"]: r
        for r in conn.execute(f"SELECT * FROM cameras WHERE camera_id IN ({marks})", ids)
    }
    out = []
    for r in base:  # preserve FTS rank order
        d = detail.get(r["camera_id"])
        if not d:
            continue
        out.append({
            "camera_id": d["camera_id"],
            "name": d["name"],
            "city": d["city"],
            "country": d["country"],
            "source_family": d["source_family"],
            "provenance": d["provenance"],
            "status": d["status"],
            "protocol": d["protocol"],
        })
    return out


# ---------------------------------------------------------------------------
# CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def _cmd_db(args) -> int:
    action = getattr(args, "db_action", None)
    if action is None:
        print("usage: wfd db {load|stats|search} ...")
        return 2

    if action == "load":
        if args.reset:
            target = pathlib.Path(dbmod.DEFAULT_DB)
            for p in (target,
                      target.with_name(target.name + "-wal"),
                      target.with_name(target.name + "-shm")):
                if p.exists():
                    p.unlink()
            print(f"reset: removed {target}")
        conn = dbmod.connect()
        try:
            dbmod.init_db(conn)
            out = load_dir(conn, args.dir)
            for f in out["files"]:
                print(f"  {f['file']:<38} rows={f['rows']:<7} "
                      f"bad_lines={f['bad_lines']} unknown_keys={f['unknown_keys']}")
            print(f"loaded {out['total']} rows from {len(out['files'])} file(s) into {dbmod.DEFAULT_DB}")
            c = dbmod.counts(conn)
            print(f"registry now: {c['total']} rows · by_provenance={c['by_provenance']} "
                  f"· by_status={c['by_status']}")
            return 0
        finally:
            conn.close()

    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        if action == "stats":
            s = stats(conn)
            print(f"registry: {s['total']} rows")
            print(f"  by_provenance: {s['by_provenance']}")
            print(f"  by_status:     {s['by_status']}")
            print("  by_family:")
            for fam, n in s["by_family"].items():
                print(f"    {fam:<26} {n}")
            print(f"  overlap urls (>1 family): {s['overlap_urls']}")
            for ex in s["overlap_examples"][:5]:
                print(f"    x{ex['families']}  {ex['url'][:100]}")
            print("  top countries:")
            for c, n in list(s["top_countries"].items())[:10]:
                print(f"    {c:<28} {n}")
            return 0
        if action == "search":
            rows = search(conn, args.query, limit=args.limit)
            print(f"{len(rows)} result(s) for {args.query!r}:")
            for r in rows:
                flag = "EXPOSED" if r["provenance"] == "exposure_aggregator" else "public "
                print(f"  [{flag}] {r['camera_id']}  {r['source_family']:<18} "
                      f"{r['name'][:44]:<44} {r['city'][:18]:<18} {r['country']}")
            return 0
    finally:
        conn.close()
    return 2


def _add_db_arguments(parser) -> None:
    sub = parser.add_subparsers(dest="db_action")
    p = sub.add_parser("load", help="load data/ingest/*.jsonl into the registry (idempotent)")
    p.add_argument("--dir", default=None, help="source directory (default: data/ingest)")
    p.add_argument("--reset", action="store_true", help="delete the db file and rebuild from scratch")
    sub.add_parser("stats", help="summary: provenance/status/family/countries + URL overlaps")
    p = sub.add_parser("search", help="FTS search over name/city/country/family/tags")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)


_cmd_db.add_arguments = _add_db_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd db``."""
    return {"db": ("registry database: load | stats | search", _cmd_db)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.registry")
    _add_db_arguments(parser)
    args = parser.parse_args(argv)
    return _cmd_db(args)


if __name__ == "__main__":
    raise SystemExit(main())

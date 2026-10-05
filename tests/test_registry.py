"""Registry tests — plain runner. Run: py -3.11 tests/test_registry.py

Covers: JSONL load (tolerant of bad lines), idempotency by camera_id,
counts/stats (incl. cross-family URL overlap), FTS search enrichment.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import db, registry
from wfd.schema import CameraRow, stable_id


def _mk_rows():
    pub1 = CameraRow(url="http://example.com/a", source_family="fampub",
                     provenance="public_by_design", name="Harbour Cam",
                     city="Sydney", country="AU", status="unknown", fetch_date="2026-10-05")
    pub2 = CameraRow(url="http://example.com/b", source_family="fampub",
                     provenance="public_by_design", name="Bridge Cam",
                     city="Melbourne", country="AU", status="unknown", fetch_date="2026-10-05")
    exp1 = CameraRow(url="http://example.com/c?u=<redacted>", source_family="famexp",
                     provenance="exposure_aggregator", city="Tokyo", country="JP",
                     status="unverified", snapshot_date="2019-02-21", geo_confidence="low",
                     was_redacted=True, credential_present=True, fetch_date="2026-10-05")
    exp2 = CameraRow(url="http://example.com/a", source_family="famexp",
                     provenance="exposure_aggregator", name="Dup URL cam", country="AU",
                     status="unverified", fetch_date="2026-10-05")  # same url as pub1, other family
    return [pub1, pub2, exp1, exp2]


def _write(tmpdir, rows, name="t1.jsonl"):
    d = pathlib.Path(tmpdir) / "ingest"
    d.mkdir(exist_ok=True)
    with (d / name).open("w", encoding="utf-8") as fh:
        for r in rows:
            r.finalize()
            fh.write(json.dumps(r.as_dict(), ensure_ascii=False) + "\n")
    return d


def test_load_counts_and_idempotency():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        d = _write(td, _mk_rows())
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        out = registry.load_dir(conn, d)
        assert out["total"] == 4, out
        c = db.counts(conn)
        assert c["total"] == 4, c
        assert c["by_provenance"] == {"public_by_design": 2, "exposure_aggregator": 2}, c
        assert c["by_status"] == {"unknown": 2, "unverified": 2}, c
        # idempotent: a second load must not duplicate
        registry.load_dir(conn, d)
        assert db.counts(conn)["total"] == 4
        conn.close()


def test_stats_overlap():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        d = _write(td, _mk_rows())
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        registry.load_dir(conn, d)
        s = registry.stats(conn)
        assert s["total"] == 4, s
        assert s["by_family"] == {"fampub": 2, "famexp": 2}, s
        assert s["overlap_urls"] == 1, s          # example.com/a in two families
        assert s["overlap_examples"][0]["url"].endswith("/a"), s
        conn.close()


def test_search_enrichment():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        d = _write(td, _mk_rows())
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        registry.load_dir(conn, d)
        hits = registry.search(conn, "Sydney")
        assert len(hits) == 1 and hits[0]["name"] == "Harbour Cam", hits
        assert hits[0]["source_family"] == "fampub" and hits[0]["provenance"] == "public_by_design"
        assert registry.search(conn, "Nosuchplace") == []
        conn.close()


def test_bad_lines_tolerated():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        d = pathlib.Path(td) / "ingest"
        d.mkdir()
        good = CameraRow(url="http://example.com/ok", source_family="fam",
                         provenance="public_by_design", name="Ok Cam", fetch_date="2026-10-05")
        good.finalize()
        (d / "t.jsonl").write_text(
            "{not json}\n" + json.dumps(good.as_dict(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        out = registry.load_dir(conn, d)
        assert out["total"] == 1 and out["files"][0]["bad_lines"] == 1, out
        conn.close()


def test_duplicate_within_family_collapses():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        dup1 = CameraRow(url="http://example.com/same", source_family="famdup",
                         provenance="public_by_design", name="A", fetch_date="2026-10-05")
        dup2 = CameraRow(url="http://example.com/same", source_family="famdup",
                         provenance="public_by_design", name="B", fetch_date="2026-10-05")
        d = _write(td, [dup1, dup2])
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        out = registry.load_dir(conn, d)
        assert out["total"] == 2, out               # both lines read
        assert db.counts(conn)["total"] == 1        # same (family,url) -> one row
        stored = db.get(conn, stable_id("famdup", "http://example.com/same"))
        assert stored is not None and stored.name == "B", stored  # last write wins
        conn.close()




def test_reingest_preserves_health_state():
    """Re-loading a JSONL must NOT reset sweep verdicts (status/last_verified)."""
    import pathlib as _p
    import tempfile as _tf
    from wfd import db as _db

    with _tf.TemporaryDirectory() as td:
        conn = _db.connect(_p.Path(td) / "t.db")
        _db.init_db(conn)
        from wfd.schema import CameraRow as _CR
        row = _CR(url="https://example.com/a", source_family="t", name="one")
        _db.upsert(conn, row)
        conn.execute("UPDATE cameras SET status='live', "
                     "last_verified='2026-10-06T01:02:03' WHERE camera_id=?",
                     (row.camera_id,))
        conn.commit()
        _db.upsert(conn, _CR(url="https://example.com/a", source_family="t", name="two"))
        got = conn.execute("SELECT status, last_verified, name FROM cameras "
                           "WHERE camera_id=?", (row.camera_id,)).fetchone()
        assert got[0] == "live", got[0]
        assert got[1] == "2026-10-06T01:02:03", got[1]
        assert got[2] == "two", got[2]           # ingest-owned columns still update
        conn.close()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Health-probe tests — plain runner. Run: py -3.11 tests/test_health.py

Offline: classification logic, pHash behaviour on synthetic images, tool
resolution, skip-dispatch, and the A1 self-heal write-back (consecutive-
failure accounting + auto-quarantine/restore, on temp DBs only). Live probes
are exercised by real sweeps.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import db, health
from wfd.schema import CameraRow


def test_classify_stream():
    assert health.classify_stream(False, False) == "dead"
    assert health.classify_stream(True, False) == "dead"
    assert health.classify_stream(True, True) == "live"
    assert health.classify_stream(True, True, froze=True) == "stale"
    assert health.classify_stream(True, True, black=True) == "stale"


def test_classify_jpeg():
    assert health.classify_jpeg(False, None) == "unknown"
    assert health.classify_jpeg(True, None) == "unknown"
    assert health.classify_jpeg(True, 0) == "stale"
    assert health.classify_jpeg(True, 5) == "stale"
    assert health.classify_jpeg(True, 6) == "live"
    assert health.classify_jpeg(True, 22) == "live"


def test_classify_youtube():
    assert health.classify_youtube(0) == "live"
    assert health.classify_youtube(101) == "dead"
    assert health.classify_youtube(1) == "unknown"


def test_phash_synthetic():
    from PIL import Image, ImageDraw

    def png(img) -> bytes:
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    a = Image.new("RGB", (128, 128), (90, 90, 90))
    d = ImageDraw.Draw(a)
    d.rectangle([10, 10, 60, 60], fill=(200, 30, 30))
    a_bytes = png(a)

    # identical => distance 0
    assert health.phash_hamming(a_bytes, a_bytes) == 0

    # visibly different => distance > 5
    b = Image.new("RGB", (128, 128), (10, 40, 120))
    db = ImageDraw.Draw(b)
    db.rectangle([70, 70, 120, 120], fill=(255, 255, 0))
    assert health.phash_hamming(a_bytes, png(b)) > 5

    # undecodable input => None
    assert health.phash_hamming(b"not an image", a_bytes) is None


def test_tool_resolution():
    assert health._tool("ffprobe"), "ffprobe must resolve on this host"
    assert health._tool("ffmpeg"), "ffmpeg must resolve on this host"


def test_probe_row_skip_dispatch():
    res = health.probe_row("https://example.com/page", "iframe")
    assert res.state == "unknown" and res.kind == "skipped", res


def test_looks_like_image():
    assert health._looks_like_image(b"\xff\xd8" + b"0" * 20) is True
    assert health._looks_like_image(b"<html>nope</html>" * 3) is False
    assert health._looks_like_image(None) is False


# --- A1 self-heal: consecutive-failure accounting + quarantine/restore ---------

TS = "2026-10-05T00:00:00"


def _mk_temp_conn(td: str):
    conn = db.connect(pathlib.Path(td) / "t.db")
    db.init_db(conn)
    return conn


def _mk_public(suffix: str) -> CameraRow:
    return CameraRow(
        url=f"http://example.com/{suffix}", source_family="testfam",
        provenance="public_by_design", name="Test Cam", protocol="jpeg",
        status="unknown",
    )


def _store(conn, row: CameraRow) -> CameraRow:
    db.upsert_many(conn, [row])
    return row


def _camera_columns(conn) -> set:
    return {r[1] for r in conn.execute("PRAGMA table_info(cameras)")}


def test_apply_result_dead_increments():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_temp_conn(td)
        cid = _store(conn, _mk_public("dead1")).camera_id

        out = health.apply_result(conn, cid, "dead", TS)
        assert out["status"] == "dead" and out["fail_count"] == 1, out
        out = health.apply_result(conn, cid, "dead", TS)
        assert out["status"] == "dead" and out["fail_count"] == 2, out

        stored = conn.execute(
            "SELECT status, fail_count, last_verified FROM cameras WHERE camera_id = ?",
            (cid,),
        ).fetchone()
        assert stored["status"] == "dead" and stored["fail_count"] == 2, dict(stored)
        assert stored["last_verified"] == TS, dict(stored)   # stamped for resumability
        conn.close()


def test_apply_result_quarantine_at_threshold():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_temp_conn(td)
        cid = _store(conn, _mk_public("q1")).camera_id

        out = None
        for _ in range(9):
            out = health.apply_result(conn, cid, "dead", TS)
        assert out["status"] == "dead" and out["fail_count"] == 9, out   # 9 fails: dead

        out = health.apply_result(conn, cid, "dead", TS)                 # 10th: quarantine
        assert out["status"] == "quarantined" and out["fail_count"] == 10, out

        out = health.apply_result(conn, cid, "dead", TS)                 # stays quarantined
        assert out["status"] == "quarantined" and out["fail_count"] == 11, out
        conn.close()


def test_apply_result_live_restores_quarantined():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_temp_conn(td)
        cid = _store(conn, _mk_public("r1")).camera_id
        for _ in range(10):
            health.apply_result(conn, cid, "dead", TS)                   # -> quarantined

        out = health.apply_result(conn, cid, "live", TS)
        assert out["status"] == "live" and out["fail_count"] == 0, out

        out = health.apply_result(conn, cid, "dead", TS)                 # streak restarts
        assert out["status"] == "dead" and out["fail_count"] == 1, out
        conn.close()


def test_apply_result_stale_resets_streak():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_temp_conn(td)
        cid = _store(conn, _mk_public("r2")).camera_id
        for _ in range(10):
            health.apply_result(conn, cid, "dead", TS)                   # -> quarantined

        out = health.apply_result(conn, cid, "stale", TS)
        assert out["status"] == "stale" and out["fail_count"] == 0, out
        conn.close()


def test_apply_result_unknown_keeps_streak():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_temp_conn(td)
        cid = _store(conn, _mk_public("u1")).camera_id
        health.apply_result(conn, cid, "dead", TS)
        health.apply_result(conn, cid, "dead", TS)

        out = health.apply_result(conn, cid, "unknown", TS)
        assert out["status"] == "unknown" and out["fail_count"] == 2, out
        conn.close()


def test_migration_old_db_then_selfheal_cycle():
    """init_db() migrates an old-shaped table; 10 deads quarantine; live restores."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = db.connect(pathlib.Path(td) / "old.db")
        # Old shape: the historical _DDL (fail_count is added only by the migration)
        conn.executescript(db._DDL)
        row = _store(conn, _mk_public("old1"))
        assert "fail_count" not in _camera_columns(conn)

        db.init_db(conn)                       # <- the migration runs (after executescript)
        assert "fail_count" in _camera_columns(conn)
        assert db.ensure_health_columns(conn) is False       # idempotent

        r = conn.execute("SELECT fail_count FROM cameras WHERE camera_id = ?",
                         (row.camera_id,)).fetchone()
        assert r["fail_count"] == 0, dict(r)   # pre-migration rows get the column default

        for _ in range(9):
            health.apply_result(conn, row.camera_id, "dead", TS)
        out = health.apply_result(conn, row.camera_id, "dead", TS)
        assert out["status"] == "quarantined" and out["fail_count"] == 10, out

        out = health.apply_result(conn, row.camera_id, "live", TS)
        assert out["status"] == "live" and out["fail_count"] == 0, out
        conn.close()


def test_run_sweep_writeback_and_evidence():
    """run_sweep writes back via apply_result; evidence JSONL carries fail_count."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tdp = pathlib.Path(td)
        db_path = tdp / "sweep.db"
        conn = db.connect(db_path)
        db.init_db(conn)
        cid = _store(conn, _mk_public("sweep1")).camera_id

        class _Shim:    # run_sweep's dbmod, pinned to the temp connection
            @staticmethod
            def connect(*a, **k):
                assert not a and not k, "sweep must reuse the temp connection"
                return conn

            @staticmethod
            def init_db(c):
                db.init_db(c)

        saved = (health.dbmod, health.probe_row, health.HEALTH_DIR)
        health.dbmod = _Shim
        health.probe_row = lambda url, proto, **k: health.ProbeResult(
            url, "jpeg", "dead", 1, {"stub": True})
        health.HEALTH_DIR = tdp / "health"
        try:
            out = health.run_sweep(limit=1, gap_s=0)
        finally:
            health.dbmod, health.probe_row, health.HEALTH_DIR = saved

        assert out["selected"] == 1 and out["counts"]["dead"] == 1, out
        with open(out["evidence"], encoding="utf-8") as fh:
            line = json.loads(fh.readline())
        assert line["camera_id"] == cid and line["state"] == "dead", line
        assert line["fail_count"] == 1, line

        conn2 = db.connect(db_path)            # run_sweep closed the first connection
        r = conn2.execute(
            "SELECT status, fail_count, last_verified FROM cameras WHERE camera_id = ?",
            (cid,),
        ).fetchone()
        assert r["status"] == "dead" and r["fail_count"] == 1, dict(r)
        assert r["last_verified"], dict(r)
        conn2.close()


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

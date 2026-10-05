"""Core smoke tests — plain-python runner (this host has no pytest).

Run:    py -3.11 tests/test_core.py       -> prints PASS lines; exit 0 = all good.

Test functions are named test_* so they also work under pytest if it is ever
installed. New test files follow the same pattern (see docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import db, profile
from wfd.schema import CameraRow, redact_url, stable_id


def test_redact_userinfo():
    url = "rtsp://admin:secret@10.0.0.5:554/Streaming/Channels/1"
    red, was = redact_url(url)
    assert was is True
    assert "admin" not in red and "secret" not in red, red
    assert red == "rtsp://10.0.0.5:554/Streaming/Channels/1", red


def test_redact_query_keys():
    url = "http://1.2.3.4/cgi-bin/snapshot.cgi?chn=0&u=admin&p=hunter2&x=1"
    red, was = redact_url(url)
    assert was is True
    assert "admin" not in red and "hunter2" not in red, red
    assert "chn=0" in red and "&x=1" in red, red


def test_redact_passthrough():
    url = "https://wzmedia.dot.ca.gov/D12/SB5MagnoliaAveSO91.stream/playlist.m3u8"
    red, was = redact_url(url)
    assert was is False and red == url


def test_stable_id():
    a = stable_id("les", "http://example.com/a")
    b = stable_id("les", "http://example.com/a")
    c = stable_id("godeye-2026-05", "http://example.com/a")
    assert a == b and a != c and len(a) == 16


def test_profile_env_secret():
    os.environ["WFD_TEST_KEY_X"] = "abc"
    try:
        assert profile.secret("WFD_TEST_KEY_X") == "abc"
        st = profile.secret_status("WFD_TEST_KEY_X")
        assert st["set"] and st["source"] == "environment", st
    finally:
        del os.environ["WFD_TEST_KEY_X"]
    assert profile.secret_status("WFD_TEST_KEY_X")["set"] is False


def test_db_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = db.connect(pathlib.Path(td) / "t.db")
        db.init_db(conn)
        row = CameraRow(
            url="http://example.com/cam1", source_family="test",
            provenance="public_by_design", name="Example Cam",
            country="Testland", city="Testville", status="unknown",
        )
        assert db.upsert_many(conn, [row]) == 1
        # idempotent by camera_id — a second upsert must update, not duplicate
        row2 = CameraRow(
            url="http://example.com/cam1", source_family="test",
            provenance="public_by_design", name="Example Cam v2", city="Testville",
        )
        db.upsert_many(conn, [row2])
        c = db.counts(conn)
        assert c["total"] == 1, c
        got = db.search(conn, "Testville")
        assert len(got) == 1 and got[0]["name"] == "Example Cam v2", got
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

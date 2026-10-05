"""Viewer backend tests — plain runner. Run: py -3.11 tests/test_viewer.py

Starts a real wfd.viewer server on an ephemeral port (background thread)
against the REAL registry (data/worldfeed.db) and exercises the JSON API over
urllib. Test functions are named test_* so they also work under pytest.
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import sqlite3
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import db as dbmod
from wfd import profile, viewer

DB_PATH = dbmod.DEFAULT_DB
_state = {"server": None, "base": None}


# --- server lifecycle -------------------------------------------------------

def _base() -> str:
    """Lazily start the shared test server (ephemeral port, daemon thread)."""
    if _state["base"] is None:
        server = viewer.make_server(port=0, quiet=True)
        threading.Thread(target=server.serve_forever, name="wfd-viewer-test",
                         daemon=True).start()
        _state["server"] = server
        _state["base"] = f"http://127.0.0.1:{server.server_address[1]}"
        atexit.register(_shutdown)
    return _state["base"]


def _shutdown() -> None:
    server = _state.pop("server", None)
    if server is not None:
        server.shutdown()
        server.server_close()
        _state["base"] = None


# --- tiny HTTP helpers -------------------------------------------------------

def _get(path):
    """GET a JSON endpoint -> (status, content_type, payload); raises on 4xx/5xx."""
    with urllib.request.urlopen(_base() + path, timeout=30) as resp:
        return (resp.status, resp.headers.get("Content-Type", ""),
                json.loads(resp.read().decode("utf-8")))


def _get_http(path):
    """GET without raising on error statuses -> (status, content_type, body)."""
    try:
        with urllib.request.urlopen(_base() + path, timeout=30) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, ctype, exc.read()


def _db_rows(sql, args=()):
    conn = sqlite3.connect(f"file:{pathlib.Path(DB_PATH).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# --- tests -------------------------------------------------------------------

def test_stats_shape():
    status, ctype, data = _get("/api/stats")
    assert status == 200
    assert ctype.startswith("application/json"), ctype
    for key in ("total", "by_provenance", "by_status", "by_family",
                "exposure_enabled", "generated_at"):
        assert key in data, (key, sorted(data))
    assert isinstance(data["total"], int) and data["total"] > 0, data["total"]
    assert isinstance(data["by_provenance"], dict) and data["by_provenance"]
    assert isinstance(data["by_status"], dict) and data["by_status"]
    assert isinstance(data["by_family"], dict) and data["by_family"]
    assert isinstance(data["exposure_enabled"], bool)
    assert "T" in data["generated_at"], data["generated_at"]


def test_cameras_featurecollection():
    status, ctype, data = _get("/api/cameras?limit=5")
    assert status == 200 and ctype.startswith("application/json"), (status, ctype)
    assert data["type"] == "FeatureCollection"
    feats = data["features"]
    assert isinstance(feats, list) and len(feats) == 5, len(feats)
    for f in feats:
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Point"
        lon, lat = f["geometry"]["coordinates"]
        assert isinstance(lon, (int, float)) and isinstance(lat, (int, float)), (lon, lat)
        p = f["properties"]
        for key in ("camera_id", "name", "city", "country", "source_family", "provenance",
                    "status", "protocol", "last_verified", "snapshot_date", "tags",
                    "display_policy"):
            assert key in p, (key, sorted(p))
        assert isinstance(p["tags"], list)


def test_cameras_limit_default_and_cap():
    _, _, d = _get("/api/cameras")
    assert len(d["features"]) == 2000, len(d["features"])       # default limit
    _, _, d = _get("/api/cameras?limit=999999")
    assert len(d["features"]) == 5000, len(d["features"])       # max clamp


def test_bbox_narrows_results():
    _, _, all_fc = _get("/api/cameras?limit=5000")
    assert len(all_fc["features"]) == 5000, len(all_fc["features"])
    bbox = "150.9,-34.2,151.3,-33.8"                            # greater Sydney
    _, _, fc = _get(f"/api/cameras?bbox={bbox}&limit=5000")
    feats = fc["features"]
    assert 0 < len(feats) < len(all_fc["features"]), len(feats)
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        assert 150.9 <= lon <= 151.3 and -34.2 <= lat <= -33.8, (lon, lat)


def test_bbox_malformed_400():
    status, _, body = _get_http("/api/cameras?bbox=1,2,3")
    assert status == 400, status
    assert "bbox" in json.loads(body)


def test_known_nsw_live_row_with_url():
    row = _db_rows(
        "SELECT camera_id FROM cameras WHERE source_family='nsw' AND status='live' "
        "AND lat IS NOT NULL AND lon IS NOT NULL LIMIT 1"
    )
    assert row, "no live NSW row with coordinates in the registry"
    camera_id = row[0]["camera_id"]

    _, _, fc = _get("/api/cameras?family=nsw&status=live&limit=5000")
    matches = [f for f in fc["features"] if f["properties"]["camera_id"] == camera_id]
    assert matches, f"{camera_id} missing from /api/cameras?family=nsw&status=live"
    p = matches[0]["properties"]
    assert p["status"] == "live", p
    assert p["provenance"] == "public_by_design", p
    assert p["url"].startswith("http"), p          # public rows carry url
    assert p["display_policy"] == "full", p


def test_q_fts_resolves_via_db_search():
    conn = sqlite3.connect(f"file:{pathlib.Path(DB_PATH).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        hits = dbmod.search(conn, "Miranda", limit=10)
        assert hits, "FTS 'Miranda' found nothing in the registry"
        surface = bool(profile.settings().get("private_exposure_surface"))
        geo_sql = ("SELECT camera_id FROM cameras "
                   "WHERE lat IS NOT NULL AND lon IS NOT NULL"
                   + ("" if surface else " AND provenance != 'exposure_aggregator'"))
        geo = {r["camera_id"] for r in conn.execute(geo_sql)}
    finally:
        conn.close()
    expected = {h["camera_id"] for h in hits} & geo
    assert expected, "no FTS 'Miranda' hit is served (coordinates/exposure gate)"

    _, _, fc = _get("/api/cameras?q=Miranda")
    got = {f["properties"]["camera_id"] for f in fc["features"]}
    assert expected <= got, (expected - got)


def test_exposure_disabled_by_profile():
    n = _db_rows("SELECT COUNT(*) AS n FROM cameras "
                 "WHERE provenance='exposure_aggregator'")[0]["n"]
    assert n > 0, "no exposure rows in registry — gate test would be vacuous"

    old = os.environ.get("WFD_PROFILE")
    os.environ["WFD_PROFILE"] = "clean"
    try:
        _, _, st = _get("/api/stats")
        assert st["exposure_enabled"] is False
        _, _, fc = _get("/api/cameras?provenance=exposure&limit=100")
        assert fc["features"] == [], fc["features"][:2]
        _, _, fc_all = _get("/api/cameras?provenance=all&limit=5000")
        leaked = [f["properties"]["camera_id"] for f in fc_all["features"]
                  if f["properties"]["provenance"] == "exposure_aggregator"]
        assert not leaked, leaked[:5]
        # a hidden exposure row is indistinguishable from a missing one
        exp_id = _db_rows("SELECT camera_id FROM cameras "
                          "WHERE provenance='exposure_aggregator' LIMIT 1")[0]["camera_id"]
        status, _, _ = _get_http(f"/api/camera/{exp_id}")
        assert status == 404, status
    finally:
        if old is None:
            os.environ.pop("WFD_PROFILE", None)
        else:
            os.environ["WFD_PROFILE"] = old


def test_exposure_law_when_surface_on():
    original = profile.settings
    profile.settings = lambda: {**original(), "private_exposure_surface": True}
    try:
        _, _, fc = _get("/api/cameras?provenance=exposure&limit=5")
        feats = fc["features"]
        assert len(feats) == 5, len(feats)
        for f in feats:
            p = f["properties"]
            assert p["provenance"] == "exposure_aggregator", p
            assert p["display_policy"] == "metadata_only", p
            assert "url" not in p, p
            assert "Unsecured camera" in p["warning"], p
        camera_id = feats[0]["properties"]["camera_id"]
        _, _, detail = _get(f"/api/camera/{camera_id}")
        assert detail["camera_id"] == camera_id
        assert detail["display_policy"] == "metadata_only"
        assert "url" not in detail
        assert "Unsecured camera" in detail["warning"]
        assert detail["provenance"] == "exposure_aggregator"
        assert "meta" in detail
    finally:
        profile.settings = original


def test_camera_detail_shape_and_404():
    row = _db_rows(
        "SELECT camera_id FROM cameras WHERE source_family='nsw' AND status='live' "
        "AND lat IS NOT NULL LIMIT 1"
    )
    assert row
    camera_id = row[0]["camera_id"]

    status, ctype, d = _get(f"/api/camera/{camera_id}")
    assert status == 200 and ctype.startswith("application/json")
    assert d["camera_id"] == camera_id
    for key in ("url", "source_family", "provenance", "name", "country", "city", "lat",
                "lon", "protocol", "status", "snapshot_date", "fetch_date", "last_verified",
                "geo_confidence", "was_redacted", "credential_present", "attribution",
                "official_url", "tags", "meta", "display_policy"):
        assert key in d, (key, sorted(d))
    assert d["status"] == "live" and d["provenance"] == "public_by_design"
    assert d["url"].startswith("http")
    assert d["display_policy"] == "full"

    status, _, body = _get_http("/api/camera/doesnotexist0000")
    assert status == 404, status
    assert json.loads(body).get("error")


def test_static_serving_from_web_dir():
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        pathlib.Path(td, "index.html").write_text(
            "<html><body>viewer ui probe</body></html>", encoding="utf-8")
        server = viewer.make_server(port=0, web_dir=td, quiet=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/", timeout=20) as resp:
                body = resp.read().decode("utf-8")
                assert resp.status == 200
                assert resp.headers.get("Content-Type", "").startswith("text/html")
                assert "viewer ui probe" in body
            try:
                urllib.request.urlopen(base + "/not-there", timeout=20)
                raise AssertionError("expected 404 for a missing static file")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
        finally:
            server.shutdown()
            server.server_close()


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
    _shutdown()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

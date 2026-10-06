"""Government enumerator scaffold tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_gov.py    -> prints PASS lines; exit 0 = all good.

Uses only ``tests/fixtures/gov/*`` (trimmed real payloads, 2026-10-05). No
network: fixture parsers are exercised directly; the NSW auth paths are
simulated with in-process monkeypatching (always restored). Live runs are
done via ``py -3.11 -m wfd.ingest.gov <name>``, not from this file.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.base import IngestResult
from wfd.ingest.gov import ENUMERATORS, caltrans, deldot, nsw, qld
from wfd.ingest.gov.base import Enumerator, check_no_liveness, registry, run_one
from wfd.schema import CameraRow

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "gov"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- registry -----------------------------------------------------------------

def test_registry():
    assert set(ENUMERATORS) == {"caltrans", "deldot", "nsw", "qld"}, set(ENUMERATORS)
    assert set(registry()) == {"caltrans", "deldot", "nsw", "qld"}
    for name, enum in ENUMERATORS.items():
        assert isinstance(enum, Enumerator)
        assert enum.name == name
        assert enum.provenance == "public_by_design"
        assert enum.source_ref


# --- caltrans -----------------------------------------------------------------

def test_caltrans_fixture_parse():
    rows = caltrans.parse_district(load("caltrans-d12-sample.json"), district="D12")
    assert len(rows) == 20, len(rows)
    assert all(r.status == "unknown" for r in rows)
    assert all(r.provenance == "public_by_design" and r.source_family == "caltrans" for r in rows)

    hls = [r for r in rows if r.protocol == "hls"]
    jpeg = [r for r in rows if r.protocol == "jpeg"]
    assert len(hls) == 17 and len(jpeg) == 3, (len(hls), len(jpeg))

    r0 = rows[0]
    assert r0.name == "I-5 #1 (Orange)", r0.name
    assert r0.url == "https://wzmedia.dot.ca.gov/D12/SB5MagnoliaAveSO91.stream/playlist.m3u8"
    assert r0.meta["caltrans_in_service"] == "true"
    assert abs(r0.lat - 33.85629) < 1e-9 and abs(r0.lon - (-117.97886)) < 1e-9

    # rows without a stream use the still and are 'jpeg'
    for row in jpeg:
        assert row.meta["caltrans_streaming_video_url"] == ""
        assert row.url == row.meta["caltrans_current_image_url"]

    # agency inService=false is preserved in meta but status stays 'unknown'
    off = [r for r in rows if r.meta["caltrans_in_service"] == "false"]
    assert len(off) == 3, len(off)
    assert all(r.status == "unknown" for r in off)


def test_caltrans_row_without_url_skipped():
    payload = {"data": [{"cctv": {"index": "9", "location": {}, "imageData": {"static": {}}}}]}
    assert caltrans.parse_district(payload, district="D01") == []


# --- deldot -------------------------------------------------------------------

def test_deldot_fixture_parse():
    rows = deldot.parse_cameras(load("deldot-videocamera-sample.json"))
    assert len(rows) == 20, len(rows)
    assert all(r.protocol == "hls" for r in rows)
    assert all(r.status == "unknown" for r in rows)
    # https m3u8s variant preferred; every stored url matches the meta copy
    assert all(r.meta["deldot_url_key"] == "m3u8s" for r in rows)
    assert all(r.url == r.meta["deldot_urls"]["m3u8s"] for r in rows)

    r0 = rows[0]
    assert r0.name == "DE 1 @ MILFORD NECK ROAD (NORTH OFF)", r0.name
    assert r0.url == "https://video.deldot.gov:443/live/KCAM001.stream/playlist.m3u8"
    assert abs(r0.lat - 38.990931) < 1e-9 and abs(r0.lon - (-75.448625)) < 1e-9
    assert r0.meta["deldot_status"] in ("Active", "Unavailable")
    assert r0.meta["deldot_id"] == "KCAM001"


# --- nsw ----------------------------------------------------------------------

def test_nsw_fixture_parse():
    rows = nsw.parse_payload(load("nsw-cameras-sample.json"))
    assert len(rows) == 20, len(rows)
    assert all(r.protocol == "jpeg" and r.status == "unknown" and r.country == "AU" for r in rows)
    r0 = rows[0]
    assert r0.name == "5 Ways (Miranda)", r0.name
    assert r0.url == "https://webcams.transport.nsw.gov.au/livetraffic-webcams/cameras/5_ways_miranda.jpeg"
    assert abs(r0.lat - (-34.02977)) < 1e-9 and abs(r0.lon - 151.10533) < 1e-9
    assert r0.meta["nsw_region"] == "SYD_SOUTH"


def test_nsw_key_required_result():
    original_secret = nsw.profile.secret
    original_status = nsw.profile.secret_status
    nsw.profile.secret = lambda name: None
    nsw.profile.secret_status = lambda name: {"name": name, "set": False, "source": "none"}
    try:
        res = nsw.NswEnumerator().enumerate()
    finally:
        nsw.profile.secret = original_secret
        nsw.profile.secret_status = original_status
    assert res.stats["key_required"] is True
    assert res.rows == []
    assert res.stats["secret"]["set"] is False
    assert "KEY REQUIRED" in res.notes and "NSW" in res.notes, res.notes


def test_nsw_auth_header_variants():
    variants = nsw.auth_header_variants("TEST-TOKEN")
    assert variants[0] == ("Authorization: apikey", {"Authorization": "apikey TEST-TOKEN"})
    assert variants[1] == ("apikey (raw header)", {"apikey": "TEST-TOKEN"})


def _fake_env(get_impl, token="TEST-TOKEN"):
    """Build (patched, restore) closures for nsw.polite_get / nsw.profile.secret."""
    calls = []

    def fake_get(url, **kw):
        calls.append(kw.get("headers") or {})
        return get_impl(len(calls))

    orig_get, orig_secret = nsw.polite_get, nsw.profile.secret
    nsw.polite_get = fake_get
    nsw.profile.secret = lambda name: token if name == "NSW_API_KEY" else None
    return calls, orig_get, orig_secret


def test_nsw_header_fallback_on_401():
    fixture_bytes = (FIXTURES / "nsw-cameras-sample.json").read_bytes()

    def impl(call_no):
        if call_no == 1:
            raise urllib.error.HTTPError(nsw.URL, 401, "Unauthorized", None, None)
        return fixture_bytes

    calls, orig_get, orig_secret = _fake_env(impl)
    try:
        res = nsw.NswEnumerator().enumerate()
    finally:
        nsw.polite_get, nsw.profile.secret = orig_get, orig_secret

    assert calls[0] == {"Authorization": "apikey TEST-TOKEN"}, calls[0]
    assert calls[1] == {"apikey": "TEST-TOKEN"}, calls[1]
    assert res.stats["auth_header"] == "apikey (raw header)", res.stats.get("auth_header")
    assert len(res.rows) == 20
    assert res.stats["bytes"] == len(fixture_bytes)
    assert all(r.status == "unknown" for r in res.rows)


def test_nsw_first_header_success():
    fixture_bytes = (FIXTURES / "nsw-cameras-sample.json").read_bytes()
    calls, orig_get, orig_secret = _fake_env(lambda call_no: fixture_bytes)
    try:
        res = nsw.NswEnumerator().enumerate()
    finally:
        nsw.polite_get, nsw.profile.secret = orig_get, orig_secret

    assert len(calls) == 1 and calls[0] == {"Authorization": "apikey TEST-TOKEN"}
    assert res.stats["auth_header"] == "Authorization: apikey"
    assert len(res.rows) == 20


# --- qld ----------------------------------------------------------------------

def test_qld_fixture_parse():
    payload = load("qld-webcams-sample.json")
    rows = qld.parse_payload(payload)
    assert len(rows) == 20, len(rows)
    assert all(r.protocol == "jpeg" and r.status == "unknown" and r.country == "AU" for r in rows)
    assert all(r.provenance == "public_by_design" and r.source_family == "qld" for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)

    r0 = rows[0]
    assert r0.name == "Archerfield - Ipswich Motorway & Granard Rd - North", r0.name
    assert r0.url == "https://cameras.qldtraffic.qld.gov.au/Metropolitan/Archerfield_Ipswich_Mwy_sth.jpg"
    assert r0.city == "Archerfield"
    assert abs(r0.lat - (-27.5551796)) < 1e-9 and abs(r0.lon - 153.0086975) < 1e-9
    assert r0.meta["qld_id"] == "1"
    assert r0.meta["qld_district"] == "Metropolitan"
    assert r0.meta["qld_direction"] == "NorthEast"
    assert r0.meta["qld_postcode"] == "4108"
    assert r0.meta["qld_url"] == "https://api.qldtraffic.qld.gov.au/v1/webcams/1"
    assert r0.meta["qld_is_custom"] is False
    assert "qldtraffic" in r0.attribution.lower()
    assert "traffic" in r0.tags


def test_qld_row_without_image_skipped():
    payload = {"features": [{"type": "Feature", "properties": {"id": 99, "description": "x"}}]}
    assert qld.parse_payload(payload) == []


def test_qld_key_required_result():
    original_secret = qld.profile.secret
    original_status = qld.profile.secret_status
    qld.profile.secret = lambda name: None
    qld.profile.secret_status = lambda name: {"name": name, "set": False, "source": "none"}
    try:
        res = qld.QldEnumerator().enumerate()
    finally:
        qld.profile.secret = original_secret
        qld.profile.secret_status = original_status
    assert res.stats["key_required"] is True
    assert res.rows == []
    assert res.stats["secret"]["set"] is False
    assert "KEY REQUIRED" in res.notes and "QLD" in res.notes, res.notes


def test_qld_fetch_uses_url_key():
    fixture_bytes = (FIXTURES / "qld-webcams-sample.json").read_bytes()
    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        captured["headers"] = kw.get("headers")
        return fixture_bytes

    orig_get, orig_secret = qld.polite_get, qld.profile.secret
    qld.polite_get = fake_get
    qld.profile.secret = lambda name: "TEST-TOKEN" if name == "QLDTRAFFIC_API_KEY" else None
    try:
        res = qld.QldEnumerator().enumerate()
    finally:
        qld.polite_get, qld.profile.secret = orig_get, orig_secret

    # key travels in the URL per spec v1.10 — and a test-local token only
    assert captured["url"] == qld.URL + "?apikey=TEST-TOKEN"
    assert not captured["headers"] or "apikey" not in {
        k.lower() for k in captured["headers"]}
    assert len(res.rows) == 20
    assert res.stats["features"] == 20
    assert res.stats["bytes"] == len(fixture_bytes)
    assert res.stats["published"] == "2026-10-01T09:03:03.8196642+10:00"
    assert res.stats["by_district"]["Metropolitan"] == 2
    assert res.stats["by_district"]["South Coast"] == 8
    assert all(r.status == "unknown" for r in res.rows)


def test_qld_fetch_error_token_scrubbed():
    orig_get, orig_secret = qld.polite_get, qld.profile.secret

    def fake_get(url, **kw):
        raise OSError(f"connection reset for {url}")

    qld.polite_get = fake_get
    qld.profile.secret = lambda name: "TEST-TOKEN" if name == "QLDTRAFFIC_API_KEY" else None
    try:
        res = qld.QldEnumerator().enumerate()
    finally:
        qld.polite_get, qld.profile.secret = orig_get, orig_secret
    assert res.rows == []
    assert "TEST-TOKEN" not in res.notes, res.notes
    assert "<redacted>" in res.notes, res.notes


# --- runner + liveness guard --------------------------------------------------

def test_no_liveness_guard_and_run_one():
    # guard rejects a liveness claim
    bad = IngestResult(family="t")
    bad.add(CameraRow(url="http://example.com/x", source_family="t", status="live"))
    bad.finalize()
    try:
        check_no_liveness(bad)
        raised = False
    except ValueError:
        raised = True
    assert raised, "guard did not reject a non-unknown row"

    # run_one (save=False) finalizes a stub enumerator without network or writes
    class Stub(Enumerator):
        name = "stub"
        source_ref = "fixture://stub"

        def enumerate(self):
            res = IngestResult(family="stub", provenance="public_by_design", source_ref=self.source_ref)
            res.add(CameraRow(url="http://example.com/x", source_family="stub"))
            return res

    res = run_one(Stub(), save=False)
    assert res.stats["rows"] == 1
    assert res.rows[0].status == "unknown"
    assert res.rows[0].camera_id  # finalize filled the stable id


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

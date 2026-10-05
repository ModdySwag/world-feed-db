"""vailresorts-brownrice enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_vailresorts_brownrice.py
        -> prints PASS lines; exit 0 = all good.

The station map is a static module constant, so no scraped fixtures are
needed; a tiny synthetic JPEG payload exercises the verification path. All
network access is avoided by monkeypatching the module-level ``polite_get``
handle (always restored). Live runs are done via
``py -3.11 -m wfd.ingest.newsrc.vailresorts_brownrice``, not from this file.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import vailresorts_brownrice as vr
from wfd.schema import stable_id

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64           # synthetic JPEG-magic payload
NOT_JPEG = b"<html>nope</html>"

VAIL_IDS = ("vailch11", "vailch21", "vailch2", "vaileaglesnest", "vailsnowsummit")


@contextlib.contextmanager
def patched(fetch_impl, entries=None):
    """Monkeypatch vr.polite_get (and optionally vr.STATION_MAP); restore after.

    ``fetch_impl(url, call_no) -> bytes`` (or raises). Yields the recorded call list.
    """
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return fetch_impl(url, len(calls))

    orig_get = vr.polite_get
    orig_map = vr.STATION_MAP
    vr.polite_get = fake_get
    if entries is not None:
        vr.STATION_MAP = tuple(entries)
    try:
        yield calls
    finally:
        vr.polite_get = orig_get
        vr.STATION_MAP = orig_map


# --- station map --------------------------------------------------------------

def test_station_map_shape_and_titles():
    assert len(vr.STATION_MAP) == 13, len(vr.STATION_MAP)
    stations = [e["station"] for e in vr.STATION_MAP]
    assert len(set(stations)) == 13, stations

    whistler = [e for e in vr.STATION_MAP if e["property"] == "whistler-blackcomb"]
    vail = [e for e in vr.STATION_MAP if e["property"] == "vail"]
    assert len(whistler) == 8 and len(vail) == 5, (len(whistler), len(vail))
    assert all(e["country"] == "CA" and e["city"] == "Whistler" for e in whistler)
    assert all(e["country"] == "US" and e["city"] == "Vail" for e in vail)

    names = {e["station"]: e["name"] for e in vr.STATION_MAP}
    assert names["whistlerroundhouse"] == "Roundhouse Lodge, Whistler Mountain"
    assert names["whistlerpeak"] == "Whistler Peak"
    assert names["whistlerblackcomb"] == "Rendezvous Lodge, Blackcomb Mountain"
    assert names["Whistleraline"] == "BIKE PARK CAM, Whistler Mountain"
    assert names["whistlervillagefitz"] == "Whistler Village Cam"
    assert names["whistlervillage"] == "Blackcomb Base, Upper Village"
    assert names["whistlercreekside"] == "Creekside Camera"
    assert names["whistler7thheaven"] == "7TH HEAVEN, Blackcomb Mountain"
    for st in VAIL_IDS:                       # id-as-name for the untitled Vail five
        assert names[st] == st

    # map order: all 8 whistler entries precede the 5 vail entries
    assert stations == [e["station"] for e in vr.STATION_MAP if e["property"] == "whistler-blackcomb"] \
        + list(VAIL_IDS)


# --- enumeration --------------------------------------------------------------

def test_enumerate_rows_offline():
    with patched(lambda url, n: JPEG) as calls:
        res = vr.ENUMERATOR.enumerate()

    assert len(res.rows) == 13, len(res.rows)
    assert len(calls) == 13, calls                      # one verification fetch per station
    assert calls[0] == "https://player.brownrice.com/snapshot/whistlerroundhouse"
    assert calls[-1] == "https://player.brownrice.com/snapshot/vailsnowsummit"

    assert res.stats["stations"] == 13
    assert res.stats["stations_verified"] == 13
    assert res.stats["stations_failed"] == []
    assert res.stats["dupes_dropped"] == 0

    for row in res.rows:
        assert row.status == "unknown"                  # enumeration never claims liveness
        assert row.provenance == "public_by_design"
        assert row.source_family == "vailresorts-brownrice"
        assert row.protocol == "jpeg"
        assert row.lat is None and row.lon is None
        assert row.attribution == vr.ATTRIBUTION
        assert row.url == f"https://player.brownrice.com/snapshot/{row.meta['station']}"
        assert row.meta["vendor"] == "brownrice"
        assert row.meta["embed_url"] == f"https://player.brownrice.com/embed/{row.meta['station']}"
        assert row.meta["discovery"] == "browser-harvested 2026-10-05 (curl-bot-walled)"
        assert row.meta["property"] in ("whistler-blackcomb", "vail")
        assert row.was_redacted is False and row.credential_present is False
        assert row.camera_id and row.camera_id == stable_id("vailresorts-brownrice", row.url)

    assert len({r.camera_id for r in res.rows}) == 13
    w = [r for r in res.rows if r.meta["property"] == "whistler-blackcomb"]
    v = [r for r in res.rows if r.meta["property"] == "vail"]
    assert len(w) == 8 and len(v) == 5
    assert all(r.country == "CA" and r.city == "Whistler" for r in w)
    assert all(r.country == "US" and r.city == "Vail" for r in v)
    # station id case is preserved verbatim in url + meta
    mixed = next(r for r in res.rows if r.meta["station"] == "Whistleraline")
    assert mixed.url == "https://player.brownrice.com/snapshot/Whistleraline"

    assert "13/13" in res.notes and "verified as JPEG" in res.notes
    assert "Vail names = station ids" in res.notes


def test_verification_records():
    with patched(lambda url, n: JPEG):
        res = vr.ENUMERATOR.enumerate()

    verified = res.stats["verified"]
    assert len(verified) == 13
    assert [rec["station"] for rec in verified] == [e["station"] for e in vr.STATION_MAP]
    for rec in verified:
        assert {"station", "http", "content_type", "bytes", "ok"} <= set(rec), rec
        assert rec["http"] == 200 and rec["content_type"] == "image/jpeg"
        assert rec["bytes"] == len(JPEG) and rec["ok"] is True


def test_failed_verification_flagged_but_row_kept():
    def impl(url, n):
        if url.endswith("/snapshot/whistlervillage"):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return JPEG

    with patched(impl):
        res = vr.ENUMERATOR.enumerate()

    assert len(res.rows) == 13                          # failing station STAYS a row
    assert any(r.meta["station"] == "whistlervillage" for r in res.rows)
    assert res.stats["stations_verified"] == 12
    assert res.stats["stations_failed"] == ["whistlervillage"]
    rec = next(r for r in res.stats["verified"] if r["station"] == "whistlervillage")
    assert rec["http"] == 404 and rec["ok"] is False and rec["bytes"] == 0
    assert "whistlervillage" in res.notes and "12/13" in res.notes
    assert all(r.status == "unknown" for r in res.rows)  # flagging is not a liveness claim


def test_non_jpeg_body_flagged():
    def impl(url, n):
        return NOT_JPEG if url.endswith("whistlerpeak") else JPEG

    with patched(impl):
        res = vr.ENUMERATOR.enumerate()

    assert res.stats["stations_verified"] == 12
    assert res.stats["stations_failed"] == ["whistlerpeak"]
    rec = next(r for r in res.stats["verified"] if r["station"] == "whistlerpeak")
    assert rec["ok"] is False and rec["bytes"] == len(NOT_JPEG) and rec["content_type"] == ""


def test_limit_caps_stations():
    en = vr.VailResortsBrownriceEnumerator()
    en.limit = 3
    with patched(lambda url, n: JPEG) as calls:
        res = en.enumerate()

    assert len(res.rows) == 3 and len(calls) == 3
    assert res.stats["stations"] == 3 and res.stats["stations_verified"] == 3
    assert [r.meta["station"] for r in res.rows] == \
        ["whistlerroundhouse", "whistlerpeak", "whistlerblackcomb"]


def test_dedupe_dropped_by_url():
    entries = [
        {"station": "whistlerroundhouse", "name": "Dup A", "property": "whistler-blackcomb",
         "country": "CA", "city": "Whistler", "title_source": "test"},
        {"station": "whistlerroundhouse", "name": "Dup B", "property": "whistler-blackcomb",
         "country": "CA", "city": "Whistler", "title_source": "test"},
    ]
    with patched(lambda url, n: JPEG, entries=entries) as calls:
        res = vr.ENUMERATOR.enumerate()

    assert len(res.rows) == 1
    assert res.rows[0].name == "Dup A"                  # first row wins
    assert res.stats["dupes_dropped"] == 1
    assert res.stats["stations"] == 2 and res.stats["stations_verified"] == 1
    assert len(calls) == 1                              # dropped dupe is not re-verified


def test_redaction_routes_snapshot_and_embed():
    orig_snap, orig_embed = vr.SNAPSHOT_URL, vr.EMBED_URL
    vr.SNAPSHOT_URL = "https://user:pass@player.brownrice.com/snapshot/{station}?token=abc"
    vr.EMBED_URL = "https://player.brownrice.com/embed/{station}?key=sekrit"
    try:
        row = vr.row_from_station(vr.STATION_MAP[0])
    finally:
        vr.SNAPSHOT_URL, vr.EMBED_URL = orig_snap, orig_embed

    assert row.was_redacted is True and row.credential_present is True
    assert "user:pass@" not in row.url and "token=abc" not in row.url
    assert row.url.startswith("https://player.brownrice.com/snapshot/whistlerroundhouse")
    assert "key=sekrit" not in row.meta["embed_url"]
    assert row.meta["embed_url"].startswith("https://player.brownrice.com/embed/whistlerroundhouse")


# --- runner integration -------------------------------------------------------

def test_run_one_and_guard():
    with patched(lambda url, n: JPEG):
        res = nb.run_one(vr.ENUMERATOR, save=False)
    assert res.stats["rows"] == 13
    assert all(r.status == "unknown" for r in res.rows)
    assert res.rows[0].camera_id and res.rows[0].fetch_date
    nb.check_no_liveness(res)                           # guard accepts our rows

    # guard still rejects a liveness claim (contract check)
    from wfd.ingest.base import IngestResult
    from wfd.schema import CameraRow
    bad = IngestResult(family="t")
    bad.add(CameraRow(url="https://example.com/x", source_family="t", status="live"))
    bad.finalize()
    try:
        nb.check_no_liveness(bad)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_run_cli_smoke():
    out = io.StringIO()
    en = vr.VailResortsBrownriceEnumerator()
    with patched(lambda url, n: JPEG), contextlib.redirect_stdout(out):
        code = nb.run_cli(en, ["--no-save"])
    assert code == 0
    text = out.getvalue()
    assert "[vailresorts-brownrice]" in text, text
    assert "rows=13" in text, text
    assert "stations_verified: 13" in text, text
    assert "13/13 snapshots fetched politely" in text, text


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

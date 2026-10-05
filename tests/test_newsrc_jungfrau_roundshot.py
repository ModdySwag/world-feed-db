"""Jungfrau-roundshot enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_jungfrau_roundshot.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/jungfrau-roundshot/`` are trimmed REAL
payloads (cp-api webcam list + status batch, fetched 2026-10-06). No network:
the newsrc FetchCache + polite_get are monkeypatched in-process (always
restored) and everything is served from the fixtures; the one image the probe
fetches is a tiny synthetic JPEG. Live runs happen via
``py -3.11 -m wfd.ingest.newsrc.jungfrau_roundshot``, not from this file.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import jungfrau_roundshot as jr

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "jungfrau-roundshot"

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"\xff\xd9"      # tiny synthetic JPEG


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_ids():
    return [e["roundshot_id"] for e in load("cp-api-webcams.json")["data"]]


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, list_payload=None):
        self.cache_dir = cache_dir
        self.list_bytes = (list_payload if list_payload is not None
                           else (FIXTURES / "cp-api-webcams.json").read_bytes())
        self.status_full = load("status-batch.json")
        self.calls: list = []

    def fake_get(self, url, **kw):
        self.calls.append(url)
        if url == jr.LIST_URL:
            return self.list_bytes
        if url.startswith(jr.STATUS_BASE):
            ids = url.split("ids=", 1)[1].split(",")
            return json.dumps({k: self.status_full[k] for k in ids
                               if k in self.status_full}).encode()
        if url.startswith("https://backend.roundshot.com/cams/"):
            return FAKE_JPEG
        raise AssertionError(f"unexpected fetch: {url}")

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = jr.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        jr.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        jr.fetch_cache = self.orig_cache
        return False


def run_offline(list_payload=None, **attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, list_payload) as net:
        en = jr.JungfrauRoundshotEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


# --- module shape --------------------------------------------------------------

def test_module_shape():
    assert isinstance(jr.ENUMERATOR, nb.Enumerator)
    assert jr.ENUMERATOR.name == "jungfrau-roundshot"
    assert jr.ENUMERATOR.provenance == "public_by_design"
    assert jr.ENUMERATOR.source_ref == jr.LIST_URL == "https://www.jungfrau.ch/cp-api/webcams/?site=en"
    assert jr.ENUMERATOR.attribution == "Jungfrau Railways — jungfrau.ch live webcams"
    assert callable(jr.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(jr.__file__).read_text(encoding="utf-8")
    assert "import urllib" not in src and "urllib.request" not in src


def test_url_and_instance_helpers():
    assert jr.image_url("abc123") == "https://backend.roundshot.com/cams/abc123/full"
    assert jr.status_url(["a", "b"]) == "https://www.jungfrau.ch/api/live-data/webcams/status?ids=a,b"
    assert jr.player_url("some-slug") == "https://webcams.jungfrau.ch/some-slug"
    assert jr.instance_of("https://maennlichen.roundshot.com") == "maennlichen.roundshot.com"
    assert jr.instance_of("https://webcams.jungfrau.ch/eigergletscher/#/") == "webcams.jungfrau.ch/eigergletscher"
    assert jr.instance_of(None) == ""


# --- fixtures + parsers ---------------------------------------------------------

def test_fixture_payloads_parse():
    entries = jr.parse_webcams(load("cp-api-webcams.json"))
    assert len(entries) == 10, len(entries)
    ids = [e["roundshot_id"] for e in entries]
    status = jr.parse_status(load("status-batch.json"))
    assert set(status) == set(ids)                 # status keys ARE the roundshot md5s
    online = [k for k, v in status.items() if v["online"]]
    offline = [k for k, v in status.items() if not v["online"]]
    assert len(online) == 9 and len(offline) == 1, (len(online), len(offline))
    assert status[offline[0]]["reason"] == "stale"  # Jungfraujoch Ostgrat at check time

    # error-shaped payloads never masquerade as data
    assert jr.parse_status({"error": True}) == {}
    assert jr.parse_webcams([]) == []
    try:
        jr.parse_webcams({"error": True, "statusMessage": "Page not found"})
        raised = False
    except ValueError:
        raised = True
    assert raised, "error payload must raise, not yield zero rows silently"


def test_coordinates_parsing():
    assert jr.parse_coordinates("46.6093, 7.9389") == (46.6093, 7.9389)
    assert jr.parse_coordinates(None) == (None, None)
    assert jr.parse_coordinates("") == (None, None)
    assert jr.parse_coordinates("n/a") == (None, None)
    assert jr.parse_coordinates("95.0, 7.9") == (None, 7.9)          # lat out of range dropped
    assert jr.parse_coordinates("46.5, 200.0") == (46.5, None)       # lon out of range dropped
    assert jr.parse_coordinates([46.5, 7.9]) == (46.5, 7.9)          # defensive (unseen) forms
    assert jr.parse_coordinates({"lat": 46.5, "lon": 7.9}) == (46.5, 7.9)


# --- the full offline enumeration ----------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline()
    nb.check_no_liveness(res)                      # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 10, len(rows)
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "jungfrau-roundshot" for r in rows)
    assert all(r.provenance == "public_by_design" and r.country == "CH" for r in rows)
    assert all(r.protocol == "jpeg" for r in rows)
    assert all(r.url.startswith("https://backend.roundshot.com/cams/") and r.url.endswith("/full")
               for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)
    assert all(set(r.meta) == {"roundshot_id", "slug", "altitude_m", "instance",
                               "player_url", "coordinates_raw", "jungfrau_status"} for r in rows)

    by_id = {r.meta["roundshot_id"]: r for r in rows}
    maen = by_id["877919abdb23eb59f63908ab8b300f1f"]
    assert maen.name == "Männlichen", maen.name
    assert abs(maen.lat - 46.6093) < 1e-9 and abs(maen.lon - 7.9389) < 1e-9
    assert maen.meta["instance"] == "maennlichen.roundshot.com"
    assert maen.meta["altitude_m"] == 2222
    assert maen.meta["player_url"] == "https://webcams.jungfrau.ch/bergstation-maennlichen"
    assert maen.meta["coordinates_raw"] == "46.6093, 7.9389"
    assert maen.meta["jungfrau_status"]["online"] is True

    # null-coordinates entry: no lat/lon, raw None preserved, altitude + slug kept
    gwt = by_id["034de41e47b30dde0362b86b42d9fb61"]
    assert gwt.lat is None and gwt.lon is None and gwt.meta["coordinates_raw"] is None
    assert gwt.meta["altitude_m"] == 937 and gwt.meta["slug"] == "grindelwald-terminal"
    # instance strips the '#/' fragment seen in the cp-api value
    eiger = by_id["8ebf876ae226aa03b0c65b0985e6f60e"]
    assert eiger.meta["instance"] == "webcams.jungfrau.ch/top-of-europe-eiger-express"
    # null altitude preserved as None
    laub = by_id["527f953c3776c0552355d4a154c2b4e8"]
    assert laub.meta["altitude_m"] is None

    # published operator flags stay in meta and NEVER touch row.status
    ostgrat = by_id["dbb5da2713c66505f2004b60c6c56609"]
    assert ostgrat.name == "Jungfraujoch (Ostgrat)"
    assert ostgrat.meta["jungfrau_status"]["online"] is False
    assert ostgrat.meta["jungfrau_status"]["reason"] == "stale"
    assert ostgrat.status == "unknown"
    assert maen.status == "unknown"

    # stats contract
    st = res.stats
    assert st["cams"] == 10 and st["cams_listed"] == 10
    assert st["status_online"] == 9 and st["status_offline"] == 1
    assert st["dupes_dropped"] == 0 and st["skipped_no_roundshot_id"] == 0
    assert st["cache_misses"] == 3 and st["cache_hits"] == 0   # list + status + image
    assert "status_error" not in st


def test_verified_fetch_mechanism():
    res, net = run_offline()
    vf = res.stats["verified_fetch"]
    assert vf["cam"] == "bergstation-maennlichen"
    assert vf["url"] == res.rows[0].url
    assert vf["http"] == 200 and vf["final_host"] == "storage2.roundshot.com"
    assert vf["content_type"] == "image/jpeg"
    assert vf["bytes"] == len(FAKE_JPEG)
    assert vf["url"] in net.calls                        # the image endpoint really was fetched
    assert "jungfrau_status" in res.notes


def test_limit_caps_cams_and_status_ids():
    ids = fixture_ids()
    res, net = run_offline(limit=3)
    assert len(res.rows) == 3 and res.stats["cams"] == 3
    status_calls = [u for u in net.calls if u.startswith(jr.STATUS_BASE)]
    assert len(status_calls) == 1
    assert status_calls[0] == jr.status_url(ids[:3])     # status asked only for the capped cams
    img_calls = [u for u in net.calls if "backend.roundshot.com" in u]
    assert img_calls == [res.rows[0].url]                # exactly one image probe


def test_dedupe_by_url():
    ids = fixture_ids()
    payload = {"data": [
        {"slug": "a", "title": "A", "coordinates": "46.5, 7.9", "roundshot_id": ids[0],
         "roundshot_url": "", "altitude_m": 1},
        {"slug": "b", "title": "B", "coordinates": "46.6, 7.9", "roundshot_id": ids[0],
         "roundshot_url": "", "altitude_m": 2},
        {"slug": "c", "title": "C", "coordinates": "46.7, 7.9", "roundshot_id": ids[1],
         "roundshot_url": "", "altitude_m": 3},
    ]}
    res, _ = run_offline(list_payload=json.dumps(payload).encode())
    assert res.stats["cams"] == 2 and res.stats["dupes_dropped"] == 1
    assert len({r.url for r in res.rows}) == 2
    assert all(r.status == "unknown" for r in res.rows)


def test_entry_without_roundshot_id_skipped():
    payload = {"data": [
        {"slug": "x", "title": "X"},
        {"slug": "y", "title": "Y", "roundshot_id": fixture_ids()[0]},
    ]}
    res, _ = run_offline(list_payload=json.dumps(payload).encode())
    assert len(res.rows) == 1 and res.stats["skipped_no_roundshot_id"] == 1
    assert res.rows[0].meta["roundshot_id"] == fixture_ids()[0]


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = jr.JungfrauRoundshotEnumerator().enumerate()
            calls_after_first = len(net.calls)
            res2 = jr.JungfrauRoundshotEnumerator().enumerate()
    assert calls_after_first == 3                        # list + status + image
    assert len(net.calls) == calls_after_first           # second run: zero new fetches
    assert res1.stats["cache_misses"] == 3 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 3 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = nb.run_one(jr.JungfrauRoundshotEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-jungfrau-roundshot.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 10
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert res.stats["written"] == 10 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-jungfrau-roundshot.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = jr.run_cli(jr.JungfrauRoundshotEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[jungfrau-roundshot]" in out and "rows=10" in out, out


# --- runner ---------------------------------------------------------------------

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

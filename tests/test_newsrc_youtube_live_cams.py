"""Youtube-live-cams enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_youtube_live_cams.py   -> PASS lines; exit 0.

Fixture under ``tests/fixtures/newsrc/youtube-live-cams/`` is ONE real oEmbed
response map (trimmed to the used keys: title/author_name/author_url/type/
version/provider_name) fetched 2026-10-06 for every registry video id (plus the
two Camsecure-embed ids verified during the same build). No network:
``nb.polite_get`` and the newsrc ``fetch_cache`` are monkeypatched in-process
(always restored). Live runs happen via
``py -3.11 -m wfd.ingest.newsrc.youtube_live_cams``.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import youtube_live_cams as yt

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "youtube-live-cams"
OEMBED_RESPONSES = json.loads((FIXTURES / "oembed-responses.json").read_text(encoding="utf-8"))

STEAMBOAT_IDS = ["2UJDLWcSADk", "evs4diWVKiY", "fI30YzAmCHw", "KJka6pGArbc",
                 "lKc9xwndUK4", "PD9MoCKRwCA", "PinqovlSY-o", "qjAqCiwCW34", "VQ37fu8sd9M"]
SPI_IDS = ["kJ_EXhKsH30", "dzylsC0KcOE", "bvL_3W7F4Fk", "0FaRaPPTS8M"]
ALL_IDS = STEAMBOAT_IDS + SPI_IDS


def video_id_of_oembed_url(url: str) -> str:
    target = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["url"][0]
    return target.split("?v=", 1)[-1]


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, responses=None):
        self.cache_dir = cache_dir
        self.responses = dict(OEMBED_RESPONSES if responses is None else responses)
        self.calls: list = []
        self.hook = None

    def fake_get(self, url, **kw):
        self.calls.append({"url": url, "headers": dict(kw.get("headers") or {})})
        if self.hook is not None:
            self.hook(url)
        if url.startswith(yt.OEMBED_ENDPOINT + "?url="):
            vid = video_id_of_oembed_url(url)
            if vid in self.responses:
                return json.dumps(self.responses[vid]).encode("utf-8")
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        raise AssertionError(f"unexpected fetch (non-oembed): {url}")

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = yt.fetch_cache
        nb.polite_get = self.fake_get
        yt.fetch_cache = lambda family, refresh=False: nb.FetchCache(self.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        yt.fetch_cache = self.orig_cache
        return False


def run_offline(responses=None, **attrs):
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td, responses)
        with net:
            en = yt.YoutubeLiveCamsEnumerator()
            for k, v in attrs.items():
                setattr(en, k, v)
            res = en.enumerate()
    return res, net


# --- module shape + registry ----------------------------------------------------

def test_module_shape():
    assert isinstance(yt.ENUMERATOR, nb.Enumerator)
    assert yt.ENUMERATOR.name == "youtube-live-cams"
    assert yt.ENUMERATOR.provenance == "public_by_design"
    assert yt.ENUMERATOR.source_ref == yt.SOURCE_REF
    assert "SteamboatResort" in yt.ENUMERATOR.source_ref
    assert "visitsouthpadreisland.com" in yt.ENUMERATOR.source_ref
    assert yt.ENUMERATOR.attribution == "Steamboat Resort + South Padre Island CVB — YouTube live cams"
    assert callable(yt.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_request():
    src = pathlib.Path(yt.__file__).read_text(encoding="utf-8")
    assert "urllib.request" not in src and "urlopen" not in src
    assert "import requests" not in src


def test_sources_registry_invariants():
    assert [s["property"] for s in yt.SOURCES] == ["Steamboat Resort", "South Padre Island"]
    steam, spi = yt.SOURCES
    assert len(steam["entries"]) == 9 and len(spi["entries"]) == 4
    assert steam["channel"] == "@SteamboatResort"
    assert spi["channel"] == "@enjoyspi / @spadrevideo"
    assert steam["city"] == "Steamboat Springs" and spi["city"] == "South Padre Island"
    assert steam["country"] == spi["country"] == "US"
    assert steam["attribution"] == "Steamboat Resort (youtube.com/@SteamboatResort)"
    assert spi["attribution"] == "South Padre Island (youtube.com/@enjoyspi)"

    ids = [e["video_id"] for s in yt.SOURCES for e in s["entries"]]
    assert ids == ALL_IDS, ids
    assert len(ids) == len(set(ids)) == 13
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{11}", i) for i in ids)
    assert "iJlOcnEbWMY" not in ids          # excluded: not a resort cam (author Jeff Carlson)
    assert all(e["name"] for s in yt.SOURCES for e in s["entries"])
    # every registry id has a build-time oembed fixture response
    assert all(i in OEMBED_RESPONSES for i in ids)


def test_oembed_url_format():
    assert yt.oembed_url("abc123XYZ_-") == (
        "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc123XYZ_-&format=json")
    assert yt.watch_url("abc123XYZ_-") == "https://www.youtube.com/watch?v=abc123XYZ_-"


# --- row builder -----------------------------------------------------------------

def test_build_row_unit():
    src, ent = yt.SOURCES[0], yt.SOURCES[0]["entries"][0]
    row = yt.build_row(src, ent, oembed=(True, "Steamboat Resort", "Steamboat Square Cam", None))
    assert row.url == "https://www.youtube.com/watch?v=2UJDLWcSADk"
    assert row.source_family == "youtube-live-cams"
    assert row.provenance == "public_by_design" and row.status == "unknown"
    assert row.protocol == "youtube" and row.country == "US" and row.city == "Steamboat Springs"
    assert row.name == "Steamboat Square"
    assert row.attribution == "Steamboat Resort (youtube.com/@SteamboatResort)"
    assert not row.was_redacted and not row.credential_present
    assert set(row.meta) == {"property", "cam_name", "channel", "oembed_ok",
                             "oembed_author", "oembed_title"}
    assert row.meta["property"] == "Steamboat Resort"
    assert row.meta["cam_name"] == "Steamboat Square"
    assert row.meta["channel"] == "@SteamboatResort"
    assert row.meta["oembed_ok"] is True
    assert row.meta["oembed_author"] == "Steamboat Resort"
    assert row.meta["oembed_title"] == "Steamboat Square Cam"

    failed = yt.build_row(src, ent, oembed=(False, "", "", "HTTPError: 404: Not Found"))
    assert failed.status == "unknown"                    # a failed oembed never drops/upgrades a row
    assert failed.meta["oembed_ok"] is False
    assert failed.meta["oembed_error"] == "HTTPError: 404: Not Found"
    assert failed.meta["oembed_author"] == "" and failed.meta["oembed_title"] == ""

    spi = yt.build_row(yt.SOURCES[1], yt.SOURCES[1]["entries"][3],
                       oembed=(True, "South Padre Surf Company", "South Padre Surf Cam 4K", None))
    assert spi.city == "South Padre Island"
    assert spi.meta["oembed_author"] == "South Padre Surf Company"


# --- the full offline enumeration -----------------------------------------------

def test_offline_full_run():
    res, net = run_offline()
    nb.check_no_liveness(res)
    assert len(res.rows) == 13
    assert all(r.status == "unknown" for r in res.rows)
    assert all(r.protocol == "youtube" and r.country == "US" for r in res.rows)
    assert all(r.provenance == "public_by_design" for r in res.rows)
    assert all(r.meta["oembed_ok"] is True for r in res.rows)
    assert all(not r.was_redacted for r in res.rows)

    by_id = {r.url.split("=", 1)[-1]: r for r in res.rows}
    assert set(by_id) == set(ALL_IDS)
    first = by_id["2UJDLWcSADk"]
    assert first.name == "Steamboat Square" and first.city == "Steamboat Springs"
    assert first.meta["oembed_title"] == "Steamboat Square Cam"
    assert first.meta["oembed_author"] == "Steamboat Resort"
    assert first.meta["channel"] == "@SteamboatResort"
    # oembed author/title come straight from the fixture responses
    for vid, row in by_id.items():
        assert row.meta["oembed_title"] == OEMBED_RESPONSES[vid]["title"]
        assert row.meta["oembed_author"] == OEMBED_RESPONSES[vid]["author_name"]
    assert by_id["0FaRaPPTS8M"].meta["oembed_author"] == "South Padre Surf Company"
    assert "Isla Blanca" in by_id["0FaRaPPTS8M"].meta["oembed_title"]
    assert by_id["kJ_EXhKsH30"].meta["channel"] == "@enjoyspi / @spadrevideo"

    st = res.stats
    assert st["entries"] == 13 and st["entries_considered"] == 13
    assert st["rows"] == 13 and st["oembed_ok_count"] == 13
    assert st["dupes_dropped"] == 0
    assert st["cache_misses"] == 13 and st["cache_hits"] == 0
    assert st["by_status"] == {"unknown": 13}
    assert st["by_country"] == {"US": 13}
    assert "oembed_failed" not in st

    # exactly 13 fetches, all oEmbed, same host — no other network traffic
    assert len(net.calls) == 13
    assert all(c["url"].startswith(yt.OEMBED_ENDPOINT) for c in net.calls)


def test_oembed_failure_keeps_row_and_flags():
    responses = {k: v for k, v in OEMBED_RESPONSES.items() if k != "PinqovlSY-o"}
    res, net = run_offline(responses=responses)
    assert len(res.rows) == 13                          # row KEPT despite failed oembed
    bad = [r for r in res.rows if "PinqovlSY-o" in r.url]
    assert len(bad) == 1 and bad[0].status == "unknown"
    assert bad[0].meta["oembed_ok"] is False
    assert "404" in bad[0].meta["oembed_error"]
    assert bad[0].name == "Rendezvous"
    assert res.stats["oembed_ok_count"] == 12
    assert res.stats["oembed_failed"] == ["PinqovlSY-o"]


def test_limit_caps_entries():
    res, net = run_offline(limit=3)
    assert res.stats["entries"] == 13 and res.stats["entries_considered"] == 3
    assert res.stats["limit"] == 3
    assert [r.url.split("=", 1)[-1] for r in res.rows] == STEAMBOAT_IDS[:3]
    assert res.stats["cache_misses"] == 3
    assert all(r.status == "unknown" for r in res.rows)


def test_dupes_dropped():
    dup_source = {"property": "Dup", "channel": "@x", "attribution": "x (youtube.com/@x)",
                  "city": "Nowhere", "country": "US",
                  "entries": [{"video_id": "2UJDLWcSADk", "name": "Duplicate entry"}]}
    orig = yt.SOURCES
    yt.SOURCES = orig + [dup_source]
    try:
        res, net = run_offline()
    finally:
        yt.SOURCES = orig
    assert res.stats["dupes_dropped"] == 1
    assert len(res.rows) == 13                          # duplicate url never materializes
    assert res.stats["cache_misses"] == 13              # and is not oembed-fetched twice


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = yt.YoutubeLiveCamsEnumerator().enumerate()
            res2 = yt.YoutubeLiveCamsEnumerator().enumerate()
    assert len(net.calls) == 13
    assert res1.stats["cache_misses"] == 13 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 13 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_429_retry():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        state = {"fired": False}

        def hook(url):
            if not state["fired"]:
                state["fired"] = True
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)

        net.hook = hook
        orig_sleep, yt._sleep = yt._sleep, lambda s: None
        try:
            with net:
                res = yt.YoutubeLiveCamsEnumerator().enumerate()
        finally:
            yt._sleep = orig_sleep
    assert len(net.calls) == 14                         # first call retried once
    assert res.stats["rows"] == 13
    assert res.stats["oembed_ok_count"] == 13
    assert res.stats["cache_misses"] == 13              # 429 attempt is not a miss


# --- run_one / CLI --------------------------------------------------------------

def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        with net:
            res = nb.run_one(yt.YoutubeLiveCamsEnumerator(), save=True, out_dir=td)
        path = pathlib.Path(td) / "newsrc-youtube-live-cams.jsonl"
        assert path.exists(), list(pathlib.Path(td).iterdir())
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 13
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert all(l["protocol"] == "youtube" and l["country"] == "US" for l in lines)
    assert res.stats["written"] == 13 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-youtube-live-cams.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        with net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = yt.run_cli(yt.YoutubeLiveCamsEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[youtube-live-cams]" in out and "rows=13" in out, out


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

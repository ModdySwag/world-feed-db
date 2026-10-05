"""Camsecure-webcams enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_camsecure_webcams.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/camsecure-webcams/`` are trimmed REAL
payloads fetched 2026-10-06: the demo index (link-bearing markup verbatim), 3
cam pages (two with their player iframe — one absolute, one protocol-relative
``//`` form — and the Tennis Club page whose wrapper was removed), 2 wrapper
pages (HLS + YouTube ``<source>`` forms, both fetched with the anti-hotlink
Referer) and one real oEmbed response. No network: ``nb.polite_get`` and the
newsrc ``fetch_cache`` are monkeypatched in-process (always restored); the
offline full run uses a mini index assembled from verbatim fixture fragments.
Live runs happen via ``py -3.11 -m wfd.ingest.newsrc.camsecure_webcams``.
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import camsecure_webcams as cam

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "camsecure-webcams"

INDEX_TEXT = (FIXTURES / "index.html").read_text(encoding="utf-8")

BALLY_PAGE = "https://www.camsecure.co.uk/ballyholme_webcam.html"
IOW_PAGE = "https://www.camsecure.co.uk/isle_of_wight_steam_railway_webcam.html"
TENNIS_PAGE = "https://www.camsecure.co.uk/Camsecure3/Tennis_Club_Webcam_London.html"
BALLY_WRAPPER = "https://camsecure.uk/httpswebcam/camsecure/ballyholme.html"
IOW_WRAPPER = "https://camsecure.co/httpswebcam/camsecure/yt/iowsteam1.html"
IOW_WATCH = "https://www.youtube.com/watch?v=b7xdKcf6TRE"

# The 31 cam-page candidates extracted from the FULL live index (verified
# 2026-10-06: raw live index == trimmed fixture, order kept). 30 demo cams +
# the Tennis Club page (wrapper removed — it must enumerate to a skip).
EXPECTED_PAGES = [
    "https://www.camsecure.co.uk/oban%20bay%20webcam.html",
    "https://www.camsecure.co.uk/ullswater_lake_webcam.html",
    "https://www.camsecure.co.uk/arnside%20pier%20webcam.html",
    "https://www.camsecure.co.uk/WinkingMan.html",
    "https://www.camsecure.co.uk/llangrannog_beach_webcam.html",
    "https://www.camsecure.co.uk/felixstowe_beach_webcam.html",
    "https://www.camsecure.co.uk/whitstable-webcam.html",
    "https://www.camsecure.co.uk/kingston_upon_thames_webcam.html",
    "https://www.camsecure.co.uk/portishead_webcam.html",
    "https://www.camsecure.co.uk/Camsecure3/Brixham_Harbour.html",
    "https://www.camsecure.co.uk/StIves1.html",
    "https://www.camsecure.co.uk/Camsecure2/Weymouth_Seafront_Webcam.html",
    "https://www.camsecure.co.uk/ballyholme_webcam.html",
    "https://www.camsecure.co.uk/island_sailing_club.html",
    "https://www.camsecure.co.uk/Ruin_Beach_Cafe.html",
    "https://www.camsecure.co.uk/Christmas/FinlandChristmasWebcam.html",
    "https://www.camsecure.co.uk/bexhill_on_sea_webcam.html",
    "https://www.camsecure.co.uk/isle_of_man_webcam.html",
    "https://www.camsecure.co.uk/PSGC.html",
    "https://www.camsecure.co.uk/CoastwatchRedcarWebcam.html",
    "https://www.camsecure.co.uk/lee_on_the_solent_webcam.html",
    "https://www.camsecure.co.uk/BudeBeach.html",
    "https://www.camsecure.co.uk/Camsecure3/ilfra2.html",
    "https://www.camsecure.co.uk/FramptonLake.html",
    "https://www.camsecure.co.uk/Portmeirion.html",
    "https://www.camsecure.co.uk/Camsecure3/Tennis_Club_Webcam_London.html",
    "https://www.camsecure.co.uk/isle_of_wight_steam_railway_webcam.html",
    "https://www.camsecure.co.uk/SouthportPierWebcam.html",
    "https://www.camsecure.co.uk/whitby%20lifeboat%20webcam.html",
    "https://www.camsecure.co.uk/derwent_water_webcam.html",
    "https://www.camsecure.co.uk/Camsecure3/Dundee_Webcam.html",
]


def _el(pattern: str, text: str = INDEX_TEXT) -> str:
    m = re.search(pattern, text, re.S | re.I)
    assert m, f"fixture element not found: {pattern}"
    return m.group(0)


def build_mini_index() -> str:
    """Mini index assembled from VERBATIM fixture elements (offline full run).

    Candidates: ballyholme (map, deduped with its grid anchor), Isle of Wight
    Steam Railway (grid, YouTube) and Tennis Club (grid, wrapper removed).
    Also carries every exclusion form: nav ProductSupport, footer sitemap,
    christmas_tv (map), World_Webcam_Map + live.html (classed grid links) and
    one classless inline prose link (WebcamHosting).
    """
    bally_area = _el(r'<area[^>]*href="/ballyholme_webcam\.html"[^>]*>')
    xmas_area = _el(r'<area[^>]*href="/christmaschannel/christmas_tv\.html"[^>]*>')
    heading = _el(r'<p class="paragraph paragraph-28">.*?</p>')
    assert "popular webcam areas" in heading.lower()
    bally_a = _el(r'<a class="[^"]*link-text[^"]*"[^>]*href="/ballyholme_webcam\.html"[^>]*>.*?</a>')
    iow_a = _el(r'<a class="[^"]*link-text[^"]*"[^>]*href="/isle_of_wight_steam_railway_webcam\.html"[^>]*>.*?</a>')
    tennis_a = _el(r'<a class="[^"]*link-text[^"]*"[^>]*href="/Camsecure3/Tennis_Club_Webcam_London\.html"[^>]*>.*?</a>')
    live_a = _el(r'<a class="[^"]*link-text[^"]*"[^>]*href="/live\.html"[^>]*>.*?</a>')
    world_a = _el(r'<a class="[^"]*link-text[^"]*"[^>]*href="/World_Webcam_Map\.html"[^>]*>.*?</a>')
    prose = _el(r'<a title="Live Streaming Service" href="/WebcamHosting\.html">.*?</a>')
    nav_ps = _el(r'<a href="/ProductSupport\.html">.*?</a>')
    sitemap_a = _el(r'<a class="link-text text-link-1" href="/sitemap\.html">.*?</a>')
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Camsecure mini index (offline test)</title></head>
<body>
<nav>
{nav_ps}
</nav>
<map name="NotNamed">
{bally_area}
{xmas_area}
</map>
{heading}
{prose}
{bally_a}
{iow_a}
{tennis_a}
{live_a}
{world_a}
<div class="row Fixed-Width-Row-Bottom" id="Page-Bottom"><div class="Bottom-Text">
{sitemap_a}
</div></div>
</body>
</html>
"""


MINI_INDEX = build_mini_index()
MINI_CANDIDATES = [BALLY_PAGE, IOW_PAGE, TENNIS_PAGE]


def _bytes(name: str):
    def load():
        return (FIXTURES / name).read_bytes()
    return load


FIXTURE_SERVER = {
    BALLY_PAGE: _bytes("cam-page-ballyholme.html"),
    IOW_PAGE: _bytes("cam-page-iow-steam-railway.html"),
    TENNIS_PAGE: _bytes("cam-page-tennis-club-london.html"),
    BALLY_WRAPPER: _bytes("wrapper-ballyholme.html"),
    IOW_WRAPPER: _bytes("wrapper-iow-steam-railway.html"),
    cam.oembed_url("b7xdKcf6TRE"): _bytes("oembed-b7xdKcf6TRE.json"),
}


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, index_bytes=None):
        self.cache_dir = cache_dir
        self.index_bytes = index_bytes if index_bytes is not None else MINI_INDEX.encode("utf-8")
        self.calls: list = []
        self.overrides: dict = {}
        self.hook = None

    def fake_get(self, url, **kw):
        self.calls.append({"url": url, "headers": dict(kw.get("headers") or {})})
        if self.hook is not None:
            self.hook(url)
        if url in self.overrides:
            return self.overrides[url]
        if url == cam.INDEX_URL:
            return self.index_bytes
        if url in FIXTURE_SERVER:
            return FIXTURE_SERVER[url]()
        raise AssertionError(f"unexpected fetch: {url}")

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = cam.fetch_cache
        nb.polite_get = self.fake_get
        cam.fetch_cache = lambda family, refresh=False: nb.FetchCache(self.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        cam.fetch_cache = self.orig_cache
        return False


def run_offline(index_bytes=None, overrides=None, **attrs):
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td, index_bytes)
        if overrides:
            net.overrides = dict(overrides)
        with net:
            en = cam.CamsecureWebcamsEnumerator()
            for k, v in attrs.items():
                setattr(en, k, v)
            res = en.enumerate()
    return res, net


# --- module shape ---------------------------------------------------------------

def test_module_shape():
    assert isinstance(cam.ENUMERATOR, nb.Enumerator)
    assert cam.ENUMERATOR.name == "camsecure-webcams"
    assert cam.ENUMERATOR.provenance == "public_by_design"
    assert cam.ENUMERATOR.source_ref == cam.INDEX_URL
    assert cam.ENUMERATOR.source_ref == "https://www.camsecure.co.uk/Camsecure_Live_Demo_Index.html"
    assert cam.ENUMERATOR.attribution == "Camsecure (camsecure.co.uk) — live demo index"
    assert callable(cam.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_request():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(cam.__file__).read_text(encoding="utf-8")
    assert "urllib.request" not in src and "urlopen" not in src
    assert "import requests" not in src


# --- index parsing --------------------------------------------------------------

def test_parse_index_cam_pages_exact():
    pages = cam.parse_index_cam_pages(INDEX_TEXT)
    assert pages == EXPECTED_PAGES, [p for p in pages if p not in EXPECTED_PAGES]
    assert len(pages) == 31


def test_parse_index_excludes_non_cam_pages():
    low = [p.lower() for p in cam.parse_index_cam_pages(INDEX_TEXT)]
    for frag in ("christmas_tv", "world_webcam_map", "live.html",
                 "productsupport", "sitemap", "camsecureipnetworkwebcams"):
        assert not any(frag in p for p in low), frag


def test_parse_index_exclusion_hints_belt_and_braces():
    # classed links INSIDE the grid range are dropped by the explicit hint set
    snippet = """<html><body>
    <map name="NotNamed"><area href="/SomeCam.html" title="x"></map>
    <p>Some of our most popular webcam areas</p>
    <a class="link-text text-link-9" href="/sitemap.html">Site Map</a>
    <a class="link-text text-link-9" href="/ProductSupport.html">Support</a>
    <a class="link-text text-link-9" href="/CamsecureIPNetworkWebcams.html">IP</a>
    <a class="link-text text-link-9" href="/live.html">Live Channel</a>
    <a class="link-text text-link-9" href="/Camsecure3/Legit_Cam.html">Legit</a>
    <div id="Page-Bottom"><a class="link-text" href="/sitemap.html">after footer</a></div>
    </body></html>"""
    assert cam.parse_index_cam_pages(snippet) == [
        "https://www.camsecure.co.uk/SomeCam.html",
        "https://www.camsecure.co.uk/Camsecure3/Legit_Cam.html",
    ]
    assert cam.parse_index_cam_pages("") == []
    assert cam.parse_index_cam_pages("<html><body>no links</body></html>") == []


def test_mini_index_candidates():
    assert cam.parse_index_cam_pages(MINI_INDEX) == MINI_CANDIDATES


# --- wrapper discovery + media parsing ------------------------------------------

def test_find_wrapper_fixtures():
    bally = (FIXTURES / "cam-page-ballyholme.html").read_text(encoding="utf-8")
    assert cam.find_wrapper(bally) == ("https://camsecure.uk/httpswebcam/camsecure/ballyholme.html", "ballyholme")
    iow = (FIXTURES / "cam-page-iow-steam-railway.html").read_text(encoding="utf-8")
    assert cam.find_wrapper(iow) == ("//camsecure.co/httpswebcam/camsecure/yt/iowsteam1.html", "yt/iowsteam1")
    tennis = (FIXTURES / "cam-page-tennis-club-london.html").read_text(encoding="utf-8")
    assert cam.find_wrapper(tennis) == (None, None)          # wrapper removed


def test_find_wrapper_ignores_other_iframes():
    # facebook / google-maps iframes (and prose mentioning camsecure) never match
    assert cam.find_wrapper(
        '<iframe src="//www.facebook.com/plugins/like.php?href=http%3A%2F%2Fwww.camsecure.co.uk"></iframe>'
    ) == (None, None)
    assert cam.find_wrapper(
        '<iframe src="//camsecure.co/httpswebcam/camsecure/foo/bar.html" "mozallowfullscreen=true"></iframe>'
    ) == ("//camsecure.co/httpswebcam/camsecure/foo/bar.html", "foo/bar")
    assert cam.find_wrapper('<iframe src="https://camsecure.uk/httpswebcam/camsecure/x.html"></iframe>') \
        == ("https://camsecure.uk/httpswebcam/camsecure/x.html", "x")


def test_parse_wrapper_media_fixtures():
    bally = (FIXTURES / "wrapper-ballyholme.html").read_text(encoding="utf-8")
    raw, url, kind = cam.parse_wrapper_media(bally, BALLY_WRAPPER)
    assert (raw, url, kind) == ("/HLS/ballyholmecam.m3u8", "https://camsecure.uk/HLS/ballyholmecam.m3u8", "hls")
    iow = (FIXTURES / "wrapper-iow-steam-railway.html").read_text(encoding="utf-8")
    raw, url, kind = cam.parse_wrapper_media(iow, IOW_WRAPPER)
    assert (raw, url, kind) == ("https://www.youtube.com/embed/b7xdKcf6TRE", IOW_WATCH, "youtube")


def test_parse_wrapper_media_all_source_forms():
    # absolute src stays as-is (ilfracombe2 shape, observed live)
    raw, url, kind = cam.parse_wrapper_media(
        '<video><source src="https://camsecure.co/HLS/ilfracombe1camz.m3u8" type="application/x-mpegURL"></video>',
        "https://camsecure.co/httpswebcam/camsecure/ilfracombe2.html")
    assert (url, kind) == ("https://camsecure.co/HLS/ilfracombe1camz.m3u8", "hls") and raw.startswith("https://")
    # protocol-relative src (weymouth shape: //camsecure.co/HLS/bayvwebcam.m3u8)
    raw, url, kind = cam.parse_wrapper_media(
        '<source src="//camsecure.co/HLS/bayvwebcam.m3u8">', "https://camsecure.co/httpswebcam/camsecure/weymouth.html")
    assert (url, kind) == ("https://camsecure.co/HLS/bayvwebcam.m3u8", "hls")
    # no source -> nothing (e.g. placeholder page fetched without Referer)
    assert cam.parse_wrapper_media("<html>placeholder</html>", BALLY_WRAPPER) == (None, None, None)


def test_page_title_and_country_for():
    bally = (FIXTURES / "cam-page-ballyholme.html").read_text(encoding="utf-8")
    assert cam.page_title(bally) == "Ballyholme Live Webcam from Bangor"
    assert cam.page_title("") == ""
    assert cam.country_for("Christmas/levi1") == "FI"
    assert cam.country_for("ballyholme") == "GB"
    assert cam.country_for("yt/iowsteam1") == "GB"


# --- the full offline enumeration -----------------------------------------------

def test_offline_full_run():
    res, net = run_offline()
    nb.check_no_liveness(res)                       # raises if any row claims liveness
    assert [r.url for r in res.rows] == ["https://camsecure.uk/HLS/ballyholmecam.m3u8", IOW_WATCH]

    r0, r1 = res.rows
    assert r0.status == "unknown" and r1.status == "unknown"
    assert r0.source_family == "camsecure-webcams" and r1.source_family == "camsecure-webcams"
    assert r0.provenance == "public_by_design" and r1.provenance == "public_by_design"
    assert r0.protocol == "hls" and r1.protocol == "youtube"
    assert r0.country == "GB" and r1.country == "GB"
    assert not r0.was_redacted and not r0.credential_present

    assert r0.name == "Ballyholme Live Webcam from Bangor"
    assert set(r0.meta) == {"index_page", "wrapper_code", "cam_page", "media", "referer_note"}
    assert r0.meta["index_page"] == cam.INDEX_URL
    assert r0.meta["wrapper_code"] == "ballyholme"
    assert r0.meta["cam_page"] == BALLY_PAGE
    assert r0.meta["media"] == "/HLS/ballyholmecam.m3u8"
    assert "referer" in r0.meta["referer_note"].lower()

    assert r1.name == "Isle Of Wight Steam Railway Webcam"
    assert r1.meta["wrapper_code"] == "yt/iowsteam1"
    assert r1.meta["media"] == "https://www.youtube.com/embed/b7xdKcf6TRE"
    assert r1.meta["oembed_ok"] is True
    assert r1.meta["oembed_author"] == "Isle of Wight"
    assert "Havenstreet" in r1.meta["oembed_title"]
    assert "oembed_error" not in r1.meta

    st = res.stats
    assert st["pages_listed"] == 3 and st["pages_considered"] == 3
    assert st["rows"] == 2 and st["hls_rows"] == 1 and st["youtube_rows"] == 1
    assert st["yt_oembed_ok"] == 1
    assert st["skipped_no_wrapper"] == 1            # Tennis Club: wrapper removed
    assert st["skipped_no_media"] == 0
    assert st["dupes_dropped"] == 0 and st["fetch_failed"] == 0
    assert st["cache_misses"] == 7 and st["cache_hits"] == 0
    assert st["by_status"] == {"unknown": 2}
    assert st["by_country"] == {"GB": 2}

    # the wrapper fetch carried the correct same-site Referer (anti-hotlink)
    wrapper_calls = [c for c in net.calls if "httpswebcam" in c["url"]]
    assert [c["url"] for c in wrapper_calls] == [BALLY_WRAPPER, IOW_WRAPPER]
    assert wrapper_calls[0]["headers"].get("Referer") == BALLY_PAGE
    assert wrapper_calls[1]["headers"].get("Referer") == IOW_PAGE


def test_limit_caps_pages():
    res, net = run_offline(limit=1)
    assert res.stats["pages_listed"] == 3 and res.stats["pages_considered"] == 1
    assert res.stats["limit"] == 1
    assert len(res.rows) == 1 and res.rows[0].meta["wrapper_code"] == "ballyholme"
    assert res.stats["cache_misses"] == 3           # index + 1 cam page + 1 wrapper
    assert not any("iowsteam1" in c["url"] for c in net.calls)
    assert all(r.status == "unknown" for r in res.rows)


def test_dedupe_by_url():
    # make the Tennis Club page serve the IoW page -> duplicate YouTube url
    overrides = {TENNIS_PAGE: (FIXTURES / "cam-page-iow-steam-railway.html").read_bytes()}
    res, _ = run_offline(overrides=overrides)
    assert res.stats["dupes_dropped"] == 1
    assert res.stats["skipped_no_wrapper"] == 0
    assert [r.url for r in res.rows] == ["https://camsecure.uk/HLS/ballyholmecam.m3u8", IOW_WATCH]
    assert len({r.url for r in res.rows}) == 2


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = cam.CamsecureWebcamsEnumerator().enumerate()
            res2 = cam.CamsecureWebcamsEnumerator().enumerate()
    assert len(net.calls) == 7
    assert res1.stats["cache_misses"] == 7 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 7 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_429_retry():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        state = {"fired": False}

        def hook(url):
            if url == cam.INDEX_URL and not state["fired"]:
                state["fired"] = True
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)

        net.hook = hook
        orig_sleep, cam._sleep = cam._sleep, lambda s: None
        try:
            with net:
                res = cam.CamsecureWebcamsEnumerator().enumerate()
        finally:
            cam._sleep = orig_sleep
    index_calls = [c for c in net.calls if c["url"] == cam.INDEX_URL]
    assert len(index_calls) == 2                    # 429 then retry succeeded
    assert res.stats["rows"] == 2
    assert res.stats["cache_misses"] == 7           # the failed 429 attempt is not a miss


# --- run_one / CLI --------------------------------------------------------------

def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        with net:
            res = nb.run_one(cam.CamsecureWebcamsEnumerator(), save=True, out_dir=td)
        path = pathlib.Path(td) / "newsrc-camsecure-webcams.jsonl"
        assert path.exists(), list(pathlib.Path(td).iterdir())
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 2
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert lines[0]["protocol"] == "hls" and lines[1]["protocol"] == "youtube"
    assert res.stats["written"] == 2 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-camsecure-webcams.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        net = OfflineNet(td)
        with net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cam.run_cli(cam.CamsecureWebcamsEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[camsecure-webcams]" in out and "rows=2" in out, out


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

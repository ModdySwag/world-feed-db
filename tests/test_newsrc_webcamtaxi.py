"""WebcamTaxi (wfd.ingest.newsrc.webcamtaxi) tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_webcamtaxi.py    -> PASS/FAIL lines; exit 0 = all good.

Never touches the network or the real fetch cache: the only patches are
  * ``webcamtaxi.fetch_cache`` -> a real FetchCache rooted in a temp dir
  * ``wfd.ingest.newsrc.base.polite_get`` -> fixture-serving stub
(both always restored). Fixtures under ``tests/fixtures/newsrc/webcamtaxi/``
are trimmed REAL pages (verbatim windows) fetched 2026-10-06: three camera
detail pages (video-id embed / YouTube-channel embed / youtube-nocookie
channel embed) and a subset of the all-cams listing.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
import sys
import tempfile
import urllib.error
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest import newsrc
from wfd.ingest.newsrc import webcamtaxi as wt
from wfd.ingest.newsrc.base import Enumerator, FetchCache, check_no_liveness, run_one
from wfd.schema import CameraRow

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "webcamtaxi"

NUUK = "/en/denmark/greenland/nuuk-inner-port-cam.html"
BR101 = "/en/brazil/santa-catarina/br101km-210-north-south-cam.html"
GARDEN = "/en/italy/veneto/garden-paradiso-beach-cam.html"
BRIGHTON = "/en/england/west-sussex/brighton-city-airport-cam.html"
SUNNY = "/en/usa/florida/sunny-isles-beach-miami-cam.html"
SAMPLE_PATHS = [NUUK, BR101, GARDEN, BRIGHTON, SUNNY]
PAGE = wt.page_url

META_KEYS = {"wt_path", "wt_country_slug", "embed_url", "source", "tags",
             "page_url", "channel_id", "video_id"}

NO_EMBED_PAGE = (b"<html><head><title>Static No-Player Cam</title></head>"
                 b"<body><p>a still image only</p></body></html>")


def fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


LISTING_BYTES = fx("listing-sample.html")


def routes_main(url):
    """Fixture router: listing + the three detail fixtures; sunny -> no-embed stub;
    anything else (nuuk) -> HTTP 404."""
    if url == wt.LISTING_URL:
        return LISTING_BYTES
    if url == PAGE(BR101):
        return fx("detail-brazil-santa-catarina-br101km-210.html")
    if url == PAGE(GARDEN):
        return fx("detail-italy-veneto-garden-paradiso.html")
    if url == PAGE(BRIGHTON):
        return fx("detail-england-west-sussex-brighton-airport.html")
    if url == PAGE(SUNNY):
        return NO_EMBED_PAGE
    raise urllib.error.HTTPError(url, 404, "Not Found (offline test)", None, None)


class OfflineEnv:
    """Context manager: temp cache root + fixture-serving polite_get stub."""

    def __init__(self, cache_dir, routes):
        self.cache_dir = pathlib.Path(cache_dir)
        self.routes = routes
        self.calls = []            # list of (url, headers)

    def __enter__(self):
        self._orig_get = newsrc.base.polite_get
        self._orig_fc = wt.fetch_cache
        calls, routes = self.calls, self.routes

        def fake_get(url, **kw):
            calls.append((url, kw.get("headers")))
            out = routes(url) if callable(routes) else routes.get(url)
            if out is None:
                raise urllib.error.HTTPError(url, 404, "Not Found (offline test)", None, None)
            if isinstance(out, Exception):
                raise out
            return out

        newsrc.base.polite_get = fake_get
        wt.fetch_cache = lambda family, refresh=False: FetchCache(self.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        newsrc.base.polite_get = self._orig_get
        wt.fetch_cache = self._orig_fc
        return False


def quiet(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


# --- module shape ---------------------------------------------------------------

def test_module_contract():
    e = wt.ENUMERATOR
    assert isinstance(e, Enumerator)
    assert e.name == "webcamtaxi"
    assert e.provenance == "aggregator_directory"
    assert e.source_ref == wt.LISTING_URL
    assert e.attribution == "WebcamTaxi (webcamtaxi.com) — third-party directory of public webcams"
    assert e.limit is None and e.refresh is False
    assert wt.BROWSER_HEADERS["User-Agent"] == (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


# --- extract_cam_paths ----------------------------------------------------------

def test_extract_cam_paths_fixture():
    paths = wt.extract_cam_paths(LISTING_BYTES.decode("utf-8"))
    # order preserved; region/country/tag/self links excluded; second
    # sunny-isles anchor collapsed as a duplicate
    assert paths == SAMPLE_PATHS, paths


def test_extract_cam_paths_edge_cases():
    html = (
        '<a href=/en/usa/new-york/9-11-memorial-museum-cam.html>x</a>'      # digit-leading slug
        '<a href=/en/usa/florida/cam.html?from=list>y</a>'                  # query stripped
        '<a href="https://www.webcamtaxi.com/en/japan/tokyo/abs-form.html">z</a>'  # absolute form
        '<a href=/en/component/tags/tag/63.html>tag</a>'                    # robots-disallowed
        '<a href=/en/usa/florida.html>region</a>'                           # 2-level
        '<a href=/en/usa/alabama.html>country-region</a>'
        '<a href=/en/webcams.html>self</a>'
        '<a href=/en/usa/florida/d/deeper.html>too deep</a>'                # 4-level
        '<a href=/en/usa/florida/UPPER-cam.html>case</a>'                   # non-lowercase
        '<a href=/en/usa/new-york/9-11-memorial-museum-cam.html>dup</a>'    # duplicate
    )
    got = wt.extract_cam_paths(html)
    assert got == [
        "/en/usa/new-york/9-11-memorial-museum-cam.html",
        "/en/usa/florida/cam.html",
        "/en/japan/tokyo/abs-form.html",
    ], got
    assert wt.extract_cam_paths("") == []
    assert wt.extract_cam_paths(None) == []
    assert wt.extract_cam_paths("<html>no links at all</html>") == []


# --- parse_detail (fixture pages, verbatim) -------------------------------------

def test_parse_detail_brazil_video_embed():
    parsed = wt.parse_detail(fx("detail-brazil-santa-catarina-br101km-210.html").decode("utf-8"), BR101)
    assert parsed["embed_kind"] == "video"
    assert parsed["video_id"] == "iG7le_TWCng" and parsed["channel_id"] == ""
    assert parsed["embed_url"] == "https://www.youtube.com/embed/iG7le_TWCng?autoplay=1&mute=1&rel=0"
    assert parsed["source"] == "https://aemflo-cdlsj.org.br/"
    assert parsed["tags"] == ["Traffic", "Landscape"]
    assert parsed["title"] == "Live BR-101 Traffic Webcam São José and Palhoça, SC, Brazil"


def test_parse_detail_italy_channel_embed():
    parsed = wt.parse_detail(fx("detail-italy-veneto-garden-paradiso.html").decode("utf-8"), GARDEN)
    assert parsed["embed_kind"] == "channel"
    assert parsed["channel_id"] == "UC0_Od4u2SnHO_TIUxU_5ULQ" and parsed["video_id"] == ""
    assert parsed["embed_url"] == (
        "https://www.youtube.com/embed/live_stream?channel=UC0_Od4u2SnHO_TIUxU_5ULQ&autoplay=1&mute=1&rel=0")
    assert parsed["source"] == "https://www.gardenparadiso.it"
    assert parsed["tags"] == ["Sea", "Beach"]
    assert parsed["title"] == "Camping Village Garden Paradiso Beach Webcam, Veneto, Italy"


def test_parse_detail_england_nocookie_channel_embed():
    parsed = wt.parse_detail(fx("detail-england-west-sussex-brighton-airport.html").decode("utf-8"), BRIGHTON)
    assert parsed["embed_kind"] == "channel"
    assert parsed["channel_id"] == "UCcjlnrL3_LV4fC9CcrHth7w"
    assert parsed["embed_url"].startswith("https://www.youtube-nocookie.com/embed/live_stream?channel=")
    assert parsed["source"] == ""                       # no Source div on this page
    assert parsed["tags"] == ["Airport", "United Kingdom"]
    assert parsed["title"] == "Live Brighton City Airport Webcam West Sussex, England"


# --- embed/source/tags edge cases (synthetic) -----------------------------------

def test_embed_extraction_variants():
    # channel wins even when an earlier iframe carries a plain video id
    html = ('<iframe src="https://www.youtube.com/embed/AAAAAAAAAAA?x=1"></iframe>'
            '<iframe src="https://www.youtube.com/embed/live_stream?channel=UCzzz_9"></iframe>')
    parsed = wt.parse_detail(html)
    assert parsed["embed_kind"] == "channel" and parsed["channel_id"] == "UCzzz_9"

    # no iframe: watch URL found in the page body
    parsed = wt.parse_detail('<a href="https://www.youtube.com/watch?v=AbCdEfGhIjK&t=1">go</a>')
    assert parsed["embed_kind"] == "video" and parsed["video_id"] == "AbCdEfGhIjK"

    # youtu.be short form
    parsed = wt.parse_detail("see https://youtu.be/AbCdEfGhIjK now")
    assert parsed["video_id"] == "AbCdEfGhIjK"

    # live_stream WITHOUT a channel id must never yield 'live_stream' as a video id
    assert wt.parse_detail('<iframe src="https://www.youtube.com/embed/live_stream?foo=1"></iframe>') is None

    # google-maps iframe alone is not an embed
    assert wt.parse_detail('<iframe id=mapa src="https://www.google.com/maps/embed?pb=x"></iframe>') is None
    assert wt.parse_detail("<html><head><title>t</title></head><body>none</body></html>") is None


def test_source_and_tags_edges():
    html = ('<iframe src="https://www.youtube.com/embed/AbCdEfGhIjK?autoplay=1"></iframe>'
            '<div>Source: <a href="https://op.example.com/">op</a></div>')
    assert wt.parse_detail(html)["source"] == "https://op.example.com/"
    html = ('<iframe src="https://www.youtube.com/embed/AbCdEfGhIjK"></iframe>'
            '<div>Source: https://plain.example.net/path</div>')
    assert wt.parse_detail(html)["source"] == "https://plain.example.net/path"
    # tags: entities decoded, duplicates collapsed, order kept
    html = ('<iframe src="https://www.youtube.com/embed/AbCdEfGhIjK"></iframe>'
            '<ul class="tags inline"> <li><a href=/en/sea.html>Sea</a></li>'
            '<li><a href=/en/sea.html>Sea</a></li>'
            '<li><a href=/en/x.html>Hotels &amp; Resorts</a></li> </ul>')
    assert wt.parse_detail(html)["tags"] == ["Sea", "Hotels & Resorts"]


def test_title_fallbacks():
    # <title> wins; otherwise h1 (tags stripped); otherwise the path slug
    base = '<iframe src="https://www.youtube.com/embed/AbCdEfGhIjK"></iframe>'
    assert wt.parse_detail("<title>  One   Two </title>" + base)["title"] == "One Two"
    assert wt.parse_detail("<h1>My <strong>Cam</strong></h1>" + base)["title"] == "My Cam"
    assert wt.parse_detail(base, "/en/usa/texas/my-cool-cam.html")["title"] == "my cool cam"


# --- row_from_page ---------------------------------------------------------------

def test_row_mapping_brazil_video():
    row = wt.row_from_page(BR101, fx("detail-brazil-santa-catarina-br101km-210.html").decode("utf-8"))
    assert isinstance(row, CameraRow)
    assert row.url == "https://www.youtube.com/watch?v=iG7le_TWCng"
    assert row.protocol == "youtube" and row.status == "unknown"
    assert row.source_family == "webcamtaxi"
    assert row.provenance == "aggregator_directory"
    assert row.country == "BR" and row.lat is None and row.lon is None
    assert row.tags == ["Traffic", "Landscape"]
    assert row.attribution == wt.ATTRIBUTION
    assert row.was_redacted is False and row.credential_present is False
    assert len(row.snapshot_date) == 10
    m = row.meta
    assert set(m) == META_KEYS
    assert m["wt_path"] == BR101 and m["wt_country_slug"] == "brazil"
    assert m["video_id"] == "iG7le_TWCng" and m["channel_id"] == ""
    assert m["source"] == "https://aemflo-cdlsj.org.br/"
    assert m["tags"] == ["Traffic", "Landscape"]
    assert m["page_url"] == "https://www.webcamtaxi.com" + BR101


def test_row_mapping_italy_channel():
    row = wt.row_from_page(GARDEN, fx("detail-italy-veneto-garden-paradiso.html").decode("utf-8"))
    assert row.url == "https://www.youtube.com/channel/UC0_Od4u2SnHO_TIUxU_5ULQ/live"
    assert row.protocol == "youtube" and row.status == "unknown"
    assert row.country == "IT"
    assert row.meta["channel_id"] == "UC0_Od4u2SnHO_TIUxU_5ULQ"
    assert row.meta["video_id"] == ""
    assert row.meta["page_url"] == "https://www.webcamtaxi.com" + GARDEN


def test_row_mapping_england():
    row = wt.row_from_page(BRIGHTON, fx("detail-england-west-sussex-brighton-airport.html").decode("utf-8"))
    assert row.url == "https://www.youtube.com/channel/UCcjlnrL3_LV4fC9CcrHth7w/live"
    assert row.country == "GB"                       # 'england' -> GB
    assert row.meta["source"] == ""


def test_country_mapping():
    assert wt.country_for_slug("usa") == "US"
    assert wt.country_for_slug("england") == "GB"
    assert wt.country_for_slug("scotland") == "GB"
    assert wt.country_for_slug("wales") == "GB"
    assert wt.country_for_slug("south-korea") == "KR"
    assert wt.country_for_slug("czech-republic") == "CZ"
    assert wt.country_for_slug("curacao") == "CW"
    # deliberately unmapped (mixed/ambiguous): island split saint-martin,
    # and virgin-islands (mixes USVI regions with BVI Tortola/Jost Van Dyke)
    assert wt.country_for_slug("saint-martin") == ""
    assert wt.country_for_slug("virgin-islands") == ""
    assert wt.country_for_slug("atlantis") == ""
    assert wt.country_for_slug(None) == ""
    # every mapped value is a plausible ISO-3166-1 alpha-2 code
    for slug, code in wt.COUNTRY_BY_SLUG.items():
        assert re.fullmatch(r"[A-Z]{2}", code), (slug, code)


def test_row_redacts_urls():
    html = ('<iframe src="https://www.youtube.com/embed/AbCdEfGhIjK?token=SYNTH-SECRET&autoplay=1"></iframe>'
            '<div>Source: https://op.example.com/feed?apikey=SYNTH-SECRET2</div>')
    row = wt.row_from_page("/en/usa/texas/redact-me.html", html)
    assert row is not None
    assert row.url == "https://www.youtube.com/watch?v=AbCdEfGhIjK"
    assert row.was_redacted is True and row.credential_present is True
    blob = json.dumps(row.as_dict(), ensure_ascii=False)
    assert "SYNTH-SECRET" not in blob and "<redacted>" in blob


def test_row_unmapped_country_stays_blank():
    row = wt.row_from_page(
        "/en/saint-martin/sint-maarten/sxm-airport-livecam.html",
        '<iframe src="https://www.youtube.com/embed/2IQmpCXbOmM?autoplay=1"></iframe>')
    assert row is not None and row.country == ""
    assert row.meta["wt_country_slug"] == "saint-martin"


# --- enumerate() flow tests (offline, fake network) ------------------------------

def test_enumerate_offline_full_and_resume():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main) as env:
        out_dir = pathlib.Path(td) / "out"
        res = quiet(run_one, wt.WebcamTaxiEnumerator(), save=True, out_dir=out_dir)

        assert res.stats["pages_total"] == 5
        assert res.stats["pages_considered"] == 5
        assert res.stats["rows"] == 3, res.stats
        assert res.stats["no_embed_skipped"] == 1          # sunny (stub page, no player)
        assert res.stats["dupes_dropped"] == 0
        assert res.stats["pages_failed"] == 1              # nuuk (404)
        assert res.stats["pages_in_cache"] == 4 and res.stats["pages_in_cache_start"] == 0
        assert res.stats["pages_uncached_start"] == 5
        assert res.stats["pages_parsed"] == 4
        assert res.stats["cache_misses"] == 5 and res.stats["cache_hits"] == 0
        assert res.stats["channel_rows"] == 2 and res.stats["video_rows"] == 1
        assert "unmapped_country_slugs" not in res.stats
        check_no_liveness(res)                             # guard: all rows 'unknown'
        assert all(r.status == "unknown" for r in res.rows)
        assert all(len(r.camera_id) == 16 for r in res.rows)
        assert res.stats["by_country"] == {"BR": 1, "IT": 1, "GB": 1}
        assert res.stats["by_status"] == {"unknown": 3}
        assert [r.meta["wt_path"] for r in res.rows] == [BR101, GARDEN, BRIGHTON]

        # exact request order of the happy path + browser UA on every fetch
        assert [u for u, _ in env.calls] == [
            wt.LISTING_URL, PAGE(NUUK), PAGE(BR101), PAGE(GARDEN), PAGE(BRIGHTON), PAGE(SUNNY),
        ]
        assert all(h.get("User-Agent", "").startswith("Mozilla/5.0") for _, h in env.calls)

        # output jsonl + sha256
        out_file = out_dir / "newsrc-webcamtaxi.jsonl"
        assert out_file.exists()
        lines = out_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        digest = hashlib.sha256(out_file.read_bytes()).hexdigest()
        assert res.stats["sha256"] == digest
        for line in lines:
            d = json.loads(line)
            assert d["status"] == "unknown" and d["provenance"] == "aggregator_directory"
            assert d["source_family"] == "webcamtaxi" and len(d["camera_id"]) == 16
            assert d["protocol"] == "youtube"

        # ---- resume: second run answers everything from cache -------------------
        calls_before = len(env.calls)
        res2 = quiet(run_one, wt.WebcamTaxiEnumerator(), save=False)
        new_calls = [u for u, _ in env.calls[calls_before:]]
        assert new_calls == [PAGE(NUUK)], new_calls       # retry only the 404
        assert res2.stats["cache_hits"] == 5 and res2.stats["cache_misses"] == 0
        assert res2.stats["pages_in_cache_start"] == 4
        assert res2.stats["rows"] == 3


def test_enumerate_limit_caps_pages():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main) as env:
        enum = wt.WebcamTaxiEnumerator()
        enum.limit = 2
        res = quiet(run_one, enum, save=False)
        assert [u for u, _ in env.calls] == [wt.LISTING_URL, PAGE(NUUK), PAGE(BR101)]
        assert res.stats["limit"] == 2
        assert res.stats["pages_total"] == 5
        assert res.stats["pages_considered"] == 2
        assert res.stats["rows"] == 1 and res.stats["pages_failed"] == 1


def test_enumerate_dedupe_by_url():
    listing = (b'<html><body>'
               b'<a href=/en/usa/texas/dup-one.html class=x>a</a>'
               b'<a href=/en/usa/texas/dup-two.html class=x>b</a>'
               b'</body></html>')
    routes = {wt.LISTING_URL: listing,
              PAGE("/en/usa/texas/dup-one.html"): fx("detail-brazil-santa-catarina-br101km-210.html"),
              PAGE("/en/usa/texas/dup-two.html"): fx("detail-brazil-santa-catarina-br101km-210.html")}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        res = quiet(run_one, wt.WebcamTaxiEnumerator(), save=False)
        assert res.stats["rows"] == 1, res.stats
        assert res.stats["dupes_dropped"] == 1
        assert res.stats["no_embed_skipped"] == 0
        assert res.rows[0].meta["wt_path"] == "/en/usa/texas/dup-one.html"


def test_enumerate_page_without_embed():
    listing = b'<html><body><a href=/en/usa/texas/no-player-cam.html>x</a></body></html>'
    routes = {wt.LISTING_URL: listing,
              PAGE("/en/usa/texas/no-player-cam.html"): NO_EMBED_PAGE}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        res = quiet(run_one, wt.WebcamTaxiEnumerator(), save=False)
        assert res.stats["rows"] == 0
        assert res.stats["no_embed_skipped"] == 1 and res.stats["pages_parsed"] == 1


def test_run_cli_limit_smoke():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main):
        out_dir = pathlib.Path(td) / "cli-out"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wt.run_cli(wt.WebcamTaxiEnumerator(), ["--limit", "2", "--out", str(out_dir)])
        assert rc == 0, buf.getvalue()
        text = buf.getvalue()
        assert "[webcamtaxi] rows=1" in text, text
        assert "sha256" in text and "pages_failed: 1" in text, text
        assert (out_dir / "newsrc-webcamtaxi.jsonl").exists()


def test_empty_listing_errors_cleanly():
    routes = {wt.LISTING_URL: b"<html><head><title>x</title></head><body>no cams</body></html>"}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        enum = wt.WebcamTaxiEnumerator()
        try:
            quiet(enum.enumerate)
            raised = False
        except RuntimeError as exc:
            raised = "0 camera paths" in str(exc)
        assert raised, "empty listing should raise RuntimeError"


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

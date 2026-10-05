"""OpenWebcamDB (wfd.ingest.newsrc.openwebcamdb) tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_openwebcamdb.py    -> PASS/FAIL lines; exit 0 = all good.

Never touches the network or the real fetch cache: the only patches are
  * ``openwebcamdb.fetch_cache`` -> a real FetchCache rooted in a temp dir
  * ``wfd.ingest.newsrc.base.polite_get`` -> fixture-serving stub
(both always restored). Fixtures under ``tests/fixtures/newsrc/openwebcamdb/``
are trimmed REAL pages (JSON-LD blocks verbatim) fetched 2026-10-06.
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
from wfd.ingest.newsrc import openwebcamdb
from wfd.ingest.newsrc.base import Enumerator, FetchCache, check_no_liveness, run_one
from wfd.schema import CameraRow

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "openwebcamdb"

SLUG_FIXTURES = {
    "peregrine-falcon-nest-at-csu-australia": "detail-peregrine-falcon-nest-at-csu-australia.html",
    "melbourne-skyline-urban-vista": "detail-melbourne-skyline-urban-vista.html",
    "anglesea-golf-course-seaside-panorama": "detail-anglesea-golf-course-seaside-panorama.html",
    "kiten-atliman-beach-panorama": "detail-kiten-atliman-beach-panorama.html",
    "lamai-beach-views-from-baobab-spot": "detail-lamai-beach-views-from-baobab-spot.html",
}
SAMPLE_SLUGS = ["peregrine-falcon-nest-at-csu-australia",
                "newcastle-harbor-cargo-ships-view",
                "melbourne-skyline-urban-vista",
                "anglesea-golf-course-seaside-panorama",
                "lamai-beach-views-from-baobab-spot",
                "kiten-atliman-beach-panorama"]
PAGE = openwebcamdb.page_url


def fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


SITEMAP_BYTES = fx("sitemap-sample.xml")


def routes_main(url):
    """Fixture router: sitemap + saved pages; everything else -> HTTP 404."""
    if url == openwebcamdb.SITEMAP_URL:
        return SITEMAP_BYTES
    m = re.search(r"/webcams/([^/?#]+)$", url)
    if m and m.group(1) in SLUG_FIXTURES:
        return fx(SLUG_FIXTURES[m.group(1)])
    raise urllib.error.HTTPError(url, 404, "Not Found (offline test)", None, None)


class OfflineEnv:
    """Context manager: temp cache root + fixture-serving polite_get stub."""

    def __init__(self, cache_dir, routes):
        self.cache_dir = pathlib.Path(cache_dir)
        self.routes = routes
        self.calls = []            # list of (url, headers)

    def __enter__(self):
        self._orig_get = newsrc.base.polite_get
        self._orig_fc = openwebcamdb.fetch_cache
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
        openwebcamdb.fetch_cache = (
            lambda family, refresh=False: FetchCache(self.cache_dir, refresh=refresh))
        return self

    def __exit__(self, *exc):
        newsrc.base.polite_get = self._orig_get
        openwebcamdb.fetch_cache = self._orig_fc
        return False


def quiet(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


# --- pure parser tests ----------------------------------------------------------

def test_module_contract():
    e = openwebcamdb.ENUMERATOR
    assert isinstance(e, Enumerator)
    assert e.name == "openwebcamdb"
    assert e.provenance == "aggregator_directory"
    assert e.source_ref == openwebcamdb.SITEMAP_URL
    assert "OpenWebcamDB" in e.attribution and "third-party directory" in e.attribution
    assert e.limit is None and e.refresh is False
    assert openwebcamdb.BROWSER_HEADERS["User-Agent"].startswith("Mozilla/5.0")
    assert "Chrome/125" in openwebcamdb.BROWSER_UA


def test_extract_slugs_from_fixture_sitemap():
    slugs = openwebcamdb.extract_slugs(SITEMAP_BYTES.decode("utf-8"))
    assert slugs == SAMPLE_SLUGS, slugs          # order preserved, non-webcams dropped
    # duplicates collapse, order kept
    text = ("<urlset><url><loc>https://openwebcamdb.com/webcams/a</loc></url>"
            "<url><loc>https://openwebcamdb.com/webcams/b</loc></url>"
            "<url><loc>https://openwebcamdb.com/webcams/a</loc></url></urlset>")
    assert openwebcamdb.extract_slugs(text) == ["a", "b"]
    # non-camera locs only
    assert openwebcamdb.extract_slugs("<loc>https://openwebcamdb.com/webcams/</loc>") == []


def test_youtube_video_id_forms():
    y = openwebcamdb.youtube_video_id
    assert y("https://www.youtube.com/watch?v=yv2RtoIMNzA") == "yv2RtoIMNzA"
    assert y("https://www.youtube.com/embed/DbLMSFvB2Og?autoplay=1&mute=1&playsinline=1") == "DbLMSFvB2Og"
    assert y("https://www.youtube.com/watch?v=AbC-123_xYz&t=42s") == "AbC-123_xYz"
    assert y("https://youtu.be/AbC123") == "AbC123"
    assert y("https://g0.ipcamlive.com/player/player.php?alias=594049acc6784") is None
    assert y("") is None and y(None) is None


def test_peregrine_row_mapping():
    html = fx(SLUG_FIXTURES["peregrine-falcon-nest-at-csu-australia"]).decode("utf-8")
    ld = openwebcamdb.parse_detail_jsonld(html)
    assert isinstance(ld, dict) and ld["@type"] == "VideoObject"
    r = openwebcamdb.row_from_detail(html, "peregrine-falcon-nest-at-csu-australia")
    assert isinstance(r, CameraRow)
    assert r.url == "https://www.youtube.com/watch?v=yv2RtoIMNzA"
    assert r.name == "Peregrine Falcon Nest at CSU Australia"
    assert r.country == "AU"
    assert abs(r.lat - (-35.063848)) < 1e-9 and abs(r.lon - 147.355309) < 1e-9
    assert r.protocol == "youtube" and r.status == "unknown"
    assert r.provenance == "aggregator_directory" and r.source_family == "openwebcamdb"
    assert r.attribution == openwebcamdb.ATTRIBUTION
    assert r.was_redacted is False and r.credential_present is False
    m = r.meta
    assert m["owdb_slug"] == "peregrine-falcon-nest-at-csu-australia"
    assert m["owdb_page"] == "https://openwebcamdb.com/webcams/peregrine-falcon-nest-at-csu-australia"
    assert m["video_id"] == "yv2RtoIMNzA"
    assert m["upload_date"] == "2025-09-22T10:06:55+00:00"
    assert m["view_count_at_enumeration"] == 1164
    assert "thumb_medium.jpg" in m["thumbnail_url"]
    assert m["source"] == ""                       # operator not derivable from page
    assert m["owdb_location_name"].startswith("Charles Sturt University")
    assert r.snapshot_date and len(r.snapshot_date) == 10


def test_country_variants_and_non_youtube_skip():
    # lamai: TH, YouTube
    r = openwebcamdb.row_from_detail(
        fx(SLUG_FIXTURES["lamai-beach-views-from-baobab-spot"]).decode("utf-8"),
        "lamai-beach-views-from-baobab-spot")
    assert r is not None and r.country == "TH"
    assert r.meta["video_id"] == "Tpj0cmMVOd0"
    # melbourne & anglesea: no address block at all -> country "", geo still present
    for slug in ("melbourne-skyline-urban-vista", "anglesea-golf-course-seaside-panorama"):
        r = openwebcamdb.row_from_detail(fx(SLUG_FIXTURES[slug]).decode("utf-8"), slug)
        assert r is not None and r.country == "", (slug, None if r is None else r.country)
        assert r.lat is not None and r.lon is not None
    # kiten: real non-YouTube player (ipcamlive) -> no usable id -> None
    assert openwebcamdb.row_from_detail(
        fx(SLUG_FIXTURES["kiten-atliman-beach-panorama"]).decode("utf-8"),
        "kiten-atliman-beach-panorama") is None


def test_row_edge_cases_synthetic():
    # geo out of range / unparseable -> None; view count string / list form
    ld = {"name": "x", "contentUrl": "https://www.youtube.com/watch?v=AbCdEfGhIjK",
          "contentLocation": {"geo": {"latitude": 999, "longitude": -999}},
          "interactionStatistic": [{"@type": "InteractionCounter", "userInteractionCount": "123"}]}
    r = openwebcamdb.row_from_ld(ld, "cam-x")
    assert r is not None and r.lat is None and r.lon is None
    assert r.meta["view_count_at_enumeration"] == 123
    ld2 = {"name": "y", "contentUrl": "https://www.youtube.com/watch?v=AbCdEfGhIjK",
           "contentLocation": {"geo": {"latitude": "nope", "longitude": "12.5"}}}
    r2 = openwebcamdb.row_from_ld(ld2, "cam-y")
    assert r2.lat is None and abs(r2.lon - 12.5) < 1e-9
    assert r2.meta["view_count_at_enumeration"] is None
    # embedUrl-only page still yields the row (id from embedUrl)
    ld3 = {"name": "z", "embedUrl": "https://www.youtube.com/embed/ZzZzZzZzZzZ?autoplay=1"}
    r3 = openwebcamdb.row_from_ld(ld3, "cam-z")
    assert r3 is not None and r3.url == "https://www.youtube.com/watch?v=ZzZzZzZzZzZ"


# --- enumerate() flow tests (offline, fake network) ------------------------------

def test_enumerate_offline_full_and_resume():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main) as env:
        out_dir = pathlib.Path(td) / "out"
        enum = openwebcamdb.OpenWebcamdbEnumerator()
        res = quiet(run_one, enum, save=True, out_dir=out_dir)

        assert res.stats["pages_total"] == 6
        assert res.stats["pages_considered"] == 6
        assert res.stats["rows"] == 4, res.stats          # peregrine, melbourne, anglesea, lamai
        assert res.stats["skipped_no_feed"] == 1          # kiten (ipcamlive)
        assert res.stats["skipped_no_ld"] == 0
        assert res.stats["pages_failed"] == 1             # newcastle (404)
        assert res.stats["dupes_dropped"] == 0
        assert res.stats["pages_in_cache"] == 5 and res.stats["pages_in_cache_start"] == 0
        assert res.stats["cache_hits"] == 0 and res.stats["cache_misses"] == 6  # sitemap + 5 pages
        check_no_liveness(res)                            # guard: all rows 'unknown'
        assert all(r.status == "unknown" for r in res.rows)
        assert res.stats["by_country"] == {"AU": 1, "TH": 1}
        # browser UA was sent on every fetch
        assert res.stats["by_status"] == {"unknown": 4}

        # output jsonl + sha256
        out_file = out_dir / "newsrc-openwebcamdb.jsonl"
        assert out_file.exists()
        lines = out_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4
        digest = hashlib.sha256(out_file.read_bytes()).hexdigest()
        assert res.stats["sha256"] == digest
        for line in lines:
            d = json.loads(line)
            assert d["status"] == "unknown" and d["provenance"] == "aggregator_directory"
            assert d["source_family"] == "openwebcamdb" and len(d["camera_id"]) == 16

        # ---- resume: second run answers everything from cache -------------------
        calls_before = len(env.calls)
        assert all(h.get("User-Agent", "").startswith("Mozilla/5.0") for _, h in env.calls)
        res2 = quiet(run_one, openwebcamdb.OpenWebcamdbEnumerator(), save=False)
        new_calls = [u for u, _ in env.calls[calls_before:]]
        assert new_calls == [PAGE("newcastle-harbor-cargo-ships-view")], new_calls  # retry only the 404
        assert res2.stats["cache_hits"] == 6 and res2.stats["cache_misses"] == 0
        assert res2.stats["rows"] == 4
        assert res2.stats["pages_in_cache_start"] == 5


def test_enumerate_limit_caps_pages():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main) as env:
        enum = openwebcamdb.OpenWebcamdbEnumerator()
        enum.limit = 2
        res = quiet(run_one, enum, save=False)
        assert [u for u, _ in env.calls] == [openwebcamdb.SITEMAP_URL,
                                             PAGE("peregrine-falcon-nest-at-csu-australia"),
                                             PAGE("newcastle-harbor-cargo-ships-view")]
        assert res.stats["limit"] == 2
        assert res.stats["pages_considered"] == 2 and res.stats["pages_total"] == 6
        assert res.stats["rows"] == 1 and res.stats["pages_failed"] == 1
        assert res.stats["pages_in_cache"] == 1


def test_enumerate_dedupe_by_url():
    xml = ('<?xml version="1.0" encoding="UTF-8"?><urlset>'
           '<url><loc>https://openwebcamdb.com/webcams/dup-one</loc></url>'
           '<url><loc>https://openwebcamdb.com/webcams/dup-two</loc></url></urlset>').encode()
    peregrine = fx(SLUG_FIXTURES["peregrine-falcon-nest-at-csu-australia"])
    routes = {openwebcamdb.SITEMAP_URL: xml,
              PAGE("dup-one"): peregrine, PAGE("dup-two"): peregrine}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        res = quiet(run_one, openwebcamdb.OpenWebcamdbEnumerator(), save=False)
        assert res.stats["rows"] == 1, res.stats
        assert res.stats["dupes_dropped"] == 1
        assert res.stats["skipped_no_feed"] == 0


def test_enumerate_page_without_jsonld():
    xml = ('<?xml version="1.0" encoding="UTF-8"?><urlset>'
           '<url><loc>https://openwebcamdb.com/webcams/no-ld-cam</loc></url></urlset>').encode()
    routes = {openwebcamdb.SITEMAP_URL: xml,
              PAGE("no-ld-cam"): b"<html><body><p>no json-ld here</p></body></html>"}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        res = quiet(run_one, openwebcamdb.OpenWebcamdbEnumerator(), save=False)
        assert res.stats["rows"] == 0
        assert res.stats["skipped_no_ld"] == 1 and res.stats["skipped_no_feed"] == 1


def test_run_cli_limit_smoke():
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", routes_main):
        out_dir = pathlib.Path(td) / "cli-out"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = openwebcamdb.run_cli(openwebcamdb.OpenWebcamdbEnumerator(),
                                      ["--limit", "3", "--out", str(out_dir)])
        assert rc == 0, buf.getvalue()
        text = buf.getvalue()
        assert "[openwebcamdb] rows=2" in text, text
        assert "sha256" in text and "pages_failed: 1" in text, text
        assert (out_dir / "newsrc-openwebcamdb.jsonl").exists()


def test_empty_sitemap_errors_cleanly():
    routes = {openwebcamdb.SITEMAP_URL: b"<?xml version='1.0'?><urlset></urlset>"}
    with tempfile.TemporaryDirectory() as td, OfflineEnv(pathlib.Path(td) / "cache", lambda u: routes.get(u)):
        enum = openwebcamdb.OpenWebcamdbEnumerator()
        try:
            quiet(enum.enumerate)
            raised = False
        except RuntimeError as exc:
            raised = "0 webcam slugs" in str(exc)
        assert raised, "empty sitemap should raise RuntimeError"


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

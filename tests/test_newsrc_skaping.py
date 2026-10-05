"""Skaping enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_skaping.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/skaping/`` are trimmed REAL payloads:
the sitemap sample (6 real ``<loc>`` blocks from ``sitemap.players.xml``,
fetched 2026-10-06) and two trimmed REAL Grouse Mountain player pages
(peak-cam: own-POV ``is_online:false``; zips-cam: own-POV ``is_online:true``
plus a quanteec live-thumbnail sibling). The remaining sitemap entries are
served by small synthetic stubs built in this file (video page, 3-segment
slug, white-label host without an ``explore`` config). No network: the newsrc
FetchCache + polite_get are monkeypatched in-process (always restored) and
everything is served from fixtures/stubs; the one capture probe fetch is a
tiny synthetic JPEG. Live runs happen via
``py -3.11 -m wfd.ingest.newsrc.skaping``, not from this file.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import skaping as sk

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "skaping"

SITEMAP_URL = sk.SITEMAP_URL
PEAK_URL = "https://www.skaping.com/grouse-mountain/peak-cam"
ZIPS_URL = "https://www.skaping.com/grouse-mountain/zips-cam"
CAUTERETS_URL = "https://www.skaping.com/cauterets/pontdespagne"
CAUTERETS_VIDEO_URL = "https://www.skaping.com/cauterets/pontdespagne/video"
LORIENT_URL = "https://www.skaping.com/lorient/rade/port-kernevel"
KYSTNOR_URL = "https://weathercam.kystnor.no/port-of-alta"

SITEMAP_LOCS = [PEAK_URL, ZIPS_URL, CAUTERETS_URL, CAUTERETS_VIDEO_URL,
                LORIENT_URL, KYSTNOR_URL]

S3_PEAK_OG = "https://skaping.s3.gra.io.cloud.ovh.net/grouse-mountain/peak-cam/2026/10/02/large/10-50.jpg"
S3_ZIPS_OG = "https://skaping.s3.gra.io.cloud.ovh.net/grouse-mountain/zips-cam/2026/10/05/large/19-40.jpg"
ZIPS_LIVE_THUMB = ("https://skaping.quanteec.com/contents/encodings/live/"
                   "02964f66-3354-4e3c-746c-7561-6665-64-847f-6f575613c132d/thumbnail.jpg")

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"\xff\xd9"      # tiny synthetic JPEG


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def sitemap_xml(locs) -> bytes:
    blocks = "\n".join(
        "<url>\r\n  <loc>" + u + "</loc>\r\n\t<priority>1.00</priority>\r\n</url>"
        for u in locs
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + blocks + "\n</urlset>\n").encode("utf-8")


def stub_page(title="", canonical="", og_image="", lat=None, lon=None, media="ImageMedia",
              media_id=1, media_url="//skaping.s3.gra.io.cloud.ovh.net/x/y/2026/10/05/19-40.jpg",
              media_date="2026-10-05 19:40:00", explore=None, broken_cfg=False) -> bytes:
    """Minimal page in the real player-page shape (meta + Launcher.start + config)."""
    parts = ["<!DOCTYPE html>", '<html class="no-js"><head>', '<meta charset="utf-8" />']
    if title:
        parts.append(f"<title>{title}</title>")
    if canonical:
        parts.append(f'<link rel="canonical" href="{canonical}" />')
    if og_image:
        parts.append(f'<meta property="og:image" content="{og_image}" />')
    if lat is not None:
        parts.append(f'<meta property="place:location:latitude" content="{lat}" />')
    if lon is not None:
        parts.append(f'<meta property="place:location:longitude" content="{lon}" />')
    cfg = {"explore": {"data": explore}} if explore is not None else {"player": {"loop": True}}
    cfg_json = json.dumps(cfg)
    if broken_cfg:
        cfg_json = cfg_json[:-2] + " BAD"
    parts += [
        "<script>",
        "window.startSkaperCallback = function() {",
        f"Launcher.start($('#skaper'), '9', new {media}({media_id}, \"{media_url}\", "
        f"DateUtil.dbDateToDate(\"{media_date}\"),0, 0), {cfg_json});",
        "};",
        "</script></head><body></body></html>",
    ]
    return "\n".join(parts).encode("utf-8")


def own_cam(pov_id, pov_url, pok="photo - fixe", online=True, live_media=""):
    pov = {"type_of_view": pok, "is_online": online, "player_url": pov_url,
           "last_media_date": "05/10/2026 à 19h40",
           "last_media": "https://skaping.s3.gra.io.cloud.ovh.net/x/y/mini/19-40.jpg"}
    if live_media:
        pov["last_media"] = live_media
    return [{"id": "1", "label": "Stub Cam", "povs": {str(pov_id): pov}}]


def default_pages():
    """URL -> bytes map for the 6-loc fixture sitemap (2 real fixtures + 4 stubs)."""
    return {
        PEAK_URL: fixture_bytes("grouse-mountain-peak-cam.html"),
        ZIPS_URL: fixture_bytes("grouse-mountain-zips-cam.html"),
        CAUTERETS_URL: stub_page(
            title="Cascade du Pont d'Espagne", canonical=CAUTERETS_URL,
            og_image="https://skaping.s3.gra.io.cloud.ovh.net/cauterets/pontdespagne/2026/10/05/large/19-40.jpg",
            lat="42.85111000", lon="-0.13969800",
            explore=own_cam(768, CAUTERETS_URL)),
        CAUTERETS_VIDEO_URL: stub_page(
            title="Cascade du Pont d'Espagne", canonical=CAUTERETS_VIDEO_URL,
            og_image="https://skaping.s3.gra.io.cloud.ovh.net/cauterets/pontdespagne/video/2026/10/05/19-40.jpg",
            media="VideoMedia", media_id=2,
            media_url="//skaping.s3.gra.io.cloud.ovh.net/cauterets/pontdespagne/video/2026/10/05/19-40.mp4",
            lat="42.85111000", lon="-0.13969800",
            explore=own_cam(790, CAUTERETS_VIDEO_URL, pok="video - fixe")),
        LORIENT_URL: stub_page(
            title="Webcam - Lorient - Port Kernevel", canonical=LORIENT_URL,
            og_image="https://skaping.s3.gra.io.cloud.ovh.net/lorient/k3-la-base/port/2026/10/05/large/19-39.jpg",
            lat="47.72641700", lon="-3.36452000",
            explore=own_cam(1326, LORIENT_URL)),
        KYSTNOR_URL: stub_page(
            title="Webcam - Port of Alta", canonical=KYSTNOR_URL,
            og_image="https://skaping.s3.gra.io.cloud.ovh.net/port-of-alta/2026/10/05/large/19-32.jpg",
            lat="69.98399700", lon="23.28359600", explore=None),
    }


class OfflineNet:
    """Fixture/stub-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, sitemap_payload=None, pages=None):
        self.cache_dir = cache_dir
        self.sitemap_bytes = (sitemap_payload if sitemap_payload is not None
                              else fixture_bytes("sitemap.players-sample.xml"))
        self.pages = default_pages() if pages is None else pages
        self.calls: list = []

    def fake_get(self, url, **kw):
        self.calls.append(url)
        if url == SITEMAP_URL:
            return self.sitemap_bytes
        if url in self.pages:
            return self.pages[url]
        if url.startswith("https://skaping.s3.gra.io.cloud.ovh.net/"):
            return FAKE_JPEG                      # capture probe target
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = sk.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        sk.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        sk.fetch_cache = self.orig_cache
        return False


def run_offline(sitemap_payload=None, pages=None, **attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, sitemap_payload, pages) as net:
        en = sk.SkapingEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


# --- module shape ---------------------------------------------------------------

def test_module_shape():
    assert isinstance(sk.ENUMERATOR, nb.Enumerator)
    assert sk.ENUMERATOR.name == "skaping"
    assert sk.ENUMERATOR.provenance == "public_by_design"
    assert sk.ENUMERATOR.source_ref == sk.SITEMAP_URL == "https://www.skaping.com/sitemap.players.xml"
    assert sk.ENUMERATOR.attribution == "Skaping (skaping.com) — operator webcam players"
    assert callable(sk.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(sk.__file__).read_text(encoding="utf-8")
    assert "import urllib" not in src and "urllib.request" not in src


# --- sitemap + url helpers -------------------------------------------------------

def test_parse_sitemap_fixture():
    locs = sk.parse_sitemap(fixture_text("sitemap.players-sample.xml"))
    assert locs == SITEMAP_LOCS, locs


def test_parse_sitemap_dedupes_and_normalizes():
    xml = ("<urlset><url><loc>https://www.skaping.com/a/b/</loc></url>"
           "<url><loc>https://www.skaping.com/a/b</loc></url>"
           "<url><loc>not-a-url</loc></url>"
           "<url><loc>https://www.skaping.com/c/d?x=1#frag</loc></url></urlset>")
    assert sk.parse_sitemap(xml) == ["https://www.skaping.com/a/b", "https://www.skaping.com/c/d"]
    assert sk.parse_sitemap("") == []
    assert sk.parse_sitemap(None) == []


def test_split_url_and_group_slug():
    assert sk.split_url(PEAK_URL) == ("www.skaping.com", ["grouse-mountain", "peak-cam"])
    assert sk.split_url(LORIENT_URL) == ("www.skaping.com", ["lorient", "rade", "port-kernevel"])
    assert sk.split_url(KYSTNOR_URL) == ("weathercam.kystnor.no", ["port-of-alta"])
    host, segs = sk.split_url(PEAK_URL + "/?q=1#frag")
    assert sk.group_slug_parts(host, segs) == ("grouse-mountain", "peak-cam")
    host, segs = sk.split_url(LORIENT_URL)
    assert sk.group_slug_parts(host, segs) == ("lorient", "rade/port-kernevel")
    host, segs = sk.split_url(KYSTNOR_URL)
    assert sk.group_slug_parts(host, segs) == ("weathercam.kystnor.no", "port-of-alta")
    host, segs = sk.split_url("https://wbcm.it/WB2qW")
    assert sk.group_slug_parts(host, segs) == ("wbcm.it", "WB2qW")


def test_country_hints():
    assert sk.country_for("www.skaping.com", "grouse-mountain") == "CA"
    assert sk.country_for("weathercam.kystnor.no", "weathercam.kystnor.no") == "NO"
    assert sk.country_for("www.skaping.com", "cauterets") == ""
    assert sk.country_for("wbcm.it", "wbcm.it") == ""


# --- the two real fixture pages ---------------------------------------------------

def test_parse_fixture_peak_page():
    page = sk.parse_player_page(fixture_text("grouse-mountain-peak-cam.html"), PEAK_URL)
    assert page["title"] == "Webcam - Grouse Mountain - Peak"
    assert page["canonical"] == PEAK_URL
    assert page["og_image"] == S3_PEAK_OG
    assert abs(page["lat"] - 49.38637477) < 1e-9 and abs(page["lon"] - -123.07616472) < 1e-9
    assert page["has_launcher"] is True and page["cfg_error"] is None
    assert page["media_kind"] == "image" and page["media_id"] == 106118024
    assert page["media_url"] == "https://skaping.s3.gra.io.cloud.ovh.net/grouse-mountain/peak-cam/2026/10/02/10-50.jpg"
    assert page["media_date"] == "2026-10-02 01:50:00"
    # own-POV flag is the peak cam's own (is_online:false), not the sibling cams'
    assert page["is_online"] is False
    # no /peak-cam/live sibling -> no live thumbnail (gravity/zips thumbs must NOT leak)
    assert page["live_thumbnail"] == ""


def test_parse_fixture_zips_page():
    page = sk.parse_player_page(fixture_text("grouse-mountain-zips-cam.html"), ZIPS_URL)
    assert page["title"] == "Webcam - Grouse Mountain - Zips Cam"
    assert page["canonical"] == ZIPS_URL
    assert page["is_online"] is True
    assert page["live_thumbnail"] == ZIPS_LIVE_THUMB
    assert page["media_date"] == "2026-10-05 10:40:00"


def test_extract_launcher_structure():
    lc = sk.extract_launcher(fixture_text("grouse-mountain-peak-cam.html"))
    assert lc["media_kind"] == "image" and lc["style_id"] == "3274"
    assert isinstance(lc["cfg"], dict) and lc["cfg_error"] is None
    assert "explore" in lc["cfg"]
    # balanced-scan tolerates nested parens/braces and escaped slashes in JSON
    lc2 = sk.extract_launcher(fixture_text("grouse-mountain-zips-cam.html"))
    assert lc2["style_id"] == "3276"
    assert lc2["cfg"]["explore"]["data"]
    assert sk.extract_launcher("<html>no launcher here</html>") is None
    # the third media ctor seen live (/live StreamMedia pages) normalizes to "stream"
    stream = stub_page(title="S", canonical="https://www.skaping.com/x/live",
                       media="StreamMedia", media_url="//skaping2.quanteec.com/contents/encodings/live/u/1")
    lc3 = sk.extract_launcher(stream.decode("utf-8"))
    assert lc3["media_kind"] == "stream"


def test_row_mapping_peak():
    page = sk.parse_player_page(fixture_text("grouse-mountain-peak-cam.html"), PEAK_URL)
    row = sk.row_from_page(page)
    assert row.url == PEAK_URL                      # canonical player page, NOT the S3 capture
    assert "skaping.s3" not in row.url and "skaping.quanteec" not in row.url
    assert row.source_family == "skaping"
    assert row.provenance == "public_by_design"
    assert row.status == "unknown" and row.protocol == "jpeg"
    assert row.country == "CA" and row.tags == ["webcam"]
    assert row.attribution == sk.ATTRIBUTION
    assert not row.was_redacted and not row.credential_present
    assert row.meta["group"] == "grouse-mountain" and row.meta["slug"] == "peak-cam"
    assert row.meta["host"] == "www.skaping.com"
    assert row.meta["is_online"] is False           # meta-only — status stays 'unknown'
    assert "live_thumbnail" not in row.meta
    assert row.meta["og_image"] == S3_PEAK_OG
    assert row.meta["latest_capture_at_enumeration"] == S3_PEAK_OG
    assert row.meta["latest_capture_date"] == "2026-10-02 01:50:00"
    assert row.meta["media_kind"] == "image" and row.meta["media_id"] == 106118024
    assert set(row.meta) == {"group", "slug", "host", "title", "og_image",
                             "latest_capture_at_enumeration", "latest_capture_date",
                             "media_kind", "media_id", "is_online"}


def test_name_fallback_group_slug():
    html = '<link rel="canonical" href="https://www.skaping.com/grouse-mountain/peak-cam" />'
    row = sk.row_from_page(sk.parse_player_page(html, PEAK_URL))
    assert row.name == "grouse-mountain/peak-cam", row.name


# --- the full offline enumeration --------------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline()
    nb.check_no_liveness(res)                      # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 6, [r.url for r in rows]
    assert [r.url for r in rows] == SITEMAP_LOCS
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "skaping" and r.provenance == "public_by_design" for r in rows)
    assert all(r.protocol == "jpeg" for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)

    by_url = {r.url: r for r in rows}
    peak = by_url[PEAK_URL]
    assert peak.meta["is_online"] is False and peak.country == "CA"
    zips = by_url[ZIPS_URL]
    assert zips.meta["is_online"] is True and zips.meta["live_thumbnail"] == ZIPS_LIVE_THUMB
    assert zips.country == "CA"
    video = by_url[CAUTERETS_VIDEO_URL]
    assert video.meta["media_kind"] == "video"
    assert video.meta["slug"] == "pontdespagne/video"
    lorient = by_url[LORIENT_URL]
    assert lorient.meta["group"] == "lorient" and lorient.meta["slug"] == "rade/port-kernevel"
    kyst = by_url[KYSTNOR_URL]
    assert kyst.meta["group"] == "weathercam.kystnor.no" and kyst.meta["slug"] == "port-of-alta"
    assert "is_online" not in kyst.meta and "live_thumbnail" not in kyst.meta  # white-label: no explore config
    assert kyst.country == "NO"

    # stats contract
    st = res.stats
    assert st["players_total"] == 6 and st["players_processed"] == 6
    assert st["pages_in_cache"] == 6 and st["pages_failed"] == 0
    assert st["rows"] == 6 and st["dupes_dropped"] == 0
    assert st["offline_flags"] == 1 and st["online_flags"] == 4  # kystnor has no flag
    assert st["non_skaping_hosts"] == 1
    assert st["pages_without_capture_url"] == 0 and st["pages_without_launcher"] == 0
    assert st["config_parse_failures"] == 0
    assert "failures" not in st
    # sitemap + 6 pages + 1 capture probe
    assert st["cache_misses"] == 8 and st["cache_hits"] == 0
    assert len(net.calls) == 8


def test_verified_capture_probe():
    res, net = run_offline()
    vf = res.stats["verified_capture"]
    assert vf["row_slug"] == "peak-cam"             # first row with a capture URL
    assert vf["url"] == S3_PEAK_OG
    assert vf["content_type"] == "image/jpeg"
    assert vf["bytes"] == len(FAKE_JPEG)
    assert vf["url"] in net.calls                   # the capture URL really was fetched
    assert all(r.status == "unknown" for r in res.rows)   # probe never claims liveness


def test_limit_caps_players():
    res, net = run_offline(limit=3)
    assert len(res.rows) == 3 and [r.url for r in res.rows] == SITEMAP_LOCS[:3]
    assert res.stats["players_processed"] == 3 and res.stats["players_total"] == 6
    assert res.stats["pages_in_cache"] == 3          # only the capped players are cached
    page_calls = [u for u in net.calls if u in SITEMAP_LOCS]
    assert page_calls == SITEMAP_LOCS[:3]            # only 3 players fetched
    assert net.calls.count(SITEMAP_URL) == 1


def test_dedupe_by_url():
    one = "https://www.skaping.com/x/one"
    two = "https://www.skaping.com/x/two"
    shared = stub_page(title="Shared", canonical="https://www.skaping.com/x/shared",
                       og_image="https://skaping.s3.gra.io.cloud.ovh.net/x/shared/2026/10/05/large/19-40.jpg")
    res, _ = run_offline(sitemap_payload=sitemap_xml([one, two]),
                         pages={one: shared, two: shared})
    assert len(res.rows) == 1 and res.stats["dupes_dropped"] == 1
    assert res.rows[0].url == "https://www.skaping.com/x/shared"
    assert all(r.status == "unknown" for r in res.rows)


def test_fetch_failure_counted_and_run_survives():
    dead = "https://www.skaping.com/dead/one"
    res, net = run_offline(sitemap_payload=sitemap_xml([PEAK_URL, dead]))
    assert len(res.rows) == 1 and res.rows[0].url == PEAK_URL
    assert res.stats["pages_failed"] == 1
    assert res.stats["failures"][0]["url"] == dead
    assert "404" in res.stats["failures"][0]["error"]


def test_config_parse_failure_is_meta_only():
    url = "https://www.skaping.com/broken/cam"
    broken = stub_page(title="Broken", canonical=url,
                       og_image="https://skaping.s3.gra.io.cloud.ovh.net/broken/cam/2026/10/05/large/19-40.jpg",
                       broken_cfg=True)
    res, _ = run_offline(sitemap_payload=sitemap_xml([url]), pages={url: broken})
    assert len(res.rows) == 1
    row = res.rows[0]
    assert row.status == "unknown"
    assert "is_online" not in row.meta                # broken config -> no flag, row still lands
    assert res.stats["config_parse_failures"] == 1


def test_retry_on_429_and_fatal_404():
    class FlakyCache:
        def __init__(self, fail_first, status=429):
            self.n = 0
            self.fail_first = fail_first
            self.status = status

        def get(self, url, **kw):
            self.n += 1
            if self.n <= self.fail_first:
                raise urllib.error.HTTPError(url, self.status, "x", None, None)
            return b"ok"

    good = FlakyCache(fail_first=2)
    assert sk._fetch_with_retry(good, "http://x", suffix=".bin", delays=(0.0, 0.0)) == b"ok"
    assert good.n == 3                                   # two 429s then success

    fatal = FlakyCache(fail_first=1, status=404)
    try:
        sk._fetch_with_retry(fatal, "http://x", suffix=".bin", delays=(0.0, 0.0))
        raised = False
    except urllib.error.HTTPError:
        raised = True
    assert raised and fatal.n == 1                       # 4xx never retried

    exhausted = FlakyCache(fail_first=99)
    try:
        sk._fetch_with_retry(exhausted, "http://x", suffix=".bin", delays=(0.0, 0.0))
        raised = False
    except urllib.error.HTTPError:
        raised = True
    assert raised and exhausted.n == 3                   # len(delays) + 1 attempts


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = sk.SkapingEnumerator().enumerate()
            calls_after_first = len(net.calls)
            res2 = sk.SkapingEnumerator().enumerate()
    assert calls_after_first == 8                        # sitemap + 6 pages + probe
    assert len(net.calls) == calls_after_first           # second run: zero new fetches
    assert res1.stats["cache_misses"] == 8 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 8 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = nb.run_one(sk.SkapingEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-skaping.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 6
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert all(l["source_family"] == "skaping" for l in lines)
    assert any(l["meta"].get("is_online") is False for l in lines)   # flag kept in meta, not status
    assert res.stats["written"] == 6 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-skaping.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = sk.run_cli(sk.SkapingEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[skaping]" in out and "rows=6" in out, out


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

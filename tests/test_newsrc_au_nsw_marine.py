"""au-nsw-marine enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_au_nsw_marine.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/au-nsw-marine/`` are trimmed REAL
payloads (NSW hub slice, three sub-page slices, three whole coastalcoms widget
pages; fetched 2026-10-06 — see that dir's ``_build_fixtures.py``) plus one
clearly SYNTHETIC stub page (no live stub was observable at build time).
No network: the newsrc FetchCache + polite_get are monkeypatched in-process
(always restored) and everything is served from the fixtures / synthetic
payloads. Live runs happen via ``py -3.11 -m wfd.ingest.newsrc.au_nsw_marine``,
not from this file.
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

from wfd.ingest.newsrc import au_nsw_marine as nm
from wfd.ingest.newsrc import base as nb

FIXTURES = (pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc"
            / "au-nsw-marine")

HUB = nm.HUB_URL
HUB2 = HUB + nm.BROWSER_CACHE_MARK
SUBPATH = ("/driving-boating-and-transport/using-waterways-boating-and-"
           "transport-information/conditions-weather-and-tides/webcams/")
BALLINA_UUID = "76818de6-1bc6-44d2-943a-3a905ee9c132"
COFFS_UUID = "c84385c2-10bb-499b-9c23-0542bff3210c"
ILUKA_UUID = "26f42761-cece-45f3-94c8-5edb9508dee1"
STREAM_BALLINA = "https://streaming-au.coastalcoms.com/cw/ballinarmscamera.stream/playlist.m3u8"
STREAM_COFFS = "https://d1nm4r8e5x1rwd.cloudfront.net/cw/coffsjettybeachcamera.stream/playlist.m3u8"
STREAM_ILUKA = "https://d1nm4r8e5x1rwd.cloudfront.net/cw/ilukacamera.stream/playlist.m3u8"

META_KEYS = {"widget_uuid", "page_slug", "page_url", "hub_url", "drift_note"}
PAD = "x" * 2000                       # keeps synthetic pages above the stub length floor


def fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def text(name: str) -> str:
    return fx(name).decode("utf-8", errors="replace")


def page_url(slug: str) -> str:
    return nm.SUBPAGE_ORIGIN + SUBPATH + slug


def widget_url(uuid: str) -> str:
    return f"{nm.WIDGET_BASE}/{uuid}"


def inline_hub(slugs):
    links = "\n".join(f'<li><a href="{SUBPATH}{s}">cam</a></li>' for s in slugs)
    return (f"<html><head><title>t</title></head><body><!-- {PAD} -->"
            f"<ul>{links}</ul></body></html>").encode()


def inline_page(uuid=None):
    if uuid:
        ifr = (f'<div><iframe title="Test webcam" '
               f'data-src="https://widget.coastalcoms.com/video/{uuid}" '
               f'src="https://widget.coastalcoms.com/video/{uuid}" frameborder="0"></iframe></div>')
    else:
        ifr = "<p>no camera here</p>"
    return f"<html><body><!-- {PAD} -->{ifr}</body></html>".encode()


def inline_widget(url: str) -> bytes:
    return (f'<html><body><!-- {PAD} --><video><source type="application/x-mpegURL" '
            f'src="{url}" /></video></body></html>').encode()


class OfflineNet:
    """URL-map-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, url_map):
        self.cache_dir = cache_dir
        self.urls = dict(url_map)
        self.calls: list = []          # [(url, User-Agent header or None)]

    def fake_get(self, url, **kw):
        ua = (kw.get("headers") or {}).get("User-Agent")
        self.calls.append((url, ua))
        val = self.urls.get(url)
        if isinstance(val, Exception):
            raise val
        if val is None:
            raise urllib.error.HTTPError(url, 404, "offline: no fixture for url", {}, None)
        return val

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = nm.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        nm.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        nm.fetch_cache = self.orig_cache
        return False


def subset_map():
    """Hub subset + the three fixture-backed pages and their widget pages."""
    return {
        HUB: fx("hub-subset.html"),
        page_url("ballina"): fx("page-ballina.html"),
        page_url("coffs-harbour"): fx("page-coffs-harbour.html"),
        page_url("iluka/yamba"): fx("page-iluka-yamba.html"),
        widget_url(BALLINA_UUID): fx("widget-ballina.html"),
        widget_url(COFFS_UUID): fx("widget-coffs-harbour.html"),
        widget_url(ILUKA_UUID): fx("widget-iluka-yamba.html"),
    }


def run_offline(url_map, **attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, url_map) as net:
        en = nm.NswMarineEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


# --- module shape --------------------------------------------------------------

def test_module_shape():
    assert isinstance(nm.ENUMERATOR, nb.Enumerator)
    assert nm.ENUMERATOR.name == "au-nsw-marine"
    assert nm.ENUMERATOR.provenance == "public_by_design"
    assert nm.ENUMERATOR.source_ref == HUB
    assert HUB.endswith("/conditions-weather-and-tides/webcams")
    assert nm.ENUMERATOR.attribution == "NSW Government (Transport for NSW) — marine webcams"
    assert callable(nm.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(nm.__file__).read_text(encoding="utf-8")
    assert "urllib" not in src


# --- parsers + stub detection ----------------------------------------------------

def test_extract_pages_real_hub_and_stub_detection():
    hub = text("hub-webcams.html")
    pages = nm.extract_pages(hub)
    slugs = [s for s, _ in pages]
    assert len(slugs) == 22 and len(set(slugs)) == 22    # page lists each link twice
    assert slugs[0] == "lake-eucumbene" and slugs[-1] == "sussex-inlet"
    assert "iluka/yamba" in slugs                        # multi-segment slug kept whole
    assert sum(1 for s in slugs if "/" in s) == 1
    assert all(p.startswith(SUBPATH) for _, p in pages)
    assert dict(pages)["iluka/yamba"] == SUBPATH + "iluka/yamba"
    # the hub link itself, social/reader links and dupes never become slugs
    assert "" not in slugs and all("sharer" not in s for s in slugs)

    assert not nm.hub_is_stub(hub)
    assert nm.hub_is_stub(text("synthetic-stub.html"))   # synthetic JS shell
    assert nm.hub_is_stub("<html></html>")               # short garbage
    assert not nm.subpage_is_stub(text("page-ballina.html"))
    assert nm.subpage_is_stub(text("synthetic-stub.html"))


def test_parse_webcam_iframe():
    w = nm.parse_webcam_iframe(text("page-ballina.html"))
    assert w == {"widget_uuid": BALLINA_UUID, "title": "Ballina webcam"}
    assert nm.parse_webcam_iframe(text("page-iluka-yamba.html")) == {
        "widget_uuid": ILUKA_UUID, "title": "Iluka / Yamba webcam"}

    # weather iframe listed FIRST: the /video/ widget must still be picked
    html = ('<iframe title="X weather widget" '
            'src="https://widget.coastalcoms.com/weather/3ac2399b-e987-479a-81f3-c739d59dc898"></iframe>'
            '<iframe title="X webcam" '
            'src="https://widget.coastalcoms.com/video/11111111-1111-1111-1111-111111111111"></iframe>')
    assert nm.parse_webcam_iframe(html)["widget_uuid"] == "11111111-1111-1111-1111-111111111111"
    # no title attribute -> empty title kept
    h2 = ('<iframe src="https://widget.coastalcoms.com/video/'
          '22222222-2222-2222-2222-222222222222"></iframe>')
    assert nm.parse_webcam_iframe(h2) == {
        "widget_uuid": "22222222-2222-2222-2222-222222222222", "title": ""}
    assert nm.parse_webcam_iframe("<html><body>none</body></html>") is None
    assert nm.parse_webcam_iframe(
        '<iframe src="https://widget.coastalcoms.com/weather/'
        '33333333-3333-3333-3333-333333333333"></iframe>') is None


def test_first_m3u8():
    assert nm.first_m3u8(text("widget-ballina.html")) == STREAM_BALLINA
    assert nm.first_m3u8(text("widget-coffs-harbour.html")) == STREAM_COFFS
    assert nm.first_m3u8(text("widget-iluka-yamba.html")) == STREAM_ILUKA
    assert nm.first_m3u8(
        '<source src="https://a.example/b.m3u8"><source src="https://a.example/c.m3u8">'
    ) == "https://a.example/b.m3u8"
    assert nm.first_m3u8("<html>no stream here</html>") is None


def test_location_name():
    assert nm.location_name("Ballina webcam", "ballina") == "Ballina"
    assert nm.location_name("Iluka / Yamba webcam", "iluka/yamba") == "Iluka / Yamba"
    assert nm.location_name("Coffs Harbour WEBCAM", "x") == "Coffs Harbour"
    assert nm.location_name("", "south-west-rocks-and-macleay-river") == (
        "South West Rocks And Macleay River")
    assert nm.location_name("", "iluka/yamba") == "Yamba"


# --- the full offline enumeration --------------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline(subset_map())
    nb.check_no_liveness(res)                    # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 3 and len({r.url for r in rows}) == 3
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "au-nsw-marine" for r in rows)
    assert all(r.provenance == "public_by_design" and r.country == "AU" for r in rows)
    assert all(r.protocol == "hls" for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)
    assert all(set(r.meta) == META_KEYS for r in rows)
    assert all(r.meta["hub_url"] == HUB and "re-resolve" in r.meta["drift_note"] for r in rows)

    by_slug = {r.meta["page_slug"]: r for r in rows}
    b, c, i = by_slug["ballina"], by_slug["coffs-harbour"], by_slug["iluka/yamba"]
    assert (b.name, b.url, b.meta["widget_uuid"]) == ("Ballina", STREAM_BALLINA, BALLINA_UUID)
    assert (c.name, c.url, c.meta["widget_uuid"]) == ("Coffs Harbour", STREAM_COFFS, COFFS_UUID)
    assert (i.name, i.url, i.meta["widget_uuid"]) == ("Iluka / Yamba", STREAM_ILUKA, ILUKA_UUID)
    assert i.meta["page_url"] == page_url("iluka/yamba")
    assert b.meta["page_url"] == page_url("ballina") == nm.SUBPAGE_ORIGIN + SUBPATH + "ballina"

    st = res.stats
    assert st["hub_stage"] == "polite"
    assert st["slugs"] == 3 and st["slugs_extracted"] == 3
    assert st["pages_failed"] == 0 and st["pages_no_widget"] == 0
    assert st["widgets"] == 3 and st["widget_fetch_failed"] == 0 and st["no_m3u8"] == 0
    assert st["rows"] == 3 and st["dupes_dropped"] == 0
    assert st["subpage_stages"] == {"polite": 3}
    assert st["cache_misses"] == 7 and st["cache_hits"] == 0
    assert "limit" not in st

    # exact fetch order: hub, then per page: page fetch -> widget fetch; default UA only
    assert [u for u, _ in net.calls] == [
        HUB,
        page_url("ballina"), widget_url(BALLINA_UUID),
        page_url("coffs-harbour"), widget_url(COFFS_UUID),
        page_url("iluka/yamba"), widget_url(ILUKA_UUID),
    ]
    assert all(ua is None for _, ua in net.calls)


def test_hub_two_stage_stub_retry_and_cache_reuse():
    m = subset_map()
    m[HUB] = fx("synthetic-stub.html")                 # default UA gets the stub
    m[HUB2] = fx("hub-subset.html")                    # browser-UA retry gets the page
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td, m) as net:
            res1 = nm.NswMarineEnumerator().enumerate()
            calls1 = len(net.calls)
            res2 = nm.NswMarineEnumerator().enumerate()
        calls2 = len(net.calls)
    assert calls1 == 8                                 # hub x2 + 3 pages + 3 widgets
    assert calls2 == calls1                            # second run: zero new fetches
    assert net.calls[0] == (HUB, None)
    assert net.calls[1] == (HUB2, nm.BROWSER_UA)        # retry really used browser UA
    assert res1.stats["hub_stage"] == "browser" and res2.stats["hub_stage"] == "browser"
    assert len(res1.rows) == 3
    assert res1.stats["cache_misses"] == 8 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 8 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_subpage_two_stage_stub_retry():
    m = subset_map()
    m[page_url("ballina")] = fx("synthetic-stub.html")
    m[page_url("ballina") + nm.BROWSER_CACHE_MARK] = fx("page-ballina.html")
    res, net = run_offline(m)
    assert res.stats["hub_stage"] == "polite"
    assert res.stats["subpage_stages"] == {"polite": 2, "browser": 1}
    assert len(res.rows) == 3
    ua_by_url = {u: ua for u, ua in net.calls}
    assert ua_by_url[page_url("ballina") + nm.BROWSER_CACHE_MARK] == nm.BROWSER_UA
    assert ua_by_url[page_url("coffs-harbour")] is None


def test_failure_paths_counted_and_skipped():
    u_no_m3u8 = "55555555-5555-5555-5555-555555555555"
    u_fail = "66666666-6666-6666-6666-666666666666"
    m = {
        HUB: inline_hub(["test-deadpage", "test-nowidget", "test-nom3u8", "test-widgetfail"]),
        # deadpage: no entry at all -> 404
        page_url("test-nowidget"): inline_page(None),          # no iframe, both UA stages
        page_url("test-nowidget") + nm.BROWSER_CACHE_MARK: inline_page(None),
        page_url("test-nom3u8"): inline_page(u_no_m3u8),
        page_url("test-widgetfail"): inline_page(u_fail),
        widget_url(u_no_m3u8): b"<html><body>stream not configured</body></html>",
        widget_url(u_fail): urllib.error.HTTPError("w", 404, "gone", {}, None),
    }
    res, net = run_offline(m)
    st = res.stats
    assert st["slugs"] == 4 and st["pages_failed"] == 1
    assert st["pages_failed_slugs"] == ["test-deadpage"]
    assert "404" in st["pages_failed_examples"][0]["error"]
    assert st["pages_no_widget"] == 1 and st["pages_no_widget_slugs"] == ["test-nowidget"]
    assert st["widgets"] == 2
    assert st["widget_fetch_failed"] == 1 and st["widget_fetch_failed_slugs"] == ["test-widgetfail"]
    assert st["no_m3u8"] == 1 and st["no_m3u8_slugs"] == ["test-nom3u8"]
    assert st["rows"] == 0 and st["dupes_dropped"] == 0
    assert st["subpage_stages"] == {"polite": 2, "stub": 1}
    nb.check_no_liveness(res)


def test_dedupe_and_redaction_by_url():
    u_a = "77777777-7777-7777-7777-777777777777"
    u_b = "88888888-8888-8888-8888-888888888888"
    m = {
        HUB: inline_hub(["test-dup-a", "test-dup-b"]),
        page_url("test-dup-a"): inline_page(u_a),
        page_url("test-dup-b"): inline_page(u_b),
        widget_url(u_a): inline_widget(
            "https://user:pass@cdn.example/cw/same.stream/playlist.m3u8"),
        widget_url(u_b): inline_widget("https://cdn.example/cw/same.stream/playlist.m3u8"),
    }
    res, _ = run_offline(m)
    assert len(res.rows) == 1 and res.stats["dupes_dropped"] == 1
    row = res.rows[0]
    assert row.url == "https://cdn.example/cw/same.stream/playlist.m3u8"
    assert row.was_redacted is True and row.credential_present is True
    assert res.stats["redacted"] == 1


def test_limit_caps_slugs():
    m = {
        HUB: fx("hub-webcams.html"),
        page_url("ballina"): fx("page-ballina.html"),
        page_url("coffs-harbour"): fx("page-coffs-harbour.html"),
        widget_url(BALLINA_UUID): fx("widget-ballina.html"),
        widget_url(COFFS_UUID): fx("widget-coffs-harbour.html"),
    }
    res, net = run_offline(m, limit=5)
    st = res.stats
    assert st["slugs"] == 5 and st["slugs_extracted"] == 22 and st["limit"] == 5
    # first five slugs: lake-eucumbene, ballina, brunswick-heads, camden-haven, coffs-harbour
    assert st["pages_failed"] == 3
    assert st["pages_failed_slugs"] == ["lake-eucumbene", "brunswick-heads", "camden-haven"]
    assert len(res.rows) == 2
    assert len(net.calls) == 8                     # hub + 5 pages + 2 widgets


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td, subset_map()) as net:
            res = nb.run_one(nm.NswMarineEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-au-nsw-marine.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 3
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert all(l["country"] == "AU" and l["protocol"] == "hls" for l in lines)
    assert res.stats["written"] == 3 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-au-nsw-marine.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td, subset_map()) as net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = nm.run_cli(nm.NswMarineEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[au-nsw-marine]" in out and "rows=3" in out, out
    assert "hub_stage: polite" in out, out


def test_hub_fetch_failure_raises():
    sleeps = []
    orig = nm._sleep
    nm._sleep = lambda s: sleeps.append(s)
    try:
        m = {HUB: urllib.error.HTTPError(HUB, 500, "boom", {}, None)}
        with tempfile.TemporaryDirectory() as td, OfflineNet(td, m) as net:
            try:
                nm.NswMarineEnumerator().enumerate()
                raised = None
            except RuntimeError as exc:
                raised = exc
    finally:
        nm._sleep = orig
    assert raised is not None and "NSW hub fetch failed" in str(raised)
    assert len(net.calls) == 3 and len(sleeps) == 2      # bounded retries on 5xx


def test_hub_zero_slugs_raises():
    m = {HUB: fx("synthetic-stub.html"), HUB2: fx("synthetic-stub.html")}
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, m) as net:
        try:
            nm.NswMarineEnumerator().enumerate()
            raised = None
        except RuntimeError as exc:
            raised = exc
    assert raised is not None and "0 webcam sub-page slugs" in str(raised)
    assert len(net.calls) == 2                           # both UA stages attempted


def test_retry_wrapper_429_transient_and_hard_4xx():
    sleeps = []
    orig = nm._sleep
    nm._sleep = lambda s: sleeps.append(s)

    class Flaky:
        def __init__(self, codes):
            self.codes, self.calls = list(codes), []

        def get(self, url, **kw):
            self.calls.append(url)
            if self.codes:
                code = self.codes.pop(0)
                if code == "oserr":
                    raise OSError("boom")
                hdrs = {"Retry-After": "7"} if code == 429 else {}
                raise urllib.error.HTTPError(url, code, "e", hdrs, None)
            return b"ok"

    try:
        flaky = Flaky([429])
        assert nm._retry_get(flaky, "https://x/") == b"ok"
        assert len(flaky.calls) == 2 and sleeps == [7.0]     # Retry-After honored

        flaky = Flaky([404])
        try:
            nm._retry_get(flaky, "https://x/")
            raised = False
        except urllib.error.HTTPError:
            raised = True
        assert raised and len(flaky.calls) == 1              # hard 4xx: no retry
        assert sleeps == [7.0]                               # ...and no extra sleep

        flaky = Flaky(["oserr", "oserr", "oserr"])
        try:
            nm._retry_get(flaky, "https://x/")
            raised = False
        except OSError:
            raised = True
        assert raised and len(flaky.calls) == 3              # transient retried
        assert len(sleeps) == 3                              # 2 backoffs + the 7.0
    finally:
        nm._sleep = orig


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

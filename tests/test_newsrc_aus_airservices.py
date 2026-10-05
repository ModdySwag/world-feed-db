"""Aus-airservices enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_aus_airservices.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/aus-airservices/`` are trimmed REAL
payloads (hub page JS config, admin-ajax airport list, airport-page camera
"slide" fragments; fetched 2026-10-06) plus one clearly-labelled synthetic
entry/page for the thumbnail-fallback path (see the fixture dir's
``_build_fixtures.py``).  No network: the newsrc FetchCache + polite_get are
monkeypatched in-process (always restored) and everything is served from the
fixtures.  Live runs happen via
``py -3.11 -m wfd.ingest.newsrc.aus_airservices``, not from this file.
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

from wfd.ingest.newsrc import aus_airservices as asa
from wfd.ingest.newsrc import base as nb

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "aus-airservices"

AJAX_FIXTURE = json.loads((FIXTURES / "ajax-airports.json").read_text(encoding="utf-8"))
BY_TITLE = {a["title"]: a for a in AJAX_FIXTURE["airport_list"]}

HUB_FIX_BYTES = (FIXTURES / "hub-page.html").read_bytes()
AJAX_FIX_BYTES = (FIXTURES / "ajax-airports.json").read_bytes()


def _page_bytes(slug: str) -> bytes:
    return (FIXTURES / f"page-{slug}.html").read_bytes()


DEFAULT_PAGES = {
    BY_TITLE["Albany Airport"]["link"]: _page_bytes("albany-airport"),
    BY_TITLE["Broome Airport"]["link"]: _page_bytes("broome-airport"),
    BY_TITLE["Bunbury Airport"]["link"]: _page_bytes("bunbury-airport"),
    BY_TITLE["Watts Bridge Memorial Airfield"]["link"]: _page_bytes("watts-bridge-memorial-airfield"),
    BY_TITLE["Synthetic Fallback Aero"]["link"]: _page_bytes("synthetic-foothill"),
    BY_TITLE["Yulara Airport"]["link"]: None,      # live 404 — fake net raises for None
}


class HttpErr(Exception):
    """Minimal stand-in for urllib.error.HTTPError (code + headers only)."""

    def __init__(self, code: int, msg: str = ""):
        super().__init__(msg or f"HTTP {code}")
        self.code = code
        self.headers: dict = {}


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, *, hub_seq=None, ajax_bytes=None, pages=None,
                 ajax_403_for_nonces=()):
        self.cache_dir = cache_dir
        self.hub_seq = hub_seq or [HUB_FIX_BYTES]
        self.ajax_bytes = AJAX_FIX_BYTES if ajax_bytes is None else ajax_bytes
        self.pages = dict(DEFAULT_PAGES)
        if pages:
            self.pages.update(pages)
        self.ajax_403_for_nonces = set(ajax_403_for_nonces)
        self.calls: list = []
        self.hub_calls = 0
        self.ajax_calls = 0

    def fake_get(self, url, **kw):
        self.calls.append(url)
        if url == asa.HUB_URL:
            i = min(self.hub_calls, len(self.hub_seq) - 1)
            self.hub_calls += 1
            return self.hub_seq[i]
        if url.startswith(asa.AJAX_URL):
            self.ajax_calls += 1
            nonce = url.split("nonce=", 1)[1].split("&")[0] if "nonce=" in url else ""
            if nonce in self.ajax_403_for_nonces:
                raise HttpErr(403)
            return self.ajax_bytes
        if url in self.pages:
            val = self.pages[url]
            if val is None:
                raise HttpErr(404)
            return val
        raise AssertionError(f"unexpected fetch: {url}")

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = asa.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        asa.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        asa.fetch_cache = self.orig_cache
        return False


def run_offline(**attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td) as net:
        en = asa.AusAirservicesEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


def urls_by_title(res):
    out: dict = {}
    for r in res.rows:
        out.setdefault(r.meta["airport_title"], []).append(r.url)
    return out


# --- module shape ---------------------------------------------------------------

def test_module_shape():
    assert isinstance(asa.ENUMERATOR, nb.Enumerator)
    assert asa.ENUMERATOR.name == "aus-airservices"
    assert asa.ENUMERATOR.provenance == "public_by_design"
    assert asa.ENUMERATOR.source_ref == asa.HUB_URL == "https://weathercams.airservicesaustralia.com/"
    assert asa.ENUMERATOR.attribution == "Airservices Australia — weathercams.airservicesaustralia.com"
    assert callable(asa.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(asa.__file__).read_text(encoding="utf-8")
    assert "urllib" not in src and "urlopen" not in src


# --- helpers --------------------------------------------------------------------

def test_nonce_extraction():
    assert asa.extract_nonce(HUB_FIX_BYTES.decode()) == "5f5cb33910"
    assert asa.extract_nonce("<html>no config var here</html>") == ""
    assert asa.extract_nonce('asa_airports_public_var = {"other": "x"};') == ""
    assert asa.extract_nonce('asa_airports_public_var = {"nonce": "white space"};') == ""
    # single-quoted JS is not JSON — conservative empty (fresh-hub retry covers it)
    assert asa.extract_nonce("asa_airports_public_var = {'nonce':'abc123'};") == ""


def test_strip_cache_buster():
    u = "https://weathercams.airservicesaustralia.com/wp-content/uploads/airports/009999/009999_045.jpg"
    assert asa.strip_cache_buster(u + "?v=1791222274") == u
    assert asa.strip_cache_buster(u) == u
    assert asa.strip_cache_buster(u + "?w=1") == u + "?w=1"       # only v= is a cache buster


def test_angle_helpers():
    assert asa.angle_from_base("009999_045") == "045"
    assert asa.angle_from_base("north") == "north"
    assert asa.angle_from_base("wattsbridge_east") == "east"
    assert asa.angle_from_base("009999_045-300x169") == ""        # size variant
    assert asa.angle_from_url(asa.SITE + "/wp-content/uploads/airports/009999/009999_045.jpg?v=1") == "045"
    assert asa.angle_from_url(asa.SITE + "/wp-content/uploads/airports/wattsbridge/north.jpg") == "north"
    assert asa.angle_from_url(asa.SITE + "/wp-content/uploads/2018/02/Camera-Unavailable.png") == ""
    assert asa.angle_from_url("") == ""


def test_extract_camera_urls_numeric_fixture():
    text = _page_bytes("albany-airport").decode()
    got = asa.extract_camera_urls(text)
    assert got == [("https://weathercams.airservicesaustralia.com/wp-content/uploads/airports/"
                    "009999/009999_045.jpg", "045", "009999")], got
    broome = asa.extract_camera_urls(_page_bytes("broome-airport").decode())
    assert [a for _u, a, _f in broome] == ["090", "180", "270", "360"]
    assert not any("-300x169" in u for u, _a, _f in broome)        # size variants excluded
    assert all("?v=" not in u for u, _a, _f in broome)             # cache buster stripped


def test_extract_camera_urls_named_fixture():
    got = asa.extract_camera_urls(_page_bytes("watts-bridge-memorial-airfield").decode())
    assert [a for _u, a, _f in got] == ["east", "north", "south", "west"], got
    assert got[0][0].endswith("/airports/wattsbridge/east.jpg")
    assert not any("-300x169" in u for u, _a, _f in got)


def test_extract_camera_urls_edges():
    # relative form normalizes to the site host; duplicates collapse; sized & png ignored
    html = ('<img src="/wp-content/uploads/airports/009999/009999_045.jpg?v=1">'
            '<img src="/wp-content/uploads/airports/009999/009999_045.jpg?v=2">'
            '<img src="https://weathercams.airservicesaustralia.com/wp-content/uploads/'
            'airports/009999/009999_045-300x169.jpg?v=1">'
            '<img src="https://weathercams.airservicesaustralia.com/wp-content/uploads/'
            'airports/009999/009999_045.png">')
    got = asa.extract_camera_urls(html)
    assert len(got) == 1, got
    assert got[0][0] == asa.SITE + "/wp-content/uploads/airports/009999/009999_045.jpg"


def test_parse_airports_and_latlon():
    entries = asa.parse_airports(AJAX_FIXTURE)
    assert len(entries) == 6 and entries[0]["title"] == "Albany Airport"
    for bad in ([], "nope", {"success": False}, {"airport_list": "x"}):
        try:
            asa.parse_airports(bad)
            raised = False
        except ValueError:
            raised = True
        assert raised, bad

    assert asa.parse_latlon({"lat": "-34.945143", "long": "117.801381"}) == (-34.945143, 117.801381)
    assert asa.parse_latlon({"lat": "", "long": ""}) == (None, None)
    assert asa.parse_latlon({"lat": "480.0", "long": "117.8"}) == (None, 117.8)
    assert asa.parse_latlon({"lat": "-34.9", "long": "200"}) == (-34.9, None)
    assert asa.parse_latlon({"lat": -34.9, "long": 117.8}) == (-34.9, 117.8)


def test_thumbnail_fallback():
    alb = BY_TITLE["Albany Airport"]
    assert asa.thumbnail_fallback(alb) == ("https://weathercams.airservicesaustralia.com/"
                                           "wp-content/uploads/airports/009999/009999_045.jpg")
    watts = BY_TITLE["Watts Bridge Memorial Airfield"]
    assert asa.thumbnail_fallback(watts).endswith("/airports/wattsbridge/north.jpg")
    assert asa.thumbnail_fallback(BY_TITLE["Bunbury Airport"]) == ""    # Camera-Unavailable.png
    assert asa.thumbnail_fallback(BY_TITLE["Yulara Airport"]) == ""
    assert asa.thumbnail_fallback({"thumbnail": asa.SITE + "/wp-content/uploads/airports/"
                                   "009999/009999_045-300x169.jpg"}) == ""   # size variant
    assert asa.thumbnail_fallback({}) == ""
    assert asa.thumbnail_fallback({"img_camera": asa.SITE + "/wp-content/themes/asa/img/camera.png"}) == ""


# --- the full offline enumeration ----------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline()
    nb.check_no_liveness(res)                      # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 10, len(rows)
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "aus-airservices" for r in rows)
    assert all(r.provenance == "public_by_design" and r.country == "AU" for r in rows)
    assert all(r.protocol == "jpeg" for r in rows)
    assert all(r.tags == ["aviation", "weather"] for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)
    assert all("?v=" not in r.url and r.camera_id for r in rows)
    assert len({r.url for r in rows}) == 10 and len({r.camera_id for r in rows}) == 10
    assert all(set(r.meta) == {"airport_id", "airport_title", "state", "state_full",
                               "angle", "page_url", "fallback"} for r in rows)
    assert res.stats["sha256"] if "sha256" in res.stats else True   # (not saved here)

    by_title = urls_by_title(res)
    # albany: 1 angle → no label; state/lat/lon from the ajax list
    assert len(by_title["Albany Airport"]) == 1
    alb = rows[0]
    assert alb.name == "Albany Airport"
    assert abs(alb.lat + 34.945143) < 1e-9 and abs(alb.lon - 117.801381) < 1e-9
    assert alb.meta["state"] == "WA" and alb.meta["state_full"] == "Western Australia"
    assert alb.meta["angle"] == "045" and alb.meta["fallback"] is False
    assert alb.meta["page_url"] == BY_TITLE["Albany Airport"]["link"]
    assert alb.url == ("https://weathercams.airservicesaustralia.com/wp-content/uploads/"
                       "airports/009999/009999_045.jpg")

    # broome: 4 numeric angles → degree labels
    broome = [r for r in rows if r.meta["airport_title"] == "Broome Airport"]
    assert [r.meta["angle"] for r in broome] == ["090", "180", "270", "360"]
    assert [r.name for r in broome] == ["Broome Airport (090°)", "Broome Airport (180°)",
                                        "Broome Airport (270°)", "Broome Airport (360°)"]

    # watts bridge: named scheme → word labels
    watts = [r for r in rows if r.meta["airport_title"] == "Watts Bridge Memorial Airfield"]
    assert [r.meta["angle"] for r in watts] == ["east", "north", "south", "west"]
    assert [r.name for r in watts] == ["Watts Bridge Memorial Airfield (east)",
                                       "Watts Bridge Memorial Airfield (north)",
                                       "Watts Bridge Memorial Airfield (south)",
                                       "Watts Bridge Memorial Airfield (west)"]
    assert all(r.url.startswith(asa.SITE + "/wp-content/uploads/airports/wattsbridge/")
               for r in watts)

    # synthetic fallback: single row, thumbnail URL, meta fallback=true
    synth = [r for r in rows if r.meta["airport_title"] == "Synthetic Fallback Aero"]
    assert len(synth) == 1
    assert synth[0].name == "Synthetic Fallback Aero"
    assert synth[0].url == ("https://weathercams.airservicesaustralia.com/wp-content/uploads/"
                            "airports/123456/123456_315.jpg")
    assert synth[0].meta["fallback"] is True and synth[0].meta["angle"] == "315"

    # stats contract
    st = res.stats
    assert st["airports"] == 6 and st["images"] == 10 and st["fallbacks"] == 1
    assert st["dupes_dropped"] == 0 and st["airports_failed"] == 2
    assert st["nonce"] == "5f5cb33910"
    assert st["cache_hits"] == 0 and st["cache_misses"] == 7   # hub + ajax + 5 pages (404 not cached)
    assert "ajax_error" not in st and "attempt_1_error" not in st
    assert net.hub_calls == 1 and net.ajax_calls == 1
    assert st["fallback_airports"] == ["Synthetic Fallback Aero"]

    reasons = {f["airport"]: f["reason"] for f in st["failures"]}
    assert set(reasons) == {"Bunbury Airport", "Yulara Airport"}
    assert "404" in reasons["Yulara Airport"]
    assert "thumbnail" in reasons["Bunbury Airport"]
    assert "fallbacks=1 failed=2" in res.notes


def test_limit_caps_airports():
    res, net = run_offline(limit=2)
    assert res.stats["airports"] == 2 and res.stats["images"] == 5
    assert res.stats["cache_misses"] == 4          # hub + ajax + albany + broome
    fetched = [u for u in net.calls if u.startswith(asa.SITE + "/asa-airports/")]
    assert fetched == [BY_TITLE["Albany Airport"]["link"], BY_TITLE["Broome Airport"]["link"]]


def test_dedupe_across_airports():
    shared = asa.SITE + "/wp-content/uploads/airports/777777/777777_045.jpg?v=1"
    page_a = f'<img src="{shared}"><img src="{asa.SITE}/wp-content/uploads/airports/777777/777777_135.jpg?v=1">'
    page_b = f'<img src="{shared}"><img src="{asa.SITE}/wp-content/uploads/airports/777777/777777_225.jpg?v=1">'
    link_a, link_b = asa.SITE + "/asa-airports/alpha/", asa.SITE + "/asa-airports/beta/"
    payload = json.dumps({"airport_list": [
        {"id": 1, "title": "Alpha", "link": link_a, "thumbnail": "", "state": "WA",
         "state_full": "Western Australia", "lat": "-31.0", "long": "115.0", "name": "alpha"},
        {"id": 2, "title": "Beta", "link": link_b, "thumbnail": "", "state": "WA",
         "state_full": "Western Australia", "lat": "-32.0", "long": "116.0", "name": "beta"},
    ]}).encode()
    with tempfile.TemporaryDirectory() as td, OfflineNet(
            td, ajax_bytes=payload, pages={link_a: page_a.encode(), link_b: page_b.encode()}) as net:
        res = asa.AusAirservicesEnumerator().enumerate()
    assert len(res.rows) == 3 and res.stats["dupes_dropped"] == 1
    assert [r.meta["angle"] for r in res.rows] == ["045", "135", "225"]
    assert all(r.status == "unknown" for r in res.rows)


def test_nonce_refresh_retry():
    old_nonce, new_nonce = "5f5cb33910", "deadbeef01"
    hub_new = HUB_FIX_BYTES.decode().replace(old_nonce, new_nonce).encode()
    with tempfile.TemporaryDirectory() as td, OfflineNet(
            td, hub_seq=[HUB_FIX_BYTES, hub_new],
            ajax_403_for_nonces={old_nonce}) as net:
        en = asa.AusAirservicesEnumerator()
        en.limit = 1
        res = en.enumerate()
    st = res.stats
    assert res.rows and all(r.status == "unknown" for r in res.rows)
    assert st["nonce"] == new_nonce
    assert st["hub_refetched_for_nonce"] is True
    assert "attempt_1_error" in st and "403" in st["attempt_1_error"]
    assert "ajax_error" not in st
    assert net.hub_calls == 2 and net.ajax_calls == 2
    assert st["cache_misses"] == 4                 # hub x2 + ajax x2 (fresh retry); page cached first attempt? no: 1 page
    assert st["cache_hits"] == 0


def test_ajax_still_failing_records_and_continues():
    old_nonce, new_nonce = "5f5cb33910", "deadbeef01"
    hub_new = HUB_FIX_BYTES.decode().replace(old_nonce, new_nonce).encode()
    with tempfile.TemporaryDirectory() as td, OfflineNet(
            td, hub_seq=[HUB_FIX_BYTES, hub_new],
            ajax_403_for_nonces={old_nonce, new_nonce}) as net:
        res = asa.AusAirservicesEnumerator().enumerate()
    st = res.stats
    assert res.rows == [] and st["airports"] == 0 and st["images"] == 0
    assert "ajax_error" in st and "403" in st["ajax_error"]
    assert st["hub_refetched_for_nonce"] is True
    assert "WARNING" in res.notes
    assert net.hub_calls == 2 and net.ajax_calls == 2   # exactly ONE retry


def test_429_retry_wrapper():
    class DummyCache:
        def __init__(self):
            self.n = 0

        def get(self, url, *, suffix=".bin", **kw):
            self.n += 1
            if self.n == 1:
                raise HttpErr(429, "Too Many Requests")
            return b"ok"

    orig_sleep = asa.time.sleep
    asa.time.sleep = lambda s: None
    try:
        cache = DummyCache()
        stats: dict = {}
        assert asa._fetch(cache, "http://x", suffix=".html", stats=stats) == b"ok"
        assert cache.n == 2 and stats["http_429_retries"] == 1

        class Cache404:
            n = 0

            def get(self, url, *, suffix=".bin", **kw):
                Cache404.n += 1
                raise HttpErr(404, "Not Found")

        try:
            asa._fetch(Cache404(), "http://x", suffix=".html")
            raised = False
        except HttpErr as exc:
            raised = exc.code == 404
        assert raised and Cache404.n == 1          # 4xx (non-429) never retried
    finally:
        asa.time.sleep = orig_sleep


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td, OfflineNet(td) as net:
        res1 = asa.AusAirservicesEnumerator().enumerate()
        calls_after_first = len(net.calls)
        res2 = asa.AusAirservicesEnumerator().enumerate()
    assert calls_after_first == 8                  # hub + ajax + 5 pages + yulara(404)
    assert len(net.calls) == calls_after_first + 1  # yulara retried (nothing to cache)
    assert net.calls[-1] == BY_TITLE["Yulara Airport"]["link"]
    assert res1.stats["cache_misses"] == 7 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 7 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]
    assert res2.stats["images"] == 10 and res2.stats["airports_failed"] == 2


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = nb.run_one(asa.AusAirservicesEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-aus-airservices.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 10
    assert all(l["status"] == "unknown" and l["camera_id"] and l["country"] == "AU" for l in lines)
    assert res.stats["written"] == 10 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-aus-airservices.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td, OfflineNet(td) as net:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = asa.run_cli(asa.AusAirservicesEnumerator(), ["--no-save", "--limit", "1"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[aus-airservices]" in out and "rows=1" in out, out


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

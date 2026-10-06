"""wfd.resolve tests — plain runner. Run: py -3.11 tests/test_resolve.py

Unit tests run fully offline against the fixture page/playlist and a TEMP
WFD_DATA_DIR cache root (nothing under data/ is touched by this file). The
final test is a real-network end-to-end proof for one skyline cam; when the
network is unavailable it fails loudly rather than pretending.

Test functions are named test_* so they also work under pytest.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# --- temp cache root BEFORE any resolve call (module may be imported next) ---
_OLD_DATA_DIR = os.environ.get("WFD_DATA_DIR")
_TMP = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["WFD_DATA_DIR"] = _TMP.name
CACHE_ROOT = pathlib.Path(_TMP.name)

from wfd import db as dbmod          # noqa: E402
from wfd import profile              # noqa: E402
from wfd import resolve              # noqa: E402
from wfd import viewer               # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "resolve"
DB_PATH = dbmod.DEFAULT_DB
SKYLINE_CID = "507b64f69e709039"
SKYLINE_URL = ("https://www.skylinewebcams.com/en/webcam/ellada/crete/"
               "heraklion/viannos.html")

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4096          # sniffable, >1KB
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _iso_ago(seconds: float) -> str:
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds)
    return when.isoformat(timespec="seconds")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _write_cache_json(relpath: str, data: dict) -> None:
    path = CACHE_ROOT / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    resolve.reset_caches()


def _db_one(sql: str, args=()):
    import sqlite3
    conn = sqlite3.connect(f"file:{pathlib.Path(DB_PATH).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# unit tests — fixtures + pure functions (no network)
# ---------------------------------------------------------------------------

def test_fixture_token_regex():
    html = _read_fixture("skyline_page.html")
    m = resolve.SKYLINE_TOKEN_RE.search(html)
    assert m, "no source:'livee.m3u8?a=...' token in the fixture page"
    assert len(m.group(1)) >= 10, m.group(1)
    inline = resolve.SKYLINE_TOKEN_RE.search("x source:'livee.m3u8?a=abc123' y")
    assert inline and inline.group(1) == "abc123"


def test_fixture_og_image():
    html = _read_fixture("skyline_page.html")
    og = resolve.parse_social_image(html, SKYLINE_URL)
    assert og == "https://cdn.skylinewebcams.com/social5081.jpg", og
    # twitter:image fallback, relative -> absolute
    assert (resolve.parse_social_image(
        '<meta name="twitter:image" content="/img/x.png">', "https://a.example/p")
        == "https://a.example/img/x.png")
    # attribute order must not matter
    assert (resolve.parse_social_image(
        '<meta content="https://x.example/y.jpg" property="og:image">')
        == "https://x.example/y.jpg")
    # og:image wins over twitter:image
    both = ('<meta name="twitter:image" content="https://t/x.png">'
            '<meta property="og:image" content="https://o/y.jpg">')
    assert resolve.parse_social_image(both) == "https://o/y.jpg"
    assert resolve.parse_social_image("<html>no meta here</html>") is None


def test_host_resolvable_mapping():
    assert resolve.host_resolvable(SKYLINE_URL) == "skylinewebcams"
    assert resolve.host_resolvable("https://skylinewebcams.com/x") == "skylinewebcams"
    assert resolve.host_resolvable("https://www.youtube.com/watch?v=abcdefghijk") == "youtube-live"
    assert resolve.host_resolvable("https://youtu.be/abcdefghijk") == "youtube-live"
    assert resolve.host_resolvable("https://example.com/cam") is None
    assert resolve.host_resolvable("") is None
    assert resolve.host_resolvable(None) is None


def test_seg_name_validation():
    assert resolve.SEG_NAME_RE.fullmatch("5081livic-1791258027334.ts")
    assert not resolve.SEG_NAME_RE.fullmatch("a/b")
    assert not resolve.SEG_NAME_RE.fullmatch("")
    assert not resolve.SEG_NAME_RE.fullmatch("x" * 181)
    assert (resolve._seg_name_from_url(
        "https://hddn53.skylinewebcams.com/5081livic-1791258027334.ts")
        == "5081livic-1791258027334.ts")
    assert resolve._seg_name_from_url("https://h.example/a b.ts?q=1") == "a_b.ts"
    long_name = resolve._seg_name_from_url("https://h.example/" + "z" * 300 + ".ts")
    assert resolve.SEG_NAME_RE.fullmatch(long_name) and len(long_name) == 180


def test_playlist_rewrite():
    resolve.reset_caches()
    cid = "c" * 16
    text = _read_fixture("skyline_playlist.m3u8")
    out = resolve.resolve_playlist(cid, text, "marker:test")
    assert "/api/live/cccccccccccccccc/seg/5081livic-1791258027334.ts" in out
    assert "hddn53.skylinewebcams.com" not in out
    assert out.startswith("#EXTM3U")
    assert "#EXTINF:3.000," in out                       # tags preserved
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            assert line.startswith(f"/api/live/{cid}/seg/"), line
    upstream = resolve.seg_upstream(cid, "5081livic-1791258027334.ts")
    assert upstream == "https://hddn53.skylinewebcams.com/5081livic-1791258027334.ts", upstream
    # URI="..." attributes (keys / init maps) are rewritten + registered too
    key_playlist = ('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://keys.example/k.bin"\n'
                    "#EXTINF:3.000,\nhttps://cdn.example.com/seg one.ts\n")
    out2 = resolve.resolve_playlist("d" * 16, key_playlist, "m2")
    assert 'URI="/api/live/' + "d" * 16 + '/seg/k.bin"' in out2, out2
    assert "/api/live/" + "d" * 16 + "/seg/seg_one.ts" in out2
    assert resolve.seg_upstream("d" * 16, "k.bin") == "https://keys.example/k.bin"
    # relative names are left alone (no base to resolve them against)
    out3 = resolve.resolve_playlist("e" * 16, "#EXTM3U\nrelative.ts\n", "m3")
    assert "relative.ts" in out3 and "/seg/" not in out3
    assert resolve.seg_upstream("e" * 16, "relative.ts") is None


def test_filler_detection():
    filler = ("#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:3.000,\n"
              "https://hddn53.skylinewebcams.com/copyright_violation-1234.ts\n")
    assert resolve.is_filler(filler)
    assert not resolve.is_filler(_read_fixture("skyline_playlist.m3u8"))
    try:
        resolve.resolve_playlist("f" * 16, filler, "m")
        raise AssertionError("expected FillerError for a filler playlist")
    except resolve.FillerError:
        pass
    # the real playlist must rewrite without raising
    resolve.resolve_playlist("f" * 16, _read_fixture("skyline_playlist.m3u8"), "m")


def test_poster_flow_offline():
    html = _read_fixture("skyline_page.html")
    calls = {"page": 0, "img": 0}
    orig_page, orig_get = resolve.fetch_page, resolve._http_get

    def fake_page(url, **kw):
        calls["page"] += 1
        return {"html": html, "cookie": "PHPSESSID=secretcookie", "final_url": url}

    def fake_page_no_og(url, **kw):
        calls["page"] += 1
        return {"html": "<html><head></head><body>plain</body></html>",
                "cookie": "", "final_url": url}

    def fake_get(url, **kw):
        calls["img"] += 1
        return _JPEG, {"content-type": "image/jpeg"}, url

    resolve.fetch_page = fake_page
    resolve._http_get = fake_get
    try:
        resolve.reset_caches()
        cid = "1" * 16
        path = resolve.get_poster(cid, SKYLINE_URL, force=True)
        assert path is not None and path.exists()
        assert path.name == f"{cid}.jpg" and path.parent == resolve.posters_dir()
        assert path.read_bytes() == _JPEG
        entry = resolve.poster_index_entry(cid)
        assert entry and entry["ok"] is True and entry["source"] == "og"
        assert entry.get("fetched_at")
        assert resolve.poster_exists(cid)
        assert resolve.cached_poster_url(cid) == f"/api/poster/{cid}"
        assert not resolve.poster_needs_refresh(cid)
        on_disk = json.loads((CACHE_ROOT / "posters" / "index.json").read_text(encoding="utf-8"))
        assert cid in on_disk and on_disk[cid]["ok"] is True
        assert not list((CACHE_ROOT / "posters").glob("*.tmp"))   # atomic write cleaned up
        # a fresh cache verdict means NO network on the next call
        n_page, n_img = calls["page"], calls["img"]
        again = resolve.get_poster(cid, SKYLINE_URL)
        assert again == path and calls["page"] == n_page and calls["img"] == n_img
        # positive TTL: 11h old still fresh, 13h old needs refresh
        on_disk[cid]["fetched_at"] = _iso_ago(11 * 3600)
        _write_cache_json("posters/index.json", on_disk)
        assert not resolve.poster_needs_refresh(cid)
        on_disk[cid]["fetched_at"] = _iso_ago(13 * 3600)
        _write_cache_json("posters/index.json", on_disk)
        assert resolve.poster_needs_refresh(cid)
        # negative path: page without og:image -> None + negative verdict
        resolve.fetch_page = fake_page_no_og
        cid2 = "2" * 16
        assert resolve.get_poster(cid2, SKYLINE_URL, force=True) is None
        neg = resolve.poster_index_entry(cid2)
        assert neg and neg["ok"] is False and neg["source"] == "fail"
        assert not resolve.poster_needs_refresh(cid2)      # fresh negative (1h TTL)
        n_page = calls["page"]
        assert resolve.get_poster(cid2, SKYLINE_URL) is None
        assert calls["page"] == n_page                     # negative cache short-circuits
        # negative goes stale after 1h
        on_disk = json.loads((CACHE_ROOT / "posters" / "index.json").read_text(encoding="utf-8"))
        on_disk[cid2]["fetched_at"] = _iso_ago(2 * 3600)
        _write_cache_json("posters/index.json", on_disk)
        assert resolve.poster_needs_refresh(cid2)
    finally:
        resolve.fetch_page = orig_page
        resolve._http_get = orig_get
        resolve.reset_caches()


def test_live_cache_offline():
    cid, cid2 = "3" * 16, "4" * 16
    calls = {"ok": 0, "fail": 0}
    orig = resolve.resolve_live_skyline

    def fake_ok(url):
        calls["ok"] += 1
        return {"kind": "hls",
                "url": "https://hd-auth.skylinewebcams.com/live.m3u8?a=T0KEN",
                "headers": {"User-Agent": "x",
                            "Referer": "https://www.skylinewebcams.com/"},
                "ttl_s": 600,
                "poster": "https://cdn.skylinewebcams.com/social1.jpg"}

    def fake_fail(url):
        calls["fail"] += 1
        return None

    resolve.resolve_live_skyline = fake_ok
    try:
        resolve.reset_caches()
        entry = resolve.get_live(cid, SKYLINE_URL)
        assert entry and entry["kind"] == "hls" and entry["ok"] is True
        assert entry["resolved_at"] and entry["host"] == "www.skylinewebcams.com"
        assert calls["ok"] == 1
        cached = resolve.get_live(cid, SKYLINE_URL)
        assert cached["url"].endswith("T0KEN") and calls["ok"] == 1
        assert resolve.cached_live(cid) is True
        assert resolve.cached_live_entry(cid)["poster"].endswith("social1.jpg")
        assert not resolve.live_needs_refresh(cid)
        resolve.get_live(cid, SKYLINE_URL, force=True)          # force re-resolves
        assert calls["ok"] == 2
        # stale (age > ttl) -> not cached; needs refresh again
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        data[cid]["resolved_at"] = _iso_ago(700)
        _write_cache_json("resolve/live.json", data)
        assert resolve.cached_live(cid) is None
        assert resolve.live_needs_refresh(cid)
        # negative results cached 120s
        resolve.resolve_live_skyline = fake_fail
        assert resolve.get_live(cid2, SKYLINE_URL) is None
        assert calls["fail"] == 1
        assert resolve.get_live(cid2, SKYLINE_URL) is None
        assert calls["fail"] == 1                               # negative TTL blocks retry
        assert resolve.cached_live(cid2) is False
        assert not resolve.live_needs_refresh(cid2)
        resolve.get_live(cid2, SKYLINE_URL, force=True)
        assert calls["fail"] == 2                               # force bypasses negative
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        data[cid2]["resolved_at"] = _iso_ago(200)
        _write_cache_json("resolve/live.json", data)
        assert resolve.live_needs_refresh(cid2)                 # stale negative re-opens
    finally:
        resolve.resolve_live_skyline = orig
        resolve.reset_caches()


def test_youtube_resolver_offline():
    orig_tool, orig_run = resolve._tool, resolve._run
    try:
        resolve._tool = lambda name: "yt-dlp" if name == "yt-dlp" else None
        resolve._run = lambda cmd, timeout: (0, "M1n2O3p4Q5r\n", "")
        res = resolve.resolve_live_youtube("https://www.youtube.com/watch?v=M1n2O3p4Q5r")
        assert res and res["kind"] == "ytid" and res["id"] == "M1n2O3p4Q5r"
        assert res["poster"] == "https://i.ytimg.com/vi/M1n2O3p4Q5r/hqdefault.jpg"
        assert res["ttl_s"] == 1800
        resolve._run = lambda cmd, timeout: (1, "", "boom")
        assert resolve.resolve_live_youtube("https://youtu.be/M1n2O3p4Q5r") is None
        resolve._tool = lambda name: None
        assert resolve.resolve_live_youtube("https://youtu.be/M1n2O3p4Q5r") is None
    finally:
        resolve._tool, resolve._run = orig_tool, orig_run


def test_count_resolvable_rows():
    n = resolve.count_resolvable_rows(DB_PATH)
    assert n > 1500, f"expected the skyline iframe family in the registry, got {n}"


def test_redaction_helpers():
    assert resolve.redact("secret-token") != "secret-token"
    assert len(resolve.redact("secret-token")) == 8
    shown = resolve.redact_url_for_display(
        "https://hd-auth.skylinewebcams.com/live.m3u8?a=SUPERSECRET")
    assert "SUPERSECRET" not in shown
    assert "hd-auth.skylinewebcams.com" in shown
    assert (resolve.redact_url_for_display("https://x.example/plain.m3u8")
            == "https://x.example/plain.m3u8")


# ---------------------------------------------------------------------------
# server tests (offline; real registry db, temp caches)
# ---------------------------------------------------------------------------

_state = {"server": None, "base": None}


def _base() -> str:
    if _state["base"] is None:
        prefs_path = CACHE_ROOT / "viewer-prefs-resolve-test.json"
        server = viewer.make_server(port=0, quiet=True, prefs_path=prefs_path,
                                    resolve_enabled=True)
        threading.Thread(target=server.serve_forever,
                         name="wfd-resolve-test", daemon=True).start()
        _state["server"] = server
        _state["base"] = f"http://127.0.0.1:{server.server_address[1]}"
    return _state["base"]


def _shutdown():
    server = _state.pop("server", None)
    if server is not None:
        server.shutdown()
        server.server_close()
    _state["base"] = None


def _get_json(path: str):
    with urllib.request.urlopen(_base() + path, timeout=30) as resp:
        return (resp.status, resp.headers.get("Content-Type", ""),
                json.loads(resp.read().decode("utf-8")))


def _get_http(path_or_url):
    url = path_or_url if str(path_or_url).startswith("http") else _base() + path_or_url
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, ctype, exc.read()


def _post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _base() + path, data=data, method="POST",
        headers={"Content-Type": "application/json", "X-WFD-Viewer": "1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _seed_skyline_poster():
    posters = CACHE_ROOT / "posters"
    posters.mkdir(parents=True, exist_ok=True)
    (posters / f"{SKYLINE_CID}.jpg").write_bytes(_JPEG)
    idx_path = posters / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    idx[SKYLINE_CID] = {"ok": True, "fetched_at": _now_iso(), "source": "og"}
    idx_path.write_text(json.dumps(idx), encoding="utf-8")
    resolve.reset_caches()


def _seed_skyline_live():
    rdir = CACHE_ROOT / "resolve"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "live.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[SKYLINE_CID] = {
        "ok": True, "kind": "hls",
        "url": "https://hd-auth.skylinewebcams.com/live.m3u8?a=SEEDTOKEN",
        "headers": {"User-Agent": "x", "Referer": "https://www.skylinewebcams.com/"},
        "ttl_s": 600, "resolved_at": _now_iso(), "host": "www.skylinewebcams.com",
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    resolve.reset_caches()


def test_server_camera_detail_fields():
    _base()
    _seed_skyline_poster()
    _seed_skyline_live()
    status, ctype, d = _get_json(f"/api/camera/{SKYLINE_CID}")
    assert status == 200 and ctype.startswith("application/json")
    assert d["provenance"] == "public_by_design"
    assert d["resolvable"] is True
    assert d["live_url"] == f"/api/live/{SKYLINE_CID}/index.m3u8"
    assert d["poster_url"] == f"/api/poster/{SKYLINE_CID}"
    # a non-resolvable display row still gets resolvable=False, no live_url
    row = _db_one("SELECT camera_id FROM cameras WHERE provenance='public_by_design' "
                  "AND url LIKE 'http%' AND url NOT LIKE '%skylinewebcams.com%' "
                  "AND url NOT LIKE '%youtube.com%' LIMIT 1")
    assert row, "no non-resolvable public row in the registry"
    _, _, d2 = _get_json(f"/api/camera/{row['camera_id']}")
    assert d2["resolvable"] is False, d2.get("resolvable")
    assert "live_url" not in d2 and "poster_url" not in d2


def test_server_exposure_rows_have_no_resolve_fields():
    _base()
    row = _db_one("SELECT camera_id FROM cameras WHERE provenance='exposure_aggregator' LIMIT 1")
    assert row, "no exposure rows in registry — gate test would be vacuous"
    exp_id = row["camera_id"]
    original = profile.settings
    profile.settings = lambda: {**original(), "private_exposure_surface": True}
    try:
        status, _, d = _get_json(f"/api/camera/{exp_id}")
        assert status == 200, status
        for key in ("resolvable", "live_url", "poster_url"):
            assert key not in d, (key, sorted(d))
        status, _, _ = _get_http(f"/api/poster/{exp_id}")
        assert status == 404, status
        status, _, _ = _get_http(f"/api/live/{exp_id}/index.m3u8")
        assert status == 404, status
        status, _, _ = _get_http(f"/api/live/{exp_id}/seg/x.ts")
        assert status == 404, status
    finally:
        profile.settings = original


def test_server_featurecollection_fields():
    _base()
    _seed_skyline_poster()
    _seed_skyline_live()
    status, _ = _post("/api/prefs/favourite", {"camera_id": SKYLINE_CID, "action": "add"})
    assert status == 200
    original = profile.settings
    profile.settings = lambda: {**original(), "private_exposure_surface": True}
    try:
        _, _, fc = _get_json("/api/cameras?favourites=1&geo=any&limit=100")
        matches = [f for f in fc["features"]
                   if f["properties"]["camera_id"] == SKYLINE_CID]
        assert matches, "skyline cam missing from the favourites feature list"
        p = matches[0]["properties"]
        assert p.get("resolvable") is True
        assert p.get("live_url") == f"/api/live/{SKYLINE_CID}/index.m3u8"
        assert p.get("poster_url") == f"/api/poster/{SKYLINE_CID}"
        # exposure features never carry any of the three fields
        _, _, fe = _get_json("/api/cameras?provenance=exposure&geo=any&limit=50")
        assert fe["features"], "exposure rows expected while surface is on"
        for f in fe["features"]:
            for key in ("resolvable", "live_url", "poster_url"):
                assert key not in f["properties"], (key, f["properties"].get("camera_id"))
    finally:
        profile.settings = original
        _post("/api/prefs/favourite", {"camera_id": SKYLINE_CID, "action": "remove"})


def test_server_poster_route():
    _base()
    _seed_skyline_poster()
    status, ctype, body = _get_http(f"/api/poster/{SKYLINE_CID}")
    assert status == 200, status
    assert ctype.startswith("image/jpeg"), ctype
    assert body == _JPEG and len(body) > 1024
    # HEAD: identical headers, no body
    req = urllib.request.Request(_base() + f"/api/poster/{SKYLINE_CID}", method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Length") == str(len(_JPEG))
        assert "max-age=600" in (resp.headers.get("Cache-Control") or "")
        assert resp.read() == b""
    # unknown camera + unknown id -> 404 JSON with an error
    status, _, body = _get_http("/api/poster/0000000000000000")
    assert status == 404, status
    assert json.loads(body).get("error")
    status, _, body = _get_http("/api/poster/not-a-camera")
    assert status == 404, status


def test_server_resolver_disabled():
    prefs_path = CACHE_ROOT / "viewer-prefs-resolve-off.json"
    server = viewer.make_server(port=0, quiet=True, prefs_path=prefs_path,
                                resolve_enabled=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _seed_skyline_poster()
        _seed_skyline_live()
        with urllib.request.urlopen(base + f"/api/camera/{SKYLINE_CID}", timeout=30) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        for key in ("resolvable", "live_url", "poster_url"):
            assert key not in d, (key, sorted(d))
        for path in (f"/api/poster/{SKYLINE_CID}",
                     f"/api/live/{SKYLINE_CID}/index.m3u8",
                     f"/api/live/{SKYLINE_CID}/seg/x.ts"):
            try:
                urllib.request.urlopen(base + path, timeout=30)
                raise AssertionError(f"expected 404 for {path}")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, (path, exc.code)
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# live end-to-end proof (needs the internet; exercises the real recipe)
# ---------------------------------------------------------------------------

def test_live_end_to_end_skyline():
    resolve.reset_caches()
    entry = resolve.get_live(SKYLINE_CID, SKYLINE_URL, force=True)
    assert entry, "no live resolution for the skyline cam (network?)"
    assert entry.get("kind") == "hls", entry.get("kind")
    marker = resolve.redact(entry.get("url", ""))
    text = resolve.fetch_playlist(entry)
    if text is None or resolve.is_filler(text):
        entry = resolve.get_live(SKYLINE_CID, SKYLINE_URL, force=True)
        text = resolve.fetch_playlist(entry)
    assert text, "upstream playlist unavailable after refresh"
    assert not resolve.is_filler(text), "filler playlist twice (token/cookies stale)"
    rewritten = resolve.resolve_playlist(SKYLINE_CID, text, marker)
    seg_lines = [l.strip() for l in rewritten.splitlines()
                 if l.strip().startswith("/api/live/")]
    assert seg_lines, rewritten[:200]
    name = seg_lines[0].rsplit("/", 1)[-1]
    assert resolve.SEG_NAME_RE.fullmatch(name), name
    upstream = resolve.seg_upstream(SKYLINE_CID, name)
    assert upstream and upstream.startswith("http"), upstream
    blob, ctype = resolve.fetch_segment(upstream, entry.get("headers"))
    assert blob is not None, "segment fetch failed"
    assert len(blob) > 20 * 1024, f"segment too small: {len(blob)}"
    poster = resolve.get_poster(SKYLINE_CID, SKYLINE_URL, force=True)
    assert poster is not None and poster.exists(), "poster fetch failed"
    data = poster.read_bytes()
    assert len(data) > 1024, len(data)
    assert data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n", data[:8]
    print(f"  live: token=sha1:{marker} playlist={len(text)}B segments={len(seg_lines)} "
          f"seg[{name}]={len(blob)}B ctype={ctype or 'video/mp2t'}")
    print(f"  poster: {poster} ({len(data)}B, {resolve.image_content_type(data)})")


def test_dead_playlist_detection():
    # skyline answers an expired token with a 6-line placeholder playlist
    dead = ("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ALLOW-CACHE:NO\n"
            "#EXT-X-TARGETDURATION:0\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-ENDLIST\n")
    assert resolve.is_dead_playlist(dead)
    assert resolve.is_dead_playlist("")            # empty body counts as dead
    assert resolve.is_dead_playlist("#EXTM3U\n")   # header-only playlist
    assert not resolve.is_dead_playlist(_read_fixture("skyline_playlist.m3u8"))
    assert not resolve.is_dead_playlist(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:3.000,\nhttps://x/y.ts\n")
    assert not resolve.is_filler(dead)             # distinct failure classes


def test_live_playlist_refresh_on_dead_token():
    """A stale cached token serving the empty ENDLIST playlist must trigger one
    forced re-resolve and still answer with a live rewritten playlist."""
    _base()
    _seed_skyline_live()
    dead = ("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ALLOW-CACHE:NO\n"
            "#EXT-X-TARGETDURATION:0\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-ENDLIST\n")
    live = _read_fixture("skyline_playlist.m3u8")
    calls = {"fetch": [], "resolve": 0}
    real_fetch = resolve.fetch_playlist
    real_resolve = resolve.resolve_live_skyline

    def fake_fetch(entry, **kwargs):
        calls["fetch"].append(entry.get("url", ""))
        return dead if "SEEDTOKEN" in entry.get("url", "") else live

    def fake_resolve(page_url):
        calls["resolve"] += 1
        return {"kind": "hls",
                "url": "https://hd-auth.skylinewebcams.com/live.m3u8?a=FRESHTOKEN",
                "headers": {"User-Agent": "x",
                            "Referer": "https://www.skylinewebcams.com/"},
                "ttl_s": 300}

    resolve.fetch_playlist = fake_fetch
    resolve.resolve_live_skyline = fake_resolve
    try:
        status, ctype, body = _get_http(f"/api/live/{SKYLINE_CID}/index.m3u8")
    finally:
        resolve.fetch_playlist = real_fetch
        resolve.resolve_live_skyline = real_resolve
        resolve.reset_caches()
    assert status == 200, (status, body[:200])
    assert ctype.startswith("application/vnd.apple.mpegurl"), ctype
    text = body.decode("utf-8")
    assert f"/api/live/{SKYLINE_CID}/seg/" in text, text[:300]
    assert "hd-auth" not in text and "hddn" not in text, "upstream urls leaked"
    assert calls["resolve"] >= 1, "no forced re-resolve after the dead playlist"
    assert len(calls["fetch"]) >= 2, calls["fetch"]


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    _shutdown()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if _OLD_DATA_DIR is None:
        os.environ.pop("WFD_DATA_DIR", None)
    else:
        os.environ["WFD_DATA_DIR"] = _OLD_DATA_DIR
    _TMP.cleanup()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

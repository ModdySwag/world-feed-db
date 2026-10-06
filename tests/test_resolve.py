"""wfd.resolve tests — plain runner. Run: py -3.11 tests/test_resolve.py

Unit tests run fully offline against the fixture page/playlist and a TEMP
WFD_DATA_DIR cache root (nothing under data/ is touched by this file). The
final tests are real-network end-to-end proofs (the skyline cam chain and the
skaping still); when the network is unavailable they fail loudly rather than
pretending.

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
# Candidate cams for the live e2e proof. A single skyline cam can be OFFLINE
# for days (the site then serves a page with NO player/token — e.g. viannos on
# 2026-10-06); that is a valid cam state, not a resolver failure. The e2e walks
# candidates until one resolves to HLS and proves the full chain on it.
SKYLINE_CANDIDATES = [
    (SKYLINE_CID, SKYLINE_URL),                       # viannos (fixture cam)
    ("e2e0000000000trevi",
     "https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/fontana-di-trevi.html"),
    ("e2e00000000000etna",
     "https://www.skylinewebcams.com/en/webcam/italia/sicilia/catania/vulcano-etna-sud.html"),
    ("e2e000000sancassiano",
     "https://www.skylinewebcams.com/en/webcam/italia/trentino-alto-adige/bolzano/san-cassiano-dolomiti.html"),
    ("e2e000000000000tropea",
     "https://www.skylinewebcams.com/en/webcam/italia/calabria/vibo-valentia/tropea.html"),
]
SKAPING_CID = "eedcbc5b9badeb3f"
SKAPING_URL = "https://www.skaping.com/millau/pouncho/panoramique-droite"
SKAPING_STILL_URL = resolve.parse_social_image(
    (FIXTURES / "skaping_page.html").read_text(encoding="utf-8"), SKAPING_URL) or ""

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


def test_skyline_page_variants():
    """Three live page shapes: HLS token | YouTube embed | OFFLINE (no stream).

    The OFFLINE capture is the real viannos page (the fixture cam went down on
    2026-10-06): it carries NO 'livee.m3u8' token at all — which is what
    "the token moved" reports actually saw. The resolver must classify it as
    'offline' (a dead cam), never treat it as an extraction change, and never
    lose the classic HLS path for cams that do carry a token.
    """
    hls_html = _read_fixture("skyline_page.html")
    off_html = _read_fixture("skyline_page2.html")
    yt_html = _read_fixture("skyline_page_yt.html")
    assert resolve.skyline_variant(hls_html) == "hls"
    assert resolve.skyline_variant(off_html) == "offline"
    assert resolve.skyline_variant(yt_html) == "youtube"
    assert resolve.skyline_variant("<html>nothing here</html>") == "no-stream"
    assert resolve.skyline_variant("") == "no-stream"
    # the offline capture: no token, no youtube id — the OFFLINE marker says why
    assert resolve.SKYLINE_TOKEN_RE.search(off_html) is None
    assert resolve.SKYLINE_YT_ID_RE.search(off_html) is None
    assert 'class="request off"' in off_html and "OFFLINE" in off_html
    # the youtube capture: a valid 11-char video id and no HLS token
    m = resolve.SKYLINE_YT_ID_RE.search(yt_html)
    assert m and resolve._YOUTUBE_ID_RE.fullmatch(m.group(1)), m and m.group(0)
    assert resolve.SKYLINE_TOKEN_RE.search(yt_html) is None


def test_skyline_resolver_page_variants_offline():
    """resolve_live_skyline handles every page variant; reasons are recorded."""
    hls_html = _read_fixture("skyline_page.html")
    off_html = _read_fixture("skyline_page2.html")
    yt_html = _read_fixture("skyline_page_yt.html")
    orig = resolve.fetch_page
    try:
        # 1) the classic HLS path still wins when the token is present
        resolve.fetch_page = lambda url, **kw: {
            "html": hls_html, "cookie": "PHPSESSID=x", "final_url": url}
        out = resolve.resolve_live_skyline(SKYLINE_URL)
        assert out and out["kind"] == "hls" and "live.m3u8?a=" in out["url"], out
        assert out["headers"].get("Cookie") == "PHPSESSID=x"
        assert out["headers"].get("Referer") == "https://www.skylinewebcams.com/"
        assert resolve.skyline_failure_reason(SKYLINE_URL) == ""
        # 2) YouTube-hosted cam -> kind ytid (the viewer embeds the YT player)
        resolve.fetch_page = lambda url, **kw: {
            "html": yt_html, "cookie": "", "final_url": url}
        out = resolve.resolve_live_skyline(SKYLINE_URL)
        assert out and out["kind"] == "ytid", out
        assert resolve._YOUTUBE_ID_RE.fullmatch(out["id"])
        assert out["poster"] == f"https://i.ytimg.com/vi/{out['id']}/hqdefault.jpg"
        assert out["ttl_s"] == resolve.SKYLINE_YTID_TTL_S
        assert resolve.skyline_failure_reason(SKYLINE_URL) == ""
        # 3) OFFLINE variant -> None, reason 'offline' (never a generic failure)
        resolve.fetch_page = lambda url, **kw: {
            "html": off_html, "cookie": "", "final_url": url}
        assert resolve.resolve_live_skyline(SKYLINE_URL) is None
        assert resolve.skyline_failure_reason(SKYLINE_URL) == "offline"
        # 4) no stream config at all -> 'no-stream'
        resolve.fetch_page = lambda url, **kw: {
            "html": "<html>nope</html>", "cookie": "", "final_url": url}
        assert resolve.resolve_live_skyline(SKYLINE_URL) is None
        assert resolve.skyline_failure_reason(SKYLINE_URL) == "no-stream"
        # 5) page fetch failed -> 'fetch-failed'
        resolve.fetch_page = lambda url, **kw: None
        assert resolve.resolve_live_skyline(SKYLINE_URL) is None
        assert resolve.skyline_failure_reason(SKYLINE_URL) == "fetch-failed"
        # a later success clears the recorded reason
        resolve.fetch_page = lambda url, **kw: {
            "html": hls_html, "cookie": "", "final_url": url}
        assert resolve.resolve_live_skyline(SKYLINE_URL)
        assert resolve.skyline_failure_reason(SKYLINE_URL) == ""
    finally:
        resolve.fetch_page = orig


def test_skyline_offline_negative_reason_via_get_live():
    """The OFFLINE variant lands as a cached negative verdict with reason 'offline'."""
    off_html = _read_fixture("skyline_page2.html")
    orig = resolve.fetch_page
    cid = "5" * 16
    resolve.fetch_page = lambda url, **kw: {
        "html": off_html, "cookie": "", "final_url": url}
    try:
        resolve.reset_caches()
        assert resolve.get_live(cid, SKYLINE_URL) is None
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        assert data[cid]["ok"] is False, data[cid]
        assert data[cid]["reason"] == "offline", data[cid]
        assert resolve.cached_negative_reason(cid) == "offline"
    finally:
        resolve.fetch_page = orig
        resolve.reset_caches()


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
    assert resolve.host_resolvable(SKAPING_URL) == "skaping"
    assert resolve.host_resolvable("https://skaping.com/x") == "skaping"
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


YT_CHANNEL_URL = "https://www.youtube.com/channel/UC0aRRZkVrO_0nqfuXYaL_Cg/live"


def test_youtube_failure_reason_classification_offline():
    """classify_youtube_failure maps the real yt-dlp stderr classes (2026-10-06)."""
    cases = [
        # not live: channel up, no broadcast
        (1, "ERROR: [youtube:tab] UChoL_UbFagRA6Fhf7K0qk5w: The channel is not currently live",
         "not-live"),
        # gone: dead handle / channel -> API 404 (the les @handle case in the scan)
        (1, "ERROR: [youtube:tab] @WebCamNL/live: Unable to download API page: "
            "HTTP Error 404: Not Found (caused by <HTTPError 404: Not Found>)", "gone"),
        (1, "ERROR: [youtube] UCzzz: This channel does not exist", "gone"),
        # extractor: the anti-bot gate and its surface messages (all observed live)
        (1, "ERROR: [youtube] G91ja1rWV3I: This video is not available", "extractor"),
        (1, "ERROR: [youtube] G91ja1rWV3I: Sign in to confirm you\u2019re not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication.", "extractor"),
        (1, "ERROR: [youtube] x: No video formats found!; please report this issue", "extractor"),
        (1, "ERROR: [youtube] x: Unable to extract nsig function code", "extractor"),
        # timeout: the host-level probe bound (wfd.health._run returns rc -9)
        (-9, "timeout", "timeout"),
        # unrecognised -> 'error', never a wrong verdict
        (1, "ERROR: something entirely new", "error"),
    ]
    for rc, err, want in cases:
        got = resolve.classify_youtube_failure(rc, err)
        assert got == want, (rc, err, got, want)


def test_youtube_negative_stores_reason_offline():
    """get_live carries the classified reason on the negative verdict; success clears it."""
    url = YT_CHANNEL_URL
    orig_tool, orig_run = resolve._tool, resolve._run
    try:
        resolve._tool = lambda name: "yt-dlp" if name == "yt-dlp" else None
        resolve._run = lambda cmd, timeout: (1, "", "ERROR: [youtube:tab] UC0aRR: "
                                             "The channel is not currently live")
        resolve.reset_caches()
        cid = "c0ffee0000000001"
        assert resolve.get_live(cid, url) is None
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        assert data[cid]["ok"] is False and data[cid]["reason"] == "not-live", data[cid]
        assert data[cid]["error"] == "youtube-live resolve failed"    # legacy field kept
        assert resolve.cached_negative_reason(cid) == "not-live"
        assert resolve.yt_failure_reason(url) == "not-live"
        # a later success resolves + clears the recorded failure
        resolve._run = lambda cmd, timeout: (0, "M1n2O3p4Q5r\n", "")
        entry = resolve.get_live(cid, url, force=True)
        assert entry and entry["kind"] == "ytid" and entry["id"] == "M1n2O3p4Q5r"
        assert resolve.cached_negative_reason(cid) == ""             # positive now
        assert resolve.yt_failure_reason(url) == ""
        # a stale negative loses its reason (freshness gate)
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        data[cid] = {"ok": False, "error": "youtube-live resolve failed",
                     "reason": "extractor", "resolved_at": _iso_ago(200),
                     "host": "www.youtube.com", "ttl_s": resolve.LIVE_NEG_TTL_S}
        _write_cache_json("resolve/live.json", data)
        assert resolve.cached_negative_reason(cid) == ""
    finally:
        resolve._tool, resolve._run = orig_tool, orig_run
        resolve.reset_caches()


def test_youtube_extractor_retry_offline():
    """First probe fails with the anti-bot gate ('extractor' class): ONE retry
    adds the verified player-client args and its rc=0 + id is the normal ytid."""
    url = YT_CHANNEL_URL
    orig_tool, orig_run = resolve._tool, resolve._run
    calls = []

    def fake_run(cmd, timeout):
        calls.append(list(cmd))
        assert timeout == 60, timeout          # 60 s per attempt, both attempts
        if len(calls) == 1:
            assert "--extractor-args" not in cmd, cmd   # first probe stays plain
            return (1, "", "ERROR: [youtube] G91ja1rWV3I: Sign in to confirm "
                           "you\u2019re not a bot. Use --cookies-from-browser "
                           "or --cookies for the authentication.")
        return (0, "M1n2O3p4Q5r\n", "")

    resolve._tool = lambda name: "yt-dlp" if name == "yt-dlp" else None
    resolve._run = fake_run
    try:
        resolve.reset_caches()
        res = resolve.resolve_live_youtube(url)
        assert res and res["kind"] == "ytid" and res["id"] == "M1n2O3p4Q5r", res
        assert res["poster"] == "https://i.ytimg.com/vi/M1n2O3p4Q5r/hqdefault.jpg"
        assert res["ttl_s"] == 1800
        assert len(calls) == 2, calls          # exactly one retry — never more
        retry = calls[1]
        assert retry[retry.index("--extractor-args") + 1] == \
            "youtube:player_client=default,-tv,-web_embedded", retry
        assert retry == ["yt-dlp", "--simulate", "--print", "id", "--no-warnings",
                         "--extractor-args",
                         "youtube:player_client=default,-tv,-web_embedded", url], retry
        assert resolve.yt_failure_reason(url) == ""    # success cleared the failure
        print("  retry argv:", " ".join(calls[1]))
    finally:
        resolve._tool, resolve._run = orig_tool, orig_run
        resolve.reset_caches()


def test_youtube_extractor_retry_failure_keeps_reason_offline():
    """Both attempts fail: the ORIGINAL 'extractor' class is what gets recorded —
    the retry's own (would-be-different-class) stderr never overwrites it."""
    url = YT_CHANNEL_URL
    orig_tool, orig_run = resolve._tool, resolve._run
    calls = []

    def fake_run(cmd, timeout):
        calls.append(list(cmd))
        assert timeout == 60, timeout
        if len(calls) == 1:
            return (1, "", "ERROR: [youtube] G91ja1rWV3I: Sign in to confirm "
                           "you\u2019re not a bot.")
        # would classify 'gone' if (wrongly) re-classified after the retry
        return (1, "", "ERROR: [youtube:tab] @WebCamNL/live: Unable to download "
                       "API page: HTTP Error 404: Not Found")

    resolve._tool = lambda name: "yt-dlp" if name == "yt-dlp" else None
    resolve._run = fake_run
    try:
        resolve.reset_caches()
        cid = "c0ffee0000000003"
        assert resolve.get_live(cid, url) is None
        assert len(calls) == 2, calls              # exactly one retry, then stop
        retry = calls[1]
        assert retry[retry.index("--extractor-args") + 1] == \
            "youtube:player_client=default,-tv,-web_embedded", retry
        assert resolve.yt_failure_reason(url) == "extractor"    # original class kept
        data = json.loads((CACHE_ROOT / "resolve" / "live.json").read_text(encoding="utf-8"))
        assert data[cid]["ok"] is False, data[cid]
        assert data[cid]["reason"] == "extractor", data[cid]
        assert data[cid]["error"] == "youtube-live resolve failed"   # legacy field kept
    finally:
        resolve._tool, resolve._run = orig_tool, orig_run
        resolve.reset_caches()


def test_fixture_skaping_og():
    """skaping player pages resolve to their newest 10-minute S3 JPEG (kind image)."""
    html = _read_fixture("skaping_page.html")
    og = resolve.parse_social_image(html, SKAPING_URL)
    assert og, "no og:image in the skaping fixture page"
    assert og.startswith("https://skaping.s3.gra.io.cloud.ovh.net/"), og
    assert og.endswith(".jpg"), og
    assert "/millau/pouncho/panoramique-droite/" in og, og

    orig = resolve.fetch_page
    resolve.fetch_page = lambda url, **kw: {"html": html, "cookie": "",
                                            "final_url": url}
    try:
        res = resolve.resolve_live_skaping(SKAPING_URL)
    finally:
        resolve.fetch_page = orig
    assert res and res["kind"] == "image", res
    assert res["url"] == og
    assert res["ttl_s"] == 900 and res["ttl_s"] == resolve.SKAPING_TTL_S
    assert res["headers"] == {"User-Agent": resolve.BROWSER_UA}, res["headers"]

    # og:image pointing at a non-image file must be rejected
    resolve.fetch_page = lambda url, **kw: {
        "html": '<meta property="og:image" content="https://x.example/player.html">',
        "cookie": "", "final_url": url}
    try:
        assert resolve.resolve_live_skaping(SKAPING_URL) is None
    finally:
        resolve.fetch_page = orig
    # no og:image at all -> None
    resolve.fetch_page = lambda url, **kw: {"html": "<html></html>", "cookie": "",
                                            "final_url": url}
    try:
        assert resolve.resolve_live_skaping(SKAPING_URL) is None
    finally:
        resolve.fetch_page = orig


def test_still_flow_offline():
    """get_still: resolve -> fetch -> ~90 s in-process memo; refresh-once on failure."""
    cid = "7" * 16
    calls = {"page": 0, "img": 0}
    orig_page, orig_get = resolve.fetch_page, resolve._http_get

    def fake_page(url, **kw):
        calls["page"] += 1
        return {"html": _read_fixture("skaping_page.html"), "cookie": "",
                "final_url": url}

    def fake_get(url, **kw):
        calls["img"] += 1
        return _JPEG, {"content-type": "image/jpeg"}, url

    resolve.fetch_page = fake_page
    resolve._http_get = fake_get
    try:
        resolve.reset_caches()
        blob, ctype = resolve.get_still(cid, SKAPING_URL, force=True)
        assert blob == _JPEG and ctype == "image/jpeg", (blob and len(blob), ctype)
        entry = resolve.cached_live_entry(cid)
        assert entry and entry["kind"] == "image", entry
        assert entry["url"] == SKAPING_STILL_URL
        assert calls == {"page": 1, "img": 1}, calls
        assert resolve.still_cached(cid)
        # second call: bytes come from the in-process memo — zero network
        assert resolve.get_still(cid, SKAPING_URL) == (blob, ctype)
        assert calls == {"page": 1, "img": 1}, calls
        # force bypasses the memo (re-resolves + re-fetches)
        assert resolve.get_still(cid, SKAPING_URL, force=True)[0] == _JPEG
        assert calls == {"page": 2, "img": 2}, calls
        # image fetch failure -> exactly one resolve refresh + one retry
        cid2 = "6" * 16
        state = {"fails": 1}

        def flaky_get(url, **kw):
            calls["img"] += 1
            if state["fails"]:
                state["fails"] -= 1
                return None, {}, url
            return _JPEG, {"content-type": "image/jpeg"}, url

        resolve._http_get = flaky_get
        blob2, ctype2 = resolve.get_still(cid2, SKAPING_URL, force=True)
        assert blob2 == _JPEG and ctype2 == "image/jpeg"
        assert calls == {"page": 4, "img": 4}, calls
        # a fresh non-image resolution yields (None, None) without any fetch
        _write_cache_json("resolve/live.json", {
            "5" * 16: {"ok": True, "kind": "hls",
                       "url": "https://x.example/y.m3u8", "ttl_s": 300,
                       "resolved_at": _now_iso(), "host": "x.example"}})
        n_img = calls["img"]
        assert resolve.get_still("5" * 16, "https://x.example/page") == (None, None)
        assert calls["img"] == n_img
    finally:
        resolve.fetch_page = orig_page
        resolve._http_get = orig_get
        resolve.reset_caches()


def test_poster_snapshot_offline():
    """get_poster(protocol=hls|mjpeg): single ffmpeg frame -> source 'snapshot'."""
    cid = "9" * 16
    url = "https://streams.example/cam.m3u8"
    orig_tool, orig_run = resolve._tool, resolve._run
    calls = {"run": 0}

    def fake_tool(name):
        return "ffmpeg" if name == "ffmpeg" else None

    def fake_run(cmd, timeout):
        calls["run"] += 1
        assert cmd[0] == "ffmpeg" and "-rw_timeout" in cmd, cmd
        assert "-frames:v" in cmd and "scale=640:-2" in cmd, cmd
        pathlib.Path(cmd[-1]).write_bytes(_JPEG)   # the -y <tmp.jpg> output
        return (0, "", "")

    resolve._tool = fake_tool
    resolve._run = fake_run
    try:
        resolve.reset_caches()
        path = resolve.get_poster(cid, url, force=True, protocol="hls")
        assert path is not None and path.exists(), "snapshot poster not stored"
        assert path.read_bytes() == _JPEG
        assert calls["run"] == 1
        entry = resolve.poster_index_entry(cid)
        assert entry and entry["ok"] is True and entry["source"] == "snapshot", entry
        assert resolve.poster_exists(cid)
        assert not list(resolve.posters_dir().glob(".snap-*"))  # tmp cleaned up
        # rc != 0 -> negative verdict, no poster file
        cid2 = "8" * 16
        resolve._run = lambda cmd, timeout: (1, "", "boom")
        assert resolve.get_poster(cid2, url, force=True, protocol="mjpeg") is None
        assert resolve._poster_file(cid2) is None
        neg = resolve.poster_index_entry(cid2)
        assert neg and neg["ok"] is False and neg["source"] == "fail"
        # snapshots stay behind a dedicated gate
        assert resolve.SNAPSHOT_GATE.cap == 2
        assert resolve.SNAPSHOT_GATE.spacing == 0.3
    finally:
        resolve._tool, resolve._run = orig_tool, orig_run
        resolve.reset_caches()


def test_warm_candidates_raw_rows_need_explicit_filter():
    """Selector: a family of raw hls/mjpeg/jpeg rows yields candidates with an
    explicit --family (or --host/--protocol) and stays 0 on a bare run."""
    dbf = CACHE_ROOT / "warmfix" / "worldfeed.db"
    conn = dbmod.connect(dbf)
    dbmod.init_db(conn)
    raw_rows = [
        ("a" * 16, "https://raw-stream.example/live.m3u8", "fixturefam", "hls"),
        ("b" * 16, "https://raw-stream.example/cam2.mjpg", "fixturefam", "mjpeg"),
        ("c" * 16, "https://raw-still.example/cam.jpg", "fixturefam", "jpeg"),
    ]
    for cid, url, fam, proto in raw_rows:
        conn.execute(
            "INSERT INTO cameras (camera_id, url, source_family, provenance, protocol) "
            "VALUES (?,?,?,?,?)", (cid, url, fam, "public_by_design", proto))
    conn.commit()
    conn.close()

    orig_data_dir = resolve.DATA_DIR
    resolve.DATA_DIR = dbf.parent          # _warm_candidates reads DATA_DIR/worldfeed.db
    try:
        # bare run: raw rows never qualify; a raw-only registry yields nothing
        assert resolve._warm_candidates("", "", "") == []
        # explicit --family includes every raw snapshot-grade row
        got = resolve._warm_candidates("fixturefam", "", "")
        assert [g[0] for g in got] == ["a" * 16, "b" * 16, "c" * 16], got
        assert [g[2] for g in got] == [None, None, None]        # no resolver host
        assert [g[3] for g in got] == ["hls", "mjpeg", "jpeg"]  # protocols kept
        # --protocol alone is a narrowing too
        assert [g[0] for g in resolve._warm_candidates("", "", "jpeg")] == ["c" * 16]
        # --host narrowing works for raw rows as well
        assert ([g[0] for g in resolve._warm_candidates("", "raw-still.example", "")]
                == ["c" * 16])
        # resolver-host rows stay candidates even on a bare run
        conn = dbmod.connect(dbf)
        conn.execute(
            "INSERT INTO cameras (camera_id, url, source_family, provenance, protocol) "
            "VALUES (?,?,?,?,?)", ("d" * 16, SKYLINE_URL, "otherfam",
                                   "aggregator_directory", "iframe"))
        conn.commit()
        conn.close()
        assert [g[0] for g in resolve._warm_candidates("", "", "")] == ["d" * 16]
        assert ([g[0] for g in resolve._warm_candidates("fixturefam", "", "")]
                == ["a" * 16, "b" * 16, "c" * 16])
    finally:
        resolve.DATA_DIR = orig_data_dir


def test_poster_raw_jpeg_direct_offline():
    """get_poster(protocol=jpeg): the row url is the live still -> source
    'direct'; non-image bytes fall back to the og:image scrape."""
    cid, cid2 = "9a" * 8, "8b" * 8
    url = "https://stills.example/cam-cam.jpeg"
    orig_get, orig_page = resolve._http_get, resolve.fetch_page
    calls = {"n": 0}
    seq = []

    def fake_get(u, **kw):
        calls["n"] += 1
        assert u == url, u
        return (_JPEG, {"content-type": "image/jpeg"}, url)

    page_html = ('<html><head><meta property="og:image" '
                 'content="https://stills.example/og.jpg"></head></html>')

    def fake_get2(u, **kw):
        seq.append(u)
        if u == "https://stills.example/page-y.jpeg":
            return (b"<html>not an image here</html>",
                    {"content-type": "text/html"}, u)
        if u == "https://stills.example/og.jpg":
            return (_JPEG, {"content-type": "image/jpeg"}, u)
        return (None, {}, u)

    try:
        resolve._http_get = fake_get
        resolve.reset_caches()
        path = resolve.get_poster(cid, url, force=True, protocol="jpeg")
        assert path is not None and path.exists(), "direct jpeg poster not stored"
        assert path.read_bytes() == _JPEG
        assert calls["n"] == 1, "direct path must not refetch a page"
        entry = resolve.poster_index_entry(cid)
        assert entry and entry["ok"] is True and entry["source"] == "direct", entry

        resolve._http_get = fake_get2
        resolve.fetch_page = (lambda u, **kw:
                              {"html": page_html, "cookie": "", "final_url": u})
        resolve.reset_caches()
        path2 = resolve.get_poster(cid2, "https://stills.example/page-y.jpeg",
                                   force=True, protocol="jpeg")
        assert path2 is not None and path2.exists(), "og fallback poster not stored"
        entry2 = resolve.poster_index_entry(cid2)
        assert entry2 and entry2["ok"] is True and entry2["source"] == "og", entry2
        assert seq == ["https://stills.example/page-y.jpeg",
                       "https://stills.example/og.jpg"], seq
    finally:
        resolve._http_get, resolve.fetch_page = orig_get, orig_page
        resolve.reset_caches()


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


def _seed_live_entry(cid: str, entry: dict) -> None:
    """Merge one live.json entry for cid (temp cache) and drop memos."""
    path = CACHE_ROOT / "resolve" / "live.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[cid] = entry
    _write_cache_json("resolve/live.json", data)


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
    excl = " AND ".join(f"lower(url) NOT LIKE '%{s}%'"
                        for s, _ in resolve.RESOLVER_REGISTRY)
    row = _db_one("SELECT camera_id FROM cameras WHERE provenance='public_by_design' "
                  f"AND url LIKE 'http%' AND {excl} LIMIT 1")
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
        for key in ("resolvable", "live_url", "poster_url", "still_url", "yt_id"):
            assert key not in d, (key, sorted(d))
        for path in (f"/api/poster/{exp_id}",
                     f"/api/still/{exp_id}",
                     f"/api/resolve/{exp_id}",
                     f"/api/live/{exp_id}/index.m3u8",
                     f"/api/live/{exp_id}/seg/x.ts"):
            status, _, _ = _get_http(path)
            assert status == 404, (path, status)
    finally:
        profile.settings = original


def test_server_image_ytid_fields():
    """Row payloads: kind image -> still_url; kind ytid -> yt_id (fresh only)."""
    _base()
    _seed_live_entry(SKAPING_CID, {
        "ok": True, "kind": "image", "url": SKAPING_STILL_URL,
        "headers": {"User-Agent": resolve.BROWSER_UA}, "ttl_s": 900,
        "resolved_at": _now_iso(), "host": "www.skaping.com"})
    status, _, d = _get_json(f"/api/camera/{SKAPING_CID}")
    assert status == 200, status
    assert d["provenance"] == "public_by_design"
    assert d.get("still_url") == f"/api/still/{SKAPING_CID}", sorted(d)
    assert "live_url" not in d and "yt_id" not in d
    # youtube: fresh ytid entry -> yt_id (11-char id only), no live_url
    yt = _db_one("SELECT camera_id FROM cameras WHERE provenance IN "
                 "('public_by_design','aggregator_directory') "
                 "AND lower(url) LIKE '%youtube.com%' LIMIT 1")
    assert yt, "no youtube rows in registry"
    _seed_live_entry(yt["camera_id"], {
        "ok": True, "kind": "ytid", "id": "M1n2O3p4Q5r",
        "poster": "https://i.ytimg.com/vi/M1n2O3p4Q5r/hqdefault.jpg",
        "ttl_s": 1800, "resolved_at": _now_iso(), "host": "www.youtube.com"})
    _, _, d2 = _get_json(f"/api/camera/{yt['camera_id']}")
    assert d2.get("yt_id") == "M1n2O3p4Q5r", sorted(d2)
    assert "live_url" not in d2 and "still_url" not in d2
    # a malformed id never leaks through as yt_id
    _seed_live_entry(yt["camera_id"], {
        "ok": True, "kind": "ytid", "id": "short", "ttl_s": 1800,
        "resolved_at": _now_iso(), "host": "www.youtube.com"})
    _, _, d3 = _get_json(f"/api/camera/{yt['camera_id']}")
    assert "yt_id" not in d3
    # stale image entry -> no still_url (freshness gate)
    _seed_live_entry(SKAPING_CID, {
        "ok": True, "kind": "image", "url": SKAPING_STILL_URL, "ttl_s": 900,
        "resolved_at": _iso_ago(1000), "host": "www.skaping.com"})
    _, _, d4 = _get_json(f"/api/camera/{SKAPING_CID}")
    assert "still_url" not in d4


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


def test_server_resolve_route():
    """GET /api/resolve/<cid>: on-demand verdict, display-only, ?refresh=1 forces."""
    _base()
    # 1) fresh ytid entry -> ok true with the 11-char yt_id
    yt = _db_one("SELECT camera_id FROM cameras WHERE provenance IN "
                 "('public_by_design','aggregator_directory') "
                 "AND lower(url) LIKE '%youtube.com%' LIMIT 1")
    assert yt, "no youtube rows in registry"
    yt_cid = yt["camera_id"]
    _seed_live_entry(yt_cid, {
        "ok": True, "kind": "ytid", "id": "M1n2O3p4Q5r",
        "poster": "https://i.ytimg.com/vi/M1n2O3p4Q5r/hqdefault.jpg",
        "ttl_s": 1800, "resolved_at": _now_iso(), "host": "www.youtube.com"})
    status, ctype, d = _get_json(f"/api/resolve/{yt_cid}")
    assert status == 200 and ctype.startswith("application/json")
    assert d["camera_id"] == yt_cid and d["ok"] is True and d["kind"] == "ytid"
    assert d["yt_id"] == "M1n2O3p4Q5r"
    # 2) fresh image entry -> ok true with still_url (no yt_id)
    _seed_live_entry(SKAPING_CID, {
        "ok": True, "kind": "image", "url": SKAPING_STILL_URL,
        "headers": {"User-Agent": resolve.BROWSER_UA}, "ttl_s": 900,
        "resolved_at": _now_iso(), "host": "www.skaping.com"})
    _, _, d2 = _get_json(f"/api/resolve/{SKAPING_CID}")
    assert d2["ok"] is True and d2["kind"] == "image"
    assert d2["still_url"] == f"/api/still/{SKAPING_CID}"
    assert "yt_id" not in d2 and "live_url" not in d2
    # 3) ?refresh=1 forces a re-resolve (offline: skaping resolver patched)
    calls = {"skaping": 0}
    orig_sk = resolve.resolve_live_skaping

    def fake_skaping(url):
        calls["skaping"] += 1
        return {"kind": "image", "url": SKAPING_STILL_URL,
                "headers": {"User-Agent": resolve.BROWSER_UA}, "ttl_s": 900}

    resolve.resolve_live_skaping = fake_skaping
    try:
        _, _, d3 = _get_json(f"/api/resolve/{SKAPING_CID}?refresh=1")
    finally:
        resolve.resolve_live_skaping = orig_sk
    assert calls["skaping"] == 1 and d3["ok"] is True, d3
    assert d3["kind"] == "image"
    # 4) resolver failure -> ok false 'resolve failed' (offline: patched)
    yt2 = _db_one("SELECT camera_id FROM cameras WHERE provenance IN "
                  "('public_by_design','aggregator_directory') "
                  "AND lower(url) LIKE '%youtube.com%' AND camera_id != ? LIMIT 1",
                  (yt_cid,))
    assert yt2, "need a second youtube row"
    orig_yt = resolve.resolve_live_youtube
    resolve.resolve_live_youtube = lambda url: None
    try:
        _, _, d4 = _get_json(f"/api/resolve/{yt2['camera_id']}")
    finally:
        resolve.resolve_live_youtube = orig_yt
    assert d4["ok"] is False and d4["reason"] == "resolve failed", d4
    assert "kind" not in d4
    # 5) non-resolvable display row -> ok false 'no-resolver'
    excl = " AND ".join(f"lower(url) NOT LIKE '%{s}%'"
                        for s, _ in resolve.RESOLVER_REGISTRY)
    nr = _db_one("SELECT camera_id FROM cameras WHERE provenance IN "
                 "('public_by_design','aggregator_directory') "
                 f"AND lower(url) LIKE 'http%' AND {excl} LIMIT 1")
    assert nr, "no non-resolvable rows"
    _, _, d5 = _get_json(f"/api/resolve/{nr['camera_id']}")
    assert d5["ok"] is False and d5["reason"] == "no-resolver", d5
    assert "kind" not in d5
    # 6) unknown camera -> 404; nothing ever echoes a token/cookie
    status, _, _ = _get_http("/api/resolve/0000000000000000")
    assert status == 404, status
    blob = json.dumps([d, d2, d3, d4, d5]).lower()
    assert "token" not in blob and "cookie" not in blob


def test_server_resolve_route_negative_reason():
    """A fresh classified-negative verdict surfaces its reason via /api/resolve."""
    _base()
    yt = _db_one("SELECT camera_id FROM cameras WHERE provenance IN "
                 "('public_by_design','aggregator_directory') "
                 "AND lower(url) LIKE '%youtube.com%' LIMIT 1")
    assert yt, "no youtube rows in registry"
    cid = yt["camera_id"]
    _seed_live_entry(cid, {
        "ok": False, "error": "youtube-live resolve failed", "reason": "not-live",
        "resolved_at": _now_iso(), "host": "www.youtube.com",
        "ttl_s": resolve.LIVE_NEG_TTL_S})
    status, ctype, d = _get_json(f"/api/resolve/{cid}")
    assert status == 200 and ctype.startswith("application/json")
    assert d["ok"] is False and d["reason"] == "not-live", d
    assert "kind" not in d and "yt_id" not in d
    # an unclassified negative (no reason field) keeps the legacy text
    _seed_live_entry(cid, {
        "ok": False, "error": "skylinewebcams resolve failed",
        "resolved_at": _now_iso(), "host": "www.skylinewebcams.com",
        "ttl_s": resolve.LIVE_NEG_TTL_S})
    _, _, d2 = _get_json(f"/api/resolve/{cid}")
    assert d2["ok"] is False and d2["reason"] == "resolve failed", d2


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
        for key in ("resolvable", "live_url", "poster_url", "still_url", "yt_id"):
            assert key not in d, (key, sorted(d))
        for path in (f"/api/poster/{SKYLINE_CID}",
                     f"/api/still/{SKYLINE_CID}",
                     f"/api/resolve/{SKYLINE_CID}",
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


def test_server_still_route():
    """GET /api/still/<cid>: serves image-kind bytes; 404 for anything else."""
    _base()
    _seed_live_entry(SKYLINE_CID, {
        "ok": True, "kind": "image", "url": "https://still.example/now.jpg",
        "headers": {"User-Agent": resolve.BROWSER_UA}, "ttl_s": 900,
        "resolved_at": _now_iso(), "host": "still.example"})
    calls = {"img": 0}
    orig_get = resolve._http_get

    def fake_get(url, **kw):
        calls["img"] += 1
        return _JPEG, {"content-type": "image/jpeg"}, url

    resolve._http_get = fake_get
    try:
        status, ctype, body = _get_http(f"/api/still/{SKYLINE_CID}")
        assert status == 200, status
        assert ctype.startswith("image/jpeg"), ctype
        assert body == _JPEG
        assert calls["img"] == 1
        # HEAD-safe: headers only, no body, 60 s cache
        req = urllib.request.Request(_base() + f"/api/still/{SKYLINE_CID}",
                                     method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Length") == str(len(_JPEG))
            assert "max-age=60" in (resp.headers.get("Cache-Control") or "")
            assert resp.read() == b""
        assert calls["img"] == 1       # HEAD used the ~90 s bytes memo
        # ?refresh=1 forces a re-resolve (skyline resolver patched offline)
        orig_sk = resolve.resolve_live_skyline
        resolve.resolve_live_skyline = lambda url: {
            "kind": "image", "url": "https://still.example/now2.jpg",
            "headers": {"User-Agent": resolve.BROWSER_UA}, "ttl_s": 900}
        try:
            status, _, body = _get_http(f"/api/still/{SKYLINE_CID}?refresh=1")
        finally:
            resolve.resolve_live_skyline = orig_sk
        assert status == 200 and body == _JPEG, (status, len(body))
        # a non-image resolution -> 404 {'error': 'no still'}
        _seed_live_entry(SKYLINE_CID, {
            "ok": True, "kind": "hls",
            "url": "https://hd-auth.example/live.m3u8?a=x", "ttl_s": 300,
            "resolved_at": _now_iso(), "host": "h.example"})
        status, _, body = _get_http(f"/api/still/{SKYLINE_CID}")
        assert status == 404, status
        assert json.loads(body).get("error") == "no still"
        # unknown camera -> 404
        status, _, _ = _get_http("/api/still/0000000000000000")
        assert status == 404, status
    finally:
        resolve._http_get = orig_get
        resolve.reset_caches()


# ---------------------------------------------------------------------------
# live end-to-end proof (needs the internet; exercises the real recipe)
# ---------------------------------------------------------------------------

def test_live_end_to_end_skaping():
    """Real-network proof: skaping page -> og:image S3 JPEG -> still + /api/resolve."""
    resolve.reset_caches()
    blob, ctype = resolve.get_still(SKAPING_CID, SKAPING_URL, force=True)
    assert blob is not None, "skaping still fetch failed (network?)"
    assert len(blob) > 5000, f"still too small: {len(blob)}"
    assert blob[:2] == b"\xff\xd8", blob[:8]
    assert ctype == "image/jpeg", ctype
    print(f"  still: {len(blob)}B {ctype} via og:image (src={SKAPING_URL})")
    _base()
    status, _, body = _get_http(f"/api/resolve/{SKAPING_CID}")
    assert status == 200, status
    d = json.loads(body)
    assert d["ok"] is True, d
    assert d["kind"] == "image", d
    assert d["still_url"] == f"/api/still/{SKAPING_CID}"
    # the still route serves the still (fresh ~90 s memo -> no extra network)
    status, ctype2, body2 = _get_http(f"/api/still/{SKAPING_CID}")
    assert status == 200 and ctype2.startswith("image/jpeg"), (status, ctype2)
    assert len(body2) > 5000 and body2[:2] == b"\xff\xd8"
    print(f"  api: resolve ok kind=image; /api/still {len(body2)}B {ctype2}")


def test_live_end_to_end_skyline():
    """Real-network proof of the skyline recipe, walking a candidate list.

    A single skyline cam can legitimately be OFFLINE for days — the site then
    serves a page with no player and no token ('request off' + OFFLINE badge),
    e.g. viannos on 2026-10-06. That is a valid cam state, not a resolver
    failure, so this test walks SKYLINE_CANDIDATES until one resolves to HLS
    and proves the full chain on it: page -> token -> upstream playlist ->
    rewritten local playlist -> segment -> poster. It fails only when NO
    candidate yields an HLS stream (a real outage/site change).
    """
    resolve.reset_caches()
    entry = cid = url = None
    attempts = []
    for cand_cid, cand_url in SKYLINE_CANDIDATES:
        got = resolve.get_live(cand_cid, cand_url, force=True)
        if got and got.get("kind") == "hls":
            cid, url, entry = cand_cid, cand_url, got
            break
        attempts.append((cand_url.rsplit("/", 1)[-1],
                         f"kind={got.get('kind')}" if got
                         else (resolve.cached_negative_reason(cand_cid) or "resolve failed")))
    assert entry, f"no skyline cam resolved to HLS (candidate outcomes: {attempts})"
    text = resolve.fetch_playlist(entry)
    if text is None or resolve.is_filler(text) or resolve.is_dead_playlist(text):
        entry = resolve.get_live(cid, url, force=True)      # one forced re-resolve
        assert entry and entry.get("kind") == "hls", "re-resolve failed after stale playlist"
        text = resolve.fetch_playlist(entry)
    assert text, "upstream playlist unavailable after refresh"
    assert not resolve.is_filler(text), "filler playlist twice (token/cookies stale)"
    assert not resolve.is_dead_playlist(text), "empty ENDLIST playlist twice (stale token)"
    marker = resolve.redact(entry.get("url", ""))
    rewritten = resolve.resolve_playlist(cid, text, marker)
    seg_lines = [l.strip() for l in rewritten.splitlines()
                 if l.strip().startswith("/api/live/")]
    assert seg_lines, rewritten[:200]
    name = seg_lines[0].rsplit("/", 1)[-1]
    assert resolve.SEG_NAME_RE.fullmatch(name), name
    upstream = resolve.seg_upstream(cid, name)
    assert upstream and upstream.startswith("http"), upstream
    blob, ctype = resolve.fetch_segment(upstream, entry.get("headers"))
    assert blob is not None, "segment fetch failed"
    assert len(blob) > 20 * 1024, f"segment too small: {len(blob)}"
    poster = resolve.get_poster(cid, url, force=True)
    assert poster is not None and poster.exists(), "poster fetch failed"
    data = poster.read_bytes()
    assert len(data) > 1024, len(data)
    assert data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n", data[:8]
    if attempts:
        print(f"  live: skipped {len(attempts)} cam(s): {attempts}")
    print(f"  live: cam={url.rsplit('/', 1)[-1]} token=sha1:{marker} "
          f"playlist={len(text)}B segments={len(seg_lines)} "
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

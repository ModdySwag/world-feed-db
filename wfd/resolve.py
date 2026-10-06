"""wfd.resolve — live-stream resolution + local HLS relay + poster cache.

Fixes the viewer's blank-tile classes:
- directory/iframe rows (www.skylinewebcams.com and similar) whose player page
  exposes a tokenised HLS stream: resolve the page (browser UA + cookie jar),
  build the streaming URL, and let the viewer relay playlist + segments
  locally so the tile actually plays.
- rows with no poster image: posters are harvested from the page's og:image
  (or a YouTube video's i.ytimg.com thumbnail) and cached on disk.
- skaping.com rows (url = an HTML player page): the page's og:image meta
  points at the newest 10-minute S3 JPEG; kind-'image' resolutions serve it
  through the viewer's /api/still/<cid> (get_still, ~90 s in-process memo).
- hls/mjpeg tiles without any og:image: a single ffmpeg frame becomes the
  poster (source 'snapshot'; SNAPSHOT_GATE caps captures at 2 per host).
- raw jpeg still rows (nsw/qld and friends): the row url IS the live image —
  the current bytes are stored as the poster (source 'direct').

Cache layout (``DATA_DIR`` from wfd.ingest.base, or ``$WFD_DATA_DIR`` when set
— tests point that at a temp dir so the real cache stays clean):
    data/posters/<camera_id>.<jpg|png>   poster bytes
    data/posters/index.json              {'<cid>': {ok, fetched_at, source, error?}}
    data/resolve/live.json               {'<cid>': {kind, url, headers, ttl_s,
                                                    poster?, ok, resolved_at, host}}
    data/resolve/warm-<kind>-<ts>.jsonl  warm-run evidence (wfd resolve warm)

Exposure discipline: nothing in this module is ever called for exposure rows —
the viewer enforces that at the route layer (same law as /api/camera/<id>).

Redaction discipline: a skyline token is an access secret. It is NEVER printed
or logged in full — use :func:`redact` (sha1[:8]) / :func:`redact_url_for_display`
for anything that reaches a terminal or a report.

Politeness/dedup: two module-level :class:`wfd.health.HostGate` instances bound
the request rate (pages: cap 2 / 0.5 s start spacing; playlist+segment relay:
cap 6 / 0.05 s), and a per-camera lock means concurrent requests for the same
camera resolve once. Every network call has an explicit timeout.

CLI (registered via wfd.cli):
    py -3.11 -m wfd resolve warm [--kind poster|live|both] [--family X]
                                 [--host skylinewebcams.com] [--protocol hls]
                                 [--limit N] [--refresh]
    py -3.11 -m wfd resolve show <camera_id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .health import HostGate, _run, _tool
from .ingest.base import DATA_DIR

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SKYLINE_REFERER = "https://www.skylinewebcams.com/"
SKYLINE_LIVE_BASE = "https://hd-auth.skylinewebcams.com/live.m3u8?a="

PAGE_TIMEOUT_S = 20.0          # page fetches (resolver + poster)
RELAY_TIMEOUT_S = 15.0         # playlist / segment relay fetches
PAGE_MAX_BYTES = 4_000_000     # a player page is a few hundred KB at most
SEGMENT_MAX_BYTES = 32_000_000 # HLS segments are ~100-500 KB; cap hard

POSTER_TTL_S = 12 * 3600       # positive poster verdict
POSTER_NEG_TTL_S = 3600        # negative poster verdict (no og:image, etc.)
LIVE_TTL_S = 300               # fresh token+cookies; skyline sessions die in ~5-10 min
LIVE_NEG_TTL_S = 120           # negative live verdict — don't hammer the site
SEG_TTL_S = 20 * 60            # per-cid segment-map entry lifetime
SKAPING_TTL_S = 900            # skaping og:image = a 10-minute slot file, refresh sooner
STILL_TTL_S = 90               # in-process still-bytes memo (viewer /api/still)
SNAPSHOT_TIMEOUT_S = 25        # one ffmpeg single-frame attempt

# URL-safe segment name; anything else is sanitised into shape.
SEG_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,180}")
_YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
SKYLINE_TOKEN_RE = re.compile(r"source:'livee\.m3u8\?a=([^']+)'")
_URI_ATTR_RE = re.compile(r"""URI\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_META_ATTR_RE = re.compile(
    r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>`]+))""")
_MEDIA_TYPE_RE = re.compile(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+")
_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png)$", re.I)

# Raw (non-resolver) row protocols a warm poster run may fetch directly, once
# the caller narrows the set: hls/mjpeg become an ffmpeg snapshot; jpeg is the
# live still itself (direct download).
_RAW_POSTER_PROTOCOLS = ("hls", "mjpeg", "jpeg")

# Resolver registry: url host suffix -> resolver name (host_resolvable, no network)
RESOLVER_REGISTRY = (
    ("skylinewebcams.com", "skylinewebcams"),
    ("youtube.com", "youtube-live"),
    ("youtu.be", "youtube-live"),
    ("skaping.com", "skaping"),
)

# Politeness gates: page fetches are rarer but heavier-handed by the site owner;
# playlist/segment relay traffic is the steady stream and needs more headroom.
PAGE_GATE = HostGate(cap=2, spacing=0.5)
RELAY_GATE = HostGate(cap=6, spacing=0.05)
SNAPSHOT_GATE = HostGate(cap=2, spacing=0.3)   # ffmpeg single-frame captures


class FillerError(ValueError):
    """Upstream served the stale-token/geo filler playlist ('copyright_violation')."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def redact(value) -> str:
    """sha1[:8] of a secret-ish string. NEVER log tokens/cookies in full."""
    if not value:
        return ""
    return hashlib.sha1(str(value).encode("utf-8", "replace")).hexdigest()[:8]


_SECRET_PARAMS = frozenset({"a", "token", "key", "sig", "signature", "auth"})


def redact_url_for_display(url: str) -> str:
    """A URL safe for terminal/report output: secret query values -> sha1[:8]."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        return redact(url)
    if not parts.query:
        return str(url)
    out = []
    for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SECRET_PARAMS and val:
            out.append((key, f"<redacted sha1:{redact(val)}>"))
        else:
            out.append((key, val))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(out),
         parts.fragment))


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _age_s(iso_str) -> Optional[float]:
    """Seconds since an ISO timestamp; None when unparsable."""
    try:
        when = dt.datetime.fromisoformat(str(iso_str))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - when).total_seconds()


def _data_dir() -> pathlib.Path:
    """DATA_DIR root — overridable with $WFD_DATA_DIR (tests use a temp dir)."""
    env = os.environ.get("WFD_DATA_DIR", "").strip()
    return pathlib.Path(env) if env else DATA_DIR


def posters_dir() -> pathlib.Path:
    return _data_dir() / "posters"


def resolve_dir() -> pathlib.Path:
    return _data_dir() / "resolve"


def image_content_type(blob: bytes) -> str:
    if blob[:2] == b"\xff\xd8":
        return "image/jpeg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:3] == b"GIF":
        return "image/gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _sniff_ext(blob: bytes) -> str:
    """ff d8 => .jpg, 89 50 => .png, else .jpg attempt (per contract)."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return "jpg"


# ---------------------------------------------------------------------------
# per-camera locks (same camera resolves once, however many requests arrive)
# ---------------------------------------------------------------------------

_LOCKS: dict = {}
_LOCKS_LOCK = threading.Lock()


def _cid_lock(camera_id: str, *, kind: str) -> threading.Lock:
    key = f"{kind}:{camera_id}"
    with _LOCKS_LOCK:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.Lock()
        return lock


# ---------------------------------------------------------------------------
# atomic JSON read/write with a 5 s re-read guard
# ---------------------------------------------------------------------------

_POSTER_MEMO: dict = {"path": None, "mtime": 0.0, "checked_at": 0.0, "data": None}
_LIVE_MEMO: dict = {"path": None, "mtime": 0.0, "checked_at": 0.0, "data": None}
_MEMO_RE_READ_S = 5.0


def _mtime(path: pathlib.Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _load_json_direct(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def _load_json_cached(path: pathlib.Path, memo: dict) -> dict:
    """Memoised read: re-read at most every 5 s (mtime-checked in between)."""
    now = time.monotonic()
    if memo.get("path") == str(path) and memo.get("data") is not None:
        if now - memo.get("checked_at", 0.0) < _MEMO_RE_READ_S:
            return memo["data"]
        if _mtime(path) == memo.get("mtime"):
            memo["checked_at"] = now
            return memo["data"]
    data = _load_json_direct(path)
    memo.update({"path": str(path), "mtime": _mtime(path),
                 "checked_at": now, "data": data})
    return data


def _save_json_atomic(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _save_json_cached(path: pathlib.Path, memo: dict, data: dict) -> None:
    _save_json_atomic(path, data)
    memo.update({"path": str(path), "mtime": _mtime(path),
                 "checked_at": time.monotonic(), "data": data})


def _write_bytes_atomic(path: pathlib.Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def reset_caches() -> None:
    """Drop all in-process caches (test/debug hook). Nothing on disk changes."""
    for memo in (_POSTER_MEMO, _LIVE_MEMO):
        memo.update({"path": None, "mtime": 0.0, "checked_at": 0.0, "data": None})
    with _SEG_LOCK:
        _SEG_MAP.clear()
    with _STILL_MEM_LOCK:
        _STILL_MEM.clear()


# ---------------------------------------------------------------------------
# resolver registry (no network)
# ---------------------------------------------------------------------------

def host_resolvable(url) -> Optional[str]:
    """Resolver name for a camera url's host, or None. Pure / no network."""
    if not url:
        return None
    try:
        host = (urllib.parse.urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    for suffix, name in RESOLVER_REGISTRY:
        if host == suffix or host.endswith("." + suffix):
            return name
    return None


def _is_image_bytes(blob: bytes) -> bool:
    """Magic-byte sniff: is this a servable image at all?"""
    if not blob or len(blob) < 16:
        return False
    return (blob[:2] == b"\xff\xd8"                      # jpeg
            or blob[:8] == b"\x89PNG\r\n\x1a\n"          # png
            or blob[:3] == b"GIF"                        # gif
            or (blob[:4] == b"RIFF" and blob[8:12] == b"WEBP"))


def count_resolvable_rows(db_path=None) -> int:
    """Cheap read-only count of rows whose url host is in the resolver registry."""
    path = pathlib.Path(db_path) if db_path else (DATA_DIR / "worldfeed.db")
    if not path.exists():
        return 0
    uri = "file:" + urllib.parse.quote(path.resolve().as_posix(), safe="/:") + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return 0
    try:
        likes = " OR ".join("lower(url) LIKE ?" for _ in RESOLVER_REGISTRY)
        args = [f"%{suffix}%" for suffix, _ in RESOLVER_REGISTRY]
        return int(conn.execute(
            f"SELECT COUNT(*) FROM cameras WHERE ({likes})", args).fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# HTTP fetching (all gated + explicitly timed out)
# ---------------------------------------------------------------------------

def _http_get(url: str, *, headers: Optional[dict] = None,
              timeout: float = PAGE_TIMEOUT_S, gate: Optional[HostGate] = None,
              max_bytes: int = PAGE_MAX_BYTES):
    """One gated GET -> (body|None, lower-cased response headers, final url)."""
    host = urllib.parse.urlsplit(url).netloc or "-"
    if gate is not None:
        gate.acquire(host)
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes)
            info = {str(k).lower(): v for k, v in resp.headers.items()}
            return body, info, resp.geturl()
    except Exception:  # noqa: BLE001 — HTTPError/timeout/refused are normal outcomes
        return None, {}, url
    finally:
        if gate is not None:
            gate.release(host)


def fetch_page(page_url: str, *, timeout: float = PAGE_TIMEOUT_S) -> Optional[dict]:
    """Fetch a cam page with browser UA + cookie jar (the verified skyline recipe).

    NOTE: the browser UA must be sent as-is and no compression may be requested
    (the recipe is "no Accept-Encoding header"; urllib sends 'identity' at most).
    Returns {'html': str, 'cookie': str, 'final_url': str} or None.
    """
    if not page_url:
        return None
    try:
        host = urllib.parse.urlsplit(page_url).netloc or "-"
    except ValueError:
        return None
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    PAGE_GATE.acquire(host)
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": BROWSER_UA})
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(PAGE_MAX_BYTES)
            final_url = resp.geturl()
    except Exception:  # noqa: BLE001
        return None
    finally:
        PAGE_GATE.release(host)
    cookie = "; ".join(f"{c.name}={c.value}" for c in jar)
    return {"html": raw.decode("utf-8", "replace"),
            "cookie": cookie, "final_url": final_url}


def parse_social_image(html: str, base_url: Optional[str] = None) -> Optional[str]:
    """og:image (preferred) or twitter:image from an HTML page; absolute-ised."""
    if not html:
        return None
    og = tw = None
    for tag in _META_TAG_RE.findall(html):
        attrs = {}
        for m in _META_ATTR_RE.finditer(tag):
            attrs[m.group(1).lower()] = (m.group(2) or m.group(3) or m.group(4) or "")
        key = (attrs.get("property") or attrs.get("name") or "").strip().lower()
        content = (attrs.get("content") or "").strip()
        if not content:
            continue
        if key == "og:image" and og is None:
            og = content
        elif key == "twitter:image" and tw is None:
            tw = content
    chosen = og or tw
    if not chosen:
        return None
    if base_url:
        chosen = urllib.parse.urljoin(base_url, chosen)
    return chosen or None


def is_filler(text) -> bool:
    """True when an upstream playlist is the stale-token/geo filler, not a stream."""
    return "copyright_violation" in str(text or "").lower()


def is_dead_playlist(text) -> bool:
    """True when a playlist carries no media segments at all (dead/expired token).

    Skyline answers an expired token with a 6-line placeholder playlist
    (#EXT-X-TARGETDURATION:0 / #EXT-X-ENDLIST, zero segment lines); hls.js can
    play nothing from it, so the relay treats it as a stale resolution and
    re-resolves once before answering.
    """
    text = str(text or "")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return False
    return True


# ---------------------------------------------------------------------------
# live resolvers
# ---------------------------------------------------------------------------

def resolve_live_skyline(page_url: str) -> Optional[dict]:
    """Resolve one skylinewebcams.com player page to its HLS stream.

    Returns {'kind':'hls', 'url': m3u8, 'headers': {UA, Referer, Cookie},
    'ttl_s', 'poster'?} or None on failure. The og:image poster URL is captured
    from the SAME fetch whenever present (no second page request).
    """
    fetched = fetch_page(page_url)
    if fetched is None:
        return None
    m = SKYLINE_TOKEN_RE.search(fetched["html"])
    if not m:
        return None
    headers = {"User-Agent": BROWSER_UA, "Referer": SKYLINE_REFERER}
    if fetched["cookie"]:
        headers["Cookie"] = fetched["cookie"]
    out = {"kind": "hls", "url": SKYLINE_LIVE_BASE + m.group(1),
           "headers": headers, "ttl_s": LIVE_TTL_S}
    poster = parse_social_image(fetched["html"], fetched.get("final_url") or page_url)
    if poster:
        out["poster"] = poster
    return out


# Failure classes stored on negative youtube verdicts (the viewer renders them):
#   not-live  — the channel is up but not broadcasting right now
#   gone      — channel/handle no longer exists (404 / does not exist)
#   extractor — yt-dlp could not extract (anti-bot gate, JS challenge, format
#               loss); the stream itself may still be live. Verified TRANSIENT
#               2026-10-06: the same command failed with 'This video is not
#               available'/'Sign in to confirm you're not a bot' and minutes
#               later resolved — so this class must never read as 'dead'.
#   timeout   — the yt-dlp probe hit the 60 s host timeout
#   error     — anything else (e.g. yt-dlp not found)
_YT_FAILURES: dict = {}          # url -> last classified failure reason
_YT_FAILURES_MAX = 512


def _record_yt_failure(url, reason: str) -> None:
    if reason:
        if len(_YT_FAILURES) >= _YT_FAILURES_MAX:
            _YT_FAILURES.clear()
        _YT_FAILURES[url] = reason
    else:
        _YT_FAILURES.pop(url, None)


def yt_failure_reason(url) -> str:
    """Last classified yt-dlp failure reason for a youtube url ('' when none)."""
    return _YT_FAILURES.get(url, "")


def classify_youtube_failure(rc, err) -> str:
    """Map a failed yt-dlp probe to its viewer-visible failure class.

    Keyword mapping calibrated against real yt-dlp stderr (2026-10-06):
      'The channel is not currently live'                       -> 'not-live'
      'HTTP Error 404: Not Found' / 'does not exist'            -> 'gone'
      \"Sign in to confirm you're not a bot\" / 'This video is
       not available' / 'No video formats found' / n-challenge  -> 'extractor'
      rc -9 / 'timeout'                                         -> 'timeout'
      anything else                                             -> 'error'
    """
    e = str(err or "").lower()
    if rc == -9 or "timeout" in e:
        return "timeout"
    if ("not currently live" in e or "no longer live" in e
            or "premieres in" in e or "channel is not live" in e):
        return "not-live"
    if ("http error 404" in e or "does not exist" in e
            or "could not be found" in e or "not found" in e):
        return "gone"
    if ("sign in to confirm" in e or "not a bot" in e or "not available" in e
            or "no video formats" in e or "n challenge" in e
            or "unable to extract" in e or "nsig" in e or "challenge" in e
            or "failed to extract" in e or "unplayable" in e):
        return "extractor"
    return "error"


def resolve_live_youtube(url: str) -> Optional[dict]:
    """Resolve a YouTube (live) url to its video id via yt-dlp.

    On failure the classified reason is recorded first — read it back with
    :func:`yt_failure_reason` so the negative verdict can carry it.
    """
    ytdlp = _tool("yt-dlp")
    if not ytdlp:
        _record_yt_failure(url, "error")
        return None
    rc, out, err = _run([ytdlp, "--simulate", "--print", "id", "--no-warnings", url],
                        timeout=60)
    if rc != 0:
        _record_yt_failure(url, classify_youtube_failure(rc, err))
        return None
    vid = ""
    for line in (out or "").splitlines():
        line = line.strip()
        if line:
            vid = line
            break
    if not _YOUTUBE_ID_RE.fullmatch(vid):
        _record_yt_failure(url, "extractor")
        return None
    _record_yt_failure(url, "")
    return {"kind": "ytid", "id": vid,
            "poster": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "ttl_s": 1800}


def resolve_live_skaping(page_url: str) -> Optional[dict]:
    """Resolve one skaping.com player page to its current S3 still JPEG.

    The page (verified recipe, 2026-10-06) carries
    ``<meta property="og:image" content="https://skaping.s3.gra.io.cloud.ovh.net/
    <group>/<slug>/YYYY/MM/DD/HH-MM.jpg">`` — a 10-minute slot filename that
    always names the newest frame. The still URL serves plain (no cookies or
    referer needed). Returns {'kind':'image', 'url':..., 'headers':{UA},
    'ttl_s':900} or None (also when the og:image target is not an image file).
    """
    fetched = fetch_page(page_url)
    if fetched is None:
        return None
    url = parse_social_image(fetched["html"], fetched.get("final_url") or page_url)
    if not url:
        return None
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return None
    if not _IMAGE_EXT_RE.search(path):
        return None
    return {"kind": "image", "url": url,
            "headers": {"User-Agent": BROWSER_UA}, "ttl_s": SKAPING_TTL_S}


# ---------------------------------------------------------------------------
# live cache (data/resolve/live.json)
# ---------------------------------------------------------------------------

def _live_path() -> pathlib.Path:
    return resolve_dir() / "live.json"


def _entry_fresh(entry, *, now_iso_age: Optional[float] = None) -> bool:
    if not isinstance(entry, dict):
        return False
    ttl = entry.get("ttl_s")
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = LIVE_TTL_S if entry.get("ok") else LIVE_NEG_TTL_S
    age = _age_s(entry.get("resolved_at"))
    if age is None:
        return False
    return age <= ttl


def _live_cache_entry(camera_id: str) -> Optional[dict]:
    """Fresh live entry (positive or negative), None when absent/stale. No network."""
    entry = _load_json_cached(_live_path(), _LIVE_MEMO).get(camera_id)
    if not isinstance(entry, dict) or not _entry_fresh(entry):
        return None
    return entry


def cached_live(camera_id: str) -> Optional[bool]:
    """No network: True = fresh positive resolution, False = fresh negative, None = none."""
    entry = _live_cache_entry(camera_id)
    if entry is None:
        return None
    return bool(entry.get("ok"))


def cached_live_entry(camera_id: str) -> Optional[dict]:
    """Fresh *positive* live entry, or None. No network (viewer row fields use this)."""
    entry = _live_cache_entry(camera_id)
    return entry if entry and entry.get("ok") else None


def cached_negative_reason(camera_id: str) -> str:
    """Failure reason of a fresh negative live verdict ('' when none/positive). No network."""
    entry = _live_cache_entry(camera_id)
    if entry is None or entry.get("ok"):
        return ""
    return str(entry.get("reason") or "")


def live_needs_refresh(camera_id: str) -> bool:
    """No network: True when the live cache holds no fresh verdict for this camera."""
    return _live_cache_entry(camera_id) is None


def cached_live_count() -> int:
    """Number of positive entries in the live cache (no network; startup display)."""
    data = _load_json_cached(_live_path(), _LIVE_MEMO)
    return sum(1 for v in data.values() if isinstance(v, dict) and v.get("ok"))


def get_live(camera_id: str, page_url: str, *, force: bool = False) -> Optional[dict]:
    """Resolve (or return cached) a live stream for one camera.

    Stale entries re-resolve; negative results are cached for 120 s so failures
    cannot hammer the upstream site. One per-camera lock serialises callers.
    """
    lock = _cid_lock(camera_id, kind="live")
    with lock:
        if not force:
            entry = _live_cache_entry(camera_id)
            if entry is not None:
                return entry if entry.get("ok") else None
        resolver = host_resolvable(page_url)
        if resolver is None:
            return None
        try:
            host = (urllib.parse.urlsplit(str(page_url)).hostname or "").lower()
        except ValueError:
            host = ""
        result = None
        fail_reason = ""
        try:
            if resolver == "skylinewebcams":
                result = resolve_live_skyline(page_url)
            elif resolver == "youtube-live":
                _YT_FAILURES.pop(page_url, None)   # never read a stale reason
                result = resolve_live_youtube(page_url)
                if not result:
                    fail_reason = yt_failure_reason(page_url)
            elif resolver == "skaping":
                result = resolve_live_skaping(page_url)
        except Exception:  # noqa: BLE001 — resolution failure is a normal outcome
            result = None
        if result:
            new = dict(result)
            new.update({"ok": True, "resolved_at": _now_iso(), "host": host or resolver})
        else:
            new = {"ok": False, "error": f"{resolver} resolve failed",
                   "resolved_at": _now_iso(), "host": host or resolver,
                   "ttl_s": LIVE_NEG_TTL_S}
            if fail_reason:
                new["reason"] = fail_reason
        data = _load_json_direct(_live_path())
        data[camera_id] = new
        _save_json_cached(_live_path(), _LIVE_MEMO, data)
        return new if new.get("ok") else None


# ---------------------------------------------------------------------------
# poster cache (data/posters/<cid>.<ext> + index.json)
# ---------------------------------------------------------------------------

def _index_path() -> pathlib.Path:
    return posters_dir() / "index.json"


def _poster_file(camera_id: str) -> Optional[pathlib.Path]:
    for ext in ("jpg", "png"):
        p = posters_dir() / f"{camera_id}.{ext}"
        if p.exists():
            return p
    return None


def poster_index_entry(camera_id: str) -> Optional[dict]:
    """Index entry for one camera (no network; memoised)."""
    entry = _load_json_cached(_index_path(), _POSTER_MEMO).get(camera_id)
    return entry if isinstance(entry, dict) else None


def poster_fresh(camera_id: str) -> bool:
    """Fresh positive poster verdict (ok + file on disk). No network."""
    entry = poster_index_entry(camera_id)
    if not entry or not entry.get("ok"):
        return False
    if _poster_file(camera_id) is None:
        return False
    age = _age_s(entry.get("fetched_at"))
    return age is not None and age <= POSTER_TTL_S


def poster_exists(camera_id: str) -> bool:
    """True when a cached poster file exists (fresh or not). No network, O(1)."""
    entry = poster_index_entry(camera_id)
    return bool(entry and entry.get("ok") and _poster_file(camera_id) is not None)


def cached_poster_url(camera_id: str) -> Optional[str]:
    """'/api/poster/<cid>' when a cached poster file exists, else None. No network."""
    return f"/api/poster/{camera_id}" if poster_exists(camera_id) else None


def poster_needs_refresh(camera_id: str) -> bool:
    """No network: True when there is no fresh verdict (positive with file, or negative)."""
    entry = poster_index_entry(camera_id)
    if not entry:
        return True
    age = _age_s(entry.get("fetched_at"))
    if age is None:
        return True
    if entry.get("ok"):
        return age > POSTER_TTL_S or _poster_file(camera_id) is None
    return age > POSTER_NEG_TTL_S


def cached_poster_count() -> int:
    """Number of positive entries in the poster index (no network; startup display)."""
    data = _load_json_cached(_index_path(), _POSTER_MEMO)
    return sum(1 for v in data.values() if isinstance(v, dict) and v.get("ok"))


def _record_poster(camera_id: str, *, ok: bool, source: str,
                   error: Optional[str] = None) -> None:
    entry = {"ok": bool(ok), "fetched_at": _now_iso(), "source": source}
    if error:
        entry["error"] = str(error)[:200]
    data = _load_json_direct(_index_path())
    data[camera_id] = entry
    _save_json_cached(_index_path(), _POSTER_MEMO, data)


def _download_poster_image(url: str) -> Optional[bytes]:
    body, _info, _final = _http_get(url, headers={"User-Agent": BROWSER_UA},
                                    timeout=PAGE_TIMEOUT_S, gate=PAGE_GATE)
    if not body:
        return None
    return body


def _og_poster_from_page(page_url: str) -> Optional[tuple]:
    """Fetch a page and pull its og:image/twitter:image -> (url, error_text)."""
    fetched = fetch_page(page_url)
    if fetched is None:
        return None, "page fetch failed"
    poster = parse_social_image(fetched["html"], fetched.get("final_url") or page_url)
    if not poster:
        return None, "no og:image meta"
    return poster, ""


def _store_poster_blob(camera_id: str, blob: bytes, source: str) -> pathlib.Path:
    """Write poster bytes atomically (jpg/png sniff), drop the other ext, record."""
    ext = _sniff_ext(blob)
    path = posters_dir() / f"{camera_id}.{ext}"
    _write_bytes_atomic(path, blob)
    for other in ("jpg", "png"):
        if other != ext:
            try:
                (posters_dir() / f"{camera_id}.{other}").unlink()
            except OSError:
                pass
    _record_poster(camera_id, ok=True, source=source)
    return path


def _snapshot_stream_frame(camera_id: str, page_url: str) -> Optional[bytes]:
    """One ffmpeg frame from an hls/mjpeg stream -> JPEG bytes or None.

    Uses the fresh resolved stream url + UA when one is cached (skyline-style
    pages), else the row url itself (raw m3u8/mjpeg). Captures run through
    SNAPSHOT_GATE (cap 2 / 0.3 s per host) so a wall of tiles cannot stampede
    one stream. rc!=0 or a missing/empty/non-image output file is a failure.
    """
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg or not page_url:
        return None
    url, ua = str(page_url), None
    entry = cached_live_entry(camera_id)
    if entry and entry.get("kind") == "hls" and entry.get("url"):
        url = entry["url"]
        ua = (entry.get("headers") or {}).get("User-Agent")
    try:
        host = urllib.parse.urlsplit(url).netloc or "-"
    except ValueError:
        host = "-"
    posters_dir().mkdir(parents=True, exist_ok=True)
    tmp = posters_dir() / (f".snap-{camera_id}-{os.getpid()}-"
                           f"{time.monotonic_ns()}.jpg")
    SNAPSHOT_GATE.acquire(host)
    try:
        cmd = [ffmpeg, "-v", "error", "-nostdin", "-rw_timeout", "15000000"]
        if ua:
            cmd += ["-user_agent", str(ua)]
        cmd += ["-i", url, "-frames:v", "1", "-vf", "scale=640:-2",
                "-f", "image2", "-y", str(tmp)]
        rc, _out, _err = _run(cmd, SNAPSHOT_TIMEOUT_S)
        if rc != 0:
            return None
        try:
            blob = tmp.read_bytes()
        except OSError:
            return None
        if not _is_image_bytes(blob):
            return None
        return blob
    finally:
        SNAPSHOT_GATE.release(host)
        try:
            tmp.unlink()
        except OSError:
            pass


def get_poster(camera_id: str, page_url: str, *, force: bool = False,
               protocol: Optional[str] = None) -> Optional[pathlib.Path]:
    """Fetch (or return cached) a poster file for one camera. Per-cid locked.

    Fresh positive (12 h) and negative (1 h) verdicts short-circuit the network;
    ``force=True`` refetches regardless. Skyline pages come with their og:image
    on the same page fetch the live resolver needs; skaping pages carry their
    10-minute S3 still as og:image; YouTube tries the page's og:image FIRST
    (fast, usually the video's best thumbnail) and keeps the yt-dlp/ytimg path
    as fallback (yt-dlp itself stays for id resolution in get_live). When
    ``protocol`` is hls/mjpeg and no page poster applies, a single ffmpeg frame
    is captured instead (source 'snapshot') — that fills stream-tile 'no
    poster' placeholders. A raw jpeg row's url IS the live image: the current
    bytes are stored directly (source 'direct'), with the og:image page scrape
    kept as a fallback when the url does not actually serve image bytes.
    """
    lock = _cid_lock(camera_id, kind="poster")
    with lock:
        if not force:
            if poster_fresh(camera_id):
                return _poster_file(camera_id)
            entry = poster_index_entry(camera_id)
            if entry is not None and not entry.get("ok"):
                age = _age_s(entry.get("fetched_at"))
                if age is not None and age <= POSTER_NEG_TTL_S:
                    return None  # negative verdict still fresh
        proto = str(protocol or "").lower()
        source = "fail"
        error = ""
        poster_url = None
        try:
            resolver = host_resolvable(page_url)
            if resolver == "skylinewebcams":
                poster_url, error = _og_poster_from_page(page_url)
                if poster_url:
                    source = "og"
            elif resolver == "youtube-live":
                poster_url, error = _og_poster_from_page(page_url)
                if poster_url:
                    source = "og"
                else:
                    entry = cached_live_entry(camera_id)
                    if entry and entry.get("kind") == "ytid" and entry.get("poster"):
                        poster_url, source = entry["poster"], "ytimg"
                    else:
                        res = resolve_live_youtube(page_url)
                        if res and res.get("poster"):
                            poster_url, source = res["poster"], "ytimg"
            elif resolver == "skaping":
                poster_url, error = _og_poster_from_page(page_url)
                if poster_url:
                    source = "og"
            elif proto == "jpeg":
                # a raw still row: the url IS the live image — store the current
                # bytes directly; when the url does not serve image bytes (e.g.
                # a mislabeled page row), fall back to the og:image scrape.
                raw_blob = _download_poster_image(page_url) if page_url else None
                if raw_blob is not None and _is_image_bytes(raw_blob):
                    return _store_poster_blob(camera_id, raw_blob, "direct")
                if page_url and str(page_url).lower().startswith(("http://", "https://")):
                    poster_url, error = _og_poster_from_page(page_url)
                    if poster_url:
                        source = "og"
                if not poster_url:
                    error = error or "raw still fetch failed"
            elif proto in ("hls", "mjpeg"):
                # a raw stream url has no page to scrape — go straight to frame
                error = "stream protocol: single-frame snapshot"
            elif page_url and str(page_url).lower().startswith(("http://", "https://")):
                poster_url, error = _og_poster_from_page(page_url)
                if poster_url:
                    source = "og"
            else:
                error = "no fetchable page url"
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        if not poster_url and proto in ("hls", "mjpeg"):
            blob = _snapshot_stream_frame(camera_id, page_url)
            if blob is not None:
                return _store_poster_blob(camera_id, blob, "snapshot")
            if not error:
                error = "snapshot failed"
        if not poster_url:
            _record_poster(camera_id, ok=False, source="fail",
                           error=error or "no poster found")
            return None
        blob = _download_poster_image(poster_url)
        if not blob:
            _record_poster(camera_id, ok=False, source="fail",
                           error="poster image download failed")
            return None
        return _store_poster_blob(camera_id, blob, source)


# ---------------------------------------------------------------------------
# still bytes cache (in-process, ~90 s) — skaping-style 'image' resolutions
# ---------------------------------------------------------------------------

_STILL_MEM: dict = {}          # cid -> {'blob': bytes, 'ctype': str, 'ts': monotonic}
_STILL_MEM_LOCK = threading.Lock()


def _still_memo_peek(camera_id: str):
    """(blob, ctype, age_s) for the fresh in-process still memo, else None."""
    with _STILL_MEM_LOCK:
        hit = _STILL_MEM.get(camera_id)
        if hit is not None:
            age = time.monotonic() - hit.get("ts", 0.0)
            if age <= STILL_TTL_S:
                return hit["blob"], hit["ctype"], age
    return None


def still_cached(camera_id: str) -> bool:
    """True when fresh still bytes sit in the in-process memo. No network."""
    return _still_memo_peek(camera_id) is not None


def _still_memo_put(camera_id: str, blob: bytes, ctype: str) -> None:
    with _STILL_MEM_LOCK:
        _STILL_MEM[camera_id] = {"blob": blob, "ctype": ctype, "ts": time.monotonic()}


def _fetch_still_image(entry: dict):
    """Fetch one 'image'-kind entry's still -> (bytes|None, content-type|None)."""
    url = (entry or {}).get("url")
    if not url:
        return None, None
    body, info, _final = _http_get(url, headers=(entry or {}).get("headers") or {},
                                   timeout=PAGE_TIMEOUT_S, gate=PAGE_GATE)
    if not _is_image_bytes(body):
        return None, None
    ctype = (info.get("content-type") or "").split(";")[0].strip()
    if not _MEDIA_TYPE_RE.fullmatch(ctype or ""):
        ctype = image_content_type(body)
    return body, ctype


def get_still(camera_id: str, page_url: str, *,
              force: bool = False) -> tuple:
    """Current still bytes for one camera -> (bytes|None, content_type|None).

    Resolves through :func:`get_live` (kind 'image' — e.g. skaping's newest
    10-minute S3 JPEG), fetches the image with the entry's headers, and memoises
    the bytes in process for ~90 s (dict + lock). On an image-fetch failure the
    resolution is refreshed once (force) and the fetch retried once. Per-cid
    locked like the other caches; (None, None) on any failure.
    """
    lock = _cid_lock(camera_id, kind="still")
    with lock:
        if not force:
            memo = _still_memo_peek(camera_id)
            if memo is not None:
                return memo[0], memo[1]
        entry = get_live(camera_id, page_url, force=force)
        blob = ctype = None
        if entry and entry.get("kind") == "image":
            blob, ctype = _fetch_still_image(entry)
            if blob is None:
                entry = get_live(camera_id, page_url, force=True)   # refresh once
                if entry and entry.get("kind") == "image":
                    blob, ctype = _fetch_still_image(entry)
        if blob is None:
            return None, None
        ctype = ctype or image_content_type(blob)
        _still_memo_put(camera_id, blob, ctype)
        return blob, ctype


# ---------------------------------------------------------------------------
# playlist rewriting + per-cid segment map
# ---------------------------------------------------------------------------

_SEG_MAP: dict = {}   # cid -> {name: {"url": upstream, "ts": monotonic, "marker": str}}
_SEG_LOCK = threading.Lock()


def _prune_segments(now: Optional[float] = None) -> None:
    now = now if now is not None else time.monotonic()
    with _SEG_LOCK:
        for cid in list(_SEG_MAP.keys()):
            entries = _SEG_MAP[cid]
            for name in list(entries.keys()):
                if now - entries[name].get("ts", 0.0) > SEG_TTL_S:
                    del entries[name]
            if not entries:
                _SEG_MAP.pop(cid, None)


def _register_segment(camera_id: str, name: str, url: str, marker: str) -> None:
    with _SEG_LOCK:
        _SEG_MAP.setdefault(camera_id, {})[name] = {
            "url": url, "ts": time.monotonic(), "marker": marker or ""}


def seg_upstream(camera_id: str, name: str) -> Optional[str]:
    """Upstream URL registered for one rewritten segment name, or None. No network."""
    now = time.monotonic()
    _prune_segments(now)
    with _SEG_LOCK:
        entry = _SEG_MAP.get(camera_id, {}).get(name)
        if entry and now - entry.get("ts", 0.0) <= SEG_TTL_S:
            return entry.get("url")
    return None


def _seg_name_from_url(raw: str) -> str:
    """URL -> URL-safe basename ([A-Za-z0-9._-]{1,180}); invalid chars -> '_'."""
    try:
        path = urllib.parse.urlsplit(str(raw)).path
    except ValueError:
        path = str(raw)
    base = urllib.parse.unquote(path.rsplit("/", 1)[-1]) if path else ""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:180]
    if not name or not SEG_NAME_RE.fullmatch(name):
        name = hashlib.sha1(str(raw).encode("utf-8", "replace")).hexdigest()[:20] + ".bin"
    return name


def _is_absolute_url(raw) -> bool:
    s = str(raw or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def resolve_playlist(camera_id: str, upstream_text: str, marker: str = "") -> str:
    """Rewrite a resolved HLS playlist so every media/attribute URI flows through
    ``/api/live/<cid>/seg/<name>`` and register ``name -> upstream URL`` in the
    per-cid in-memory segment map (module-level, pruned after 20 min).

    Pure apart from that in-memory registration (no network, no disk). Raises
    :class:`FillerError` when the playlist is the 'copyright_violation' filler —
    the caller refreshes the resolution once and retries.
    """
    if is_filler(upstream_text):
        raise FillerError("upstream playlist is the copyright_violation filler")
    prefix = f"/api/live/{camera_id}/seg/"
    out = []
    for line in str(upstream_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
        elif stripped.startswith("#"):
            if "URI=" in stripped:
                def _sub(m):
                    raw = m.group(1) if m.group(1) is not None else m.group(2)
                    if not _is_absolute_url(raw):
                        return m.group(0)
                    name = _seg_name_from_url(raw)
                    _register_segment(camera_id, name, raw, marker)
                    return f'URI="{prefix}{name}"'
                line = _URI_ATTR_RE.sub(_sub, line)
            out.append(line)
        elif _is_absolute_url(stripped):
            name = _seg_name_from_url(stripped)
            _register_segment(camera_id, name, stripped, marker)
            out.append(prefix + name)
        else:
            out.append(line)
    text = "\n".join(out)
    if str(upstream_text or "").endswith("\n"):
        text += "\n"
    return text


def fetch_playlist(entry: dict, *, timeout: float = RELAY_TIMEOUT_S) -> Optional[str]:
    """Fetch the resolved upstream playlist using the resolver headers."""
    url = (entry or {}).get("url")
    if not url:
        return None
    body, _info, _final = _http_get(url, headers=(entry or {}).get("headers") or {},
                                    timeout=timeout, gate=RELAY_GATE)
    if body is None:
        return None
    return body.decode("utf-8", "replace")


def fetch_segment(url: str, headers: Optional[dict] = None, *,
                  timeout: float = RELAY_TIMEOUT_S):
    """Fetch one upstream segment/child URI -> (body|None, content_type|None)."""
    body, info, _final = _http_get(url, headers=headers or {}, timeout=timeout,
                                   gate=RELAY_GATE, max_bytes=SEGMENT_MAX_BYTES)
    if body is None:
        return None, None
    ctype = (info.get("content-type") or "").split(";")[0].strip()
    if not _MEDIA_TYPE_RE.fullmatch(ctype):
        ctype = None
    return body, ctype


# ---------------------------------------------------------------------------
# CLI: wfd resolve warm / show
# ---------------------------------------------------------------------------

def _warm_candidates(family: str, host: str, protocol: str = ""):
    """[(camera_id, url, resolver, protocol)] for displayable rows worth warming.

    Resolver-host rows (skylinewebcams / youtube / skaping) are always
    candidates. Raw rows — hls/mjpeg (poster via ffmpeg snapshot) and jpeg
    stills (poster via direct download) — are only candidates once the caller
    narrows with ``--host``/``--family``/``--protocol``; a bare
    ``warm --kind poster`` must never try to snapshot the whole
    multi-thousand-row stream wall.
    """
    db_path = DATA_DIR / "worldfeed.db"
    if not db_path.exists():
        return None
    uri = "file:" + urllib.parse.quote(db_path.resolve().as_posix(), safe="/:") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT camera_id, url, source_family, protocol FROM cameras "
            "WHERE provenance IN ('public_by_design','aggregator_directory')"
        ).fetchall()
    finally:
        conn.close()
    out = []
    fam = (family or "").strip().lower()
    host = (host or "").strip().lower()
    proto = (protocol or "").strip().lower()
    narrow = bool(fam or host or proto)
    for r in rows:
        if fam and (r["source_family"] or "").lower() != fam:
            continue
        row_proto = (r["protocol"] or "").lower()
        if proto and row_proto != proto:
            continue
        if host:
            try:
                h = (urllib.parse.urlsplit(r["url"]).hostname or "").lower()
            except ValueError:
                h = ""
            if not (h == host or h.endswith("." + host)):
                continue
        resolver = host_resolvable(r["url"])
        if resolver is None:
            if not narrow:
                continue          # no explicit narrowing: resolver hosts only
            if row_proto not in _RAW_POSTER_PROTOCOLS:
                continue          # only snapshot-grade rows qualify
        out.append((r["camera_id"], r["url"], resolver, row_proto))
    out.sort()
    return out


def _cmd_resolve_warm(args) -> int:
    kind = getattr(args, "kind", "both") or "both"
    family = getattr(args, "family", "") or ""
    host = getattr(args, "host", "") or ""
    protocol = getattr(args, "protocol", "") or ""
    limit = max(0, int(getattr(args, "limit", 0) or 0))
    refresh = bool(getattr(args, "refresh", False))
    kinds = ("poster", "live") if kind == "both" else (kind,)

    candidates = _warm_candidates(family, host, protocol)
    if candidates is None:
        print(f"resolve warm: registry database not found at {DATA_DIR / 'worldfeed.db'}")
        return 1
    ev_path = resolve_dir() / f"warm-{kind}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"resolve warm: kind={kind} candidates={len(candidates)}"
          + (f" family={family}" if family else "")
          + (f" host={host}" if host else "")
          + (f" protocol={protocol}" if protocol else "")
          + (f" limit={limit}" if limit else "")
          + f"\n  evidence: {ev_path}")

    processed = ok = fail = skipped = 0
    with ev_path.open("a", encoding="utf-8") as ev:
        for cid, url, resolver, proto in candidates:
            for k in kinds:
                if limit and processed >= limit:
                    break
                if k == "live" and resolver is None:
                    skipped += 1       # no resolver for this row — nothing to warm
                    continue
                if not refresh:
                    needs = (poster_needs_refresh(cid) if k == "poster"
                             else live_needs_refresh(cid))
                    if not needs:
                        skipped += 1
                        continue
                t0 = time.monotonic()
                error = ""
                good = False
                try:
                    if k == "poster":
                        good = get_poster(cid, url, force=refresh,
                                          protocol=proto) is not None
                    else:
                        good = get_live(cid, url, force=refresh) is not None
                except Exception as exc:  # noqa: BLE001 — record, keep going
                    error = f"{type(exc).__name__}: {exc}"
                ms = int((time.monotonic() - t0) * 1000)
                processed += 1
                if good:
                    ok += 1
                else:
                    fail += 1
                ev.write(json.dumps({"cid": cid, "ok": good, "kind": k, "ms": ms,
                                     "error": error}, ensure_ascii=False) + "\n")
                ev.flush()
                if processed % 25 == 0:
                    print(f"  [{processed}] ok={ok} fail={fail} skipped={skipped}")
            if limit and processed >= limit:
                break
    print(f"resolve warm: done kind={kind} processed={processed} ok={ok} "
          f"fail={fail} skipped={skipped}")
    return 0


def _cmd_resolve_show(args) -> int:
    cid = str(getattr(args, "camera_id", "") or "").strip()
    print(f"resolve show {cid}")
    index = _load_json_direct(_index_path())
    entry = index.get(cid)
    path = _poster_file(cid)
    if path is not None:
        try:
            size = path.stat().st_size
            head = path.read_bytes()[:16]
        except OSError:
            size, head = 0, b""
        fresh = "fresh" if poster_fresh(cid) else "stale"
        print(f"  poster: {path} ({size} bytes, {image_content_type(head)}, {fresh})")
    elif isinstance(entry, dict):
        state = "ok but file missing" if entry.get("ok") else "failed"
        print(f"  poster: none ({state}; source={entry.get('source')}"
              + (f", error={entry.get('error')}" if entry.get("error") else "") + ")")
    else:
        print("  poster: none (not cached)")

    live = _load_json_direct(_live_path()).get(cid)
    if not isinstance(live, dict):
        print("  live:   none (not cached)")
    else:
        age = _age_s(live.get("resolved_at"))
        state = "fresh" if _entry_fresh(live) else "stale"
        print(f"  live:   kind={live.get('kind')} host={live.get('host')} "
              f"resolved_at={live.get('resolved_at')} ttl={live.get('ttl_s')}s "
              f"({state}" + (f", age={int(age)}s" if age is not None else "") + ")")
        if live.get("kind") == "ytid":
            vid = str(live.get("id") or "")
            shown_id = vid if _YOUTUBE_ID_RE.fullmatch(vid) else "<invalid>"
            print(f"          yt_id={shown_id}")
        if live.get("url"):
            print(f"          url={redact_url_for_display(live['url'])}")
        headers = live.get("headers") or {}
        for key in ("Cookie", "cookie"):
            if headers.get(key):
                n = str(headers[key]).count("=")
                print(f"          cookie=<redacted sha1:{redact(headers[key])}> "
                      f"({n} pair(s) hidden)")
                break
        if live.get("poster"):
            print(f"          poster={live['poster']}")
        if live.get("kind") == "image":
            memo = _still_memo_peek(cid)
            if memo is not None:
                print(f"          still:  in-process memo ({len(memo[0])} bytes, "
                      f"{memo[1]}, age={int(memo[2])}s)")
            else:
                print("          still:  not in this process's memo "
                      f"(/api/still/{cid} fetches on demand)")
        if not live.get("ok") and live.get("error"):
            print(f"          error={live.get('error')}")
    return 0


def _cmd_resolve(args) -> int:
    sub = getattr(args, "resolve_command", None)
    if sub == "warm":
        return _cmd_resolve_warm(args)
    if sub == "show":
        return _cmd_resolve_show(args)
    print("usage: wfd resolve {warm,show} ...  (see 'wfd resolve warm --help')")
    return 2


def _add_resolve_arguments(parser) -> None:
    sub = parser.add_subparsers(dest="resolve_command")
    warm = sub.add_parser("warm", help="cache posters / live resolutions (resumable, polite)")
    warm.add_argument("--kind", choices=("poster", "live", "both"), default="both")
    warm.add_argument("--family", default="", help="restrict to one source_family")
    warm.add_argument("--host", default="", help="restrict to one url host (suffix match)")
    warm.add_argument("--protocol", default="",
                      help="restrict to one protocol (hls|mjpeg|jpeg|...); plain "
                           "hls/mjpeg/jpeg snapshot candidates are only ever "
                           "included when --host/--family/--protocol narrows the set")
    warm.add_argument("--limit", type=int, default=0,
                      help="max rows to fetch this run (0 = no cap)")
    warm.add_argument("--refresh", action="store_true",
                      help="re-fetch even when a fresh cache verdict exists")
    show = sub.add_parser("show", help="debug: cached poster + live summary for one camera")
    show.add_argument("camera_id")


_cmd_resolve.add_arguments = _add_resolve_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd resolve``."""
    return {"resolve": ("resolve live streams + posters (skyline/youtube) and cache them",
                        _cmd_resolve)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.resolve")
    _add_resolve_arguments(parser)
    return _cmd_resolve(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())

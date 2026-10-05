"""wfd.ingest.newsrc.camsecure_webcams — Camsecure Live Demo Index (demo cams).

Camsecure (camsecure.co.uk) hosts webcams for clubs/venues and publishes a
public "Live Demo Index" of them. Enumeration path (mechanism verified live
2026-10-06 — see notes inline):

1. Index: ``GET https://www.camsecure.co.uk/Camsecure_Live_Demo_Index.html``
   (39,230 B; our identifiable default UA is accepted fine). Cam pages are
   taken from the two demo listing zones — the CoffeeCup image map
   (``<area href=...>``) and the "most popular webcam areas" region grid
   (``<a class="link-text ...">`` anchors up to ``id="Page-Bottom"``). Non-cam
   pages never enter: product/support/nav links sit outside those zones, and
   the explicit exclusion set also drops the Christmas TV *channel* page, the
   world-map index page and the live-channel demo (``live.html``).
2. Per cam page, the player wrapper iframe:
   ``(?:https?:)?//camsecure.(co|uk)/httpswebcam/camsecure/<code>.html`` —
   BOTH absolute and protocol-relative ``//`` forms occur (a first-pass crawl
   that matched only ``http(s)://`` missed 5 wrappers).
3. Fetch the wrapper WITH ``Referer: <its cam page URL>``. Without the
   Referer the wrapper answers ``200 image/png`` with a 108,341 B placeholder
   ("This Website Is Not Authorised to Show This Content") — anti-hotlink
   guard, not a feed (verified both ways 2026-10-06). The LIVE m3u8s
   themselves are open once known (no Referer needed).
4. The wrapper holds a video.js player with exactly one ``<source src=...>``:
   - HLS: ``/HLS/<name>.m3u8`` (root-relative), ``//<host>/HLS/...``
     (protocol-relative) or absolute — all three forms occur; resolve against
     the wrapper URL (host is camsecure.co or camsecure.uk). Wrapper code !=
     stream name (``weymouth`` -> ``bayvwebcam.m3u8``): parse, never construct.
   - YouTube: ``https://www.youtube.com/embed/<id>`` — the 2 YouTube demo cams
     (Levi, Finland; Isle of Wight Steam Railway); row url becomes
     ``https://www.youtube.com/watch?v=<id>``, protocol ``youtube``.

Liveness doctrine: every row enters ``status="unknown"`` — enumeration NEVER
claims liveness. The two YouTube rows get an oEmbed existence check recorded
as ``meta["oembed_ok"]`` (200 = the video exists, NOT that it is live).

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.camsecure_webcams
"""
from __future__ import annotations

import html as _html
import json as _json
import re
import time
import urllib.error
import urllib.parse

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

INDEX_URL = "https://www.camsecure.co.uk/Camsecure_Live_Demo_Index.html"
INDEX_BASE = "https://www.camsecure.co.uk/"
OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
ATTRIBUTION = "Camsecure (camsecure.co.uk) — live demo index"

# --- link / markup patterns ---------------------------------------------------

_MAP_RE = re.compile(r"<map\b[^>]*>(.*?)</map>", re.S | re.I)
_TAG_RE = re.compile(r"<(area|a)\b([^>]*)>", re.I)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_SRC_RE = re.compile(r"""src\s*=\s*["']([^"']+)["']""", re.I)
_CLASS_RE = re.compile(r"""class\s*=\s*["']([^"']*)["']""", re.I)
_GRID_HEADING = "popular webcam areas"
_GRID_END_RE = re.compile(r"""id\s*=\s*["']Page-Bottom["']""", re.I)
_IFRAME_RE = re.compile(r"<iframe\b[^>]*>", re.I)
_WRAPPER_RE = re.compile(
    r"^(?:(?:https?:)?//camsecure\.(?:co|uk)(?:\.uk)?)?/httpswebcam/camsecure/"
    r"(?P<code>[^\"'?#\s]+?)\.html(?:[?#].*)?$",
    re.I)
_SOURCE_SRC_RE = re.compile(r"<source\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_YT_EMBED_RE = re.compile(r"youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]+)", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_WS_RE = re.compile(r"\s+")

# Camsecure's non-cam pages. The scoped extraction (map + region grid) already
# keeps these out; the explicit set is drift insurance and covers the ones
# that DO appear inside the grid (christmas_tv, world map, live channel demo).
_NON_CAM_HINTS = (
    "productsupport", "sitemap", "camsecureipnetworkwebcams", "site_information",
    "webcamhosting", "contact_us", "christmas_tv", "world_webcam_map",
)


def _clean_url(href: str) -> str:
    """Normalize an index href: unquote, re-quote (spaces -> %20), absolutize."""
    ref = urllib.parse.unquote(_html.unescape(href).strip())
    ref = urllib.parse.quote(ref, safe="/")
    return urllib.parse.urljoin(INDEX_BASE, ref)


def _is_non_cam(url: str) -> bool:
    low = url.lower()
    if any(h in low for h in _NON_CAM_HINTS):
        return True
    return urllib.parse.urlsplit(low).path.endswith("/live.html")


def parse_index_cam_pages(index_html: str) -> list:
    """Cam-page URLs listed on the Live Demo Index (order kept, deduped).

    Sources: the image map's ``<area>`` links + the region-grid anchors
    (``class="...link-text..."`` between the "popular webcam areas" heading and
    ``id="Page-Bottom"``). Inline prose links inside the same region carry no
    ``link-text`` class and are skipped; non-cam pages are excluded explicitly.
    """
    html = index_html or ""
    hrefs: list = []
    for block in _MAP_RE.findall(html):
        for tag, attrs in _TAG_RE.findall(block):
            if tag.lower() == "area":
                m = _HREF_RE.search(attrs)
                if m:
                    hrefs.append(m.group(1))
    i0 = html.lower().find(_GRID_HEADING)
    if i0 != -1:
        end = _GRID_END_RE.search(html, i0)
        grid = html[i0:end.start() if end else len(html)]
        for tag, attrs in _TAG_RE.findall(grid):
            if tag.lower() != "a":
                continue
            cls = _CLASS_RE.search(attrs)
            if not cls or "link-text" not in cls.group(1):
                continue                      # inline prose links have no class
            m = _HREF_RE.search(attrs)
            if m:
                hrefs.append(m.group(1))

    pages, seen = [], set()
    for href in hrefs:
        url = _clean_url(href)
        if not urllib.parse.urlsplit(url).path.lower().endswith(".html"):
            continue
        if _is_non_cam(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        pages.append(url)
    return pages


def find_wrapper(cam_page_html: str):
    """``(iframe_src, wrapper_code)`` for the camsecure player iframe.

    Handles absolute AND protocol-relative (``//camsecure.co/...``) srcs —
    both occur across the index. ``(None, None)`` when the page has no wrapper
    (e.g. the Tennis Club page, whose wrapper was removed).
    """
    for tag in _IFRAME_RE.findall(cam_page_html or ""):
        m = _SRC_RE.search(tag)
        if not m:
            continue
        src = _html.unescape(m.group(1).strip())
        wm = _WRAPPER_RE.match(src)
        if wm:
            return src, wm.group("code")
    return None, None


def parse_wrapper_media(wrapper_html: str, wrapper_url: str):
    """First ``<source src=...>`` of the wrapper player -> ``(raw, url, kind)``.

    ``kind`` is ``"hls"`` (m3u8 resolved against the wrapper URL's host) or
    ``"youtube"`` (embed id -> watch URL). ``(None, None, None)`` when no
    source exists (e.g. the anti-hotlink placeholder fetched without Referer).
    """
    m = _SOURCE_SRC_RE.search(wrapper_html or "")
    if not m:
        return None, None, None
    raw = _html.unescape(m.group(1).strip())
    yt = _YT_EMBED_RE.search(raw)
    if yt:
        return raw, f"https://www.youtube.com/watch?v={yt.group(1)}", "youtube"
    return raw, urllib.parse.urljoin(wrapper_url, raw), "hls"


def page_title(cam_page_html: str) -> str:
    """Cleaned ``<title>`` of a cam page ("" when absent)."""
    m = _TITLE_RE.search(cam_page_html or "")
    if not m:
        return ""
    return _WS_RE.sub(" ", _html.unescape(m.group(1))).strip()


def country_for(wrapper_code: str) -> str:
    """GB for the UK demo cams; FI for Levi (Lapland) — the one non-UK cam."""
    return "FI" if clean_str(wrapper_code).lower().startswith("christmas/levi") else "GB"


def oembed_url(video_id: str) -> str:
    """oEmbed existence-check URL for a YouTube watch URL."""
    target = f"https://www.youtube.com/watch?v={clean_str(video_id)}"
    return f"{OEMBED_ENDPOINT}?url={urllib.parse.quote(target, safe='')}&format=json"


# --- fetch helper (429 retry) -------------------------------------------------

_429_DELAY_S = 5.0
_sleep = time.sleep                      # module-level seam for tests


def _fetch(cache, url: str, *, headers=None, suffix: str = ".html", attempts: int = 3) -> bytes:
    """Cache GET with bounded 429 retry + Retry-After respect.

    ``base.polite_get`` retries 5xx/network errors but raises 4xx (including
    429) immediately; this helper adds the 429 backoff locally (base.py is
    off-limits for this build task).
    """
    for i in range(attempts):
        try:
            return cache.get(url, headers=headers, suffix=suffix)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or i == attempts - 1:
                raise
            delay = _429_DELAY_S * (i + 1)
            try:
                delay = max(delay, float((exc.headers or {}).get("Retry-After")))
            except (TypeError, ValueError):
                pass
            _sleep(min(delay, 60.0))
    raise AssertionError("unreachable")


# --- enumerator ---------------------------------------------------------------

class CamsecureWebcamsEnumerator(Enumerator):
    """Enumerate the Camsecure live demo cams (index -> cam pages -> wrappers)."""

    name = "camsecure-webcams"
    source_ref = INDEX_URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=INDEX_URL,
            notes=("index -> cam pages (image map + region grid) -> Referer'd wrapper -> "
                   "<source> media; wrapper code != stream name (parsed, never constructed); "
                   "oembed on the 2 YouTube rows is an existence check only (meta oembed_ok)"),
        )

        index_html = _fetch(cache, INDEX_URL).decode("utf-8", "replace")
        pages = parse_index_cam_pages(index_html)
        result.stats["pages_listed"] = len(pages)
        if not pages:
            raise RuntimeError("camsecure demo index yielded 0 cam pages")
        work = pages[: int(self.limit)] if self.limit is not None else pages
        if self.limit is not None:
            result.stats["limit"] = int(self.limit)
        result.stats["pages_considered"] = len(work)

        seen: set = set()
        dupes = skipped_wrapper = skipped_media = 0
        hls_rows = youtube_rows = yt_oembed_ok = 0
        failed: list = []

        for cam_page in work:
            try:
                page_html = _fetch(cache, cam_page).decode("utf-8", "replace")
            except Exception as exc:  # noqa: BLE001 — count and continue; re-run resumes
                failed.append((cam_page, f"{type(exc).__name__}: {exc}"))
                continue

            wrapper_src, code = find_wrapper(page_html)
            if not wrapper_src:
                skipped_wrapper += 1          # e.g. Tennis Club: wrapper removed
                continue
            wrapper_url = urllib.parse.urljoin(cam_page, wrapper_src)
            try:
                wrapper_html = _fetch(
                    cache, wrapper_url, headers={"Referer": cam_page}
                ).decode("utf-8", "replace")
            except Exception as exc:  # noqa: BLE001
                failed.append((wrapper_url, f"{type(exc).__name__}: {exc}"))
                continue

            media_raw, media_url, kind = parse_wrapper_media(wrapper_html, wrapper_url)
            if not media_url:
                skipped_media += 1
                continue

            url, was_red, cred = redact_and_flag(media_url)
            if url in seen:
                dupes += 1
                continue
            seen.add(url)

            meta = {
                "index_page": INDEX_URL,
                "wrapper_code": code,
                "cam_page": cam_page,
                "media": media_raw,           # raw <source src> value (drift evidence)
                "referer_note": ("same-site Referer required for the wrapper fetch "
                                 "(placeholder PNG without it); Referer used = cam_page"),
            }
            if kind == "youtube":
                video_id = media_url.split("=", 1)[-1]
                ok, author, title = False, "", ""
                try:
                    payload = _json.loads(
                        _fetch(cache, oembed_url(video_id), suffix=".json")
                        .decode("utf-8-sig", "replace"))
                    if not isinstance(payload, dict):
                        raise ValueError(f"unexpected oembed payload type {type(payload).__name__}")
                    ok, author, title = True, clean_str(payload.get("author_name")), clean_str(payload.get("title"))
                except Exception as exc:  # noqa: BLE001 — meta-only; row is kept
                    meta["oembed_error"] = f"{type(exc).__name__}: {exc}"
                meta.update({"oembed_ok": ok, "oembed_author": author, "oembed_title": title})
                if ok:
                    yt_oembed_ok += 1
                youtube_rows += 1
                proto = Protocol.YOUTUBE.value
            else:
                hls_rows += 1
                proto = Protocol.HLS.value

            row = CameraRow(
                url=url,
                source_family=self.name,
                provenance=Provenance.PUBLIC.value,
                name=page_title(page_html) or clean_str(code) or "Camsecure webcam",
                country=country_for(code),
                protocol=proto,
                status=Health.UNKNOWN.value,   # enumeration never claims liveness
                snapshot_date=today_iso(),
                attribution=ATTRIBUTION,
                was_redacted=was_red,
                credential_present=cred,
                tags=["webcam"],
                meta=meta,
            )
            result.add(row)

        result.stats.update({
            **cache.stats(),
            "hls_rows": hls_rows,
            "youtube_rows": youtube_rows,
            "yt_oembed_ok": yt_oembed_ok,
            "dupes_dropped": dupes,
            "skipped_no_wrapper": skipped_wrapper,
            "skipped_no_media": skipped_media,
            "fetch_failed": len(failed),
        })
        if failed:
            result.stats["fetch_failed_examples"] = [
                {"url": u, "error": e} for u, e in failed[:5]]
        return result.finalize()


ENUMERATOR = CamsecureWebcamsEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

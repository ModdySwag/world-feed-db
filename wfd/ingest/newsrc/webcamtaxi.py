"""wfd.ingest.newsrc.webcamtaxi — WebcamTaxi directory enumerator (build unit NS).

WebcamTaxi (webcamtaxi.com) is a third-party directory of public webcams;
detail pages embed YouTube live players and credit the original operator in a
``<div>Source: <url></div>`` element. Enumeration NEVER claims liveness — rows
enter ``status="unknown"`` (published player state stays untouched).

Enumeration path (re-verified live 2026-10-06; drift vs dossier noted):
1. ``GET https://www.webcamtaxi.com/en/webcams.html`` (browser UA) — one page,
   ~2.67 MB served (dossier said ~350 KB — drift), holding every camera link.
   Raw ``/en/...*.html`` links ~2,900 unique at all depths; 2,219 unique
   camera paths survive the strict shape filter (dossier estimated ~2,230;
   the strict filter catches four digit-leading slugs the dossier regex misses
   and drops six ``/en/component/tags/...`` tag-index links the dossier regex
   falsely matched; robots.txt disallows query-string URLs and ``/component/``
   — camera pages are plain paths and allowed, verified live).
2. Per camera page (browser UA): (a) the player iframe —
   ``youtube(-nocookie).com/embed/<VIDEOID>?...`` (majority, verified) or
   ``youtube(-nocookie).com/embed/live_stream?channel=<CHANNELID>&...``;
   (b) operator source from ``<div>Source: <url></div>`` (absent on many
   pages -> ``""``); (c) tags from ``<ul class="tags inline">``; (d) title
   from ``<title>``.
3. Row mapping: channel embed -> ``https://www.youtube.com/channel/<ID>/live``
   (stable channel-live URL; meta ``channel_id``), video id ->
   ``https://www.youtube.com/watch?v=<ID>`` (meta ``video_id``). Pages with no
   YouTube embed are skipped and counted (``no_embed_skipped``). Country comes
   from the page path's country slug via a clean static map to ISO-3166-1
   alpha-2 (repo convention — other families store codes like ``CH``/``US``);
   the intentionally-ambiguous slug ``saint-martin`` (island split between
   MF/SX; sampled page proved Dutch-side content under the French-side slug)
   stays unmapped -> country ``""`` (reported in ``unmapped_country_slugs``).
   meta keys: ``wt_path``, ``wt_country_slug``, ``embed_url``, ``source``,
   ``tags``, ``page_url``, ``channel_id``, ``video_id`` — all stored URLs are
   routed through :func:`wfd.schema.redact_and_flag` first. Rows are deduped
   by url within the family (keep first; ``dupes_dropped``) — note two camera
   pages sharing one channel embed collapse to one row by design.

Resumability (the point): pages are cached under
``data/ingest/cache/webcamtaxi/`` via
:class:`~wfd.ingest.newsrc.base.FetchCache` (one atomic file per URL); a run
does an ensure-cache pass (skips whatever is already on disk) and then
assembles rows from the FULL cache. A killed run loses nothing — re-issue the
same command and it resumes. ``--limit N`` caps the number of camera pages
processed (tests/smoke runs); ``--refresh`` refetches everything.

Note: ``cache._path`` (FetchCache's private key helper) is used read-only to
count/read cache state without refetching — the base package exposes no public
helper for that (noted per build rules; no base files were modified).

Run::  py -3.11 -m wfd.ingest.newsrc.webcamtaxi
Writes:  data/ingest/newsrc-webcamtaxi.jsonl (gitignored)
"""
from __future__ import annotations

import html as _html
import re
from typing import Optional

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "webcamtaxi"
SITE = "https://www.webcamtaxi.com"
LISTING_URL = "https://www.webcamtaxi.com/en/webcams.html"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BROWSER_HEADERS = {"User-Agent": BROWSER_UA}
ATTRIBUTION = "WebcamTaxi (webcamtaxi.com) — third-party directory of public webcams"

# robots.txt disallowed path prefixes (site root-relative); camera pages are
# plain /en/<country>/<region>/<cam>.html paths and are NOT disallowed.
_ROBOTS_DISALLOWED_DIRS = frozenset({
    "administrator", "bin", "cache", "cli", "component", "components",
    "includes", "installation", "language", "layouts", "libraries", "logs",
    "modules", "plugins", "tmp",
})

# One relative-or-embedded /en/*.html candidate; the strict filter below keeps
# exactly the 3-level camera-page shape (/en/<country>/<region>/<file>.html).
_LINK_RE = re.compile(r"/en/[^\"'<>\s\\]+?\.html")
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
_FILE_RE = re.compile(r"[a-z0-9][a-z0-9._-]*\.html")

_IFRAME_RE = re.compile(r"<iframe\b[^>]*>", re.I)
_IFRAME_SRC_RE = re.compile(
    r"\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>'\"]+))", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_SOURCE_RE = re.compile(r"<div[^>]*>\s*Source:\s*(.{0,400}?)</div>", re.I | re.S)
_TAGS_UL_RE = re.compile(
    r'<ul[^>]*class\s*=\s*"?tags\s+inline[^>]*>(.*?)</ul>', re.I | re.S)
_TAG_A_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

_YT_CHANNEL_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/embed/live_stream\?[^\"'\s<>]*?\bchannel=([A-Za-z0-9_-]+)",
    re.I)
_YT_EMBED_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/embed/(?!live_stream\b)([A-Za-z0-9_-]{6,})",
    re.I)
_YT_WATCH_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/watch\?[^\"'\s<>]*?\bv=([A-Za-z0-9_-]{6,})",
    re.I)
_YT_SHORT_RE = re.compile(r"youtu\.be/([A-Za-z0-9_-]{6,})", re.I)
_YT_SHORTS_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/shorts/([A-Za-z0-9_-]{6,})", re.I)

# Clean country-slug -> ISO-3166-1 alpha-2 map (repo convention stores codes).
# Deliberately absent: "saint-martin" (the slug covers both the French and the
# Dutch side; a sampled page under it showed Sint Maarten content — no guessing).
COUNTRY_BY_SLUG = {
    "andorra": "AD", "anguilla-island": "AI", "argentina": "AR", "aruba": "AW",
    "australia": "AU", "austria": "AT", "bahamas": "BS",
    "bailiwick-of-jersey": "JE", "belarus": "BY", "belgium": "BE",
    "bermuda": "BM", "bosnia-herzegovina": "BA", "brazil": "BR",
    "bulgaria": "BG", "canada": "CA", "cape-verde": "CV",
    "cayman-islands": "KY", "chile": "CL", "china": "CN", "costa-rica": "CR",
    "croatia": "HR", "curacao": "CW", "cyprus": "CY",
    "czech-republic": "CZ", "denmark": "DK", "dominican-republic": "DO",
    "dr-congo": "CD", "ecuador": "EC", "egypt": "EG", "el-salvador": "SV",
    "england": "GB", "estonia": "EE", "finland": "FI", "france": "FR",
    "french-polynesia": "PF", "germany": "DE", "greece": "GR",
    "guatemala": "GT", "hungary": "HU", "iceland": "IS", "india": "IN",
    "indonesia": "ID", "iraq": "IQ", "ireland": "IE", "israel": "IL",
    "italy": "IT", "jamaica": "JM", "japan": "JP", "kazakhstan": "KZ",
    "kenya": "KE", "laos": "LA", "latvia": "LV", "lithuania": "LT",
    "malta": "MT", "mauritius": "MU", "mexico": "MX", "namibia": "NA",
    "netherlands": "NL", "new-zealand": "NZ", "north-macedonia": "MK",
    "norway": "NO", "panama": "PA", "paraguay": "PY", "peru": "PE",
    "philippines": "PH", "poland": "PL", "portugal": "PT", "romania": "RO",
    "russia": "RU", "saint-barthelemy": "BL", "saudi-arabia": "SA",
    "scotland": "GB", "serbia": "RS", "singapore": "SG", "slovakia": "SK",
    "slovenia": "SI", "south-africa": "ZA", "south-korea": "KR", "spain": "ES",
    "sweden": "SE", "switzerland": "CH", "taiwan": "TW", "tanzania": "TZ",
    "thailand": "TH", "turkey": "TR", "turks-and-caicos-islands": "TC",
    "ukraine": "UA", "uruguay": "UY", "usa": "US", "vatican": "VA",
    "vietnam": "VN", "wales": "GB",
}


# --- pure parsers (fixture-testable) -------------------------------------------

def extract_cam_paths(html: str) -> list:
    """Camera-page paths (``/en/<country>/<region>/<file>.html``) from the listing.

    Strict 3-level shape only; robots-disallowed prefixes (``/component/``, ...)
    are dropped; duplicates collapse, first-occurrence order kept. Absolute
    ``https://www.webcamtaxi.com/en/...`` links are caught by the same scan
    (their ``/en/...`` tail matches) and normalized to the path form.
    """
    paths, seen = [], set()
    for raw in _LINK_RE.findall(html or ""):
        path = raw.split("?", 1)[0].split("#", 1)[0]
        parts = path.split("/")
        if len(parts) != 5 or parts[1] != "en":
            continue
        country, region, fname = parts[2], parts[3], parts[4]
        if country in _ROBOTS_DISALLOWED_DIRS:
            continue
        if not _SLUG_RE.fullmatch(country) or not _SLUG_RE.fullmatch(region):
            continue
        if not _FILE_RE.fullmatch(fname):
            continue
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def page_url(path: str) -> str:
    """Absolute detail-page URL for one ``/en/...`` camera path."""
    return SITE + path


def country_for_slug(slug: str) -> str:
    """ISO-3166-1 alpha-2 for a clean country slug (``""`` when unmapped)."""
    return COUNTRY_BY_SLUG.get(clean_str(slug), "")


def _collapse(text: str) -> str:
    return _html.unescape(re.sub(r"\s+", " ", text)).strip()


def _title(html: str, path: str = "") -> str:
    m = _TITLE_RE.search(html or "")
    if m:
        title = _collapse(m.group(1))
        if title:
            return title
    m = _H1_RE.search(html or "")
    if m:
        title = _collapse(_ANY_TAG_RE.sub(" ", m.group(1)))
        if title:
            return title
    slug = clean_str(path).rsplit("/", 1)[-1]
    return slug[:-5].replace("-", " ") if slug.endswith(".html") else slug


def _iframe_srcs(html: str) -> list:
    out = []
    for tag in _IFRAME_RE.findall(html or ""):
        m = _IFRAME_SRC_RE.search(tag)
        if m:
            out.append(_html.unescape(m.group(1) or m.group(2) or m.group(3) or ""))
    return out


def _is_youtube(src: str) -> bool:
    s = src.lower()
    return "youtube.com/" in s or "youtube-nocookie.com/" in s or "youtu.be/" in s


def _channel_id_from(text: str) -> str:
    m = _YT_CHANNEL_RE.search(text or "")
    return m.group(1) if m else ""


def _video_id_from(text: str) -> str:
    for rx in (_YT_EMBED_RE, _YT_WATCH_RE, _YT_SHORTS_RE, _YT_SHORT_RE):
        m = rx.search(text or "")
        if m:
            return m.group(1)
    return ""


def _extract_embed(html: str) -> tuple:
    """First YouTube player embed on a page -> ``(kind, id, embed_url)``.

    ``kind`` is ``"channel"`` (``live_stream?channel=<id>`` — wins when present),
    ``"video"`` (a video id), or ``""`` (no embed). Iframe srcs are scanned
    first (the single player iframe; verified live), then the whole document as
    a fallback for non-iframe variants.
    """
    first_video = ("", "")
    for src in _iframe_srcs(html):
        if not _is_youtube(src):
            continue
        cid = _channel_id_from(src)
        if cid:
            return ("channel", cid, src)
        vid = _video_id_from(src)
        if vid and not first_video[1]:
            first_video = (vid, src)
    if first_video[1]:
        return ("video", first_video[0], first_video[1])
    m = _YT_CHANNEL_RE.search(html or "")
    if m:
        return ("channel", m.group(1), m.group(0))
    for rx in (_YT_EMBED_RE, _YT_WATCH_RE, _YT_SHORTS_RE, _YT_SHORT_RE):
        m = rx.search(html or "")
        if m:
            return ("video", m.group(1), m.group(0))
    return ("", "", "")


def _source_url(html: str) -> str:
    """Operator URL from ``<div>Source: <url></div>`` (``""`` when absent)."""
    m = _SOURCE_RE.search(html or "")
    if not m:
        return ""
    chunk = m.group(1)
    am = re.search(r"\bhref\s*=\s*[\"']?([^\"'\s>]+)", chunk, re.I)
    um = re.search(r"https?://[^\s<\"']+", chunk)
    raw = am.group(1) if am else (um.group(0) if um else "")
    return _html.unescape(raw).strip()


def _tags(html: str) -> list:
    """Tag names from the ``<ul class="tags inline">`` block (deduped, in order)."""
    m = _TAGS_UL_RE.search(html or "")
    if not m:
        return []
    out, seen = [], set()
    for inner in _TAG_A_RE.findall(m.group(1)):
        name = _collapse(_ANY_TAG_RE.sub(" ", inner))
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def parse_detail(html: str, path: str = "") -> Optional[dict]:
    """Structured view of one camera page (None when there is no YouTube embed).

    Keys: ``title``, ``embed_kind`` ("channel"/"video"), ``channel_id``,
    ``video_id``, ``embed_url``, ``source`` (operator URL or ""), ``tags``.
    """
    kind, ident, embed = _extract_embed(html)
    if not kind:
        return None
    return {
        "title": _title(html, path),
        "embed_kind": kind,
        "channel_id": ident if kind == "channel" else "",
        "video_id": ident if kind == "video" else "",
        "embed_url": embed,
        "source": _source_url(html),
        "tags": _tags(html),
    }


def row_from_page(path: str, html: str) -> Optional[CameraRow]:
    """Map one camera page to a CameraRow (None when it has no YouTube embed).

    URLs are redacted before storage; the row always enters ``status="unknown"``
    (enumeration never claims liveness).
    """
    parsed = parse_detail(html, path)
    if parsed is None:
        return None

    if parsed["channel_id"]:
        url_raw = f"https://www.youtube.com/channel/{parsed['channel_id']}/live"
    else:
        url_raw = f"https://www.youtube.com/watch?v={parsed['video_id']}"

    url, was_red, cred = redact_and_flag(url_raw)
    page_red, page_was, page_cred = redact_and_flag(page_url(path))
    embed_red, embed_was, embed_cred = redact_and_flag(parsed["embed_url"])
    source_red, source_was, source_cred = (
        redact_and_flag(parsed["source"]) if parsed["source"] else ("", False, False))

    country_slug = path.split("/")[2] if len(path.split("/")) >= 3 else ""
    return CameraRow(
        url=url,
        source_family=FAMILY,
        provenance=Provenance.DIRECTORY.value,
        name=parsed["title"],
        country=country_for_slug(country_slug),
        lat=None,
        lon=None,
        protocol=Protocol.YOUTUBE.value,
        status=Health.UNKNOWN.value,      # enumeration never claims liveness
        snapshot_date=today_iso(),
        attribution=ATTRIBUTION,
        was_redacted=any((was_red, page_was, embed_was, source_was)),
        credential_present=any((cred, page_cred, embed_cred, source_cred)),
        tags=list(parsed["tags"]),
        meta={
            "wt_path": path,
            "wt_country_slug": country_slug,
            "embed_url": embed_red,
            "source": source_red,
            "tags": list(parsed["tags"]),
            "page_url": page_red,
            "channel_id": parsed["channel_id"],
            "video_id": parsed["video_id"],
        },
    )


class WebcamTaxiEnumerator(Enumerator):
    """Enumerate webcamtaxi.com: all-cams listing + per-page YouTube embeds (cache-resumable)."""

    name = FAMILY
    source_ref = LISTING_URL
    provenance = Provenance.DIRECTORY.value
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family=self.name,
            provenance=Provenance.DIRECTORY.value,
            snapshot_date=today_iso(),
            source_ref=LISTING_URL,
            notes=("all-cams listing -> strict 3-level camera paths -> per-page YouTube "
                   "embed (channel-live or watch URL); operator Source/tags/title in "
                   "meta; no-embed pages skipped and counted; fetch-cache resumable"),
        )
        cache = fetch_cache(self.name, refresh=self.refresh)

        try:
            listing = cache.text(LISTING_URL, headers=BROWSER_HEADERS)
        except Exception as exc:  # noqa: BLE001 — report, don't half-run
            raise RuntimeError(
                f"webcamtaxi listing fetch failed ({LISTING_URL}): "
                f"{type(exc).__name__}: {exc}") from exc

        all_paths = extract_cam_paths(listing)
        if not all_paths:
            raise RuntimeError("webcamtaxi listing yielded 0 camera paths")
        result.stats["pages_total"] = len(all_paths)

        work = all_paths[: self.limit] if self.limit is not None else all_paths
        if self.limit is not None:
            result.stats["limit"] = int(self.limit)
        result.stats["pages_considered"] = len(work)

        def cached(path: str) -> bool:
            return cache._path(page_url(path), ".html").exists()

        pre_cached = sum(1 for p in work if cached(p))
        result.stats["pages_in_cache_start"] = pre_cached
        result.stats["pages_uncached_start"] = len(work) - pre_cached

        # -- phase 1: ensure-cache pass (re-runs skip whatever is on disk) ------
        hits0, misses0 = cache.hits, cache.misses
        failed = []
        for i, path in enumerate(work, 1):
            try:
                cache.get(page_url(path), headers=BROWSER_HEADERS, suffix=".html")
            except Exception as exc:  # noqa: BLE001 — 404/5xx after retries: skip
                failed.append((path, f"{type(exc).__name__}: {exc}"))
            if i % 100 == 0 or i == len(work):
                print(f"  webcamtaxi: cache pass {i}/{len(work)} "
                      f"(from-cache={cache.hits - hits0}, fetched={cache.misses - misses0}, "
                      f"failed={len(failed)})", flush=True)

        # -- phase 2: assemble rows from the FULL cache --------------------------
        seen_urls = set()
        parsed = 0
        no_embed = 0
        dupes = 0
        channel_rows = 0
        video_rows = 0
        unmapped_slugs = set()
        for path in work:
            cache_file = cache._path(page_url(path), ".html")
            if not cache_file.exists():
                continue                      # fetch failed (counted in pages_failed)
            body = cache_file.read_bytes().decode("utf-8", errors="replace")
            parsed += 1
            row = row_from_page(path, body)
            if row is None:
                no_embed += 1
                continue
            if row.url in seen_urls:
                dupes += 1
                continue
            seen_urls.add(row.url)
            if row.meta["channel_id"]:
                channel_rows += 1
            else:
                video_rows += 1
            if not row.country:
                unmapped_slugs.add(row.meta["wt_country_slug"])
            result.add(row)

        in_cache = sum(1 for p in work if cached(p))
        result.stats.update({
            **cache.stats(),
            "pages_in_cache": in_cache,
            "pages_parsed": parsed,
            "pages_failed": len(failed),
            "no_embed_skipped": no_embed,
            "dupes_dropped": dupes,
            "channel_rows": channel_rows,
            "video_rows": video_rows,
        })
        if failed:
            result.stats["pages_failed_examples"] = [
                {"path": p, "error": e} for p, e in failed[:5]]
        if unmapped_slugs:
            result.stats["unmapped_country_slugs"] = sorted(unmapped_slugs)
        return result.finalize()


ENUMERATOR = WebcamTaxiEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

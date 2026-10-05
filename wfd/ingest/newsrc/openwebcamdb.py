"""wfd.ingest.newsrc.openwebcamdb — OpenWebcamDB directory enumerator (build unit NS).

OpenWebcamDB (openwebcamdb.com) is a third-party directory of public webcams;
almost every detail page embeds a YouTube live stream and carries one
``<script type="application/ld+json">`` ``VideoObject`` block with the feed URL,
geo coordinates, country and view count. Enumeration NEVER claims liveness —
rows enter ``status="unknown"``.

Enumeration path (verified live 2026-10-06):
1. ``GET https://openwebcamdb.com/sitemap.xml`` (browser UA) -> 458,471 bytes,
   1,966 ``<loc>`` entries, 1,882 of them ``/webcams/<slug>`` camera pages.
   robots.txt has no ``Disallow`` rules; ToS: free non-commercial use — we fetch
   politely (>= 1 s/host via :func:`polite_get` defaults, never lowered).
2. Per camera page (browser UA) -> parse the JSON-LD ``VideoObject`` block:
   ``contentUrl`` (may be ``youtube.com/watch?v=<id>`` OR a non-YouTube player,
   e.g. ipcamlive), ``embedUrl``, ``thumbnailUrl``, ``uploadDate``,
   ``contentLocation.geo {latitude, longitude}`` / ``.address.addressCountry``,
   ``name``, ``interactionStatistic.userInteractionCount``. Some pages carry no
   ``address`` block at all (country stays ``""``) and some feeds are not
   YouTube — those pages are skipped and counted in ``skipped_no_feed``.
3. Row mapping: ``url = https://www.youtube.com/watch?v=<id>`` (id normalized
   out of ``watch?v=`` or ``/embed/<id>``), ``protocol="youtube"``,
   ``provenance="aggregator_directory"`` (owner decision 2026-10-06), meta keys
   ``owdb_slug``, ``owdb_page``, ``video_id``, ``upload_date``,
   ``view_count_at_enumeration``, ``thumbnail_url``, ``source`` (operator
   attribution — not derivable from the page, verified 2026-10-06 -> ``""``),
   ``owdb_location_name``.

Resumability: pages are cached under ``data/ingest/cache/openwebcamdb/`` via
:class:`~wfd.ingest.newsrc.base.FetchCache` (one file per URL); a run does an
ensure-cache pass (skips whatever is already on disk) and then assembles rows
from the FULL cache. A killed run loses nothing — re-issue the same command.
``--limit N`` caps the number of pages processed (tests/smoke runs);
``--refresh`` refetches everything.

Note: ``cache._path`` (FetchCache's private key helper) is used read-only to
count cache state without refetching — the base package exposes no public
helper for that (noted per build rules; no base files were modified).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_float, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

SITEMAP_URL = "https://openwebcamdb.com/sitemap.xml"
PAGE_PATTERN = "https://openwebcamdb.com/webcams/<slug>"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BROWSER_HEADERS = {"User-Agent": BROWSER_UA}
ATTRIBUTION = "OpenWebcamDB (openwebcamdb.com) — third-party directory of public webcams"

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_CAMERA_LOC_RE = re.compile(
    r"^https?://openwebcamdb\.com/webcams/([^/?#\s]+)/?$", re.I)
_LD_RE = re.compile(
    r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.S | re.I)
_YT_WATCH_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/watch\?[^#\s]*\bv=([A-Za-z0-9_-]+)", re.I)
_YT_EMBED_RE = re.compile(
    r"youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]+)", re.I)
_YT_SHORT_RE = re.compile(r"youtu\.be/([A-Za-z0-9_-]+)", re.I)


def page_url(slug: str) -> str:
    """Detail-page URL for one camera slug."""
    return f"https://openwebcamdb.com/webcams/{slug}"


def extract_slugs(xml_text: str) -> list:
    """All ``/webcams/<slug>`` slugs from the sitemap XML (unique, order kept)."""
    slugs, seen = [], set()
    for loc in _LOC_RE.findall(xml_text or ""):
        m = _CAMERA_LOC_RE.match(loc.strip())
        if not m:
            continue
        slug = m.group(1)
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def parse_detail_jsonld(html: str) -> Optional[dict]:
    """First parseable JSON-LD object from a detail page (None when absent)."""
    for block in _LD_RE.findall(html or ""):
        try:
            payload = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
    return None


def youtube_video_id(url_or_text: str) -> Optional[str]:
    """YouTube video id from a watch/embed/short URL (None when not YouTube)."""
    s = clean_str(url_or_text)
    if not s:
        return None
    for rx in (_YT_WATCH_RE, _YT_EMBED_RE, _YT_SHORT_RE):
        m = rx.search(s)
        if m:
            return m.group(1)
    return None


def _as_int(v) -> Optional[int]:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _valid_lat(v) -> Optional[float]:
    lat = clean_float(v)
    return lat if (lat is not None and -90.0 <= lat <= 90.0) else None


def _valid_lon(v) -> Optional[float]:
    lon = clean_float(v)
    return lon if (lon is not None and -180.0 <= lon <= 180.0) else None


def _view_count(ld: dict) -> Optional[int]:
    inter = ld.get("interactionStatistic")
    for cand in (inter if isinstance(inter, list) else [inter]):
        if isinstance(cand, dict):
            n = _as_int(cand.get("userInteractionCount"))
            if n is not None:
                return n
    return None


def row_from_ld(ld: dict, slug: str) -> Optional[CameraRow]:
    """Map one JSON-LD VideoObject dict to a CameraRow (None: no YouTube id)."""
    if not isinstance(ld, dict):
        return None
    content = clean_str(ld.get("contentUrl"))
    vid = youtube_video_id(content) or youtube_video_id(clean_str(ld.get("embedUrl")))
    if not vid:
        return None

    url, was_red, cred = redact_and_flag(f"https://www.youtube.com/watch?v={vid}")

    loc = ld.get("contentLocation") if isinstance(ld.get("contentLocation"), dict) else {}
    geo = loc.get("geo") if isinstance(loc.get("geo"), dict) else {}
    addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}

    thumb_raw = clean_str(ld.get("thumbnailUrl"))
    thumb_red, thumb_was, _ = (redact_and_flag(thumb_raw) if thumb_raw else ("", False, False))

    return CameraRow(
        url=url,
        source_family="openwebcamdb",
        provenance=Provenance.DIRECTORY.value,
        name=clean_str(ld.get("name")),
        country=clean_str(addr.get("addressCountry")),
        lat=_valid_lat(geo.get("latitude")),
        lon=_valid_lon(geo.get("longitude")),
        protocol=Protocol.YOUTUBE.value,
        status=Health.UNKNOWN.value,        # enumeration never claims liveness
        snapshot_date=today_iso(),
        attribution=ATTRIBUTION,
        was_redacted=was_red or thumb_was,
        credential_present=cred,
        meta={
            "owdb_slug": slug,
            "owdb_page": page_url(slug),
            "video_id": vid,
            "upload_date": clean_str(ld.get("uploadDate")),
            "view_count_at_enumeration": _view_count(ld),
            "thumbnail_url": thumb_red,
            # operator attribution is not present on the page (verified 2026-10-06)
            "source": "",
            "owdb_location_name": clean_str(loc.get("name")),
        },
    )


def row_from_detail(html: str, slug: str) -> Optional[CameraRow]:
    """Map one raw detail-page HTML to a CameraRow (None when unusable)."""
    ld = parse_detail_jsonld(html)
    if ld is None:
        return None
    return row_from_ld(ld, slug)


class OpenWebcamdbEnumerator(Enumerator):
    """Enumerate openwebcamdb.com via its sitemap + per-page JSON-LD (cache-resumable)."""

    name = "openwebcamdb"
    source_ref = SITEMAP_URL
    provenance = Provenance.DIRECTORY.value
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family=self.name,
            provenance=Provenance.DIRECTORY.value,
            snapshot_date=today_iso(),
            source_ref=SITEMAP_URL,
            notes=("sitemap -> detail pages -> JSON-LD; rows are YouTube watch URLs "
                   "(protocol=youtube); non-YouTube/missing-JSON-LD pages skipped "
                   "and counted; fetch-cache resumable"),
        )
        cache = fetch_cache(self.name, refresh=self.refresh)

        # NB: use .get() (not .text()) — base's FetchCache.text() hardcodes
        # suffix=".html", so a .xml suffix cannot be passed through it.
        try:
            xml_bytes = cache.get(SITEMAP_URL, headers=BROWSER_HEADERS, suffix=".xml")
            xml_text = xml_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — report, don't half-run
            raise RuntimeError(
                f"openwebcamdb sitemap fetch failed ({SITEMAP_URL}): "
                f"{type(exc).__name__}: {exc}") from exc

        all_slugs = extract_slugs(xml_text)
        if not all_slugs:
            raise RuntimeError("openwebcamdb sitemap yielded 0 webcam slugs")
        result.stats["pages_total"] = len(all_slugs)

        work = all_slugs[: self.limit] if self.limit is not None else all_slugs
        if self.limit is not None:
            result.stats["limit"] = int(self.limit)
        result.stats["pages_considered"] = len(work)

        def cached(slug: str) -> bool:
            return cache._path(page_url(slug), ".html").exists()

        pre_cached = sum(1 for s in work if cached(s))
        result.stats["pages_in_cache_start"] = pre_cached
        result.stats["pages_uncached_start"] = len(work) - pre_cached

        # -- phase 1: ensure-cache pass (re-runs skip whatever is on disk) ------
        hits0, misses0 = cache.hits, cache.misses
        failed = []
        for i, slug in enumerate(work, 1):
            try:
                cache.get(page_url(slug), headers=BROWSER_HEADERS, suffix=".html")
            except Exception as exc:  # noqa: BLE001 — 404/5xx after retries: skip
                failed.append((slug, f"{type(exc).__name__}: {exc}"))
            if i % 100 == 0 or i == len(work):
                print(f"  openwebcamdb: cache pass {i}/{len(work)} "
                      f"(from-cache={cache.hits - hits0}, fetched={cache.misses - misses0}, "
                      f"failed={len(failed)})", flush=True)

        # -- phase 2: assemble rows from the FULL cache --------------------------
        seen_urls = set()
        parsed = 0
        skipped_no_feed = 0
        skipped_no_ld = 0
        dupes = 0
        for slug in work:
            path = cache._path(page_url(slug), ".html")
            if not path.exists():
                continue                      # fetch failed (counted in pages_failed)
            html = path.read_bytes().decode("utf-8", errors="replace")
            parsed += 1
            ld = parse_detail_jsonld(html)
            if ld is None:
                skipped_no_ld += 1
                skipped_no_feed += 1
                continue
            row = row_from_ld(ld, slug)
            if row is None:
                skipped_no_feed += 1
                continue
            if row.url in seen_urls:
                dupes += 1
                continue
            seen_urls.add(row.url)
            result.add(row)

        in_cache = sum(1 for s in work if cached(s))
        result.stats.update({
            **cache.stats(),
            "pages_in_cache": in_cache,
            "pages_parsed": parsed,
            "pages_failed": len(failed),
            "skipped_no_feed": skipped_no_feed,
            "skipped_no_ld": skipped_no_ld,
            "dupes_dropped": dupes,
        })
        if failed:
            result.stats["pages_failed_slugs"] = [s for s, _ in failed[:25]]
            result.stats["pages_failed_examples"] = [
                {"slug": s, "error": e} for s, e in failed[:5]]
        return result.finalize()


ENUMERATOR = OpenWebcamdbEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

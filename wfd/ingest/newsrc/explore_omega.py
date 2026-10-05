"""wfd.ingest.newsrc.explore_omega — Explore.org livecams enumerator (build unit NS).

Family ``explore-omega``: Explore.org (Annenberg Foundation) publishes its live
nature cams (YouTube-hosted feeds) through a keyless JSON API:

1. ``GET https://omega.explore.org/api/initial?contenttype=livecams`` — the
   camgroup directory (``data.camgroups[]``; ~101 list entries / ~89 unique ids,
   one list entry per collection, feed lists overlap heavily across groups).
2. ``GET https://omega.explore.org/api/get_cam_group_snapshots.json?id=<id>`` —
   per-group feed records (slug, title, snapshot/thumb urls, is_offline,
   force_offline, snapshot_enabled, stream_id, ...).
3. ONE cam page per group: ``https://explore.org/livecams/<group>/<feed>`` —
   the Next.js page embeds the site-wide feed catalog; harvest
   ``slug -> video_id`` by regexing the escaped records
   ``"slug":"...","camgroup_slug":"...","video_id":"..."`` (verified
   2026-10-06; the flight-payload layers backslashes before quotes, hence the
   ``\\\\*`` tolerance in the pattern; a record's own ``camgroup_slug`` tag can
   point at a different collection than the page, so the unfiltered harvest is
   the one that maximizes video coverage).

Row mapping per feed record: YouTube ``watch?v=<video_id>`` when a video id was
harvested, else the stillframe/snapshot URL (jpeg), else the cam page URL
(iframe). Operator flags (is_offline/force_offline/...) stay in ``meta`` only —
enumeration NEVER claims liveness: every row enters ``status="unknown"``
(enforced by :func:`wfd.ingest.newsrc.base.run_one`).

Everything goes through the resumable per-family :class:`FetchCache`
(``data/ingest/cache/explore-omega/``); re-runs skip cached fetches and
``--refresh`` refetches. ``--limit`` caps the number of camgroups processed.

Run::  py -3.11 -m wfd.ingest.newsrc.explore_omega
Writes:  data/ingest/newsrc-explore-omega.jsonl (gitignored)
"""
from __future__ import annotations

import re
from typing import Optional

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "explore-omega"
INITIAL_URL = "https://omega.explore.org/api/initial?contenttype=livecams"
SNAPSHOT_URL_TMPL = "https://omega.explore.org/api/get_cam_group_snapshots.json?id={id}"
PAGE_URL_TMPL = "https://explore.org/livecams/{group}/{feed}"
YOUTUBE_URL_TMPL = "https://www.youtube.com/watch?v={video_id}"
ATTRIBUTION = "Explore.org (Annenberg Foundation) — explore.org/livecams"

# Matches one embedded feed record with any number of backslash escape layers
# before the quotes (served: \"slug\":..., older/simpler forms tolerated).
_PAGE_RECORD_RE = re.compile(
    r'\\*"slug\\*":\\*"([^"\\]+)\\*",\\*"camgroup_slug\\*":\\*"([^"\\]+)\\*",'
    r'\\*"video_id\\*":\\*"([^"\\]+)\\*"'
)


# --- pure parsers (fixture-testable) -------------------------------------------

def parse_initial(payload) -> list:
    """Normalize the initial API payload -> ``[{id, slug, title, feed_count, feeds}]``.

    Keeps list order; skips malformed entries. ``feeds`` entries are reduced to
    ``{slug, title}``.
    """
    data = (payload or {}).get("data") or {}
    groups = data.get("camgroups") or []
    out = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        slug = clean_str(group.get("slug")) or clean_str(group.get("camgroup_slug"))
        gid = group.get("id")
        if not slug or gid is None:
            continue
        feeds = []
        for feed in group.get("feeds") or []:
            if not isinstance(feed, dict):
                continue
            fslug = clean_str(feed.get("slug"))
            if fslug:
                feeds.append({"slug": fslug, "title": clean_str(feed.get("title"))})
        try:
            feed_count = int(group.get("feed_count"))
        except (TypeError, ValueError):
            feed_count = len(feeds)
        out.append({"id": gid, "slug": slug, "title": clean_str(group.get("title")),
                    "feed_count": feed_count, "feeds": feeds})
    return out


def parse_group_snapshots(payload) -> list:
    """Per-feed records from a ``get_cam_group_snapshots.json`` payload."""
    data = (payload or {}).get("data")
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def parse_page_video_ids(html: str, group_slug: Optional[str] = None) -> dict:
    """Harvest ``{feed_slug: video_id}`` from one cam page's embedded records.

    ``group_slug`` filters on the record's own ``camgroup_slug`` tag when given;
    the unfiltered call keeps every record on the page (pages carry the whole
    site catalog; slug values are globally unique, first occurrence wins).
    Harvested ids are normalized — some records publish a trailing ``/``
    (e.g. ``"video_id":"feR0k8-nkWE/"``), which is not part of the YouTube id.
    """
    if not html:
        return {}
    found: dict = {}
    for feed_slug, rec_group, video_id in _PAGE_RECORD_RE.findall(html):
        if group_slug is not None and rec_group != group_slug:
            continue
        video_id = clean_str(video_id).strip("/")
        if not video_id:
            continue
        if feed_slug not in found:
            found[feed_slug] = video_id
    return found


def _as_bool(value) -> Optional[bool]:
    """Tidy a published flag to True/False/None (never a liveness claim)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def _still_url(feed: dict) -> str:
    """Best available stillframe/snapshot URL for a feed record ("" when none)."""
    for key in ("snapshot", "thumb", "thumb_large", "thumbnail_large_url"):
        url = clean_str(feed.get(key))
        if url:
            return url
    imageset = feed.get("stillframe_imageset")
    if isinstance(imageset, dict):
        for dim in ("width", "height"):
            variants = imageset.get(dim)
            if isinstance(variants, dict):
                for url in variants.values():
                    url = clean_str(url)
                    if url:
                        return url
    return ""


def row_from_feed(feed: dict, group: dict, video_id=None) -> Optional[CameraRow]:
    """Map one feed record (+ its group + harvested video id) to a CameraRow.

    Returns None when the feed has no slug (nothing addressable to store).
    URLs are redacted before storage; published flags go to ``meta`` only and
    the row always enters ``status="unknown"``.
    """
    feed = feed or {}
    group = group or {}
    feed_slug = clean_str(feed.get("slug"))
    if not feed_slug:
        return None

    group_slug = clean_str(group.get("slug"))
    group_id = group.get("id")
    feed_title = clean_str(feed.get("title")) or feed_slug
    vid = clean_str(video_id)

    page_raw = PAGE_URL_TMPL.format(group=group_slug, feed=feed_slug)
    still_raw = _still_url(feed)

    if vid:
        url_raw = YOUTUBE_URL_TMPL.format(video_id=vid)
        protocol = Protocol.YOUTUBE.value
    elif still_raw:
        url_raw = still_raw
        protocol = Protocol.JPEG.value
    else:
        url_raw = page_raw
        protocol = Protocol.IFRAME.value

    url, was_redacted, credential_present = redact_and_flag(url_raw)
    page_url = redact_and_flag(page_raw)[0]

    return CameraRow(
        url=url,
        source_family=FAMILY,
        provenance=Provenance.PUBLIC.value,
        name=feed_title,
        country="",
        lat=None,
        lon=None,
        protocol=protocol,
        status=Health.UNKNOWN.value,      # published flags are NOT our verdict
        attribution=ATTRIBUTION,
        was_redacted=was_redacted,
        credential_present=credential_present,
        tags=["nature"],
        meta={
            "camgroup_id": group_id,
            "camgroup_slug": group_slug,
            "feed_slug": feed_slug,
            "feed_title": feed_title,
            "video_id": vid,
            "is_offline": _as_bool(feed.get("is_offline")),
            "force_offline": _as_bool(feed.get("force_offline")),
            "snapshot_enabled": _as_bool(feed.get("snapshot_enabled")),
            "page_url": page_url,
            "stream_id": clean_str(feed.get("stream_id")),
        },
    )


class ExploreOmegaEnumerator(Enumerator):
    """Enumerate explore.org livecams: initial dir + per-group snapshots + one page/group."""

    name = FAMILY
    source_ref = INITIAL_URL
    provenance = Provenance.PUBLIC.value
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=self.provenance,
            snapshot_date=today_iso(),
            source_ref=self.source_ref,
            notes=("omega initial + per-camgroup snapshots + one cam page per group "
                   "(slug->video_id harvest); operator flags stay in meta, rows stay 'unknown'"),
        )

        initial = cache.json(INITIAL_URL)
        groups = parse_initial(initial)
        groups_available = len(groups)
        if self.limit is not None:
            groups = groups[: max(0, int(self.limit))]

        video_map: dict = {}
        feed_batches = []            # (group, [feed record, ...]) — processing order kept
        snapshot_failed = []
        page_failed = []
        pages_fetched = 0
        pages_without_video_ids = 0
        feeds_missing_in_snapshots = 0

        for group in groups:
            gid = group["id"]
            gslug = group["slug"]

            records = []
            try:
                payload = cache.json(SNAPSHOT_URL_TMPL.format(id=gid))
                records = parse_group_snapshots(payload)
            except Exception as exc:  # noqa: BLE001 — skip this group, keep the run alive
                snapshot_failed.append({"camgroup_id": gid, "camgroup_slug": gslug,
                                        "error": f"{type(exc).__name__}: {exc}"})

            initial_feeds = group.get("feeds") or []
            if records:
                have = {clean_str(r.get("slug")) for r in records}
                for feed in initial_feeds:
                    if feed["slug"] not in have:
                        records.append({"slug": feed["slug"], "title": feed.get("title", "")})
                        feeds_missing_in_snapshots += 1
            else:
                records = [{"slug": f["slug"], "title": f.get("title", "")}
                           for f in initial_feeds]

            page_feed = clean_str(records[0].get("slug")) if records else ""
            if page_feed:
                page_url = PAGE_URL_TMPL.format(group=gslug, feed=page_feed)
                try:
                    page_html = cache.text(page_url)
                    pages_fetched += 1
                    vid_map = parse_page_video_ids(page_html)
                    if not vid_map:
                        pages_without_video_ids += 1
                    for slug, vid in vid_map.items():
                        video_map.setdefault(slug, vid)
                except Exception as exc:  # noqa: BLE001 — fallback rows still land
                    page_failed.append({"camgroup_id": gid, "camgroup_slug": gslug,
                                        "page_url": page_url,
                                        "error": f"{type(exc).__name__}: {exc}"})

            feed_batches.append((group, records))

        seen_urls = set()
        dupes_dropped = 0
        for group, records in feed_batches:
            for feed in records:
                row = row_from_feed(feed, group,
                                    video_map.get(clean_str(feed.get("slug"))))
                if row is None:
                    continue
                if row.url in seen_urls:
                    dupes_dropped += 1
                    continue
                seen_urls.add(row.url)
                result.add(row)

        unique_slugs = {clean_str(r.get("slug"))
                        for _, records in feed_batches for r in records
                        if clean_str(r.get("slug"))}
        with_video = sum(1 for slug in unique_slugs if slug in video_map)

        result.stats.update({
            "camgroups": len(groups),
            "camgroups_available": groups_available,
            "feeds": len(unique_slugs),
            "feed_records": sum(len(records) for _, records in feed_batches),
            "feeds_with_video": with_video,
            "feeds_without_video": len(unique_slugs) - with_video,
            "dupes_dropped": dupes_dropped,
            "video_ids_found": len(video_map),
            "pages_fetched": pages_fetched,
            "pages_without_video_ids": pages_without_video_ids,
            "feeds_missing_in_snapshots": feeds_missing_in_snapshots,
            "groups_snapshot_failed_count": len(snapshot_failed),
            "groups_page_failed_count": len(page_failed),
        })
        if snapshot_failed:
            result.stats["groups_snapshot_failed"] = snapshot_failed
        if page_failed:
            result.stats["groups_page_failed"] = page_failed
        result.stats.update(cache.stats())
        return result


ENUMERATOR = ExploreOmegaEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

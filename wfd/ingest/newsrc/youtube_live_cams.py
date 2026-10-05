"""wfd.ingest.newsrc.youtube_live_cams — YouTube-embed live cam publishers.

A small SOURCE REGISTRY of publishers whose live cams are YouTube live embeds,
so future embedders slot in as ``SOURCES`` entries. Current registry
(dossier-verified 2026-10-06, all oEmbed checks re-run 200 + title at build):

- Steamboat Resort (Steamboat Springs, Colorado) — 9 resort cams on channel
  ``@SteamboatResort`` (feed ids recovered from the public
  steamboatpilot.com/webcams gallery that embeds the resort's YouTube feeds;
  the resort site itself sits behind an Imperva WAF). Excluded:
  ``iJlOcnEbWMY`` ("FITH – Steamboat 2019…", author Jeff Carlson — not a
  resort cam).
- South Padre Island (Texas, CVB visitsouthpadreisland.com/live-webcams/) —
  4 cams: 3 run by the CVB channel ``@enjoyspi``, 1 (Isla Blanca surf cam)
  operated by South Padre Surf Company on ``@spadrevideo`` and embedded by
  the CVB.

Enumeration: for every registry entry, one public oEmbed existence check
``GET https://www.youtube.com/oembed?url=<watch url>&format=json``. A 200
proves the video EXISTS (author/title recorded); it is NOT a liveness claim —
rows always enter ``status="unknown"`` and the check lands in
``meta["oembed_ok"]``. A failed oEmbed never drops a row; it is flagged
(``meta["oembed_ok"] = False`` + ``oembed_error`` + ``stats["oembed_failed"]``).

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.youtube_live_cams
"""
from __future__ import annotations

import json as _json
import time
import urllib.error
import urllib.parse

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
SOURCE_REF = ("https://www.youtube.com/@SteamboatResort | "
              "https://visitsouthpadreisland.com/live-webcams/")
ATTRIBUTION = "Steamboat Resort + South Padre Island CVB — YouTube live cams"

# --- the source registry ------------------------------------------------------

SOURCES = [
    {
        "property": "Steamboat Resort",
        "channel": "@SteamboatResort",
        "attribution": "Steamboat Resort (youtube.com/@SteamboatResort)",
        "city": "Steamboat Springs",
        "country": "US",
        "entries": [
            {"video_id": "2UJDLWcSADk", "name": "Steamboat Square"},
            {"video_id": "evs4diWVKiY", "name": "Four Points Lodge"},
            {"video_id": "fI30YzAmCHw", "name": "Christie Peak Express & Wild Blue Gondola"},
            {"video_id": "KJka6pGArbc", "name": "Thunderhead"},
            {"video_id": "lKc9xwndUK4", "name": "Mid-Mountain Snow Stake"},
            {"video_id": "PD9MoCKRwCA", "name": "Champagne Powder Snow Cam"},
            {"video_id": "PinqovlSY-o", "name": "Rendezvous"},
            {"video_id": "qjAqCiwCW34", "name": "Thunderhead Lodge"},
            {"video_id": "VQ37fu8sd9M", "name": "Christie Base"},
        ],
    },
    {
        "property": "South Padre Island",
        "channel": "@enjoyspi / @spadrevideo",
        "attribution": "South Padre Island (youtube.com/@enjoyspi)",
        "city": "South Padre Island",
        "country": "US",
        "entries": [
            {"video_id": "kJ_EXhKsH30", "name": "North Beach / Sand Rose Beach Resort"},
            {"video_id": "dzylsC0KcOE", "name": "Courtyard by Marriott Beach"},
            {"video_id": "bvL_3W7F4Fk", "name": "Queen Isabella Causeway"},
            {"video_id": "0FaRaPPTS8M", "name": "Surf Cam, Isla Blanca Beach Park"},
        ],
    },
]


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={clean_str(video_id)}"


def oembed_url(video_id: str) -> str:
    """oEmbed existence-check URL for a watch URL (url-param encoded)."""
    return f"{OEMBED_ENDPOINT}?url={urllib.parse.quote(watch_url(video_id), safe='')}&format=json"


# --- fetch helper (429 retry) -------------------------------------------------

_429_DELAY_S = 5.0
_sleep = time.sleep                      # module-level seam for tests


def _fetch(cache, url: str, *, headers=None, suffix: str = ".json", attempts: int = 3) -> bytes:
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


def build_row(source: dict, entry: dict, oembed=(False, "", "", None)) -> CameraRow:
    """One registry entry -> CameraRow.

    ``oembed`` is ``(ok, author, title, error_or_None)`` from the existence
    check — never a liveness claim; ``status`` stays ``unknown``.
    """
    ok, author, title, err = oembed
    meta = {
        "property": clean_str(source.get("property")),
        "cam_name": clean_str(entry.get("name")),
        "channel": clean_str(source.get("channel")),
        "oembed_ok": bool(ok),
        "oembed_author": clean_str(author),
        "oembed_title": clean_str(title),
    }
    if err:
        meta["oembed_error"] = err
    url, was_red, cred = redact_and_flag(watch_url(entry.get("video_id")))
    return CameraRow(
        url=url,
        source_family="youtube-live-cams",
        provenance=Provenance.PUBLIC.value,
        name=clean_str(entry.get("name")),
        city=clean_str(source.get("city")),
        country=clean_str(source.get("country")) or "US",
        protocol=Protocol.YOUTUBE.value,
        status=Health.UNKNOWN.value,       # enumeration never claims liveness
        snapshot_date=today_iso(),
        attribution=clean_str(source.get("attribution")),
        was_redacted=was_red,
        credential_present=cred,
        tags=["webcam", "youtube-live"],
        meta=meta,
    )


class YoutubeLiveCamsEnumerator(Enumerator):
    """Enumerate the YouTube-embed cam registry (oEmbed existence check per id)."""

    name = "youtube-live-cams"
    source_ref = SOURCE_REF
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=SOURCE_REF,
            notes=("source registry of YouTube-embed cam publishers; oembed 200 = "
                   "existence only (never liveness); failed oembed keeps the row "
                   "with meta oembed_ok=false"),
        )

        pairs = [(src, ent) for src in SOURCES for ent in (src.get("entries") or [])]
        total = len(pairs)
        if self.limit is not None:
            pairs = pairs[: int(self.limit)]
            result.stats["limit"] = int(self.limit)

        seen: set = set()
        dupes = oembed_ok_count = 0
        failed: list = []
        for src, ent in pairs:
            url = watch_url(ent.get("video_id"))
            if url in seen:
                dupes += 1
                continue
            seen.add(url)

            oembed = (False, "", "", None)
            try:
                payload = _json.loads(
                    _fetch(cache, oembed_url(ent.get("video_id"))).decode("utf-8-sig", "replace"))
                if not isinstance(payload, dict):
                    raise ValueError(f"unexpected oembed payload type {type(payload).__name__}")
                oembed = (True, clean_str(payload.get("author_name")),
                          clean_str(payload.get("title")), None)
            except Exception as exc:  # noqa: BLE001 — flag, never drop the row
                oembed = (False, "", "", f"{type(exc).__name__}: {exc}")
                failed.append(clean_str(ent.get("video_id")))
            if oembed[0]:
                oembed_ok_count += 1

            result.add(build_row(src, ent, oembed=oembed))

        result.stats.update({
            **cache.stats(),
            "entries": total,
            "entries_considered": len(pairs),
            "oembed_ok_count": oembed_ok_count,
            "dupes_dropped": dupes,
        })
        if failed:
            result.stats["oembed_failed"] = failed
        return result.finalize()


ENUMERATOR = YoutubeLiveCamsEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

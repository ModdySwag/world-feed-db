"""wfd.ingest.newsrc.au_goldcoast_beach — City of Gold Coast beach cameras.

Endpoints (verified live 2026-10-06):

- List: ``GET https://mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches``
  -> top-level JSON array of ``{title, shareId, cams: [m3u8 URL, ...], ...}``.
  Live snapshot at build time: 27 items, 32 item x cam entries, 21 unique
  stream URLs, ~164 KB. The API is the council's own mobile-app backend (no
  key, no auth) and is the enumeration ground truth.

Row mapping: one row per (item x cam URL). ``url`` is the m3u8 URL exactly as
returned by the API (``protocol="hls"``), ``name`` is the item title — suffixed
``" cam N"`` when the item lists several cams (N = 1-based ``cam_index``, which
is the camera ordinal within the item). ``country="AU"``, ``city="Gold Coast"``.
``meta`` carries ``shareId``, ``cam_index``, ``api_url``, ``title``, plus
``shared_by`` and ``drift_note`` (below).

Dedupe: rows are deduped by URL — cams shared across beaches collapse to the
FIRST listing encountered; later listings are dropped and counted in
``stats["dupes_dropped"]``. Every kept row's ``meta["shared_by"]`` lists all
item titles referencing that stream, in enumeration order — the first entry is
the item whose row was kept (so "which one kept first" is recoverable).

Drift doctrine: ``<name>.stream`` CloudFront slugs drift (streams get renamed
or rotated), so the stored URL must be re-resolved from this discover API on
every sweep (``meta["drift_note"]``). Research on 2026-10-06 found only 1 of
the 21 live streams responding (``tweedriverstatic``); the other ~20 returned
404 at CloudFront. That is expected to recur — enumeration records URLs as
published and NEVER claims liveness (all rows enter ``status="unknown"``;
health sweeps decide later). This module does NOT probe streams.

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.au_goldcoast_beach

No network at import; network only via ``fetch_cache`` / ``polite_get``.
"""
from __future__ import annotations

import json
from time import sleep as _sleep

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

API_URL = "https://mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches"
ATTRIBUTION = "City of Gold Coast — goldcoast.qld.gov.au beach cameras"
DRIFT_NOTE = ("stream slugs drift — re-resolve each '<name>.stream' HLS URL from "
              "this discover API on every sweep")


def parse_discover(payload) -> list:
    """Cam-entry list from a discover payload (error/unexpected shapes handled).

    The live API returns a top-level array; list-in-dict forms are accepted
    defensively (drift insurance). Non-list/dict payload types raise so a
    broken fetch can never masquerade as an empty beach list silently.
    """
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = (payload.get("data") or payload.get("items")
                   or payload.get("results") or [])
    else:
        raise ValueError(f"discover payload: unexpected type {type(payload).__name__}")
    return [e for e in entries if isinstance(e, dict)]


def cam_urls(entry: dict) -> list:
    """The m3u8 URLs an item publishes (empty list when absent/odd-shaped)."""
    raw = (entry or {}).get("cams") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [clean_str(c) for c in raw if clean_str(c)]


def _retry_wait(exc, backoff: float, attempt: int) -> float:
    """Backoff seconds for one retry; honors a Retry-After header when present."""
    wait = backoff * (attempt + 1)
    headers = getattr(exc, "headers", None)
    ra = headers.get("Retry-After") if headers is not None and hasattr(headers, "get") else None
    try:
        wait = max(wait, min(float(ra), 30.0))
    except (TypeError, ValueError):
        pass
    return wait


def _retry_get(cache, url: str, *, suffix: str = ".json", attempts: int = 3,
               backoff: float = 3.0) -> bytes:
    """``cache.get`` with retries for 429/transients.

    ``polite_get`` already retries 5xx internally but raises 4xx (including
    429) immediately — this module-local wrapper adds 429 + Retry-After
    handling and a final bounded retry for transient transport errors. Other
    4xx (404 etc.) still raise on the spot. Base package untouched.
    """
    last = None
    for attempt in range(attempts):
        try:
            return cache.get(url, suffix=suffix)
        except Exception as exc:  # noqa: BLE001 — classify, don't swallow
            code = getattr(exc, "code", None)
            if code is not None and code != 429 and code < 500:
                raise                                  # hard 4xx: propagate
            last = exc
            if attempt < attempts - 1:
                _sleep(_retry_wait(exc, backoff, attempt))
    raise last


class GoldCoastBeachEnumerator(Enumerator):
    """Enumerate the Gold Coast beach-cam discover API (one JSON GET)."""

    name = "au-goldcoast-beach"
    source_ref = API_URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=API_URL,
            notes=("discover API array -> one row per (item x cam URL), deduped by URL "
                   "(first listing kept; meta['shared_by'] says who shares it); rows "
                   "status=unknown (enumeration never claims liveness); ~20/21 streams "
                   "404 at CloudFront as of 2026-10-06 — expected; drift rule: "
                   "re-resolve slugs from this API per sweep"),
        )

        raw = _retry_get(cache, API_URL, suffix=".json")
        payload = json.loads(raw.decode("utf-8-sig", errors="replace"))
        entries = parse_discover(payload)
        result.stats["items_total"] = len(entries)
        if self.limit is not None:
            entries = entries[: int(self.limit)]
            result.stats["limit"] = int(self.limit)
        if not entries:
            result.notes += "; WARNING: discover API returned no entries"

        # pass 1 — share map keyed by the REDACTED url (the dedupe key)
        shared_by: dict = {}
        items_without = 0
        for entry in entries:
            urls = cam_urls(entry)
            if not urls:
                items_without += 1
                continue
            label = self._label(entry)
            for cam in urls:
                url, _, _ = redact_and_flag(cam)
                shared_by.setdefault(url, []).append(label)

        # pass 2 — rows; first listing of a URL kept, later listings dropped
        seen: set = set()
        dupes = 0
        for entry in entries:
            title = clean_str(entry.get("title"))
            share_id = clean_str(entry.get("shareId"))
            label = self._label(entry)
            urls = cam_urls(entry)
            multi = len(urls) > 1
            for idx, cam in enumerate(urls, 1):
                url, was_red, cred = redact_and_flag(cam)
                if url in seen:
                    dupes += 1
                    continue
                seen.add(url)
                result.add(CameraRow(
                    url=url,
                    source_family=self.name,
                    provenance=Provenance.PUBLIC.value,
                    name=f"{label} cam {idx}" if multi else label,
                    country="AU",
                    city="Gold Coast",
                    protocol=Protocol.HLS.value,
                    status=Health.UNKNOWN.value,   # enumeration never claims liveness
                    snapshot_date=today_iso(),
                    attribution=ATTRIBUTION,
                    was_redacted=was_red,
                    credential_present=cred,
                    tags=["webcam", "beach"],
                    meta={
                        "shareId": share_id,
                        "cam_index": idx,           # 1-based ordinal within the item
                        "api_url": API_URL,
                        "title": title,
                        "shared_by": list(shared_by.get(url, [])),
                        "drift_note": DRIFT_NOTE,
                    },
                ))

        result.stats.update({
            "items": len(entries),
            "items_without_stream": items_without,
            "unique_streams": len(shared_by),
            "dupes_dropped": dupes,
            **cache.stats(),
        })
        result.stats["rows"] = len(result.rows)
        return result.finalize()

    @staticmethod
    def _label(entry: dict) -> str:
        """Row name base for an item (title; shareId tail / placeholder fallback)."""
        title = clean_str(entry.get("title"))
        if title:
            return title
        tail = clean_str(entry.get("shareId")).rsplit("/", 1)[-1]
        return tail or "unnamed beach"


ENUMERATOR = GoldCoastBeachEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

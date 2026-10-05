"""wfd.ingest.newsrc.vailresorts_brownrice — Vail Resorts cam snapshots via Brownrice.

Family ``vailresorts-brownrice``: the Brownrice still-snapshot endpoint
(``https://player.brownrice.com/snapshot/<station>``) behind the public
mountain-cams pages of Vail Resorts properties. This module covers the 13
stations browser-harvested on 2026-10-05 from

- whistlerblackcomb.com (8 stations, titles paired by DOM order), and
- vail.com (5 stations, no titles — the station id is kept as the name).

Why a constant: both operator sites are Akamai/Incapsula bot-walled to plain
curl (discovery needed a rendering browser — see
``research/new-sources/NS3-resorts.md`` § Whistler Blackcomb), so the station
map is embedded rather than scraped.

Build-time verification (inside :meth:`VailResortsBrownriceEnumerator.enumerate`):
every snapshot URL is fetched once, politely (per-host spacing via
``polite_get``; ~1 s, snapshots refresh on the order of minutes), and the body
is checked for the JPEG magic prefix. Per-station records land in
``stats["verified"]`` as ``{station, http, content_type, bytes, ok}``. A
station failing verification STAYS a row (honest enumeration) but is flagged
in ``stats["stations_failed"]`` + notes.

Mechanism note: ``polite_get`` returns body bytes only (no headers), so
``content_type`` is sniffed from the JPEG magic bytes and a successful fetch
is recorded as ``http=200`` — the shared helper raises on 4xx/5xx (after
bounded retries), and the dossier's live checks showed this endpoint returns
``200 image/jpeg``. No FetchCache is used: snapshot bytes are verification-only
and never stored, so a byte cache would only make re-run verification stale.

Enumeration NEVER claims liveness — rows enter as ``status="unknown"``
(``run_one`` enforces it via ``check_no_liveness``).
"""
from __future__ import annotations

import urllib.error

from .base import Enumerator, run_cli
from ..base import IngestResult, polite_get, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "vailresorts-brownrice"
VENDOR = "brownrice"
SOURCE_REF = ("https://player.brownrice.com/snapshot/<station> "
              "(station map browser-harvested 2026-10-05)")
ATTRIBUTION = "Vail Resorts (Whistler Blackcomb / Vail) — player.brownrice.com snapshots"
DISCOVERY = "browser-harvested 2026-10-05 (curl-bot-walled)"

SNAPSHOT_URL = "https://player.brownrice.com/snapshot/{station}"
EMBED_URL = "https://player.brownrice.com/embed/{station}"
JPEG_MAGIC = b"\xff\xd8\xff"

# Whistler Blackcomb stations — titles verified in-browser (DOM order pairing).
WHISTLER_STATIONS = {
    "whistlerroundhouse": "Roundhouse Lodge, Whistler Mountain",
    "whistlerpeak": "Whistler Peak",
    "whistlerblackcomb": "Rendezvous Lodge, Blackcomb Mountain",
    "Whistleraline": "BIKE PARK CAM, Whistler Mountain",
    "whistlervillagefitz": "Whistler Village Cam",
    "whistlervillage": "Blackcomb Base, Upper Village",
    "whistlercreekside": "Creekside Camera",
    "whistler7thheaven": "7TH HEAVEN, Blackcomb Mountain",
}

# Vail stations — no titles in the dossier; station id used as the name
# (noted in row meta + result notes).
VAIL_STATIONS = ("vailch11", "vailch21", "vailch2", "vaileaglesnest", "vailsnowsummit")


def _station_entries() -> list:
    """Flat station-map entries: whistler (titled) + vail (id-as-name)."""
    entries = [
        {
            "station": station,
            "name": name,
            "property": "whistler-blackcomb",
            "country": "CA",
            "city": "Whistler",
            "title_source": "dossier (browser-harvested 2026-10-05)",
        }
        for station, name in WHISTLER_STATIONS.items()
    ]
    entries += [
        {
            "station": station,
            "name": station,
            "property": "vail",
            "country": "US",
            "city": "Vail",
            "title_source": "station id (no dossier title)",
        }
        for station in VAIL_STATIONS
    ]
    return entries


STATION_MAP = tuple(_station_entries())


def row_from_station(entry: dict) -> CameraRow:
    """Map one station-map entry -> CameraRow (URLs redacted before storage)."""
    station = entry["station"]
    url, was_redacted, credential = redact_and_flag(SNAPSHOT_URL.format(station=station))
    embed, embed_redacted, embed_credential = redact_and_flag(EMBED_URL.format(station=station))
    return CameraRow(
        url=url,
        source_family=FAMILY,
        provenance=Provenance.PUBLIC.value,
        name=entry["name"],
        country=entry["country"],
        city=entry["city"],
        lat=None,
        lon=None,
        protocol=Protocol.JPEG.value,
        status=Health.UNKNOWN.value,          # enumeration never claims liveness
        attribution=ATTRIBUTION,
        was_redacted=was_redacted or embed_redacted,
        credential_present=credential or embed_credential,
        tags=["webcam", "resort", "ski"],
        meta={
            "station": station,
            "property": entry["property"],
            "vendor": VENDOR,
            "embed_url": embed,
            "discovery": DISCOVERY,
            "title_source": entry["title_source"],
        },
    )


def verify_snapshot(station: str) -> dict:
    """Politely fetch one snapshot and check it is a JPEG.

    Returns a record ``{station, http, content_type, bytes, ok}`` (+ ``error``
    on failure). Success is recorded as ``http=200``: ``polite_get`` raises on
    4xx/5xx (after bounded retries) and returns only on 2xx. ``content_type``
    is sniffed from the JPEG magic prefix (see module docstring).
    """
    record = {"station": station, "http": None, "content_type": "", "bytes": 0, "ok": False}
    try:
        body = polite_get(SNAPSHOT_URL.format(station=station))
    except urllib.error.HTTPError as exc:      # 4xx raised immediately; 5xx after retries
        record["http"] = exc.code
        record["error"] = f"HTTP {exc.code} {exc.reason}"
        return record
    except Exception as exc:  # noqa: BLE001 — failed station is flagged, enumeration continues
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    record["http"] = 200
    record["bytes"] = len(body)
    record["ok"] = body[:3] == JPEG_MAGIC
    record["content_type"] = "image/jpeg" if record["ok"] else ""
    return record


class VailResortsBrownriceEnumerator(Enumerator):
    """Enumerate the 13 harvested Brownrice snapshot stations (8 Whistler + 5 Vail)."""

    name = FAMILY
    source_ref = SOURCE_REF
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family=FAMILY,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=SOURCE_REF,
        )

        entries = list(STATION_MAP)
        if isinstance(self.limit, int):        # cap the number of STATIONS processed
            entries = entries[: max(0, self.limit)]

        seen_urls = set()
        kept, dupes_dropped = [], 0
        for entry in entries:
            row = row_from_station(entry)
            if row.url in seen_urls:           # dedupe rows by url within the family
                dupes_dropped += 1
                continue
            seen_urls.add(row.url)
            kept.append(entry)
            result.add(row)

        verified = [verify_snapshot(entry["station"]) for entry in kept]
        failed = [rec["station"] for rec in verified if not rec["ok"]]
        n_ok = len(verified) - len(failed)
        n_whistler = sum(1 for e in entries if e["property"] == "whistler-blackcomb")
        n_vail = sum(1 for e in entries if e["property"] == "vail")

        result.stats["stations"] = len(entries)
        result.stats["stations_verified"] = n_ok
        result.stats["stations_failed"] = failed
        result.stats["verified"] = verified
        result.stats["verification_method"] = (
            "one polite snapshot fetch per station; success recorded as http=200 "
            "(polite_get raises on 4xx/5xx); content_type sniffed from JPEG magic bytes"
        )
        result.stats["dupes_dropped"] = dupes_dropped

        note = (
            f"build-time verification: {n_ok}/{len(verified)} snapshots fetched politely "
            f"and verified as JPEG ({n_whistler} Whistler Blackcomb + {n_vail} Vail stations); "
            f"Vail names = station ids (no dossier titles)"
        )
        if failed:
            note += f"; verification failed for: {', '.join(failed)}"
        result.notes = note
        return result.finalize()


ENUMERATOR = VailResortsBrownriceEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

"""wfd.ingest.gov.caltrans — Caltrans CCTV district enumerator (build task C).

Endpoint pattern (S2 §1, verified 2026-10-05): each of the 12 districts serves
``https://cwwp2.dot.ca.gov/data/d<N>/cctv/cctvStatusD<NN>.json`` (directory
``d<N>``, file zero-padded ``D01``…``D12``). D03 is a known persistent HTTP 500
(server-side) — failed districts are skipped after polite retries and recorded
in ``stats["districts_failed"]``.

Row mapping: ``url`` = ``imageData.streamingVideoURL`` (HLS) when present, else
``imageData.static.currentImageURL`` (JPEG still). ``inService`` is an agency
service flag and stays in ``meta`` — rows always enter as ``status="unknown"``.
"""
from __future__ import annotations

from typing import Optional

from .base import Enumerator
from ..base import IngestResult, clean_float, clean_str, polite_json, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

DISTRICTS = tuple(range(1, 13))
SOURCE_PATTERN = "https://cwwp2.dot.ca.gov/data/d<N>/cctv/cctvStatusD<NN>.json"
ATTRIBUTION = "Caltrans CCTV (cwwp2.dot.ca.gov) — California DOT public data"


def district_url(n) -> str:
    """URL for district N (int 1..12) — dir ``d<N>``, file ``cctvStatusD<NN>.json``."""
    n = int(n)
    return f"https://cwwp2.dot.ca.gov/data/d{n}/cctv/cctvStatusD{n:02d}.json"


def _clean_url(raw: str) -> tuple:
    """Redact a URL -> (redacted, was_redacted, credential_present)."""
    raw = clean_str(raw)
    if not raw:
        return "", False, False
    return redact_and_flag(raw)


def row_from_cam(cam: dict, district: str = "") -> Optional[CameraRow]:
    """Map one ``cctv`` object to a CameraRow (None when no imagery URL exists)."""
    loc = cam.get("location") or {}
    img = cam.get("imageData") or {}
    static = img.get("static") or {}

    stream_raw = clean_str(img.get("streamingVideoURL"))
    still_raw = clean_str(static.get("currentImageURL"))
    url_raw = stream_raw or still_raw
    if not url_raw:
        return None

    url, was_red, cred = _clean_url(url_raw)
    stream_red = _clean_url(stream_raw)[0]
    still_red = _clean_url(still_raw)[0]

    index = clean_str(cam.get("index"))
    route = clean_str(loc.get("route"))
    county = clean_str(loc.get("county"))
    name = f"{route} #{index} ({county})" if route else f"Caltrans {district} #{index} ({county})"

    lat = clean_float(loc.get("latitude"))
    lon = clean_float(loc.get("longitude"))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None

    return CameraRow(
        url=url,
        source_family="caltrans",
        provenance=Provenance.PUBLIC.value,
        name=name,
        country="US",
        lat=lat,
        lon=lon,
        protocol=Protocol.HLS.value if stream_raw else Protocol.JPEG.value,
        status=Health.UNKNOWN.value,      # inService is NOT our liveness verdict
        attribution=ATTRIBUTION,
        was_redacted=was_red,
        credential_present=cred,
        tags=["traffic"],
        meta={
            "caltrans_in_service": clean_str(cam.get("inService")),  # agency flag only
            "caltrans_streaming_video_url": stream_red,
            "caltrans_current_image_url": still_red,
            "caltrans_district": district or clean_str(loc.get("district")),
            "caltrans_index": index,
            "caltrans_route": route,
            "caltrans_county": county,
            "caltrans_direction": clean_str(loc.get("direction")),
            "caltrans_location_name": clean_str(loc.get("locationName")),
            "caltrans_nearby_place": clean_str(loc.get("nearbyPlace")),
            "caltrans_postmile": clean_str(loc.get("postmile")),
            "caltrans_record_timestamp": cam.get("recordTimestamp") or {},
        },
    )


def parse_district(payload, district: str = "") -> list:
    """Parse one district JSON ({"data": [{"cctv": {...}}, ...]}) -> rows."""
    if isinstance(payload, list):
        entries = payload
    else:
        entries = (payload or {}).get("data") or []
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cam = entry.get("cctv") if "cctv" in entry else entry
        if not isinstance(cam, dict):
            continue
        row = row_from_cam(cam, district)
        if row is not None:
            rows.append(row)
    return rows


class CaltransEnumerator(Enumerator):
    """Enumerate all 12 Caltrans CCTV districts (D03 known-broken, skipped)."""

    name = "caltrans"
    source_ref = SOURCE_PATTERN
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family="caltrans",
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=SOURCE_PATTERN,
            notes="districts fetched politely; failing districts skipped (D03 is a known HTTP 500)",
        )
        ok, failed = [], []
        streaming_total = 0
        for n in DISTRICTS:
            label = f"D{n:02d}"
            try:
                payload = polite_json(district_url(n))
            except Exception as exc:  # noqa: BLE001 — skip district, keep enumerating
                failed.append({"district": label, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rows = parse_district(payload, label)
            for row in rows:
                result.add(row)
            streaming = sum(1 for r in rows if r.protocol == Protocol.HLS.value)
            streaming_total += streaming
            ok.append({"district": label, "rows": len(rows), "streaming": streaming})
        result.stats["districts"] = ok
        result.stats["districts_failed"] = failed
        result.stats["cams_with_streaming"] = streaming_total
        return result.finalize()

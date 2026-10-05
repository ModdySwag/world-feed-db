"""wfd.ingest.gov.deldot — DelDOT video camera enumerator (build task C).

Endpoint (S2 §2, verified 2026-10-05): ``https://tmc.deldot.gov/json/videocamera.json``
-> ``{"cameraCount": N, "videoCameras": [...]}``; each camera carries
``urls{m3u8s (https), m3u8, rtmp, f4m, mssmooth}`` plus ``id``/``title``/
``county``/``lat``/``lon``/``status``/``enabled``.

Rows are built from the m3u8-family URL (``m3u8s`` https variant preferred,
``m3u8`` fallback — the chosen key is recorded in ``meta["deldot_url_key"]``),
protocol ``hls``. The agency's own ``status``/``enabled`` flags stay in ``meta``
— rows always enter as ``status="unknown"``.
"""
from __future__ import annotations

from .base import Enumerator
from ..base import IngestResult, clean_float, clean_str, polite_get, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag
import json

URL = "https://tmc.deldot.gov/json/videocamera.json"
ATTRIBUTION = "DelDOT (Delaware Department of Transportation) — tmc.deldot.gov"


def _pick_url(urls: dict) -> tuple:
    """Prefer the https ``m3u8s`` variant, fall back to ``m3u8``; -> (url, key)."""
    for key in ("m3u8s", "m3u8"):
        value = clean_str((urls or {}).get(key))
        if value:
            return value, key
    return "", ""


def parse_cameras(payload) -> list:
    """Parse the videocamera.json payload -> rows (one per camera with an m3u8)."""
    rows = []
    for cam in (payload or {}).get("videoCameras") or []:
        urls = cam.get("urls") or {}
        raw_url, url_key = _pick_url(urls)
        if not raw_url:
            continue
        url, was_red, cred = redact_and_flag(raw_url)
        urls_redacted = {
            key: redact_and_flag(clean_str(value))[0] for key, value in urls.items()
        }

        lat = clean_float(cam.get("lat"))
        lon = clean_float(cam.get("lon"))
        if lat is not None and not (-90.0 <= lat <= 90.0):
            lat = None
        if lon is not None and not (-180.0 <= lon <= 180.0):
            lon = None

        rows.append(
            CameraRow(
                url=url,
                source_family="deldot",
                provenance=Provenance.PUBLIC.value,
                name=clean_str(cam.get("title")),
                country="US",
                lat=lat,
                lon=lon,
                protocol=Protocol.HLS.value,
                status=Health.UNKNOWN.value,   # agency 'Active' is NOT our liveness verdict
                attribution=ATTRIBUTION,
                was_redacted=was_red,
                credential_present=cred,
                tags=["traffic"],
                meta={
                    "deldot_id": clean_str(cam.get("id")),
                    "deldot_status": cam.get("status"),      # agency flag only
                    "deldot_enabled": cam.get("enabled"),    # agency flag only
                    "deldot_county": clean_str(cam.get("county")),
                    "deldot_url_key": url_key,
                    "deldot_urls": urls_redacted,
                },
            )
        )
    return rows


class DeldotEnumerator(Enumerator):
    """Enumerate the DelDOT statewide camera list."""

    name = "deldot"
    source_ref = URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family="deldot",
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=URL,
        )
        raw = polite_get(URL)
        payload = json.loads(raw.decode("utf-8-sig", errors="replace"))
        for row in parse_cameras(payload):
            result.add(row)
        result.stats["bytes"] = len(raw)
        result.stats["http"] = "2xx ok (polite_get raises on 4xx/5xx)"
        result.stats["camera_count_field"] = payload.get("cameraCount")
        result.stats["source_timestamp"] = payload.get("timestamp")
        return result.finalize()

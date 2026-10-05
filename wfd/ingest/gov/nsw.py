"""wfd.ingest.gov.nsw — Transport for NSW live camera enumerator (key-gated).

Endpoint (S2 §13): ``https://api.transport.nsw.gov.au/v1/live/cameras`` — a
GeoJSON FeatureCollection; each Point feature carries ``properties.href``
(JPEG image URL) plus title/region/view/direction, and top-level ``rights``.

Honest key-gated behaviour: when the key is missing the enumerator returns an
empty :class:`IngestResult` with ``stats["key_required"]=True`` and
``notes = profile.key_required_state("Transport for NSW Open Data")`` — no
request, no exception. With a key present, the request uses
``Authorization: apikey <token>`` and falls back to a raw ``apikey: <token>``
header on 401/403; the working variant is recorded in ``stats["auth_header"]``
(display-safe label — the token value is never printed or logged).
"""
from __future__ import annotations

import json
import urllib.error

from .base import Enumerator
from ..base import IngestResult, clean_float, clean_str, polite_get, today_iso
from ... import profile
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

URL = "https://api.transport.nsw.gov.au/v1/live/cameras"
SERVICE = "Transport for NSW Open Data"
SECRET_NAME = "NSW_API_KEY"
ATTRIBUTION = "Transport for NSW Open Data — opendata.transport.nsw.gov.au/dataset/live-traffic-cameras"


def auth_header_variants(token: str) -> list:
    """Header options in try-order as (display-safe label, headers) pairs."""
    return [
        ("Authorization: apikey", {"Authorization": f"apikey {token}"}),
        ("apikey (raw header)", {"apikey": token}),
    ]


def parse_payload(payload) -> list:
    """Parse the NSW GeoJSON payload -> rows (one per feature with an href)."""
    rows = []
    for feature in (payload or {}).get("features") or []:
        props = feature.get("properties") or {}
        href_raw = clean_str(props.get("href"))
        if not href_raw:
            continue
        url, was_red, cred = redact_and_flag(href_raw)

        lat = lon = None
        geom = feature.get("geometry") or {}
        if geom.get("type") == "Point":
            coords = geom.get("coordinates") or []
            if len(coords) >= 2:
                lon_c = clean_float(coords[0])
                lat_c = clean_float(coords[1])
                if lat_c is not None and -90.0 <= lat_c <= 90.0:
                    lat = lat_c
                if lon_c is not None and -180.0 <= lon_c <= 180.0:
                    lon = lon_c

        rows.append(
            CameraRow(
                url=url,
                source_family="nsw",
                provenance=Provenance.PUBLIC.value,
                name=clean_str(props.get("title")),
                country="AU",
                lat=lat,
                lon=lon,
                protocol=Protocol.JPEG.value,
                status=Health.UNKNOWN.value,   # enumeration never claims liveness
                attribution=ATTRIBUTION,
                was_redacted=was_red,
                credential_present=cred,
                tags=["traffic"],
                meta={
                    "nsw_feature_id": clean_str(feature.get("id")),
                    "nsw_region": props.get("region"),
                    "nsw_view": props.get("view"),
                    "nsw_direction": props.get("direction"),
                },
            )
        )
    return rows


class NswEnumerator(Enumerator):
    """Enumerate the TfNSW live camera feed (requires NSW_API_KEY)."""

    name = "nsw"
    source_ref = URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family="nsw",
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=URL,
        )
        token = profile.secret(SECRET_NAME)
        if not token:
            result.stats["key_required"] = True
            result.stats["secret"] = profile.secret_status(SECRET_NAME)
            result.notes = profile.key_required_state(SERVICE)
            return result.finalize()

        last_exc = None
        for label, headers in auth_header_variants(token):
            try:
                raw = polite_get(URL, headers=headers)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (401, 403):
                    continue        # try the next header variant
                result.stats["http_error"] = f"{exc.code} {exc.reason}"
                result.notes = f"fetch failed: HTTP {exc.code}"
                return result.finalize()
            except Exception as exc:  # noqa: BLE001 — network errors: honest empty result
                last_exc = exc
                result.notes = f"fetch failed: {type(exc).__name__}: {exc}"
                return result.finalize()

            payload = json.loads(raw.decode("utf-8-sig", errors="replace"))
            for row in parse_payload(payload):
                result.add(row)
            result.stats["auth_header"] = label
            result.stats["bytes"] = len(raw)
            result.stats["http"] = "2xx ok (polite_get raises on 4xx/5xx)"
            result.stats["features"] = len(payload.get("features") or [])
            result.stats["rights"] = payload.get("rights") or {}
            return result.finalize()

        # every header variant was rejected
        result.stats["auth_failed"] = str(last_exc)
        result.notes = "authentication rejected with both header variants"
        return result.finalize()

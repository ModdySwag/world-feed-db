"""wfd.ingest.gov.qld — QLDTraffic (Queensland TMR) webcam enumerator (key-gated).

Endpoint (S2 §13, API spec v1.10): ``https://api.qldtraffic.qld.gov.au/v1/webcams``
— a GeoJSON FeatureCollection; each Point feature (crs EPSG:7844, ``[lon, lat]``)
carries ``properties.id / description / direction / district / locality /
postcode / image_url / url`` and the payload has top-level ``published`` +
``rights``.

Key handling (spec v1.10 — owner-registered): the key goes **in the URL** as the
``apikey`` query parameter, NOT a header. Anonymous access returns HTTP 401.
The authed URL is built at call time and never printed: failure notes record
only the error type/status and any exception text is scrubbed of the token
before it can reach ``stats``/``notes``.

Rows are still images (``properties.image_url``, JPEG) — protocol ``jpeg``,
like the NSW sibling. The per-camera ``properties.url`` (API detail URL) is
kept redacted in ``meta["qld_url"]``. Enumeration never claims liveness — rows
always enter as ``status="unknown"``.
"""
from __future__ import annotations

import json
import urllib.error

from .base import Enumerator
from ..base import IngestResult, clean_float, clean_str, polite_get, tally, today_iso
from ... import profile
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

URL = "https://api.qldtraffic.qld.gov.au/v1/webcams"
SERVICE = "QLDTraffic (Queensland Department of Transport and Main Roads)"
SECRET_NAME = "QLDTRAFFIC_API_KEY"
ATTRIBUTION = (
    "© State of Queensland (Department of Transport and Main Roads) — QLDTraffic "
    "(qldtraffic.qld.gov.au)"
)


def authed_url(token: str) -> str:
    """Request URL with the key in the query per spec v1.10.

    Callers must NEVER print/log the returned string (it embeds the token).
    """
    return f"{URL}?apikey={token}"


def _sanitize(text: str, token: str) -> str:
    """Scrub the live token from error text that may be recorded/displayed."""
    return text.replace(token, "<redacted>") if token else text


def parse_payload(payload) -> list:
    """Parse the webcams GeoJSON payload -> rows (one per feature with an image)."""
    rows = []
    for feature in (payload or {}).get("features") or []:
        props = feature.get("properties") or {}
        img_raw = clean_str(props.get("image_url"))
        if not img_raw:
            continue
        url, was_red, cred = redact_and_flag(img_raw)

        detail_raw = clean_str(props.get("url"))
        detail_red, detail_was_red, detail_cred = (
            redact_and_flag(detail_raw) if detail_raw else ("", False, False)
        )

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
                source_family="qld",
                provenance=Provenance.PUBLIC.value,
                name=clean_str(props.get("description")),
                country="AU",
                city=clean_str(props.get("locality")),
                lat=lat,
                lon=lon,
                protocol=Protocol.JPEG.value,
                status=Health.UNKNOWN.value,   # enumeration never claims liveness
                attribution=ATTRIBUTION,
                was_redacted=was_red or detail_was_red,
                credential_present=cred or detail_cred,
                tags=["traffic", "webcam"],
                meta={
                    "qld_id": clean_str(props.get("id")),
                    "qld_direction": clean_str(props.get("direction")),
                    "qld_district": clean_str(props.get("district")),
                    "qld_postcode": clean_str(props.get("postcode")),
                    "qld_url": detail_red,
                    "qld_is_custom": props.get("isCustom"),
                    "qld_image_sourced_from": clean_str(props.get("image_sourced_from")),
                    "qld_extra_info": clean_str(props.get("extra_info")),
                },
            )
        )
    return rows


class QldEnumerator(Enumerator):
    """Enumerate the QLDTraffic webcam feed (requires QLDTRAFFIC_API_KEY)."""

    name = "qld"
    source_ref = URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        result = IngestResult(
            family="qld",
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=URL,
            notes="key passed in the URL per API spec v1.10 (not a header)",
        )
        token = profile.secret(SECRET_NAME)
        if not token:
            result.stats["key_required"] = True
            result.stats["secret"] = profile.secret_status(SECRET_NAME)
            result.notes = profile.key_required_state("QLDTraffic (Queensland TMR)")
            return result.finalize()

        try:
            raw = polite_get(authed_url(token))
        except urllib.error.HTTPError as exc:
            result.stats["http_error"] = f"{exc.code} {_sanitize(clean_str(exc.reason), token)}"
            result.notes = f"fetch failed: HTTP {exc.code}"
            return result.finalize()
        except Exception as exc:  # noqa: BLE001 — network errors: honest empty result
            result.notes = (
                f"fetch failed: {type(exc).__name__}: {_sanitize(str(exc), token)}"
            )
            return result.finalize()

        payload = json.loads(raw.decode("utf-8-sig", errors="replace"))
        for row in parse_payload(payload):
            result.add(row)
        result.stats["bytes"] = len(raw)
        result.stats["http"] = "2xx ok (polite_get raises on 4xx/5xx)"
        features = payload.get("features") or []
        result.stats["features"] = len(features)
        result.stats["published"] = payload.get("published")
        result.stats["rights"] = payload.get("rights") or {}
        result.stats["by_district"] = tally(
            clean_str((f.get("properties") or {}).get("district")) for f in features
        )
        return result.finalize()

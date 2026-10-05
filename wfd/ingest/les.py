"""wfd.ingest.les — Live-Environment-Streams corpus ingester (build task C).

Parses ``research/seed-tabs/data/LES-streams.geojson`` (5,997 features) into
:class:`wfd.schema.CameraRow` rows with ``source_family="les"`` and
``provenance="public_by_design"``.

Hard rules (docs/ARCHITECTURE.md §wfd.ingest.les):
- The corpus ``status`` ("active") is an HTTP-200 CI check only — it is NEVER
  carried as liveness. Every row enters as ``status="unknown"``; the corpus
  flag is preserved in ``meta["les_status"]`` and the full original property
  set under ``meta["les_props"]`` (the committed geojson remains the source
  of truth).
- URLs are redacted at parse time: 66 corpus URLs carry tokens (64 embedded
  ``?token=`` plus 2 with ``wowzatoken*`` query params that
  ``wfd.schema.redact_url`` does not cover — scrubbed locally, see
  :func:`_redact`). Redaction collapses 3 balticlivecam paths that differ
  only by token value into duplicates, so the finalized corpus is **5,994
  rows** with ``stats["redacted"] == 63`` and 3 duplicates dropped.
  ``meta["les_props"]["url"]`` is stored redacted too.

Mapping summary:
- ``url``           <- properties.url (redacted)
- ``protocol``      <- url_type: hls->hls, youtube->youtube, html_page->iframe
- ``country``       <- country_code; ``name`` <- display_name | name
- ``lat``/``lon``   <- geometry Point [lon, lat]; out-of-degree values are
  Web-Mercator meters and are converted (flagged in ``meta["les_coords_note"]``)
- ``last_verified`` <- corpus verification date part (informational: the
  corpus's own HTTP check date, not a liveness claim by us)
- everything else   -> ``meta["les_props"]``

Runner:  ``py -3.11 -m wfd.ingest.les``  ->  ``data/ingest/les.jsonl``
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys
import urllib.parse
from typing import Iterable, Optional

from .base import DATA_DIR, IngestResult, clean_float, clean_str, tally, write_jsonl
from .. import profile
from ..schema import CameraRow, Health, Protocol, Provenance, REDACTED, redact_and_flag

GEOJSON_PATH = profile.REPO_ROOT / "research" / "seed-tabs" / "data" / "LES-streams.geojson"
OUTPUT_PATH = DATA_DIR / "ingest" / "les.jsonl"

_URL_TYPE_PROTOCOL = {
    "hls": Protocol.HLS.value,
    "youtube": Protocol.YOUTUBE.value,
    "html_page": Protocol.IFRAME.value,
}

_MERCATOR_MAX = 20037508.342789244


def _coords_from_geometry(geom: dict) -> tuple:
    """Map a geojson geometry to (lat, lon, note).

    WGS84 degrees pass through; coordinates outside degree ranges but inside
    Web-Mercator bounds are converted (EPSG:3857 -> WGS84) and flagged via
    ``note``; anything else is left unmapped. ``note`` is "" when no
    special handling was needed.
    """
    if not geom or geom.get("type") != "Point":
        return None, None, ""
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None, None, ""
    x = clean_float(coords[0])
    y = clean_float(coords[1])
    if x is None or y is None:
        return None, None, ""
    if -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0:
        return y, x, ""
    if abs(x) <= _MERCATOR_MAX and abs(y) <= _MERCATOR_MAX:
        lon = x * 180.0 / _MERCATOR_MAX
        lat = math.degrees(2.0 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2.0)
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return lat, lon, "epsg:3857->wgs84"
    return None, None, "coords out of range; not mapped"


def _redact(url: str) -> tuple:
    """Redact credentials -> ``(url, was_redacted, credential_present)``.

    Starts from :func:`wfd.schema.redact_and_flag` and additionally scrubs any
    query key containing "token" (covers ``wowzatokenhash`` /
    ``wowzatokenendtime`` / ``wowzatokenstarttime`` which the schema helper's
    fixed key list misses). Core files are off-limits in this build task, so
    the gap is closed here instead of editing ``wfd/schema.py``.
    """
    red, was, cred = redact_and_flag(url)
    parts = urllib.parse.urlsplit(red)
    if parts.query:
        pairs = []
        changed = False
        for piece in parts.query.split("&"):
            key, sep, value = piece.partition("=")
            if sep and value != REDACTED and "token" in key.strip().lower():
                pairs.append(f"{key}={REDACTED}")
                changed = True
            else:
                pairs.append(piece)
        if changed:
            red = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, "&".join(pairs), parts.fragment)
            )
            was = changed or was
            cred = True
    return red, was, cred


def load_features(path=None) -> list:
    """Read the corpus geojson and return its feature list."""
    p = pathlib.Path(path) if path else GEOJSON_PATH
    with p.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return list(doc.get("features") or [])


def row_from_feature(feature: dict) -> Optional[CameraRow]:
    """Map one LES geojson feature to a CameraRow (None when it has no url)."""
    props = feature.get("properties") or {}
    url_raw = clean_str(props.get("url"))
    if not url_raw:
        return None
    url, was_red, cred = _redact(url_raw)

    geom = feature.get("geometry") or {}
    lat, lon, coords_note = _coords_from_geometry(geom)

    last_verified = ""
    lv = clean_str(props.get("last_verified"))
    if len(lv) >= 10 and lv[4:5] == "-" and lv[7:8] == "-":
        last_verified = lv[:10]          # corpus date part; raw value stays in meta

    tags = []
    for tag in (props.get("environment"), props.get("scene_type")):
        t = clean_str(tag)
        if t and t not in tags:
            tags.append(t)

    props_kept = dict(props)
    if was_red:
        props_kept["url"] = url          # never persist the raw tokenized url

    row = CameraRow(
        url=url,
        source_family="les",
        provenance=Provenance.PUBLIC.value,
        name=clean_str(props.get("display_name")) or clean_str(props.get("name")),
        country=clean_str(props.get("country_code")),
        city=clean_str(props.get("city")),
        lat=lat,
        lon=lon,
        protocol=_URL_TYPE_PROTOCOL.get(clean_str(props.get("url_type")), Protocol.UNKNOWN.value),
        status=Health.UNKNOWN.value,     # NEVER carry the corpus CI flag as liveness
        last_verified=last_verified,
        was_redacted=was_red,
        credential_present=cred,
        tags=tags,
        meta={
            "les_status": props.get("status"),
            "les_source_family": props.get("source_family"),
            "les_url_type": props.get("url_type"),
            "les_coordinates_quality": props.get("coordinates_quality"),
            "les_last_verified": props.get("last_verified"),
            "les_resolution": props.get("resolution"),
            "les_source_url_requires": props.get("source_url_requires"),
            "les_environment": props.get("environment"),
            "les_scene_type": props.get("scene_type"),
            "les_quality_tier": props.get("quality_tier"),
            "les_props": props_kept,
            "les_geometry": geom,
        },
    )
    if coords_note:
        row.meta["les_coords_note"] = coords_note
    return row


def dedupe_rows(rows: Iterable[CameraRow]) -> tuple:
    """Keep the first row per url -> ``(unique_rows, dropped_count)``."""
    seen: set = set()
    unique: list = []
    dropped = 0
    for row in rows:
        key = (row.url or "").strip()
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        unique.append(row)
    return unique, dropped


def parse_features(features: Iterable[dict]) -> tuple:
    """Parse features -> ``(rows, stats)`` with dedupe + redaction accounting."""
    feature_list = list(features)
    rows: list = []
    skipped_no_url = 0
    for feature in feature_list:
        row = row_from_feature(feature)
        if row is None:
            skipped_no_url += 1
            continue
        rows.append(row)
    unique, dropped = dedupe_rows(rows)
    lv = sorted(r.last_verified for r in unique if r.last_verified)
    stats = {
        "features": len(feature_list),
        "rows": len(unique),
        "duplicates_dropped": dropped,
        "skipped_no_url": skipped_no_url,
        "redacted": sum(1 for r in unique if r.was_redacted),
        "by_url_type": tally((r.meta.get("les_url_type") or "unknown") for r in unique),
        "last_verified_range": [lv[0], lv[-1]] if lv else [],
    }
    return unique, stats


def ingest(path=None) -> IngestResult:
    """Full corpus ingest -> finalized :class:`IngestResult` (no file writes)."""
    p = pathlib.Path(path) if path else GEOJSON_PATH
    features = load_features(p)
    rows, stats = parse_features(features)
    try:
        source_ref = str(p.relative_to(profile.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        source_ref = str(p)
    result = IngestResult(
        family="les",
        provenance=Provenance.PUBLIC.value,
        snapshot_date="",   # corpus carries no snapshot date; see last_verified_range
        source_ref=source_ref,
        notes="corpus 'status' is an HTTP-200 CI check only — rows enter as 'unknown'",
    )
    result.rows.extend(rows)
    result.stats.update(stats)
    return result.finalize()


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    result = ingest()
    written = write_jsonl(OUTPUT_PATH, result.rows)
    digest = _sha256_file(OUTPUT_PATH)
    out_rel = OUTPUT_PATH.relative_to(profile.REPO_ROOT)
    stats = result.stats

    print("L-E-S corpus ingester")
    print(f"  source:              {result.source_ref}")
    print(f"  features read:       {stats['features']}")
    print(
        f"  rows after dedupe:   {written}"
        f"  (duplicates dropped: {stats['duplicates_dropped']}; skipped without url: {stats['skipped_no_url']})"
    )
    print(f"  redacted urls:       {stats['redacted']}")
    print("  by url_type:")
    for key, value in stats["by_url_type"].items():
        print(f"      {key:<12} {value}")
    top10 = list(stats.get("by_country", {}).items())[:10]
    print("  by country (top 10): " + ", ".join(f"{k}={v}" for k, v in top10))
    if stats.get("last_verified_range"):
        print(f"  corpus last_verified range: {stats['last_verified_range'][0]} .. {stats['last_verified_range'][1]}")
    print(f"  by status:           {stats.get('by_status')}")
    print(f"  output:              {out_rel}  ({written} rows, sha256 {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

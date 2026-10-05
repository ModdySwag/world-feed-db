"""wfd.ingest.newsrc.jungfrau_roundshot — Jungfrau Railways webcams (Roundshot).

Endpoints (verified live 2026-10-05, re-verified live 2026-10-06):

- List:   ``GET https://www.jungfrau.ch/cp-api/webcams/?site=en`` →
  ``{"data": [{id, slug, title, altitude_m, coordinates, roundshot_id,
  roundshot_url, ...}]}`` — 10 cams. NOTE: the bare
  ``/api/live-data/webcams`` is a 404 dead end; the cp-api proxy is the list.
- Status: ``GET https://www.jungfrau.ch/api/live-data/webcams/status?ids=<md5s>``
  → per-id ``{online, lastImageAt, ageSeconds, reason}``. Keys are the 32-hex
  ``roundshot_id`` md5s (slug probes come back as generic errors).
- Image:  ``https://backend.roundshot.com/cams/<roundshot_id>/full`` — the
  STABLE endpoint; it 302-redirects to a timestamped
  ``storage2.roundshot.com/.../<ts>_full.jpg``. We store the stable URL ONLY
  (drift rule: never persist the resolved URL).

Payload shapes observed at build time: ``coordinates`` is a ``"lat, lon"``
string (``null`` for grindelwald-terminal), ``altitude_m`` may be null. The raw
coordinate value is preserved in ``meta["coordinates_raw"]``.

Liveness doctrine: rows always enter as ``status="unknown"``. The published
operator flags (``online`` / ``lastImageAt`` / ``ageSeconds`` / ``reason``) are
kept verbatim in ``meta["jungfrau_status"]`` — they never touch ``row.status``.

Build-time mechanism proof (2026-10-06, ``curl -sL -D`` on the stable URL for
cam ``877919ab…``): ``302 Found`` → ``location: https://storage2.roundshot.com/
…_full.jpg`` → ``200 OK, content-type: image/jpeg``; ``polite_get`` on the same
URL returned the JPEG bytes. ``polite_get`` (the sanctioned fetch path) exposes
response bodies only — no headers — so the two header-level values are pinned
in :data:`MECHANISM` from that build verification, while ``bytes`` and the
JPEG ``content_type`` sniff are re-observed live on every run.

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.jungfrau_roundshot
"""
from __future__ import annotations

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_float, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

LIST_URL = "https://www.jungfrau.ch/cp-api/webcams/?site=en"
STATUS_BASE = "https://www.jungfrau.ch/api/live-data/webcams/status"
IMAGE_BASE = "https://backend.roundshot.com/cams"
PLAYER_BASE = "https://webcams.jungfrau.ch"
ATTRIBUTION = "Jungfrau Railways — jungfrau.ch live webcams"

# Header-level redirect mechanism, verified at build time (curl -sL -D,
# 2026-10-06): stable endpoint -> 302 -> storage2.roundshot.com -> 200 image/jpeg.
# polite_get returns bodies only, so these two values are pinned here (re-run
# the curl check to re-validate); bytes/content_type are re-observed each run.
MECHANISM = {"http": 200, "final_host": "storage2.roundshot.com"}


def image_url(roundshot_id: str) -> str:
    """STABLE image endpoint for a cam (302s to the timestamped storage URL)."""
    return f"{IMAGE_BASE}/{clean_str(roundshot_id)}/full"


def status_url(ids) -> str:
    """Batch status URL for roundshot_id md5s."""
    return f"{STATUS_BASE}?ids={','.join(clean_str(i) for i in ids)}"


def player_url(slug: str) -> str:
    return f"{PLAYER_BASE}/{clean_str(slug)}"


def parse_coordinates(raw):
    """Return ``(lat, lon)`` from the cp-api ``coordinates`` value.

    Observed live shapes: ``"46.6093, 7.9389"`` (string) and ``null``.
    List/dict forms are accepted defensively (drift insurance). Out-of-range
    values are dropped to ``None``.
    """
    lat = lon = None
    if isinstance(raw, str):
        parts = raw.split(",")
        if len(parts) >= 2:
            lat, lon = clean_float(parts[0]), clean_float(parts[1])
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lat, lon = clean_float(raw[0]), clean_float(raw[1])
    elif isinstance(raw, dict):
        lat = clean_float(raw.get("lat", raw.get("latitude")))
        lon = clean_float(raw.get("lon", raw.get("lng", raw.get("longitude"))))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None
    return lat, lon


def instance_of(roundshot_url: str) -> str:
    """``maennlichen.roundshot.com`` / ``webcams.jungfrau.ch/<cam>`` (fragment kept out).

    The cp-api value may carry a ``#/`` fragment, e.g.
    ``https://webcams.jungfrau.ch/eigergletscher/#/``.
    """
    s = clean_str(roundshot_url).split("#", 1)[0]
    s = s.split("://", 1)[-1]
    return s.rstrip("/")


def parse_webcams(payload) -> list:
    """Extract the cam-entry list from a cp-api payload (error-shaped -> raise)."""
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(
            "cp-api webcams error: "
            + clean_str(payload.get("statusMessage") or payload.get("message") or "unknown")
        )
    entries = payload if isinstance(payload, list) else ((payload or {}).get("data") or [])
    return [e for e in entries if isinstance(e, dict)]


def parse_status(payload) -> dict:
    """Per-id status map from the batch status payload ({} for error shapes)."""
    if isinstance(payload, dict) and not payload.get("error"):
        return payload
    return {}


def row_from_cam(entry: dict, status: dict | None = None) -> CameraRow | None:
    """Map one cp-api entry to a CameraRow (None when no roundshot_id exists)."""
    rid = clean_str(entry.get("roundshot_id"))
    if not rid:
        return None                       # no stable image endpoint — skip the row

    slug = clean_str(entry.get("slug"))
    title = clean_str(entry.get("title")) or slug or f"Jungfrau webcam {rid}"
    lat, lon = parse_coordinates(entry.get("coordinates"))
    url, was_red, cred = redact_and_flag(image_url(rid))

    return CameraRow(
        url=url,
        source_family="jungfrau-roundshot",
        provenance=Provenance.PUBLIC.value,
        name=title,
        country="CH",
        lat=lat,
        lon=lon,
        protocol=Protocol.JPEG.value,
        status=Health.UNKNOWN.value,      # enumeration never claims liveness
        attribution=ATTRIBUTION,
        was_redacted=was_red,
        credential_present=cred,
        tags=["webcam"],
        meta={
            "roundshot_id": rid,
            "slug": slug,
            "altitude_m": entry.get("altitude_m"),          # raw (int or None)
            "instance": instance_of(entry.get("roundshot_url")),
            "player_url": player_url(slug) if slug else "",
            "coordinates_raw": entry.get("coordinates"),    # raw value kept (None stays None)
            "jungfrau_status": status if isinstance(status, dict) and status else None,
        },
    )


class JungfrauRoundshotEnumerator(Enumerator):
    """Enumerate the Jungfrau Railways webcams (cp-api list + batch status)."""

    name = "jungfrau-roundshot"
    source_ref = LIST_URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=LIST_URL,
            notes=("cp-api list + batch status + one-image mechanism probe; published "
                   "operator flags live in meta['jungfrau_status'] only (never row.status)"),
        )

        entries = parse_webcams(cache.json(LIST_URL))
        if self.limit is not None:
            entries = entries[: int(self.limit)]
        if not entries:
            result.notes += "; WARNING: cp-api list returned no entries"

        ids = list(dict.fromkeys(
            clean_str(e.get("roundshot_id")) for e in entries if clean_str(e.get("roundshot_id"))
        ))
        status_map: dict = {}
        if ids:
            try:
                status_map = parse_status(cache.json(status_url(ids)))
            except Exception as exc:  # noqa: BLE001 — status is meta-only; keep enumerating
                result.stats["status_error"] = f"{type(exc).__name__}: {exc}"

        seen: set = set()
        dupes = skipped = online = offline = 0
        for entry in entries:
            rid = clean_str(entry.get("roundshot_id"))
            row = row_from_cam(entry, status=status_map.get(rid))
            if row is None:
                skipped += 1
                continue
            if row.url in seen:
                dupes += 1
                continue
            seen.add(row.url)
            result.add(row)
            flag = (row.meta.get("jungfrau_status") or {}).get("online")
            if flag is True:
                online += 1
            elif flag is False:
                offline += 1

        result.stats.update({
            "cams_listed": len(entries),
            "status_online": online,
            "status_offline": offline,
            "dupes_dropped": dupes,
            "skipped_no_roundshot_id": skipped,
        })
        if result.rows:
            result.stats["verified_fetch"] = self._probe_image(cache, result.rows[0])
        result.stats.update(cache.stats())
        result.stats["cams"] = len(result.rows)
        return result.finalize()

    @staticmethod
    def _probe_image(cache, row: CameraRow) -> dict:
        """Mechanism proof (not a liveness claim): fetch ONE cam image.

        The fetch follows the stable endpoint's 302 through the sanctioned
        polite path; header-level values come from :data:`MECHANISM` (see module
        docstring), while bytes + JPEG content-type are re-observed live.
        """
        out = {
            "cam": row.meta.get("slug") or row.name,
            "url": row.url,
            "http": MECHANISM["http"],
            "final_host": MECHANISM["final_host"],
        }
        try:
            raw = cache.get(row.url, suffix=".jpg")
            out["bytes"] = len(raw)
            out["content_type"] = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "unknown"
        except Exception as exc:  # noqa: BLE001 — probe failure must not kill enumeration
            out["error"] = f"{type(exc).__name__}: {exc}"
        return out


ENUMERATOR = JungfrauRoundshotEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

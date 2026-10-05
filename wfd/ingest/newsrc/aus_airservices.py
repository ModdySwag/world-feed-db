"""wfd.ingest.newsrc.aus_airservices — Airservices Australia weather cameras.

Family ``aus-airservices``: the Airservices Australia public aviation weather
camera site (``weathercams.airservicesaustralia.com``) — ~39 Australian
airports, each publishing four JPEG camera angles (picture only, no streams).

Enumeration path (verified live 2026-10-06, re-verified at build):

1. Hub:   ``GET https://weathercams.airservicesaustralia.com/`` → the page's
   JS config var ``asa_airports_public_var`` carries ``{"nonce": "...", ...}``.
   The nonce is read fresh from the page on every run (it may rotate; it was
   ``5f5cb33910`` on 2026-10-06 and still at build).
2. List:  ``GET .../wp-admin/admin-ajax.php?action=get_airports_list&filter=
   &type=map&filter_type=normal&nonce=<nonce>`` — plain GET with query params
   works (no POST needed; the reconnaissance note described a POST body).
   → ``{"airport_list": [{id, name, title, state, state_full, lat, long,
   link, thumbnail, img_camera}, ...]}`` — 39 airports, HTTP 200, ~18.6 KB.
3. Pages: one HTML page per airport (``link``).  Camera JPEGs are published in
   TWO filename schemes (both live-verified 2026-10-06):

   - numeric: ``…/wp-content/uploads/airports/<code>/<code>_<angle>.jpg``
     where ``<code>`` is a per-airport 6-digit upload folder — NOT the ICAO
     ident (the reconnaissance note read Albany's ``009999`` as a zero-padded
     ICAO; live check shows every airport has its own code, e.g. Broome
     ``003003``, Hobart ``094250``) — and ``<angle>`` is the camera azimuth in
     whole degrees (observed sets: 045/135/225/315, 090/180/270/360,
     070/160/250/340 — the note's fixed "E/N/S/W" mapping does not hold);
   - named: ``…/wp-content/uploads/airports/<slug>/<direction>.jpg`` with word
     directions, e.g. Watts Bridge Memorial Airfield publishes
     ``wattsbridge/{north,east,south,west}.jpg``.

   Pages also carry ``-<W>x<H>.jpg`` grid thumbnails — excluded; stored URLs
   have the ``?v=`` cache-buster stripped.

Fallback: an airport whose page yields no camera JPEG (dead/removed page)
falls back to the ajax ``thumbnail`` — only when that thumbnail is itself a
real ``uploads/airports/…jpg`` camera image (row ``fallback=true``).
Placeholder thumbnails (``Camera-Unavailable.png``) and theme icons are never
stored as camera feeds; such airports are counted in ``airports_failed`` with
the reason recorded (live 2026-10-06: Bunbury — page up but no cameras,
placeholder thumb; Yulara — page 404, placeholder thumb).  Retry semantics: a
403/nonce failure on the ajax call triggers ONE retry against a freshly
fetched hub page (for a rotated nonce); 429s are retried (≤2) honoring
``Retry-After`` —
``polite_get`` itself raises 4xx (incl. 429) immediately, so the wrapper here
supplies the documented 429 respect.

Liveness doctrine: rows always enter as ``status="unknown"`` — enumeration
never claims liveness (``run_one`` enforces it).  No camera-image probing
happens here; fetching images is the health sweep's concern.

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.aus_airservices
"""
from __future__ import annotations

import json as _json
import re
import time

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_float, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "aus-airservices"
SITE = "https://weathercams.airservicesaustralia.com"
HUB_URL = SITE + "/"
AJAX_URL = SITE + "/wp-admin/admin-ajax.php"
ATTRIBUTION = "Airservices Australia — weathercams.airservicesaustralia.com"

NONCE_VAR = "asa_airports_public_var"
_NONCE_BLOCK_RE = re.compile(NONCE_VAR + r"\s*=\s*(\{.*?\})\s*;", re.S)
_NONCE_FIELD_RE = re.compile(r'"nonce"\s*:\s*"([^"]+)"')
_NONCE_OK_RE = re.compile(r"^[A-Za-z0-9]{4,64}$")

# Camera JPEGs: .../uploads/airports/<folder>/<file>.jpg — folder/file cover
# both live schemes (numeric `009999/009999_045.jpg`, named
# `wattsbridge/north.jpg`).  WordPress size variants (`…-300x169.jpg`,
# `…-1024x576.jpg`, …) are filtered out via _SIZE_SUFFIX_RE.  Absolute and
# root-relative forms are both matched; the relative matcher also re-matches
# inside absolute URLs, which the SITE-prefix normalization collapses into one
# normalized URL.
_CAMERA_ABS_RE = re.compile(
    r"(?P<url>https?://[^\"'<>\s]*?/wp-content/uploads/airports/"
    r"(?P<folder>[A-Za-z0-9_-]+)/(?P<file>[A-Za-z0-9_-]+)\.jpg)"
    r"(?P<query>\?[^\"'<>\s]*)?"
)
_CAMERA_REL_RE = re.compile(
    r"(?P<url>/wp-content/uploads/airports/"
    r"(?P<folder>[A-Za-z0-9_-]+)/(?P<file>[A-Za-z0-9_-]+)\.jpg)"
    r"(?P<query>\?[^\"'<>\s]*)?"
)
_SIZE_SUFFIX_RE = re.compile(r"-\d+x\d+\.jpg$")


def strip_cache_buster(url: str) -> str:
    """Drop a ``?v=<ts>`` cache-buster; keep any other query untouched."""
    base, sep, query = url.partition("?")
    if not sep:
        return url
    if query and all(piece.split("=", 1)[0] == "v" for piece in query.split("&")):
        return base
    return url


def extract_nonce(html: str) -> str:
    """Read the admin-ajax nonce from the hub page's JS config var.

    Returns ``""`` when the var/field is absent or malformed (the caller
    records that and retries with a fresh page fetch).
    """
    m = _NONCE_BLOCK_RE.search(html)
    if not m:
        return ""
    block = m.group(1)
    value = ""
    try:
        obj = _json.loads(block)
        if isinstance(obj, dict):
            value = clean_str(obj.get("nonce"))
    except ValueError:
        fm = _NONCE_FIELD_RE.search(block)
        value = fm.group(1) if fm else ""
    return value if _NONCE_OK_RE.match(value) else ""


def ajax_list_url(nonce: str) -> str:
    """Airport-list admin-ajax URL (plain GET; the verified working form)."""
    return (f"{AJAX_URL}?action=get_airports_list&filter=&type=map"
            f"&filter_type=normal&nonce={nonce}")


def extract_camera_urls(html: str) -> list:
    """Full-size camera JPEGs on one airport page as ``[(url, angle, folder)]``.

    Cache-busters stripped, WordPress size variants (``-WxH.jpg``) excluded,
    duplicates collapsed, sorted by angle token (degrees numerically, words
    alphabetically), then URL for stability.
    """
    found: dict = {}
    for regex in (_CAMERA_ABS_RE, _CAMERA_REL_RE):
        for m in regex.finditer(html):
            file_base = m.group("file")
            if _SIZE_SUFFIX_RE.search(file_base + ".jpg"):
                continue
            url = m.group("url")
            if not url.startswith("http"):
                url = SITE + url
            url = strip_cache_buster(url)
            found.setdefault(url, (url, angle_from_base(file_base),
                                   m.group("folder")))
    return sorted(found.values(), key=lambda t: (_angle_sort_key(t[1]), t[0]))


def parse_airports(payload) -> list:
    """Airport entries from the ajax payload; raises on error-shaped payloads."""
    if not isinstance(payload, dict):
        raise ValueError(
            f"airports list: expected a JSON object, got {type(payload).__name__}"
        )
    entries = payload.get("airport_list")
    if not isinstance(entries, list):
        raise ValueError(
            "airports list: 'airport_list' array missing — nonce/expiry error shape?"
        )
    return [e for e in entries if isinstance(e, dict)]


def parse_latlon(entry: dict):
    """``(lat, lon)`` from ajax ``lat``/``long``; out-of-range/blank → None."""
    lat = clean_float(entry.get("lat"))
    lon = clean_float(entry.get("long"))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None
    return lat, lon


def thumbnail_fallback(entry: dict) -> str:
    """A usable fallback camera URL from the ajax entry, or ``""``.

    Only URLs that are themselves ``uploads/airports/…`` JPEGs qualify —
    placeholder images (``Camera-Unavailable.png``) and theme icons are never
    stored as camera feeds.
    """
    for key in ("thumbnail", "img_camera"):
        cand = strip_cache_buster(clean_str(entry.get(key)))
        if cand and _CAMERA_ABS_RE.match(cand) and not _SIZE_SUFFIX_RE.search(cand):
            return cand
    return ""


def angle_from_base(file_base: str) -> str:
    """Camera angle token from a JPEG filename base.

    Numeric scheme → degree token (``009999_045`` → ``"045"``); named scheme →
    direction word (``north`` → ``"north"``, ``wattsbridge_east`` → ``"east"``).
    """
    base = clean_str(file_base)
    if base.endswith(".jpg"):
        base = base[:-4]
    token = base.rsplit("_", 1)[-1] if "_" in base else base
    return token if re.fullmatch(r"[A-Za-z0-9]{1,12}", token) else ""


def angle_from_url(url: str) -> str:
    """Angle token from a full camera JPEG URL (``""`` when absent)."""
    m = re.search(r"/([A-Za-z0-9_-]+)\.jpg(?:[?#].*)?$", strip_cache_buster(url))
    return angle_from_base(m.group(1)) if m else ""


def _angle_sort_key(angle: str):
    """Degree tokens sort numerically first; word tokens sort alphabetically."""
    if angle.isdigit():
        return (0, int(angle), "")
    return (1, 0, angle)


def row_from_camera(entry: dict, url: str, angle: str, *, page_url: str,
                    multi: bool, fallback: bool = False) -> CameraRow:
    """Map one camera JPEG URL to a CameraRow (URL redacted before storage)."""
    lat, lon = parse_latlon(entry)
    title = (clean_str(entry.get("title")) or clean_str(entry.get("name"))
             or "Airservices airport camera")
    if multi:
        label = f"{angle}°" if angle.isdigit() else angle
        name = f"{title} ({label})"
    else:
        name = title
    red_url, was_red, cred = redact_and_flag(url)
    return CameraRow(
        url=red_url,
        source_family=FAMILY,
        provenance=Provenance.PUBLIC.value,
        name=name,
        country="AU",
        lat=lat,
        lon=lon,
        protocol=Protocol.JPEG.value,
        status=Health.UNKNOWN.value,      # enumeration never claims liveness
        attribution=ATTRIBUTION,
        was_redacted=was_red,
        credential_present=cred,
        tags=["aviation", "weather"],
        meta={
            "airport_id": entry.get("id"),
            "airport_title": title,
            "state": clean_str(entry.get("state")),
            "state_full": clean_str(entry.get("state_full")),
            "angle": angle,
            "page_url": page_url,
            "fallback": bool(fallback),
        },
    )


def _fetch(cache, url: str, *, suffix: str, stats=None) -> bytes:
    """``FetchCache.get`` with the documented 429/Retry-After handling.

    ``polite_get`` retries network errors and 5xx but raises 4xx (incl. 429)
    immediately; the project convention says to respect 429/Retry-After, so
    this wrapper retries 429 only, up to twice, honoring ``Retry-After``
    (clamped to 2..60 s; default 5 s).  Retry counts land in
    ``stats["http_429_retries"]``.
    """
    retries = 0
    while True:
        try:
            raw = cache.get(url, suffix=suffix)
        except Exception as exc:  # noqa: BLE001 — re-raised unless it is a 429
            if getattr(exc, "code", None) != 429 or retries >= 2:
                raise
            retries += 1
            wait = 5.0
            headers = getattr(exc, "headers", None)
            if headers is not None:
                try:
                    wait = float(headers.get("Retry-After") or wait)
                except (TypeError, ValueError):
                    pass
            time.sleep(min(max(wait, 2.0), 60.0))
            continue
        if stats is not None and retries:
            stats["http_429_retries"] = stats.get("http_429_retries", 0) + retries
        return raw


def _cached_text(cache, url: str, stats=None) -> str:
    return _fetch(cache, url, suffix=".html", stats=stats).decode("utf-8", errors="replace")


def _cached_json(cache, url: str, stats=None):
    raw = _fetch(cache, url, suffix=".json", stats=stats)
    return _json.loads(raw.decode("utf-8-sig", errors="replace"))


class AusAirservicesEnumerator(Enumerator):
    """Enumerate the Airservices Australia weather cameras (~39 airports)."""

    name = FAMILY
    source_ref = HUB_URL
    attribution = ATTRIBUTION

    @staticmethod
    def _ajax_airports(cache, nonce: str, stats) -> list:
        payload = _cached_json(cache, ajax_list_url(nonce), stats=stats)
        return parse_airports(payload)

    def enumerate(self) -> IngestResult:
        primary = fetch_cache(self.name, refresh=self.refresh)
        caches = [primary]
        result = IngestResult(
            family=FAMILY,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=HUB_URL,
            notes=("hub nonce + admin-ajax airport list + one page fetch per airport; "
                   "rows enter status='unknown' (enumeration never claims liveness); "
                   "no image probing (health-sweep concern)"),
        )
        stats = result.stats

        # --- nonce + airport list, with ONE fresh-hub retry on failure ---------
        entries: list = []
        nonce = ""
        cache = primary
        for attempt in (1, 2):
            if attempt == 2:
                cache = fetch_cache(self.name, refresh=True)   # ignore the cache
                caches.append(cache)
                stats["hub_refetched_for_nonce"] = True
            try:
                nonce = extract_nonce(_cached_text(cache, HUB_URL, stats=stats))
                if not nonce:
                    raise ValueError(
                        f"{NONCE_VAR} nonce not found on hub page"
                    )
                entries = self._ajax_airports(cache, nonce, stats)
                stats["nonce"] = nonce
                break
            except Exception as exc:  # noqa: BLE001 — recorded; retry once
                stats[f"attempt_{attempt}_error"] = f"{type(exc).__name__}: {exc}"
                entries = []
        else:
            stats["ajax_error"] = stats.get("attempt_2_error") or stats.get("attempt_1_error")
            result.notes += "; WARNING: airport list unavailable — see stats"

        airports = entries
        if self.limit is not None:
            airports = airports[: max(0, int(self.limit))]
        stats["airports"] = len(airports)

        # --- one page per airport; fall back to a real thumbnail JPEG ----------
        seen: set = set()
        dupes = fallbacks = failed = 0
        failures: list = []
        fallback_airports: list = []
        for entry in airports:
            title = (clean_str(entry.get("title")) or clean_str(entry.get("name"))
                     or "Airservices airport camera")
            link = clean_str(entry.get("link"))
            page_err = ""
            cams: list = []
            if link.startswith(SITE + "/"):
                try:
                    cams = extract_camera_urls(_cached_text(cache, link, stats=stats))
                except Exception as exc:  # noqa: BLE001 — counted, keep enumerating
                    page_err = f"{type(exc).__name__}: {exc}"
            else:
                page_err = f"off-site link {link!r}"

            added = 0
            multi = len(cams) > 1
            for url, angle, _folder in cams:
                row = row_from_camera(entry, url, angle, page_url=link, multi=multi)
                if row.url in seen:
                    dupes += 1
                    continue
                seen.add(row.url)
                result.add(row)
                added += 1

            if not cams:
                fb = thumbnail_fallback(entry)
                if fb:
                    row = row_from_camera(entry, fb, angle_from_url(fb),
                                          page_url=link, multi=False, fallback=True)
                    if row.url in seen:
                        dupes += 1
                    else:
                        seen.add(row.url)
                        result.add(row)
                        fallbacks += 1
                        fallback_airports.append(title)
                        added += 1

            if added == 0:
                failed += 1
                reason = page_err or ("no camera JPEGs on page and no usable "
                                      "thumbnail fallback")
                failures.append({"airport": title, "reason": reason})

        stats.update({
            "airports": len(airports),
            "airports_failed": failed,
            "images": len(result.rows),
            "fallbacks": fallbacks,
            "dupes_dropped": dupes,
            "cache_hits": sum(c.hits for c in caches),
            "cache_misses": sum(c.misses for c in caches),
        })
        if fallback_airports:
            stats["fallback_airports"] = fallback_airports
        if failures:
            stats["failures"] = failures
        result.notes += (f"; airports={len(airports)} images={len(result.rows)} "
                         f"fallbacks={fallbacks} failed={failed}")
        return result.finalize()


ENUMERATOR = AusAirservicesEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

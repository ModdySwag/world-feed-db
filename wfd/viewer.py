"""wfd.viewer — local, stdlib-only viewer backend (Q4: shared backend + local web UI).

Serves the static frontend under ``wfd/web/`` and a small JSON API over the
registry database (``data/worldfeed.db``). Binds 127.0.0.1 only — a local
surface, never a public one; CORS is deliberately absent.

Run:
    py -3.11 -m wfd viewer [--port 8773]

API (the wfd/web/ frontend is built to exactly this contract):
    GET  /api/stats              -> {total, by_provenance, by_status, by_family,
                                     exposure_enabled, generated_at}
    GET  /api/overview           -> dashboard aggregates: totals, top families
                                     (with live counts), top countries,
                                     favourites_count, exposure_enabled
    GET  /api/facets             -> counts for the CURRENT filter context:
                                     total, by_status, by_provenance, by_protocol,
                                     by_family, by_country, by_tag
    GET  /api/cameras            -> GeoJSON FeatureCollection (list/search)
    GET  /api/globe-points       -> compact GeoJSON FeatureCollection of every
                                    geocoded row for the globe view: short keys
                                    {c,n,s,p,f,y,v} + Point [lon,lat]. Rows with
                                    no coordinates and the (0,0) null-island rows
                                    are skipped; exposure rows are included only
                                    while the surface is on (they render
                                    metadata-only on the globe). No params.
    GET  /api/camera/<camera_id> -> one row, all fields incl. ``meta``;
                                    404 when missing
    GET  /api/poster/<camera_id> -> cached poster image bytes (og:image from the
                                    page, a YouTube thumbnail, or a single-frame
                                    ffmpeg snapshot for hls/mjpeg rows); 404 with
                                    {'error':'no poster'} when none can be had
    GET  /api/still/<camera_id>  -> current still image bytes for 'image'-kind
                                    resolutions (e.g. skaping's newest 10-minute
                                    S3 JPEG); ?refresh=1 forces a re-resolve;
                                    404 with {'error':'no still'} otherwise
    GET  /api/resolve/<camera_id> -> on-demand resolve verdict:
                                    {ok, kind, yt_id?, live_url?, still_url?,
                                    poster_url?, reason?} (never a token)
    GET  /api/live/<camera_id>/index.m3u8 -> resolved HLS playlist rewritten to
                                    local /api/live/<cid>/seg/<name> URLs so the
                                    frontend plays it through this server;
                                    502 on resolve/relay failure
    GET  /api/live/<camera_id>/seg/<name> -> one relayed media segment (HLS)

    The /api/live|poster|still|resolve routes exist only while the resolver is
    enabled (``wfd viewer --no-resolve`` disables them, and row fields below
    disappear). They serve FULL_DISPLAY_PROVENANCE rows only — exposure rows
    never get a preview, exactly like the rest of the exposure law.
    GET  /api/prefs              -> {favourites, favourite_ids, settings, updated_at}
    POST /api/prefs/favourite    -> {"camera_id", "action": add|remove|label, "label"?}
    POST /api/prefs/reorder      -> {"order": [camera_id, ...]}
    POST /api/prefs/settings     -> {"settings": {...}} (shallow-merged)

    /api/cameras + /api/facets params:
        provenance=public|directory|exposure|all  (csv; default all; "public" =
            the displayable non-exposure set: public_by_design + aggregator_directory)
        status=<csv>   family=<csv>   protocol=<csv>   country=<csv, case-insensitive>
        tag=<csv>      (substring match on the tags JSON text)
        q=<FTS text>   (resolved via wfd.db.search ids)
        bbox=minLon,minLat,maxLon,maxLat
        geo=only|any   (default: cameras -> only [back-compat]; facets -> any)
        favourites=1   (restrict to saved favourites; combines with q=)
        sort=<col> order=asc|desc    (cameras; default camera_id asc)
        limit (default 2000, max 5000)   offset
    Feature properties: camera_id, name, city, country, source_family,
        provenance, status, protocol, last_verified, snapshot_date, tags,
        display_policy; ``url`` for public_by_design + aggregator_directory rows only.
        Those rows also gain ``resolvable`` (bool) plus ``live_url`` for hls
        resolutions, ``still_url`` for image resolutions, ``yt_id`` for ytid
        resolutions, and ``poster_url`` when a cached poster exists — in-memory
        lookups only, never for exposure rows, and omitted entirely when the
        resolver is disabled.

POST hardening: requests must carry ``X-WFD-Viewer: 1`` and, when an Origin
header is present, it must be localhost/127.0.0.1 — this blocks cross-site
POSTs from an arbitrary web page against the local viewer.

Exposure law (D6 / S5 §B / Q8), enforced here:
- ``exposure_enabled`` mirrors ``wfd.profile.settings()['private_exposure_surface']``.
- exposure_aggregator rows are served ONLY while that surface is on; with it
  off they are silently excluded from every response — even when asked for by
  name (``provenance=exposure`` yields an empty set; detail lookups answer 404).
- exposure rows never carry a ``url`` key: ``display_policy="metadata_only"``
  plus the click-through ``warning`` text (Q8: metadata + warning, no preview).
- aggregator_directory rows are third-party directory listings of public feeds
  (owner decision 2026-10-06): displayed like public rows (url included);
  provenance stays honest in the payload.

The registry is opened read-only per request (``file:...?mode=ro`` + query_only);
this process never writes to it — the ONE read-write store is the viewer prefs
file (``wfd.prefs``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import pathlib
import re
import sqlite3
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import db as dbmod
from . import prefs as prefsmod
from . import profile
from . import resolve as resolvemod

WEB_DIR = pathlib.Path(__file__).resolve().parent / "web"
DEFAULT_PORT = 8773

DEFAULT_LIMIT = 2000
MAX_LIMIT = 5000
_FTS_CAP = 5000          # q= resolves through FTS; hits beyond one page are moot
_IN_CHUNK = 500          # bound the camera_id IN (...) placeholder count
_MAX_BODY = 65536        # POST body cap

EXPOSURE_WARNING = (
    "Unsecured camera listed by a public aggregator - may capture private "
    "scenes; location approximate; unverified."
)

# Provenance classes displayed in full (url included). Third-party directories of
# public feeds belong here (owner decision 2026-10-06); exposure stays metadata-only.
FULL_DISPLAY_PROVENANCE = ("public_by_design", "aggregator_directory")

_PROV_MAP = {
    "public": ("public_by_design", "aggregator_directory"),
    "directory": ("aggregator_directory",),
    "exposure": ("exposure_aggregator",),
}

_SORT_COLUMNS = frozenset({
    "camera_id", "name", "country", "city", "source_family", "status",
    "protocol", "last_verified", "snapshot_date", "fetch_date",
})

_CAMERA_ID_RE = re.compile(r"[0-9a-f]{16}")


# ---------------------------------------------------------------------------
# query-param helpers
# ---------------------------------------------------------------------------

def _int_param(raw, default: int, low: int, high: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(n, high))


def _csv_params(raw) -> list:
    """'a,b , c' -> ['a','b','c'] (lowercased; registry vocabulary is lowercase)."""
    if not raw:
        return []
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _parse_bbox(raw):
    """'minLon,minLat,maxLon,maxLat' -> tuple of floats or None when malformed."""
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError:
        return None
    if min_lon > max_lon or min_lat > max_lat:
        return None
    return min_lon, min_lat, max_lon, max_lat


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _json_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _is_local_origin(origin: str) -> bool:
    try:
        host = urllib.parse.urlsplit(origin).hostname
    except ValueError:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


def _build_where(params, *, exposure_on: bool, geo_only: bool):
    """Common filter params -> (where list, args list, error-or-None)."""
    def one(name):
        return (params.get(name) or [None])[0]

    where, args = [], []

    prov_raw = one("provenance")
    if prov_raw:
        provs = _csv_params(prov_raw)
        if not provs or "all" not in provs:
            concrete = set()
            for p in provs:
                if p not in _PROV_MAP:
                    return None, None, ("provenance must be a csv of "
                                        "public|directory|exposure|all")
                concrete.update(_PROV_MAP[p])
            concrete = sorted(concrete)
            where.append("provenance IN (%s)" % ", ".join("?" * len(concrete)))
            args.extend(concrete)

    if not exposure_on:
        # surface off: exposure rows are not part of the served set,
        # even when asked for by name (provenance=exposure yields empty)
        where.append("provenance != 'exposure_aggregator'")

    for param, column in (("status", "status"), ("family", "source_family"),
                          ("protocol", "protocol")):
        values = _csv_params(one(param))
        if values:
            where.append(f"{column} IN (%s)" % ", ".join("?" * len(values)))
            args.extend(values)

    countries = [c.upper() for c in _csv_params(one("country"))]
    if countries:
        where.append("upper(trim(country)) IN (%s)" % ", ".join("?" * len(countries)))
        args.extend(countries)

    tags = _csv_params(one("tag"))
    if tags:
        likes = []
        for t in tags:
            likes.append("tags LIKE ?")
            args.append(f'%"{t}"%')
        where.append("(" + " OR ".join(likes) + ")")

    bbox_raw = one("bbox")
    if bbox_raw:
        bbox = _parse_bbox(bbox_raw)
        if bbox is None:
            return None, None, "bbox must be minLon,minLat,maxLon,maxLat"
        min_lon, min_lat, max_lon, max_lat = bbox
        where.append("lon BETWEEN ? AND ?")
        where.append("lat BETWEEN ? AND ?")
        args.extend([min_lon, max_lon, min_lat, max_lat])

    if geo_only:
        where.append("lat IS NOT NULL")
        where.append("lon IS NOT NULL")

    return where, args, None


def _clause_chunks(clause: str, args: list, candidates):
    """Yield (clause, args) pairs — one, or one per camera_id chunk when a
    candidate id list (from q= / favourites=1) is in play."""
    if candidates is None:
        yield clause, list(args)
        return
    for chunk in _chunks(candidates, _IN_CHUNK):
        marks = ", ".join("?" * len(chunk))
        yield f"{clause} AND camera_id IN ({marks})", [*args, *chunk]


def _sort_rows(rows, sort: str, order: str):
    """Python-side sort matching the SQL path (NULLs last; case-insensitive)."""
    valued = [r for r in rows if r[sort] is not None]
    nulls = [r for r in rows if r[sort] is None]
    valued.sort(key=lambda r: (str(r[sort]).lower(), r["camera_id"]),
                reverse=(order == "desc"))
    return valued + nulls


def _fetch_rows(conn, clause, args, *, candidates, sort, order, limit, offset):
    if candidates is None:
        sql = (f"SELECT * FROM cameras WHERE {clause} "
               f"ORDER BY ({sort} IS NULL), {sort} COLLATE NOCASE {order.upper()}, camera_id "
               f"LIMIT ? OFFSET ?")
        return conn.execute(sql, (*args, limit, offset)).fetchall()
    rows = []
    for ch_clause, ch_args in _clause_chunks(clause, args, candidates):
        rows.extend(conn.execute(
            f"SELECT * FROM cameras WHERE {ch_clause}", ch_args).fetchall())
    rows = _sort_rows(rows, sort, order)
    return rows[offset:offset + limit]


# ---------------------------------------------------------------------------
# row -> display payload (the exposure law lives here)
# ---------------------------------------------------------------------------

def _add_resolved_fields(payload: dict, *, camera_id: str, url, provenance: str,
                         resolve_on: bool) -> None:
    """Additive resolve/poster fields for full-display rows only (never exposure).

    Cache lookups are in-memory (memoised index / live.json), so 5000-row
    /api/cameras lists stay fast; nothing here touches the network.
    """
    if not resolve_on or provenance not in FULL_DISPLAY_PROVENANCE:
        return
    payload["resolvable"] = bool(resolvemod.host_resolvable(url or ""))
    entry = resolvemod.cached_live_entry(camera_id)
    if entry:
        kind = entry.get("kind")
        if kind == "hls":
            payload["live_url"] = f"/api/live/{camera_id}/index.m3u8"
        elif kind == "image":
            payload["still_url"] = f"/api/still/{camera_id}"
        elif kind == "ytid":
            vid = str(entry.get("id") or "")
            if len(vid) == 11 and resolvemod._YOUTUBE_ID_RE.fullmatch(vid):
                payload["yt_id"] = vid
    poster = resolvemod.cached_poster_url(camera_id)
    if poster:
        payload["poster_url"] = poster


def _display_props(row: sqlite3.Row, resolve_on: bool = True) -> dict:
    """Feature properties for one camera row, applying url/display_policy rules."""
    provenance = row["provenance"]
    props = {
        "camera_id": row["camera_id"],
        "name": row["name"],
        "city": row["city"],
        "country": row["country"],
        "source_family": row["source_family"],
        "provenance": provenance,
        "status": row["status"],
        "protocol": row["protocol"],
        "last_verified": row["last_verified"],
        "snapshot_date": row["snapshot_date"],
        "tags": _json_list(row["tags"]),
        "display_policy": "full" if provenance in FULL_DISPLAY_PROVENANCE else "metadata_only",
    }
    if provenance in FULL_DISPLAY_PROVENANCE:
        props["url"] = row["url"]          # url for displayable (non-exposure) rows
        _add_resolved_fields(props, camera_id=row["camera_id"], url=row["url"],
                             provenance=provenance, resolve_on=resolve_on)
    elif provenance == "exposure_aggregator":
        props["warning"] = EXPOSURE_WARNING
    return props


def _feature(row: sqlite3.Row, resolve_on: bool = True) -> dict:
    lon, lat = row["lon"], row["lat"]
    geometry = ({"type": "Point", "coordinates": [lon, lat]}
                if lon is not None and lat is not None else None)
    return {"type": "Feature", "geometry": geometry,
            "properties": _display_props(row, resolve_on)}


def _detail_payload(row, resolve_on: bool = True) -> dict:
    """Full detail dict for one row — same url/display_policy rules as features."""
    payload = row.as_dict()
    displayable = row.provenance in FULL_DISPLAY_PROVENANCE
    payload["display_policy"] = "full" if displayable else "metadata_only"
    if not displayable:
        payload.pop("url", None)
    else:
        _add_resolved_fields(payload, camera_id=row.camera_id, url=row.url,
                             provenance=row.provenance, resolve_on=resolve_on)
    if row.provenance == "exposure_aggregator":
        payload["warning"] = EXPOSURE_WARNING
    return payload


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class ViewerServer(ThreadingHTTPServer):
    """Threaded local server; config rides on the server so handlers stay stateless."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler_cls, db_path, quiet: bool = False,
                 prefs_path=None, resolve_enabled: bool = True):
        self.db_path = pathlib.Path(db_path)
        self.quiet = quiet
        self.prefs = prefsmod.PrefsStore(prefs_path)
        self.resolve_enabled = bool(resolve_enabled)
        super().__init__(address, handler_cls)


class ViewerHandler(SimpleHTTPRequestHandler):
    """/api/* -> JSON API; everything else -> static files from wfd/web/."""

    server_version = "wfd-viewer/0.3"
    protocol_version = "HTTP/1.1"
    # Explicit map so .js/.mjs always serve as JS even when the Windows
    # registry-backed mimetypes module guesses text/plain (breaks ES modules).
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".webmanifest": "application/manifest+json",
    }

    # -- routing ------------------------------------------------------------

    def do_GET(self):                      # noqa: N802 (stdlib naming)
        self._route()

    def do_HEAD(self):                     # noqa: N802
        self._route()

    def do_POST(self):                     # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        if path.startswith("/api/"):
            try:
                self._api_post(path)
            except Exception as exc:  # noqa: BLE001 — a local viewer answers, never dies
                try:
                    self._send_json(500, {"error": f"internal error: {type(exc).__name__}"})
                except Exception:  # noqa: BLE001
                    pass
            return
        self.send_error(405, "method not allowed")

    def _route(self):
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        if path.startswith("/api/"):
            try:
                self._api(path, parts.query)
            except Exception as exc:  # noqa: BLE001 — a local viewer answers, never dies
                try:
                    self._send_json(500, {"error": f"internal error: {type(exc).__name__}"})
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def _api(self, path: str, query: str):
        if path == "/api/stats":
            return self._handle_stats()
        if path == "/api/overview":
            return self._handle_overview()
        if path == "/api/facets":
            return self._handle_facets(query)
        if path == "/api/cameras":
            return self._handle_cameras(query)
        if path == "/api/globe-points":
            return self._handle_globe_points()
        if path == "/api/prefs":
            return self._handle_prefs_get()
        if path.startswith("/api/camera/"):
            return self._handle_camera(urllib.parse.unquote(path[len("/api/camera/"):]))
        if path.startswith("/api/poster/") or path.startswith("/api/still/") \
                or path.startswith("/api/resolve/") or path.startswith("/api/live/"):
            if not self.server.resolve_enabled:
                return self._send_json(404, {"error": "resolver disabled "
                                             "(wfd viewer --no-resolve)", "path": path})
            if path.startswith("/api/poster/"):
                return self._handle_poster(
                    urllib.parse.unquote(path[len("/api/poster/"):]), query)
            if path.startswith("/api/still/"):
                return self._handle_still(
                    urllib.parse.unquote(path[len("/api/still/"):]), query)
            if path.startswith("/api/resolve/"):
                return self._handle_resolve(
                    urllib.parse.unquote(path[len("/api/resolve/"):]), query)
            rest = path[len("/api/live/"):]
            if "/seg/" in rest:                 # checked first: seg names can't contain '/'
                cid, _, name = rest.partition("/seg/")
                return self._handle_live_segment(urllib.parse.unquote(cid),
                                                 urllib.parse.unquote(name))
            if rest.endswith("/index.m3u8"):
                return self._handle_live_index(
                    urllib.parse.unquote(rest[: -len("/index.m3u8")]), query)
            return self._send_json(404, {"error": "unknown api route", "path": path})
        return self._send_json(404, {"error": "unknown api route", "path": path})

    # -- infrastructure -----------------------------------------------------

    def _open_db(self):
        """Read-only registry connection, or None when the db has not been built."""
        db_path = self.server.db_path
        if not db_path.exists():
            return None
        uri = "file:" + urllib.parse.quote(db_path.resolve().as_posix(), safe="/:") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def _exposure_enabled(self) -> bool:
        """Surface state, evaluated per request. Fails closed (off) on any trouble."""
        try:
            return bool(profile.settings().get("private_exposure_surface"))
        except Exception:  # noqa: BLE001
            return False

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_bytes(self, status: int, body: bytes, content_type: str,
                    cache_control: str = "no-store"):
        """Raw-bytes response (poster images, playlists, segments); HEAD-safe."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _db_missing(self):
        return self._send_json(503, {"error": "registry database not found",
                                     "db": str(self.server.db_path)})

    def log_message(self, fmt, *args):     # quieter in tests / embedded runs
        if not getattr(self.server, "quiet", False):
            super().log_message(fmt, *args)

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return None, "bad Content-Length"
        if length <= 0:
            return None, "request body required"
        if length > _MAX_BODY:
            return None, f"request body too large (max {_MAX_BODY} bytes)"
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, "invalid JSON body"
        if not isinstance(data, dict):
            return None, "JSON object required"
        return data, None

    def _prefs_payload(self, data=None) -> dict:
        data = data if data is not None else self.server.prefs.load()
        return {
            "favourites": data["favourites"],
            "favourite_ids": [f["camera_id"] for f in data["favourites"]],
            "settings": data["settings"],
            "updated_at": data.get("updated_at", ""),
        }

    def _candidate_ids(self, conn, params):
        """q= / favourites=1 -> candidate camera_id list (None when neither)."""
        def one(name):
            return (params.get(name) or [None])[0]
        q = (one("q") or "").strip()
        favs = (one("favourites") or "").strip().lower() in ("1", "true", "yes")
        ids = None
        if q:
            ids = [h["camera_id"] for h in dbmod.search(conn, q, limit=_FTS_CAP)]
        if favs:
            fav_ids = self.server.prefs.favourite_ids()
            ids = fav_ids if ids is None else [i for i in ids if i in set(fav_ids)]
        return ids

    # -- endpoints ------------------------------------------------------------

    def _handle_stats(self):
        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            counts = dbmod.counts(conn)
            by_family = {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT source_family, COUNT(*) FROM cameras "
                    "GROUP BY source_family ORDER BY COUNT(*) DESC, source_family"
                )
            }
        finally:
            conn.close()
        self._send_json(200, {
            "total": counts["total"],
            "by_provenance": counts["by_provenance"],
            "by_status": counts["by_status"],
            "by_family": by_family,
            "exposure_enabled": self._exposure_enabled(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        })

    def _handle_overview(self):
        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            gate = "" if self._exposure_enabled() else "WHERE provenance != 'exposure_aggregator'"
            total = conn.execute(f"SELECT COUNT(*) FROM cameras {gate}").fetchone()[0]
            by_status = {r[0]: r[1] for r in conn.execute(
                f"SELECT status, COUNT(*) FROM cameras {gate} GROUP BY status")}
            by_prov = {r[0]: r[1] for r in conn.execute(
                f"SELECT provenance, COUNT(*) FROM cameras {gate} GROUP BY provenance")}
            top_families = [
                {"family": r[0], "total": r[1], "live": r[2] or 0}
                for r in conn.execute(
                    f"SELECT source_family, COUNT(*), "
                    f"SUM(CASE WHEN status='live' THEN 1 ELSE 0 END) "
                    f"FROM cameras {gate} GROUP BY source_family "
                    f"ORDER BY 2 DESC, 1 LIMIT 12")
            ]
            top_countries = {r[0]: r[1] for r in conn.execute(
                f"SELECT upper(trim(country)), COUNT(*) FROM cameras {gate} "
                f"{'AND' if gate else 'WHERE'} country IS NOT NULL AND trim(country) != '' "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 12")}
            fav_count = len(self.server.prefs.load()["favourites"])
        finally:
            conn.close()
        self._send_json(200, {
            "total": total,
            "by_status": by_status,
            "by_provenance": by_prov,
            "top_families": top_families,
            "top_countries": top_countries,
            "favourites_count": fav_count,
            "exposure_enabled": self._exposure_enabled(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        })

    def _handle_facets(self, query: str):
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        def one(name):
            return (params.get(name) or [None])[0]

        geo = (one("geo") or "any").strip().lower()
        geo_only = geo == "only"
        where, args, err = _build_where(params, exposure_on=self._exposure_enabled(),
                                        geo_only=geo_only)
        if err:
            payload = {"error": err}
            if err.startswith("bbox"):
                payload["bbox"] = one("bbox")
            return self._send_json(400, payload)

        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            candidates = self._candidate_ids(conn, params)
            out = {"total": 0, "by_status": {}, "by_provenance": {}, "by_protocol": {},
                   "by_family": {}, "by_country": {}, "by_tag": {}}
            if candidates == []:
                return self._send_json(200, out)
            clause = " AND ".join(where) or "1=1"
            dims = (("by_status", "status"), ("by_provenance", "provenance"),
                    ("by_protocol", "protocol"))
            for ch_clause, ch_args in _clause_chunks(clause, args, candidates):
                out["total"] += conn.execute(
                    f"SELECT COUNT(*) FROM cameras WHERE {ch_clause}", ch_args).fetchone()[0]
                for key, col in dims:
                    for value, n in conn.execute(
                            f"SELECT {col}, COUNT(*) FROM cameras WHERE {ch_clause} "
                            f"GROUP BY {col}", ch_args):
                        out[key][value] = out[key].get(value, 0) + n
                for value, n in conn.execute(
                        f"SELECT source_family, COUNT(*) FROM cameras "
                        f"WHERE {ch_clause} GROUP BY source_family", ch_args):
                    out["by_family"][value] = out["by_family"].get(value, 0) + n
                for value, n in conn.execute(
                        f"SELECT upper(trim(country)), COUNT(*) FROM cameras "
                        f"WHERE {ch_clause} AND country IS NOT NULL AND trim(country) != '' "
                        f"GROUP BY 1", ch_args):
                    out["by_country"][value] = out["by_country"].get(value, 0) + n
                for (raw_tags,) in conn.execute(
                        f"SELECT tags FROM cameras WHERE {ch_clause}", ch_args):
                    for tag in _json_list(raw_tags):
                        key = str(tag).lower()
                        out["by_tag"][key] = out["by_tag"].get(key, 0) + 1
            out["by_family"] = dict(sorted(out["by_family"].items(),
                                           key=lambda kv: (-kv[1], kv[0])))
            out["by_country"] = dict(sorted(out["by_country"].items(),
                                            key=lambda kv: (-kv[1], kv[0]))[:120])
            out["by_tag"] = dict(sorted(out["by_tag"].items(),
                                        key=lambda kv: (-kv[1], kv[0]))[:80])
        finally:
            conn.close()
        self._send_json(200, out)

    def _handle_cameras(self, query: str):
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        def one(name):
            return (params.get(name) or [None])[0]

        sort = (one("sort") or "camera_id").strip()
        order = (one("order") or "asc").strip().lower()
        if sort not in _SORT_COLUMNS:
            return self._send_json(400, {"error": "sort must be one of "
                                         + "|".join(sorted(_SORT_COLUMNS)), "sort": sort})
        if order not in ("asc", "desc"):
            return self._send_json(400, {"error": "order must be asc|desc", "order": order})

        geo = (one("geo") or "only").strip().lower()
        geo_only = geo != "any"
        where, args, err = _build_where(params, exposure_on=self._exposure_enabled(),
                                        geo_only=geo_only)
        if err:
            payload = {"error": err}
            if err.startswith("bbox"):
                payload["bbox"] = one("bbox")
            return self._send_json(400, payload)

        limit = _int_param(one("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int_param(one("offset"), 0, 0, 1_000_000_000)

        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            candidates = self._candidate_ids(conn, params)
            if candidates == []:
                features = []
            else:
                clause = " AND ".join(where) or "1=1"
                rows = _fetch_rows(conn, clause, args, candidates=candidates,
                                   sort=sort, order=order, limit=limit, offset=offset)
                features = [_feature(r, self.server.resolve_enabled) for r in rows]
        finally:
            conn.close()
        self._send_json(200, {"type": "FeatureCollection", "features": features})

    def _handle_globe_points(self):
        """Compact GeoJSON FeatureCollection for the globe view (no params).

        Every row with usable coordinates, short property keys so the ~14k
        features stay small for the WebGL layer: c=camera_id, n=name, s=status,
        p=protocol, f=source_family, y=country (trimmed), v=provenance,
        t=city (trimmed, may be empty — drives the city label tier). Rows
        with NULL lat/lon and the (0,0) null-island rows are skipped. Exposure
        rows are served ONLY while the surface is on, and they keep
        v='exposure_aggregator' so the globe renders them metadata-only.
        """
        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        where = ["lat IS NOT NULL", "lon IS NOT NULL", "NOT (lat = 0 AND lon = 0)"]
        if not self._exposure_enabled():
            where.append("provenance != 'exposure_aggregator'")
        try:
            rows = conn.execute(
                "SELECT camera_id, name, status, protocol, source_family, country, "
                "city, lon, lat, provenance FROM cameras WHERE " + " AND ".join(where)
            ).fetchall()
        finally:
            conn.close()
        features = [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "c": row["camera_id"],
                "n": row["name"] or "",
                "s": row["status"] or "",
                "p": row["protocol"] or "",
                "f": row["source_family"] or "",
                "y": (row["country"] or "").strip(),
                "v": row["provenance"],
                "t": (row["city"] or "").strip()[:48],
            },
        } for row in rows]
        self._send_json(200, {"type": "FeatureCollection", "features": features})

    def _handle_camera(self, camera_id: str):
        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            row = dbmod.get(conn, camera_id)
        finally:
            conn.close()
        # hidden rows are indistinguishable from missing ones while the surface is off
        if row is None or (row.provenance == "exposure_aggregator"
                           and not self._exposure_enabled()):
            return self._send_json(404, {"error": "camera not found", "camera_id": camera_id})
        self._send_json(200, _detail_payload(row, self.server.resolve_enabled))

    def _handle_prefs_get(self):
        return self._send_json(200, self._prefs_payload())

    # -- resolve relay (poster image + HLS playlist/segments) -----------------

    def _relay_row(self, camera_id: str):
        """(row, db_missing) for relay routes — full-display rows only.

        Same exposure law as _handle_camera (missing rows and hidden exposure
        rows are both 404); exposure rows never get a preview even while the
        surface is on, so provenance must be in FULL_DISPLAY_PROVENANCE.
        """
        conn = self._open_db()
        if conn is None:
            return None, True
        try:
            row = dbmod.get(conn, camera_id)
        finally:
            conn.close()
        if row is None or row.provenance not in FULL_DISPLAY_PROVENANCE:
            return None, False
        return row, False

    def _resolve_and_fetch(self, camera_id, page_url, *, force: bool):
        """(live entry|None, upstream playlist text|None) — no exception escapes."""
        try:
            entry = resolvemod.get_live(camera_id, page_url, force=force)
        except Exception:  # noqa: BLE001 — resolution failure is an answer, not a crash
            entry = None
        if not entry or entry.get("kind") != "hls":
            return entry, None
        try:
            return entry, resolvemod.fetch_playlist(entry)
        except Exception:  # noqa: BLE001 — upstream fetch failure is an answer
            return entry, None

    def _rewrite_or_reason(self, camera_id, text, entry):
        """(rewritten playlist|None, reason|None) — never raises."""
        if text is None:
            return None, "upstream playlist unavailable"
        if resolvemod.is_filler(text):
            return None, "upstream sent a filler playlist"
        if resolvemod.is_dead_playlist(text):
            return None, "upstream playlist carries no segments (stale token?)"
        try:
            return resolvemod.resolve_playlist(
                camera_id, text,
                resolvemod.redact((entry or {}).get("url", ""))), None
        except resolvemod.FillerError:
            return None, "upstream sent a filler playlist"
        except Exception:  # noqa: BLE001 — a rewrite bug must not kill the request
            return None, "playlist rewrite failed"

    def _fetch_seg(self, url, headers):
        """fetch_segment with a hard no-raise guarantee -> (blob|None, ctype|None).

        An empty upstream body is a failed fetch (evicted segment, CDN hiccup):
        report None so the one-refresh retry path can take over."""
        try:
            blob, ctype = resolvemod.fetch_segment(url, headers)
        except Exception:  # noqa: BLE001
            return None, None
        if not blob:
            return None, None
        return blob, ctype

    def _live_playlist_text(self, camera_id, page_url, *, force=False):
        """Rewritten playlist, or (None, short reason). On filler/dead/failure the
        resolution is refreshed once (force) and retried once."""
        entry, text = self._resolve_and_fetch(camera_id, page_url, force=force)
        bad = (text is None or resolvemod.is_filler(text)
               or resolvemod.is_dead_playlist(text))
        if bad and not force:
            entry, text = self._resolve_and_fetch(camera_id, page_url, force=True)
        return self._rewrite_or_reason(camera_id, text, entry)

    def _refill_for_segment(self, camera_id, page_url, name, *, force=False):
        """Resolve + fetch + rewrite the playlist, then look the segment up."""
        entry, text = self._resolve_and_fetch(camera_id, page_url, force=force)
        bad = (text is None or resolvemod.is_filler(text)
               or resolvemod.is_dead_playlist(text))
        if bad and not force:
            entry, text = self._resolve_and_fetch(camera_id, page_url, force=True)
        self._rewrite_or_reason(camera_id, text, entry)   # registers the seg map
        return entry, resolvemod.seg_upstream(camera_id, name)

    def _handle_poster(self, camera_id: str, query: str):
        row, db_missing = self._relay_row(camera_id)
        if db_missing:
            return self._db_missing()
        if row is None:
            return self._send_json(404, {"error": "camera not found",
                                         "camera_id": camera_id})
        force = "refresh" in urllib.parse.parse_qs(query, keep_blank_values=True)
        try:
            path = resolvemod.get_poster(camera_id, row.url, force=force,
                                         protocol=row.protocol)
        except Exception:  # noqa: BLE001
            path = None
        if path is None:
            return self._send_json(404, {"error": "no poster", "camera_id": camera_id})
        try:
            blob = pathlib.Path(path).read_bytes()
        except OSError:
            return self._send_json(404, {"error": "no poster", "camera_id": camera_id})
        self._send_bytes(200, blob, resolvemod.image_content_type(blob),
                         cache_control="max-age=600")

    def _handle_still(self, camera_id: str, query: str):
        """Current still bytes for an 'image'-kind camera (skaping 10-min JPEG).

        ``?refresh=1`` forces a re-resolve. Misses answer 404 {'error':'no
        still'}; the bytes memo (~90 s, in wfd.resolve) keeps tile walls calm.
        """
        row, db_missing = self._relay_row(camera_id)
        if db_missing:
            return self._db_missing()
        if row is None:
            return self._send_json(404, {"error": "camera not found",
                                         "camera_id": camera_id})
        force = "refresh" in urllib.parse.parse_qs(query, keep_blank_values=True)
        try:
            blob, ctype = resolvemod.get_still(camera_id, row.url, force=force)
        except Exception:  # noqa: BLE001 — a fetch failure is an answer of 'none'
            blob, ctype = None, None
        if not blob:
            return self._send_json(404, {"error": "no still"})
        self._send_bytes(200, blob, ctype or "image/jpeg",
                         cache_control="max-age=60")

    def _handle_resolve(self, camera_id: str, query: str):
        """On-demand resolver verdict for one row (cache-aware; ?refresh=1 forces).

        The response shape is display-only — it never carries a token, cookie
        or upstream secret. Negative verdicts reuse the 120 s live-cache so
        repeated calls for an unresolvable row stay cheap.
        """
        row, db_missing = self._relay_row(camera_id)
        if db_missing:
            return self._db_missing()
        if row is None:
            return self._send_json(404, {"error": "camera not found",
                                         "camera_id": camera_id})
        if not resolvemod.host_resolvable(row.url):
            return self._send_json(200, {"camera_id": camera_id, "ok": False,
                                         "reason": "no-resolver"})
        force = "refresh" in urllib.parse.parse_qs(query, keep_blank_values=True)
        try:
            entry = resolvemod.get_live(camera_id, row.url, force=force)
        except Exception:  # noqa: BLE001 — resolution failure is an answer
            entry = None
        if not entry:
            return self._send_json(200, {"camera_id": camera_id, "ok": False,
                                         "reason": "resolve failed"})
        kind = entry.get("kind")
        payload = {"camera_id": camera_id, "ok": True, "kind": kind}
        if kind == "ytid":
            vid = str(entry.get("id") or "")
            if len(vid) == 11 and resolvemod._YOUTUBE_ID_RE.fullmatch(vid):
                payload["yt_id"] = vid
        elif kind == "image":
            payload["still_url"] = f"/api/still/{camera_id}"
        elif kind == "hls":
            payload["live_url"] = f"/api/live/{camera_id}/index.m3u8"
        poster = resolvemod.cached_poster_url(camera_id)
        if poster:
            payload["poster_url"] = poster
        self._send_json(200, payload)

    def _handle_live_index(self, camera_id: str, query: str):
        row, db_missing = self._relay_row(camera_id)
        if db_missing:
            return self._db_missing()
        if row is None:
            return self._send_json(404, {"error": "camera not found",
                                         "camera_id": camera_id})
        force = "refresh" in urllib.parse.parse_qs(query, keep_blank_values=True)
        text, reason = self._live_playlist_text(camera_id, row.url, force=force)
        if text is None:
            text, reason = self._live_playlist_text(camera_id, row.url, force=True)
        if text is None:
            return self._send_json(502, {"error": "live resolve failed",
                                         "reason": reason or "unknown"})
        self._send_bytes(200, text.encode("utf-8"),
                         "application/vnd.apple.mpegurl", cache_control="no-store")

    def _handle_live_segment(self, camera_id: str, name: str):
        row, db_missing = self._relay_row(camera_id)
        if db_missing:
            return self._db_missing()
        if row is None:
            return self._send_json(404, {"error": "camera not found",
                                         "camera_id": camera_id})
        if not resolvemod.SEG_NAME_RE.fullmatch(name or ""):
            return self._send_json(404, {"error": "unknown segment", "name": name})
        upstream = resolvemod.seg_upstream(camera_id, name)
        entry = None
        if upstream is None:
            # map miss: re-resolve + refetch + rewrite once, then retry the lookup
            entry, upstream = self._refill_for_segment(camera_id, row.url, name)
        if upstream is None:
            return self._send_json(404, {"error": "unknown segment", "name": name})
        if entry is None:
            try:
                entry = resolvemod.get_live(camera_id, row.url)
            except Exception:  # noqa: BLE001
                entry = None
        blob, ctype = self._fetch_seg(upstream, (entry or {}).get("headers"))
        if blob is None:
            # upstream 403/timeout (stale token): refresh the resolver once, retry once
            entry, upstream = self._refill_for_segment(camera_id, row.url, name,
                                                       force=True)
            if upstream is not None:
                blob, ctype = self._fetch_seg(upstream,
                                              (entry or {}).get("headers"))
        if blob is None:
            return self._send_json(502, {"error": "segment fetch failed",
                                         "name": name})
        self._send_bytes(200, blob, ctype or "video/mp2t", cache_control="no-store")

    # -- POST endpoints (prefs; hardened for the local-UI-only rule) ----------

    def _api_post(self, path: str):
        if self.headers.get("X-WFD-Viewer") != "1":
            return self._send_json(403, {"error": "POST requires X-WFD-Viewer: 1 (same-origin UI only)"})
        origin = self.headers.get("Origin")
        if origin and not _is_local_origin(origin):
            return self._send_json(403, {"error": "cross-origin POST rejected"})
        body, err = self._read_json_body()
        if err:
            return self._send_json(400, {"error": err})

        if path == "/api/prefs/favourite":
            cid = str(body.get("camera_id") or "").strip()
            action = str(body.get("action") or "").strip().lower()
            if not _CAMERA_ID_RE.fullmatch(cid):
                return self._send_json(400, {"error": "camera_id must be 16 lowercase hex"})
            if action not in ("add", "remove", "label"):
                return self._send_json(400, {"error": "action must be add|remove|label"})
            if action == "add":
                conn = self._open_db()
                if conn is None:
                    return self._db_missing()
                try:
                    row = conn.execute("SELECT provenance FROM cameras "
                                       "WHERE camera_id=?", (cid,)).fetchone()
                finally:
                    conn.close()
                if row is None or (row["provenance"] == "exposure_aggregator"
                                   and not self._exposure_enabled()):
                    return self._send_json(404, {"error": "camera not found",
                                                 "camera_id": cid})
                data = self.server.prefs.add_favourite(cid)
            elif action == "remove":
                data = self.server.prefs.remove_favourite(cid)
            else:  # label
                data = self.server.prefs.update_label(cid, str(body.get("label") or ""))
            return self._send_json(200, self._prefs_payload(data))

        if path == "/api/prefs/reorder":
            order = body.get("order")
            if not isinstance(order, list) or not all(isinstance(i, str) for i in order):
                return self._send_json(400, {"error": "order must be a list of camera ids"})
            data = self.server.prefs.reorder_favourites(order)
            return self._send_json(200, self._prefs_payload(data))

        if path == "/api/prefs/settings":
            patch_body = body.get("settings")
            try:
                data = self.server.prefs.update_settings(patch_body)
            except ValueError as exc:
                return self._send_json(400, {"error": str(exc)})
            return self._send_json(200, self._prefs_payload(data))

        return self._send_json(404, {"error": "unknown api route", "path": path})


# ---------------------------------------------------------------------------
# server factory + CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, db_path=None,
                web_dir=None, quiet: bool = False, prefs_path=None,
                resolve_enabled: bool = True) -> ViewerServer:
    """Build (not start) a viewer server. ``port=0`` -> ephemeral (tests)."""
    db_path = pathlib.Path(db_path) if db_path else dbmod.DEFAULT_DB
    web_dir = pathlib.Path(web_dir) if web_dir else WEB_DIR
    handler = functools.partial(ViewerHandler, directory=str(web_dir))
    return ViewerServer((host, port), handler, db_path, quiet=quiet,
                        prefs_path=prefs_path, resolve_enabled=resolve_enabled)


def _cmd_viewer(args) -> int:
    port = getattr(args, "port", DEFAULT_PORT)
    resolve_enabled = not getattr(args, "no_resolve", False)
    try:
        server = make_server(port=port, resolve_enabled=resolve_enabled)
    except OSError as exc:
        print(f"viewer: cannot bind 127.0.0.1:{port} ({exc})")
        return 1
    bound_port = server.server_address[1]
    surface = ("on (private exposure surface)"
               if bool(profile.settings().get("private_exposure_surface")) else "off (clean)")
    print("wfd viewer — local registry viewer")
    print(f"  url:              http://127.0.0.1:{bound_port}/")
    print(f"  db (read-only):   {server.db_path}")
    print(f"  prefs:            {server.prefs.path}")
    print(f"  static:           {WEB_DIR}")
    if not (WEB_DIR / "index.html").exists():
        print("                    (index.html not built yet — API only)")
    print(f"  exposure surface: {surface}")
    if server.resolve_enabled:
        try:
            n_resolvable = resolvemod.count_resolvable_rows(server.db_path)
        except Exception:  # noqa: BLE001 — the startup line must never kill the server
            n_resolvable = -1
        print(f"  resolver:         on — {n_resolvable} resolvable rows in db "
              f"(posters cached: {resolvemod.cached_poster_count()}, "
              f"live cached: {resolvemod.cached_live_count()})")
    else:
        print("  resolver:         off (--no-resolve; live/poster/still/resolve routes disabled)")
    print("  api:              /api/{stats,overview,facets,cameras,camera/<id>,prefs,"
          "poster/<id>,still/<id>,resolve/<id>,live/<id>/index.m3u8,live/<id>/seg/<name>}")
    print("  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nviewer: stopped")
    finally:
        server.server_close()
    return 0


def _add_viewer_arguments(parser) -> None:
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port to bind on 127.0.0.1 (default: {DEFAULT_PORT})")
    parser.add_argument("--no-resolve", action="store_true",
                        help="disable live-stream resolution + poster/still/resolve "
                             "relay (those routes 404)")


_cmd_viewer.add_arguments = _add_viewer_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd viewer``."""
    return {"viewer": ("local web viewer: static UI + JSON API (prefs read-write; registry read-only)",
                       _cmd_viewer)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.viewer")
    _add_viewer_arguments(parser)
    args = parser.parse_args(argv)
    return _cmd_viewer(args)


if __name__ == "__main__":
    raise SystemExit(main())

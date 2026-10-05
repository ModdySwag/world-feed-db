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
    GET  /api/camera/<camera_id> -> one row, all fields incl. ``meta``;
                                    404 when missing
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

def _display_props(row: sqlite3.Row) -> dict:
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
    elif provenance == "exposure_aggregator":
        props["warning"] = EXPOSURE_WARNING
    return props


def _feature(row: sqlite3.Row) -> dict:
    lon, lat = row["lon"], row["lat"]
    geometry = ({"type": "Point", "coordinates": [lon, lat]}
                if lon is not None and lat is not None else None)
    return {"type": "Feature", "geometry": geometry,
            "properties": _display_props(row)}


def _detail_payload(row) -> dict:
    """Full detail dict for one row — same url/display_policy rules as features."""
    payload = row.as_dict()
    displayable = row.provenance in FULL_DISPLAY_PROVENANCE
    payload["display_policy"] = "full" if displayable else "metadata_only"
    if not displayable:
        payload.pop("url", None)
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
                 prefs_path=None):
        self.db_path = pathlib.Path(db_path)
        self.quiet = quiet
        self.prefs = prefsmod.PrefsStore(prefs_path)
        super().__init__(address, handler_cls)


class ViewerHandler(SimpleHTTPRequestHandler):
    """/api/* -> JSON API; everything else -> static files from wfd/web/."""

    server_version = "wfd-viewer/0.2"
    protocol_version = "HTTP/1.1"

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
        if path == "/api/prefs":
            return self._handle_prefs_get()
        if path.startswith("/api/camera/"):
            return self._handle_camera(urllib.parse.unquote(path[len("/api/camera/"):]))
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
                features = [_feature(r) for r in rows]
        finally:
            conn.close()
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
        self._send_json(200, _detail_payload(row))

    def _handle_prefs_get(self):
        return self._send_json(200, self._prefs_payload())

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
                web_dir=None, quiet: bool = False, prefs_path=None) -> ViewerServer:
    """Build (not start) a viewer server. ``port=0`` -> ephemeral (tests)."""
    db_path = pathlib.Path(db_path) if db_path else dbmod.DEFAULT_DB
    web_dir = pathlib.Path(web_dir) if web_dir else WEB_DIR
    handler = functools.partial(ViewerHandler, directory=str(web_dir))
    return ViewerServer((host, port), handler, db_path, quiet=quiet,
                        prefs_path=prefs_path)


def _cmd_viewer(args) -> int:
    port = getattr(args, "port", DEFAULT_PORT)
    try:
        server = make_server(port=port)
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
    print("  api:              /api/{stats,overview,facets,cameras,camera/<id>,prefs}")
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

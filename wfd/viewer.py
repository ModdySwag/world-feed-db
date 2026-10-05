"""wfd.viewer — local, stdlib-only viewer backend (Q4: shared backend + local web UI).

Serves the static frontend under ``wfd/web/`` and a small JSON API over the
registry database (``data/worldfeed.db``). Binds 127.0.0.1 only — a local
surface, never a public one; CORS is deliberately absent.

Run:
    py -3.11 -m wfd viewer [--port 8773]

API (the wfd/web/ frontend is built to exactly this contract):
    GET /api/stats               -> {total, by_provenance, by_status, by_family,
                                     exposure_enabled, generated_at}
    GET /api/cameras             -> GeoJSON FeatureCollection, points only
                                    (rows with lat+lon)
    GET /api/camera/<camera_id>  -> one row, all fields incl. ``meta``;
                                    404 when missing

    /api/cameras params:
        provenance=public|directory|exposure|all   (default all; "public" =
            the displayable non-exposure set: public_by_design + aggregator_directory)
        status=<csv>                     family=<csv>
        q=<FTS text>                     (resolved via wfd.db.search ids)
        bbox=minLon,minLat,maxLon,maxLat
        limit (default 2000, max 5000)   offset
    Feature properties: camera_id, name, city, country, source_family,
        provenance, status, protocol, last_verified, snapshot_date, tags,
        display_policy; ``url`` for public_by_design + aggregator_directory rows only.

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
this process never writes to it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import pathlib
import sqlite3
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import db as dbmod
from . import profile

WEB_DIR = pathlib.Path(__file__).resolve().parent / "web"
DEFAULT_PORT = 8773

DEFAULT_LIMIT = 2000
MAX_LIMIT = 5000
_FTS_CAP = 5000          # q= resolves through FTS; hits beyond one page are moot
_IN_CHUNK = 500          # bound the camera_id IN (...) placeholder count

EXPOSURE_WARNING = (
    "Unsecured camera listed by a public aggregator - may capture private "
    "scenes; location approximate; unverified."
)

# Provenance classes displayed in full (url included). Third-party directories of
# public feeds belong here (owner decision 2026-10-06); exposure stays metadata-only.
FULL_DISPLAY_PROVENANCE = ("public_by_design", "aggregator_directory")


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
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": _display_props(row),
    }


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

    def __init__(self, address, handler_cls, db_path, quiet: bool = False):
        self.db_path = pathlib.Path(db_path)
        self.quiet = quiet
        super().__init__(address, handler_cls)


class ViewerHandler(SimpleHTTPRequestHandler):
    """/api/* -> JSON API; everything else -> static files from wfd/web/."""

    server_version = "wfd-viewer/0.1"
    protocol_version = "HTTP/1.1"

    # -- routing ------------------------------------------------------------

    def do_GET(self):                      # noqa: N802 (stdlib naming)
        self._route()

    def do_HEAD(self):                     # noqa: N802
        self._route()

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
        if path == "/api/cameras":
            return self._handle_cameras(query)
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

    def _handle_cameras(self, query: str):
        params = urllib.parse.parse_qs(query, keep_blank_values=False)

        def one(name):
            return (params.get(name) or [None])[0]

        provenance = (one("provenance") or "all").strip().lower() or "all"
        if provenance not in ("public", "directory", "exposure", "all"):
            return self._send_json(400, {"error": "provenance must be one of public|directory|exposure|all",
                                         "provenance": provenance})
        q = (one("q") or "").strip()
        statuses = _csv_params(one("status"))
        families = _csv_params(one("family"))
        bbox_raw = one("bbox")
        bbox = None
        if bbox_raw:
            bbox = _parse_bbox(bbox_raw)
            if bbox is None:
                return self._send_json(400, {"error": "bbox must be minLon,minLat,maxLon,maxLat",
                                             "bbox": bbox_raw})
        limit = _int_param(one("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int_param(one("offset"), 0, 0, 1_000_000_000)

        conn = self._open_db()
        if conn is None:
            return self._db_missing()
        try:
            ids = None                      # None -> unfiltered; [] -> q matched nothing
            if q:
                ids = [h["camera_id"] for h in dbmod.search(conn, q, limit=_FTS_CAP)]
            if ids == []:
                rows = []
            else:
                where = ["lat IS NOT NULL", "lon IS NOT NULL"]
                args = []
                if not self._exposure_enabled():
                    # surface off: exposure rows are not part of the served set,
                    # even when provenance=exposure is requested explicitly
                    where.append("provenance != 'exposure_aggregator'")
                if provenance == "public":
                    # the displayable non-exposure set (directories included)
                    where.append("provenance IN ('public_by_design','aggregator_directory')")
                elif provenance == "directory":
                    where.append("provenance = 'aggregator_directory'")
                elif provenance == "exposure":
                    where.append("provenance = 'exposure_aggregator'")
                if statuses:
                    where.append("status IN (%s)" % ", ".join("?" * len(statuses)))
                    args.extend(statuses)
                if families:
                    where.append("source_family IN (%s)" % ", ".join("?" * len(families)))
                    args.extend(families)
                if bbox:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    where.append("lon BETWEEN ? AND ?")
                    where.append("lat BETWEEN ? AND ?")
                    args.extend([min_lon, max_lon, min_lat, max_lat])
                clause = " AND ".join(where)

                if ids is None:
                    rows = conn.execute(
                        f"SELECT * FROM cameras WHERE {clause} "
                        f"ORDER BY camera_id LIMIT ? OFFSET ?",
                        (*args, limit, offset),
                    ).fetchall()
                else:
                    rows = []
                    for chunk in _chunks(ids, _IN_CHUNK):
                        marks = ", ".join("?" * len(chunk))
                        rows.extend(conn.execute(
                            f"SELECT * FROM cameras WHERE camera_id IN ({marks}) AND {clause}",
                            (*chunk, *args),
                        ).fetchall())
                    rows.sort(key=lambda r: r["camera_id"])
                    rows = rows[offset:offset + limit]
        finally:
            conn.close()
        self._send_json(200, {"type": "FeatureCollection",
                              "features": [_feature(r) for r in rows]})

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


# ---------------------------------------------------------------------------
# server factory + CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, db_path=None,
                web_dir=None, quiet: bool = False) -> ViewerServer:
    """Build (not start) a viewer server. ``port=0`` -> ephemeral (tests)."""
    db_path = pathlib.Path(db_path) if db_path else dbmod.DEFAULT_DB
    web_dir = pathlib.Path(web_dir) if web_dir else WEB_DIR
    handler = functools.partial(ViewerHandler, directory=str(web_dir))
    return ViewerServer((host, port), handler, db_path, quiet=quiet)


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
    print(f"  static:           {WEB_DIR}")
    if not (WEB_DIR / "index.html").exists():
        print("                    (index.html not built yet — API only)")
    print(f"  exposure surface: {surface}")
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
    return {"viewer": ("local web viewer: static UI + read-only JSON API", _cmd_viewer)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.viewer")
    _add_viewer_arguments(parser)
    args = parser.parse_args(argv)
    return _cmd_viewer(args)


if __name__ == "__main__":
    raise SystemExit(main())

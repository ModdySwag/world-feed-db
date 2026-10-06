"""wfd.geo — offline city geocoding for registry rows (GeoNames cities1000).

The registry's ``city`` column is source-provided and mostly empty outside a
few families. This module enriches rows that carry coordinates but no usable
city by matching each row to the nearest populated place in an offline
GeoNames dump (``data/geo/cities1000.txt``) within a distance gate. Results are
written to dedicated ``city_geo*`` columns (never ``city``): a re-ingest cannot
clobber them, and every geocoded value carries its dataset source, distance in
km, and timestamp.

Ops (also registered on the ``wfd`` CLI):
    py -3.11 -m wfd geo fetch [--refresh]      # download + manifest (sha256, dump date)
    py -3.11 -m wfd geo city [--family F] [--limit N] [--refresh] [--dry-run] [--gate-km K]

Dataset: GeoNames cities1000 (CC BY 4.0) —
<https://download.geonames.org/export/dump/>. Evidence: one JSONL line per row
in ``data/geo/city-<ts>.jsonl``. The pass is resumable: rows already carrying a
``city_geo_src`` are skipped unless ``--refresh``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import math
import pathlib
import time
import urllib.request
import zipfile

from . import db as dbmod
from . import profile
from .schema import effective_city

DATA_DIR = profile.REPO_ROOT / "data" / "geo"
CITIES_FILE = DATA_DIR / "cities1000.txt"
MANIFEST_FILE = DATA_DIR / "manifest.json"
CITIES_URL = "https://download.geonames.org/export/dump/cities1000.zip"

DEFAULT_GATE_KM = 25.0
SRC_MATCH = "geonames:cities1000"
SRC_NONE = "geonames:cities1000:none"

# Sub-city sections (GeoNames PPLX: rioni, dong, "Financial District"...) are
# not cities for label purposes — they are a FALLBACK only: preferred over
# nothing, never over a real city within the gate (so cams aggregate under the
# parent city name; some whole towns — e.g. Wagga Wagga — are PPLX-coded).
_SECTION_CODE = "PPLX"
# Metropolitan preference: a much larger city within a short additional
# distance outranks a micro-locality (Rome over the Trevi rione, Seoul over
# Yongsan-dong). All three conditions must hold.
METRO_POP_FLOOR = 250_000
METRO_RATIO = 8
METRO_WINDOW_KM = 5.0

# GeoNames cities1000.txt column indexes (tab-separated, 19 fields).
_C_NAME, _C_LAT, _C_LON, _C_CC, _C_POP = 1, 4, 5, 8, 14

_EARTH_R_KM = 6371.0088


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def manifest_info() -> dict:
    try:
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _print_dataset(info: dict) -> None:
    if not info:
        if CITIES_FILE.exists():
            print(f"dataset: {CITIES_FILE} (no manifest — re-fetch for provenance)")
        return
    date = (info.get("http_last_modified") or "")[:16] or "unknown"
    sha = (info.get("txt_sha256") or "")[:12]
    print(f"dataset: GeoNames cities1000 · dump {date} · sha256 {sha} · "
          f"fetched {info.get('fetched_at', '?')}")


def fetch_cities(refresh: bool = False, *, quiet: bool = False) -> dict:
    """Download + extract cities1000.txt and write the provenance manifest."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CITIES_FILE.exists() and not refresh:
        info = manifest_info()
        if not quiet:
            print(f"cities1000 already present: {CITIES_FILE}")
            _print_dataset(info)
        return info
    conf = profile.settings()
    req = urllib.request.Request(
        CITIES_URL, headers={"User-Agent": conf.get("user_agent", "world-feed-db/0.1")})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
        last_modified = resp.headers.get("Last-Modified", "")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        if "cities1000.txt" not in zf.namelist():
            raise RuntimeError(f"cities1000.txt not found inside {CITIES_URL}")
        text = zf.read("cities1000.txt")
    CITIES_FILE.write_bytes(text)
    info = {
        "source": "GeoNames cities1000 (CC BY 4.0)",
        "url": CITIES_URL,
        "zip_bytes": len(raw),
        "zip_sha256": hashlib.sha256(raw).hexdigest(),
        "txt_bytes": len(text),
        "txt_sha256": hashlib.sha256(text).hexdigest(),
        "http_last_modified": last_modified,
        "fetched_at": _now(),
    }
    MANIFEST_FILE.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(f"fetched: {CITIES_URL}")
        _print_dataset(info)
    return info


def load_cities(path=None):
    """Parse the dump -> ``(places, grid)``.

    ``places``: list of ``(name, lat, lon, cc, pop)``; ``grid``: 1-degree-cell
    index ``{(floor(lat), floor(lon)): [places-index, ...]}``.
    """
    path = pathlib.Path(path or CITIES_FILE)
    places = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15:
                continue
            is_section = (parts[7] or "") == _SECTION_CODE
            try:
                lat = float(parts[_C_LAT])
                lon = float(parts[_C_LON])
            except ValueError:
                continue
            name = (parts[_C_NAME] or "").strip()
            if not name:
                continue
            try:
                pop = int(parts[_C_POP] or "0")
            except ValueError:
                pop = 0
            places.append((name, lat, lon, (parts[_C_CC] or "").strip(), pop, is_section))
    grid = {}
    for idx, (_n, la, lo, _cc, _p, _s) in enumerate(places):
        grid.setdefault((int(math.floor(la)), int(math.floor(lo))), []).append(idx)
    return places, grid


def _haversine(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * _EARTH_R_KM * math.asin(math.sqrt(a))


def nearest_place(lat: float, lon: float, places, grid, gate_km: float):
    """Nearest populated place within ``gate_km`` -> ``(name, km, cc)`` or None.

    Selection, in order: (1) real cities beat PPLX sub-city sections (sections
    are a fallback only — used when nothing else is within the gate);
    (2) nearest wins (ties -> larger population); (3) one override — a place of
    ``METRO_RATIO`` x the population (and >= ``METRO_POP_FLOOR`` people) within
    ``METRO_WINDOW_KM`` of the nearest candidate's distance outranks the
    micro-locality, so cams in metro areas aggregate under the metro name.
    The longitude cell window wraps across the antimeridian.
    """
    dlat = gate_km / 111.32
    coslat = max(math.cos(math.radians(lat)), 0.01)
    dlon = min(gate_km / (111.32 * coslat), 180.0)
    candidates = []      # (km, pop, name, cc, is_section)
    for cla in range(int(math.floor(lat - dlat)), int(math.floor(lat + dlat)) + 1):
        for clo in range(int(math.floor(lon - dlon)), int(math.floor(lon + dlon)) + 1):
            key = ((clo + 180) % 360) - 180
            for idx in grid.get((cla, key), ()):
                name, pla, plo, cc, pop, is_sec = places[idx]
                km = _haversine(lat, lon, pla, plo)
                if km <= gate_km:
                    candidates.append((km, pop, name, cc, is_sec))
    if not candidates:
        return None
    pool = [c for c in candidates if not c[4]] or candidates
    best = min(pool, key=lambda c: (c[0], -c[1]))
    metros = [c for c in pool
              if (c[1] >= METRO_POP_FLOOR and c[1] > best[1]
                  and c[1] >= METRO_RATIO * max(best[1], 1)
                  and c[0] <= best[0] + METRO_WINDOW_KM)]
    if metros:
        best = max(metros, key=lambda c: (c[1], -c[0]))
    return (best[2], round(best[0], 2), best[3])


def geocode(conn, *, family=None, gate_km=DEFAULT_GATE_KM, refresh=False,
            limit=None, dry_run=False, cities_path=None, evidence_dir=None,
            progress=print, progress_every=500):
    """Run the enrichment pass over geo-valid rows lacking a usable city.

    Returns a summary dict. Resumable: rows already carrying ``city_geo_src``
    are skipped unless ``refresh``. With ``dry_run`` nothing is written (no
    evidence file either — a dry run only reports counts).
    """
    dbmod.ensure_city_columns(conn)
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.commit()
    if not CITIES_FILE.exists() and not cities_path:
        raise FileNotFoundError(
            f"dataset missing: {CITIES_FILE} — run `py -3.11 -m wfd geo fetch` first")
    places, grid = load_cities(cities_path)

    where = ["lat IS NOT NULL", "lon IS NOT NULL", "NOT (lat = 0 AND lon = 0)"]
    args = []
    if family:
        where.append("source_family = ?")
        args.append(family)
    rows = conn.execute(
        "SELECT camera_id, source_family, lat, lon, city, city_geo_src "
        "FROM cameras WHERE " + " AND ".join(where), args).fetchall()

    targets, skipped_have_city, skipped_done = [], 0, 0
    for r in rows:
        if not effective_city(r["city"], ""):
            if not refresh and (r["city_geo_src"] or ""):
                skipped_done += 1
            else:
                targets.append(r)
        else:
            skipped_have_city += 1
    if limit is not None:
        targets = targets[: int(limit)]

    evidence_path = None
    ev = None
    if not dry_run:
        if evidence_dir is None:
            evidence_dir = DATA_DIR
        evidence_dir = pathlib.Path(evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / f"city-{_now_stamp()}.jsonl"
        ev = open(evidence_path, "a", encoding="utf-8")

    started = time.time()
    at = _now()
    n_ok = n_none = 0
    by_family = {}
    try:
        for i, r in enumerate(targets, 1):
            hit = nearest_place(r["lat"], r["lon"], places, grid, gate_km)
            if hit:
                name, km, cc = hit
                n_ok += 1
                by_family[r["source_family"]] = by_family.get(r["source_family"], 0) + 1
            else:
                name, km, cc = "", None, ""
                n_none += 1
            if not dry_run:
                conn.execute(
                    "UPDATE cameras SET city_geo = ?, city_geo_km = ?, "
                    "city_geo_src = ?, city_geo_at = ? WHERE camera_id = ?",
                    (name, km, SRC_MATCH if hit else SRC_NONE, at, r["camera_id"]))
                if hit:
                    rid = conn.execute(
                        "SELECT rowid FROM cameras WHERE camera_id = ?",
                        (r["camera_id"],)).fetchone()[0]
                    dbmod.refresh_fts(conn, rid)
                if i % 200 == 0:
                    conn.commit()
            if ev is not None:
                ev.write(json.dumps({
                    "camera_id": r["camera_id"], "family": r["source_family"],
                    "lat": r["lat"], "lon": r["lon"], "city_before": r["city"],
                    "place": name or None, "km": km, "cc": cc or None, "at": at,
                }, ensure_ascii=False) + "\n")
                if i % 200 == 0:
                    ev.flush()
            if progress and progress_every and i % progress_every == 0:
                progress(f"  [{i}/{len(targets)}] matched={n_ok} none={n_none} "
                         f"({time.time() - started:.0f}s)")
        if not dry_run:
            conn.commit()
    finally:
        if ev is not None:
            ev.close()

    return {
        "dataset": "cities1000", "gate_km": gate_km, "dry_run": bool(dry_run),
        "scanned": len(rows), "targets": len(targets),
        "matched": n_ok, "none": n_none,
        "skipped_have_city": skipped_have_city, "skipped_done": skipped_done,
        "by_family": by_family, "seconds": round(time.time() - started, 1),
        "evidence": str(evidence_path) if evidence_path else "",
    }


def coverage(conn) -> dict:
    """``{total, with_city, by_family}`` over geo-valid rows (display-effective city)."""
    dbmod.ensure_city_columns(conn)
    total = with_city = 0
    by_family = {}
    for r in conn.execute(
            "SELECT source_family, city, city_geo FROM cameras "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL AND NOT (lat = 0 AND lon = 0)"):
        total += 1
        if effective_city(r["city"], r["city_geo"]):
            with_city += 1
            by_family[r["source_family"]] = by_family.get(r["source_family"], 0) + 1
    return {"total": total, "with_city": with_city, "by_family": by_family}


# ---------------------------------------------------------------------------
# CLI (registered as ``wfd geo`` — see wfd.cli)
# ---------------------------------------------------------------------------

def _cmd_geo(args) -> int:
    action = getattr(args, "geo_action", None)
    if action == "fetch":
        fetch_cities(refresh=bool(getattr(args, "refresh", False)))
        return 0
    if action != "city":
        print("usage: wfd geo fetch [--refresh] | wfd geo city [options]")
        return 2
    if not CITIES_FILE.exists():
        print(f"dataset missing: {CITIES_FILE}")
        print("run first:  py -3.11 -m wfd geo fetch")
        return 2
    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        before = coverage(conn)
        _print_dataset(manifest_info())
        print(f"gate: {args.gate_km:g} km · family: {args.family or 'all'}"
              + (" · refresh" if args.refresh else "")
              + (" · DRY RUN (no writes)" if args.dry_run else ""))
        s = geocode(conn, family=args.family, gate_km=args.gate_km,
                    refresh=bool(args.refresh), limit=args.limit,
                    dry_run=bool(args.dry_run))
        after = coverage(conn)
    finally:
        conn.close()
    print(f"scanned={s['scanned']} targets={s['targets']} matched={s['matched']} "
          f"no-place-within-gate={s['none']} skipped(have-city)={s['skipped_have_city']} "
          f"skipped(done)={s['skipped_done']} in {s['seconds']}s")
    if s["evidence"]:
        print(f"evidence: {s['evidence']}")

    def pct(n, d):
        return f"{100.0 * n / d:.1f}%" if d else "-"

    print(f"city coverage (geo rows): {before['with_city']}/{before['total']} "
          f"({pct(before['with_city'], before['total'])}) -> "
          f"{after['with_city']}/{after['total']} "
          f"({pct(after['with_city'], after['total'])})")
    fams = sorted(set(before["by_family"]) | set(after["by_family"]))
    if any(before["by_family"].get(f) != after["by_family"].get(f) for f in fams):
        print("  by family (before -> after):")
        for f in fams:
            b = before["by_family"].get(f, 0)
            a = after["by_family"].get(f, 0)
            if b or a:
                print(f"    {f:<24} {b:>6} -> {a:>6}")
    return 0


def _add_geo_arguments(parser) -> None:
    sub = parser.add_subparsers(dest="geo_action")
    p = sub.add_parser("fetch", help="download the GeoNames cities1000 dump into data/geo/")
    p.add_argument("--refresh", action="store_true", help="re-download even when present")
    p = sub.add_parser("city", help="fill city_geo for geocoded rows lacking a city (resumable)")
    p.add_argument("--family", default=None, help="restrict to one source_family")
    p.add_argument("--limit", type=int, default=None, help="cap rows processed this run")
    p.add_argument("--refresh", action="store_true",
                   help="recompute rows that already carry a city_geo_src")
    p.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    p.add_argument("--gate-km", type=float, default=DEFAULT_GATE_KM,
                   help=f"max distance to the nearest place (default {DEFAULT_GATE_KM:g} km)")


_cmd_geo.add_arguments = _add_geo_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd geo``."""
    return {"geo": ("city geocoding: fetch | city", _cmd_geo)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.geo")
    _add_geo_arguments(parser)
    args = parser.parse_args(argv)
    return _cmd_geo(args)


if __name__ == "__main__":
    raise SystemExit(main())

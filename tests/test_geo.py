"""Geo tests — plain runner. Run: py -3.11 tests/test_geo.py

Covers: cities1000 parsing + nearest lookup, gate boundary, the geocode pass
(fill / junk / none / skip), resume + refresh, the schema migration, the
effective-city FTS sync, and the viewer display/sort coalesce.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import db, geo
from wfd.schema import CameraRow, effective_city, stable_id

CANB = ("Canberra", -35.28346, 149.12807)
SYD = ("Sydney", -33.86785, 151.20732)
MEL = ("Melbourne", -37.8136, 144.9631)
QT = ("Queenstown", -45.03116, 168.66271)
INT = ("Interlaken", 46.68353, 7.85756)


def _city_line(gid, name, lat, lon, cc, pop):
    return "\t".join([str(gid), name, name, "", f"{lat}", f"{lon}", "P", "PPL",
                      cc, "", "01", "", "", "", str(pop), "", "0", "Test/Zone",
                      "2025-01-01"])


def _write_cities(td) -> pathlib.Path:
    p = pathlib.Path(td) / "cities1000.txt"
    lines = [
        _city_line(1, *CANB, "AU", 367752),
        _city_line(2, *SYD, "AU", 4627345),
        _city_line(3, *MEL, "AU", 4200000),
        _city_line(4, *QT, "NZ", 10187),
        _city_line(5, *INT, "CH", 5335),
    ]
    # a PPLX sub-city section next to Melbourne (must lose to the real city)
    sec = _city_line(6, "Melbourne Section", MEL[1] + 0.001, MEL[2] + 0.001, "AU", 4000).split("\t")
    sec[7] = "PPLX"
    lines.append("\t".join(sec))
    # a PPLX-coded lone town (must be USED when nothing else is near —
    # GeoNames codes some whole towns, e.g. Wagga Wagga, as PPLX)
    sec2 = _city_line(7, "Solo Section", -20.5, 130.5, "AU", 2000).split("\t")
    sec2[7] = "PPLX"
    lines.append("\t".join(sec2))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _lat_lon_km_away(city, km):
    """A point ~km km due east of a city (small-scale flat approximation)."""
    _name, lat, lon = city
    dlon = km / (111.32 * math.cos(math.radians(lat)))
    return lat, lon + dlon


def _mk_db(td):
    conn = db.connect(pathlib.Path(td) / "t.db")
    db.init_db(conn)
    return conn


def _rows():
    near2 = _lat_lon_km_away(CANB, 2)
    near20 = _lat_lon_km_away(CANB, 20)
    far30 = _lat_lon_km_away(CANB, 30)
    return {
        "A": CameraRow(url="http://x.test/a", source_family="fam-a",
                       provenance="public_by_design", name="A",
                       lat=near2[0], lon=near2[1]),
        "B": CameraRow(url="http://x.test/b", source_family="fam-a",
                       provenance="public_by_design", name="B",
                       lat=near20[0], lon=near20[1]),
        "C": CameraRow(url="http://x.test/c", source_family="fam-b",
                       provenance="public_by_design", name="C",
                       lat=far30[0], lon=far30[1]),
        "D": CameraRow(url="http://x.test/d", source_family="fam-b",
                       provenance="public_by_design", name="D", city="-",
                       lat=SYD[1] + 0.01, lon=SYD[2] + 0.01),
        "E": CameraRow(url="http://x.test/e", source_family="fam-c",
                       provenance="public_by_design", name="E", city="Melbourne",
                       lat=SYD[1], lon=SYD[2]),
        "F": CameraRow(url="http://x.test/f", source_family="fam-c",
                       provenance="public_by_design", name="F"),
    }


def test_load_and_nearest():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        places, grid = geo.load_cities(_write_cities(td))
        assert len(places) == 7, len(places)      # 5 cities + 2 PPLX sections
        hit = geo.nearest_place(CANB[1], CANB[2], places, grid, 25.0)
        assert hit and hit[0] == "Canberra" and hit[1] <= 0.1, hit
        assert geo.nearest_place(0.0, -140.0, places, grid, 25.0) is None
        qlat, qlon = _lat_lon_km_away(QT, 2)
        hit = geo.nearest_place(qlat, qlon, places, grid, 25.0)
        assert hit and hit[0] == "Queenstown", hit
        ilat, ilon = _lat_lon_km_away(INT, 3)
        hit = geo.nearest_place(ilat, ilon, places, grid, 25.0)
        assert hit and hit[0] == "Interlaken", hit


def test_pplx_section_preference_and_fallback():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        places, grid = geo.load_cities(_write_cities(td))
        # a real city beats a neighbouring PPLX section
        hit = geo.nearest_place(MEL[1] + 0.001, MEL[2] + 0.001, places, grid, 25.0)
        assert hit and hit[0] == "Melbourne", hit
        # where nothing but a (PPLX-coded) town is near, it is used
        hit = geo.nearest_place(-20.5 + 0.002, 130.5 + 0.002, places, grid, 25.0)
        assert hit and hit[0] == "Solo Section", hit


def test_metro_preference():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        p = pathlib.Path(td) / "cities1000.txt"
        lat = -35.30
        km = 4.5 / (111.32 * math.cos(math.radians(lat)))
        p.write_text("\n".join([
            _city_line(1, "Microtown", lat, 149.30, "AZ", 4000),
            _city_line(2, "Bigcity", lat, 149.30 + km, "AZ", 900000),
            _city_line(3, "Midtown", lat, 150.30, "AZ", 100000),
            _city_line(4, "Megatown", lat, 150.30 + km, "AZ", 600000),
        ]) + "\n", encoding="utf-8")
        places, grid = geo.load_cities(p)
        hit = geo.nearest_place(lat, 149.30, places, grid, 25.0)
        assert hit and hit[0] == "Bigcity", hit              # 900k within +5 km beats the 4k micro-locality
        hit = geo.nearest_place(lat, 150.30, places, grid, 25.0)
        assert hit and hit[0] == "Midtown", hit              # 6x is below METRO_RATIO -> nearest stays


def test_gate_boundary():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        places, grid = geo.load_cities(_write_cities(td))
        lat24, lon24 = _lat_lon_km_away(CANB, 24)
        lat26, lon26 = _lat_lon_km_away(CANB, 26)
        hit = geo.nearest_place(lat24, lon24, places, grid, 25.0)
        assert hit and hit[0] == "Canberra" and 23.0 < hit[1] < 25.0, hit
        assert geo.nearest_place(lat26, lon26, places, grid, 25.0) is None
        assert geo.nearest_place(lat24, lon24, places, grid, 10.0) is None


def test_geocode_pass():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_db(td)
        db.upsert_many(conn, list(_rows().values()))
        s = geo.geocode(conn, cities_path=_write_cities(td), evidence_dir=td)
        assert s["scanned"] == 5, s
        assert s["targets"] == 4, s
        assert s["matched"] == 3 and s["none"] == 1, s
        assert s["skipped_have_city"] == 1, s
        a = conn.execute(
            "SELECT city_geo, city_geo_km, city_geo_src FROM cameras WHERE camera_id=?",
            (stable_id("fam-a", "http://x.test/a"),)).fetchone()
        assert a["city_geo"] == "Canberra" and a["city_geo_src"] == geo.SRC_MATCH, dict(a)
        assert a["city_geo_km"] is not None and 0 < a["city_geo_km"] < 5, dict(a)
        d = conn.execute(
            "SELECT city_geo FROM cameras WHERE camera_id=?",
            (stable_id("fam-b", "http://x.test/d"),)).fetchone()
        assert d["city_geo"] == "Sydney", dict(d)
        c = conn.execute(
            "SELECT city_geo, city_geo_src, city_geo_km FROM cameras WHERE camera_id=?",
            (stable_id("fam-b", "http://x.test/c"),)).fetchone()
        assert (c["city_geo"] == "" and c["city_geo_src"] == geo.SRC_NONE
                and c["city_geo_km"] is None), dict(c)
        e = conn.execute(
            "SELECT city_geo, city_geo_src FROM cameras WHERE camera_id=?",
            (stable_id("fam-c", "http://x.test/e"),)).fetchone()
        assert e["city_geo"] == "" and e["city_geo_src"] == "", dict(e)  # untouched
        ev = list(pathlib.Path(td).glob("city-*.jsonl"))
        assert len(ev) == 1, ev
        lines = [json.loads(l) for l in ev[0].read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 4, len(lines)
        assert effective_city("-", "Sydney") == "Sydney"
        conn.close()


def test_resume_and_refresh():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_db(td)
        db.upsert_many(conn, list(_rows().values()))
        cities = _write_cities(td)
        geo.geocode(conn, cities_path=cities, evidence_dir=td)
        s2 = geo.geocode(conn, cities_path=cities, evidence_dir=td)
        assert s2["targets"] == 0 and s2["skipped_done"] == 4, s2
        s3 = geo.geocode(conn, cities_path=cities, evidence_dir=td, refresh=True)
        assert s3["targets"] == 4 and s3["matched"] == 3, s3
        conn.close()


def test_migration_and_old_db_fts():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = db.connect(pathlib.Path(td) / "old.db")   # production conn (Row factory)
        conn.executescript(db._DDL)          # pre-geocode schema
        cols = {r[1] for r in conn.execute("PRAGMA table_info(cameras)")}
        assert "city_geo" not in cols
        conn.execute(
            "INSERT INTO cameras (camera_id, url, source_family, provenance, name, city) "
            "VALUES ('c1', 'http://x', 'f', 'public_by_design', 'One', 'Canberra')")
        db.refresh_fts(conn, 1)              # old-DB fallback path must not raise
        r = conn.execute("SELECT city FROM cameras_fts WHERE camera_id='c1'").fetchone()
        assert r and r[0] == "Canberra", r
        assert db.ensure_city_columns(conn) is True
        cols = {r[1] for r in conn.execute("PRAGMA table_info(cameras)")}
        assert {"city_geo", "city_geo_km", "city_geo_src", "city_geo_at"} <= cols
        assert db.ensure_city_columns(conn) is False
        conn.close()


def test_fts_effective_and_reload():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_db(td)
        rows = _rows()
        db.upsert_many(conn, list(rows.values()))
        geo.geocode(conn, cities_path=_write_cities(td), evidence_dir=td)
        hit = {h["camera_id"] for h in db.search(conn, "Canberra")}
        assert stable_id("fam-a", "http://x.test/a") in hit, hit
        # a re-load (upsert again) must not wipe the effective city out of FTS
        db.upsert_many(conn, list(rows.values()))
        hit2 = {h["camera_id"] for h in db.search(conn, "Canberra")}
        assert stable_id("fam-a", "http://x.test/a") in hit2, hit2
        conn.close()


def test_viewer_display_and_sort():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        conn = _mk_db(td)
        db.upsert_many(conn, list(_rows().values()))
        geo.geocode(conn, cities_path=_write_cities(td), evidence_dir=td)
        import wfd.viewer as viewer

        d_id = stable_id("fam-b", "http://x.test/d")
        row = conn.execute("SELECT * FROM cameras WHERE camera_id=?", (d_id,)).fetchone()
        assert viewer._eff_city(row) == "Sydney", viewer._eff_city(row)
        props = viewer._display_props(row, False)
        assert props["city"] == "Sydney", props["city"]
        a_id = stable_id("fam-a", "http://x.test/a")
        row_a = conn.execute("SELECT * FROM cameras WHERE camera_id=?", (a_id,)).fetchone()
        assert viewer._eff_city(row_a) == "Canberra"
        ordered = viewer._fetch_rows(conn, "1=1", [], candidates=None,
                                     sort="city", order="asc", limit=50, offset=0)
        eff = [viewer._eff_city(r) for r in ordered]
        assert eff[:2] == ["Canberra", "Canberra"], eff
        assert set(eff[2:4]) == {"Melbourne", "Sydney"}, eff
        assert eff[4:] == ["", ""], eff       # C and F sort last (no city)
        conn.close()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

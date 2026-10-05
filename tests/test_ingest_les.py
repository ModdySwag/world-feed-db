"""L-E-S corpus ingester tests — plain-python runner (no pytest on this host).

Run:    py -3.11 tests/test_ingest_les.py    -> prints PASS lines; exit 0 = all good.

Reads the real committed corpus ``research/seed-tabs/data/LES-streams.geojson``.
Test functions are named test_* so they also work under pytest if installed.
"""
from __future__ import annotations

import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest import les
from wfd.schema import stable_id

_RESULT = None


def result():
    """Parse the corpus once for the whole test run."""
    global _RESULT
    if _RESULT is None:
        _RESULT = les.ingest()
    return _RESULT


def test_features_count():
    res = result()
    assert res.stats["features"] == 5997, res.stats["features"]
    # 3 balticlivecam paths differ only by token value -> collapse after redaction
    assert res.stats["duplicates_dropped"] == 3
    assert res.stats["skipped_no_url"] == 0
    assert len(res.rows) == 5994, len(res.rows)
    assert res.stats["rows"] == 5994


def test_never_claims_liveness():
    rows = result().rows
    assert set(r.status for r in rows) == {"unknown"}
    assert set(r.provenance for r in rows) == {"public_by_design"}
    assert set(r.source_family for r in rows) == {"les"}


def test_dedupe_by_url():
    # the finalized corpus is deduped by stored (redacted) url: 5,997 features
    # -> 5,994 rows (3 balticlivecam urls collapse to identical redacted urls)
    rows = result().rows
    urls = [r.url for r in rows]
    assert len(urls) == len(set(urls)) == 5994
    assert result().stats["duplicates_dropped"] == 3

    # dedupe_rows keeps the first row and counts the drop
    a = les.CameraRow(url="https://example.com/a", source_family="les")
    b = les.CameraRow(url="https://example.com/a", source_family="les")
    c = les.CameraRow(url="https://example.com/b", source_family="les")
    unique, dropped = les.dedupe_rows([a, b, c])
    assert len(unique) == 2 and dropped == 1 and unique[0] is a, (len(unique), dropped)

    # parse_features applies the same rule at parse time
    feats = [
        {"properties": {"url": "https://example.com/a", "status": "active", "url_type": "hls"}, "geometry": None},
        {"properties": {"url": "https://example.com/a", "status": "active", "url_type": "hls"}, "geometry": None},
        {"properties": {"url": "https://example.com/b", "status": "unverified", "url_type": "youtube"},
         "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}},
    ]
    parsed, stats = les.parse_features(feats)
    assert stats["features"] == 3 and stats["rows"] == 2 and stats["duplicates_dropped"] == 1, stats


def test_protocol_mapping():
    from wfd.ingest.base import tally

    by_protocol = tally(r.protocol for r in result().rows)
    assert by_protocol == {"hls": 3751, "iframe": 1768, "youtube": 475}, by_protocol


def test_meta_preserves_original_props():
    for row in result().rows[:200]:
        assert row.meta["les_status"] in ("active", "unverified"), row.meta["les_status"]
        assert row.meta["les_props"]["status"] == row.meta["les_status"]
        assert len(row.meta["les_props"]) == 14, row.meta["les_props"].keys()
        assert row.meta["les_props"]["url"] == row.url  # stored copy is the redacted url


def test_coordinates_from_geometry():
    rows = result().rows
    rows_by_url = {r.url: r for r in rows}
    feature = next(
        f for f in les.load_features()
        if f["properties"].get("coordinates_quality") == "exact"
        and "token" not in f["properties"]["url"].lower()   # raw url == stored url
    )
    row = rows_by_url[feature["properties"]["url"]]
    lon, lat = feature["geometry"]["coordinates"]
    assert abs(row.lon - lon) < 1e-9 and abs(row.lat - lat) < 1e-9, (row.lat, row.lon, lat, lon)

    # every row has usable coords; the 50 Web-Mercator features are converted + flagged
    assert all(r.lat is not None and r.lon is not None for r in rows)
    converted = [r for r in rows if r.meta.get("les_coords_note") == "epsg:3857->wgs84"]
    assert len(converted) == 50, len(converted)
    for r in converted:
        assert -90.0 <= r.lat <= 90.0 and -180.0 <= r.lon <= 180.0
        assert r.meta["les_geometry"]["type"] == "Point"   # raw geometry retained


def test_redaction_of_token_urls():
    res = result()
    assert res.stats["redacted"] == 63, res.stats["redacted"]
    assert sum(1 for r in res.rows if r.was_redacted) == 63

    token_rows = 0
    token_keys = 0
    for row in res.rows:
        query = urllib.parse.urlsplit(row.url).query
        row_has_token = False
        for piece in query.split("&"):
            key, sep, value = piece.partition("=")
            if sep and "token" in key.strip().lower():
                assert value == "<redacted>", (key, value)
                token_keys += 1
                row_has_token = True
        if row_has_token:
            token_rows += 1
        assert not re.search(r"token=[0-9a-fA-F%]{8,}", row.url), row.url
    # 61 surviving balticlivecam `token=` rows + 2 wowza rows (3 wowza keys each)
    assert token_rows == 63, token_rows
    assert token_keys == 67, token_keys

    # the nested original-props copy was scrubbed too
    for row in res.rows:
        if row.was_redacted:
            assert row.meta["les_props"]["url"] == row.url
            assert "<redacted>" in row.url


def test_last_verified_dates():
    res = result()
    dates = [r.last_verified for r in res.rows if r.last_verified]
    assert dates, "no corpus last_verified dates parsed"
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates)
    assert res.stats["last_verified_range"] == [min(dates), max(dates)]


def test_camera_id_stability():
    row = result().rows[0]
    assert row.camera_id == stable_id("les", row.url)
    assert len(row.camera_id) == 16
    # same family+url -> same id across parser runs
    again = les.row_from_feature(les.load_features()[0])
    again.finalize()
    assert again.camera_id == row.camera_id


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

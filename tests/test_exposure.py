"""Exposure ingester tests — plain-python runner (this host has no pytest).

Run:    py -3.11 tests/test_exposure.py     -> prints PASS lines; exit 0 = all good.

Fixtures under ``tests/fixtures/exposure/`` are SANITIZED samples: every URL was
run through the ingester's own redactor before being saved, and device hosts were
replaced with RFC 5737 test ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).
``cred_synthetic_urls.json`` holds fake, synthetic credential URLs for redaction
unit tests — no real credential value exists in any fixture or in this file.

Test functions are named ``test_*`` so they also work under pytest if installed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wfd.ingest import exposure  # noqa: E402
from wfd.schema import CameraRow, stable_id  # noqa: E402

FIX = HERE / "fixtures" / "exposure"

# credential shapes that must never appear with a live value in stored data
# (value class excludes whitespace so a scan never spans lines)
_SENS_RE = re.compile(
    r"(?:^|[?&;])(u|user|username|usr|login|p|pass|password|pwd|passwd|credential|auth|"
    r"token|key|apikey|api_key|secret|session|sessionid|sig|signature|wmsauthsign|otp)=([^&;#\"\s]*)",
    re.IGNORECASE,
)
_USERINFO_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^/@\s\"]+@")


def _leaked_values(text: str) -> list:
    """Sensitive params whose value is neither empty nor the <redacted> marker."""
    return [m.group(0) for m in _SENS_RE.finditer(text) if m.group(2) not in ("", "<redacted>")]


def _assert_exposure_row(r: CameraRow, family: str, snapshot: str) -> None:
    """Every exposure row obeys the laws (S5 §B / docs/ARCHITECTURE.md)."""
    assert r.provenance == "exposure_aggregator", r.provenance
    assert r.status == "unverified", r.status
    assert r.geo_confidence == "low", r.geo_confidence
    assert r.snapshot_date == snapshot, r.snapshot_date
    assert r.source_family == family, r.source_family
    assert r.fetch_date, "fetch_date missing"
    assert r.camera_id == stable_id(r.source_family, r.url), r.camera_id
    assert set(r.tags) >= {"exposed", f"snapshot_{snapshot.replace('-', '')}", "geo_approximate"}, r.tags
    blob = json.dumps(r.as_dict(), ensure_ascii=False)
    assert not _leaked_values(blob), (r.url, _leaked_values(blob)[:2])
    assert not _USERINFO_RE.search(r.url), r.url


# --- redaction unit tests ---------------------------------------------------------------

def test_sanitize_synthetic_credentials():
    cases = json.loads((FIX / "cred_synthetic_urls.json").read_text(encoding="utf-8"))["cases"]
    for c in cases:
        red, was, value_present = exposure.sanitize_url(c["url"])
        assert was is c["expect_redacted"], (c["style"], red)
        assert value_present is c["expect_value_present"], (c["style"], value_present)
        for tok in c["must_scrub"]:
            assert tok not in red, (c["style"], tok, red)
        for tok in c["must_keep"]:
            assert tok in red, (c["style"], tok, red)
        # idempotent: re-sanitizing an already-stored URL must not change it
        red2, _was2, _val2 = exposure.sanitize_url(red)
        assert red2 == red, (c["style"], red2)


def test_sanitize_userinfo_and_query_styles():
    red, was, val = exposure.sanitize_url("http://admin:hunter2@192.0.2.20:8080/cgi-bin/snapshot.cgi")
    assert was and val
    assert red == "http://192.0.2.20:8080/cgi-bin/snapshot.cgi", red
    red2, was2, val2 = exposure.sanitize_url("http://192.0.2.21/snap.cgi?u=admin&p=hunter2")
    assert was2 and val2 and "admin" not in red2 and "hunter2" not in red2, red2
    assert "u=<redacted>" in red2 and "p=<redacted>" in red2, red2


# --- parser tests (fixtures) ------------------------------------------------------------

def test_parse_jrw_fixture():
    res = exposure.parse_jrw_tsv((FIX / "jrw_sample.tsv").read_text(encoding="utf-8"), source_ref="fixture")
    assert res.stats["source_rows"] == 30, res.stats
    assert len(res.rows) == 30 - res.stats["duplicates_dropped"], res.stats
    n_red = 0
    for r in res.rows:
        _assert_exposure_row(r, "jrw-2019", "2019-02-21")
        assert r.meta.get("ip_port"), r.meta
        assert r.url.startswith("http://192.0.2."), r.url
        n_red += bool(r.was_redacted)
    assert n_red >= 5, n_red
    assert res.stats["redacted"] == n_red == res.stats["redacted_values"], res.stats


def test_parse_godeye_fixture():
    raw = (FIX / "godeye_sample.json").read_text(encoding="utf-8")
    res = exposure.parse_godeye_json(raw, source_ref="fixture")
    assert res.stats["source_rows"] == 30, res.stats
    assert len(res.rows) == 30
    assert "&amp;" in raw, "fixture should keep raw entity form for non-credential rows"
    urls = [r.url for r in res.rows]
    assert all("&amp;" not in u for u in urls), "entities must be unescaped at parse time"
    assert any("&" in u for u in urls), "at least one unescaped URL expected"
    for r in res.rows:
        _assert_exposure_row(r, "godeye-2026-05", "2026-05-27")
        assert r.url.startswith("http://198.51.100."), r.url
        assert isinstance(r.lat, float) and isinstance(r.lon, float)
        assert r.meta.get("manufacturer") and r.meta.get("id"), r.meta


def test_parse_rafasapiens_fixture():
    jres = exposure.parse_rafasapiens_json(
        (FIX / "rafasapiens_sample.json").read_text(encoding="utf-8"),
        source_ref="fixture", snapshot_date="2026-10-05")
    cres = exposure.parse_rafasapiens_csv(
        (FIX / "rafasapiens_sample.csv").read_text(encoding="utf-8"),
        source_ref="fixture", snapshot_date="2026-10-05")
    for res in (jres, cres):
        assert res.stats["source_rows"] == 30, res.stats
        assert len(res.rows) == 30
        for r in res.rows:
            _assert_exposure_row(r, "rafasapiens-2026-10", "2026-10-05")
            assert r.url.startswith("http://203.0.113."), r.url
            assert r.city
            assert r.meta["view_page"].startswith("http://www.insecam.org/en/view/"), r.meta["view_page"]
            assert r.meta["title"] and r.meta["location"] and r.meta["source"] == "Insecam", r.meta
    # the JSON and CSV mirrors must yield the same rows (same order)
    assert [r.url for r in jres.rows] == [r.url for r in cres.rows]


# --- dedupe + era diff ------------------------------------------------------------------

def test_dedupe_within_dataset():
    tsv = (
        "ip:port\tcountry\tcity\timage feed link\n"
        "192.0.2.1:80\tTestland\tAlpha\thttp://192.0.2.1:80/cam.jpg\n"
        "192.0.2.1:80\tTestland\tAlpha\thttp://192.0.2.1:80/cam.jpg\n"
        "192.0.2.2:80\tTestland\tBeta\thttp://192.0.2.2:80/cam.jpg\n"
    )
    res = exposure.parse_jrw_tsv(tsv)
    assert len(res.rows) == 2 and res.stats["duplicates_dropped"] == 1, res.stats

    recs = [
        {"title": "t1", "url": "http://www.insecam.org/en/view/1/", "image": "http://192.0.2.9/a.mjpg",
         "location": "l1", "source": "Insecam", "city": "c1"},
        {"title": "t2", "url": "http://www.insecam.org/en/view/2/", "image": "http://192.0.2.9/a.mjpg",
         "location": "l2", "source": "Insecam", "city": "c2"},
    ]
    res2 = exposure.parse_rafasapiens_json(json.dumps(recs), snapshot_date="2026-10-05")
    assert len(res2.rows) == 1 and res2.stats["duplicates_dropped"] == 1, res2.stats


def test_diff_eras():
    a = [CameraRow(url="http://x/a"), CameraRow(url="http://x/b"), CameraRow(url="http://x/c")]
    b = [CameraRow(url="http://x/b"), CameraRow(url="http://x/c"), CameraRow(url="http://x/d")]
    assert exposure.diff_eras(a, b) == {"added": 1, "removed": 1, "common": 2}
    # meta-key lookup (jrw ip_port style)
    a2 = [CameraRow(url="", meta={"ip_port": "192.0.2.1:80"}),
          CameraRow(url="", meta={"ip_port": "192.0.2.2:80"})]
    b2 = [CameraRow(url="", meta={"ip_port": "192.0.2.2:80"})]
    assert exposure.diff_eras(a2, b2, key="ip_port") == {"added": 0, "removed": 1, "common": 1}
    # plain dicts supported
    assert exposure.diff_eras([{"url": "a"}], [{"url": "b"}]) == {"added": 1, "removed": 1, "common": 0}


# --- fixture hygiene --------------------------------------------------------------------

def test_fixtures_are_sanitized():
    for f in sorted(FIX.glob("*")):
        if f.name == "cred_synthetic_urls.json" or f.suffix not in (".tsv", ".json", ".csv"):
            continue  # synthetic file deliberately contains FAKE credential URLs (tested above)
        text = f.read_text(encoding="utf-8")
        assert not _leaked_values(text), (f.name, _leaked_values(text)[:3])
    tsv = (FIX / "jrw_sample.tsv").read_text(encoding="utf-8")
    for line in tsv.splitlines()[1:]:
        assert line.split("\t")[0].startswith("192.0.2."), line
    for rec in json.loads((FIX / "godeye_sample.json").read_text(encoding="utf-8")):
        assert "198.51.100." in rec["stream"]
    for rec in json.loads((FIX / "rafasapiens_sample.json").read_text(encoding="utf-8")):
        assert "203.0.113." in rec["image"]


def test_full_file_counts_when_raw_present():
    """Full-file count checks (17,398 / 1,775 / 2,100 source rows). Raw downloads live
    under gitignored dirs except jrw (committed corpus); skip cleanly if absent."""
    res = exposure.ingest("jrw")
    assert res.stats["source_rows"] == 17398, res.stats
    assert len(res.rows) == 17034 and res.stats["duplicates_dropped"] == 364, res.stats
    for name, src_n, kept_n in (("godeye", 1775, 1775), ("rafasapiens", 2100, 2072)):
        raw = exposure.DATASETS[name]["raw"]
        if not raw.exists():
            print(f"      SKIP {name}: raw file absent ({raw.name})")
            continue
        r = exposure.ingest(name)
        assert r.stats["source_rows"] == src_n, (name, r.stats)
        assert len(r.rows) == kept_n, (name, r.stats)


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

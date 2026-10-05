"""wfd.ingest.exposure — insecam-class dataset ingesters (build task B).

Three era snapshots of the exposure category (PLAN D6 / S5 §B), ingested as
**static dataset files only** — no listed device is ever contacted, and the
insecam *view pages* (``.../en/view/<id>/``) are stored as metadata but NEVER
fetched. The only network reads this module ever performs are the dataset URLs
in :data:`DATASETS` (raw.githubusercontent.com); refresh = re-download.

===============  ==========================================  ========  ==================
family           source                                      format    snapshot
===============  ==========================================  ========  ==================
jrw-2019         justrandomwebcams/totalynothackedijokeyounot  TSV    2019-02-21
godeye-2026-05   Hacker-Sam-is-here/GODEYE                   JSON      2026-05-27
rafasapiens-2026-10  rafasapiens/webscraping                  JSON+CSV  fetch date (current era)
===============  ==========================================  ========  ==================

Exposure laws enforced on every row (docs/ARCHITECTURE.md “exposure laws”, S5 §B):

- ``provenance='exposure_aggregator'``, ``status='unverified'``,
  ``geo_confidence='low'`` and a ``snapshot_date`` — always;
- credentials are redacted **at parse time** via :func:`wfd.schema.redact_url`
  *before* anything is stored or logged; ``was_redacted``/``credential_present``
  are recorded per row and redactions are counted;
- enumeration never claims liveness (``status`` stays ``unverified``).

Row-mapping notes:

- jrw: ``url`` = image-feed link (redacted); ``country``/``city`` kept; the raw
  ``ip:port`` key goes to ``meta['ip_port']``.
- godeye: ``url`` = ``stream`` (redacted); ``lat``/``lng`` → ``lat``/``lon``;
  ``manufacturer`` and ``id`` go to ``meta``.
- rafasapiens: ``url`` = the device image URL (``image``, redacted);
  ``city`` kept; ``title``/``location``/``source`` + the *view page* go to
  ``meta`` (view page stored redacted, never fetched).

Dedupe is per-dataset only (eras stay separate): jrw by ``ip:port``; godeye and
rafasapiens by redacted URL.  ``diff_eras()`` supports comparing two snapshots
of the *same* dataset (refresh diff: added / removed / common), not cross-era.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import pathlib
import re
import sys
from typing import Optional, Sequence

from .. import profile
from ..schema import REDACTED, CameraRow, redact_and_flag
from ..schema import _SENSITIVE_QUERY_KEYS  # mirrors the shared scrubber key list
from .base import (
    DATA_DIR,
    IngestResult,
    clean_float,
    clean_str,
    polite_get,
    today_iso,
    write_jsonl,
)

RAW_DIR = profile.REPO_ROOT / "research" / "exposed" / "raw"
OUT_DIR = DATA_DIR / "ingest"

PROVENANCE = "exposure_aggregator"
STATUS = "unverified"
GEO_CONFIDENCE = "low"

# --- dataset registry (the ONLY URLs this module may ever fetch) ------------------------

DATASETS: dict = {
    "jrw": {
        "family": "jrw-2019",
        "format": "tsv",
        "snapshot_date": "2019-02-21",
        "source_ref": (
            "https://raw.githubusercontent.com/justrandomwebcams/"
            "totalynothackedijokeyounot/HEAD/190221dump_alphabetical.csv"
        ),
        "url": (
            "https://raw.githubusercontent.com/justrandomwebcams/"
            "totalynothackedijokeyounot/HEAD/190221dump_alphabetical.csv"
        ),
        # committed corpus (not under raw/); re-downloadable from the URL above
        "raw": profile.REPO_ROOT / "research" / "exposed"
        / "totalynothackedijokeyounot__190221dump_alphabetical.csv",
    },
    "godeye": {
        "family": "godeye-2026-05",
        "format": "json",
        "snapshot_date": "2026-05-27",
        "source_ref": "https://raw.githubusercontent.com/Hacker-Sam-is-here/GODEYE/HEAD/data/insecam_cameras.json",
        "url": "https://raw.githubusercontent.com/Hacker-Sam-is-here/GODEYE/HEAD/data/insecam_cameras.json",
        "raw": RAW_DIR / "godeye_insecam_cameras_2026-05-27.json",
    },
    "rafasapiens": {
        "family": "rafasapiens-2026-10",
        "format": "json+csv",
        "snapshot_date": None,  # current-era snapshot → fetch date of the raw file
        "source_ref": "https://raw.githubusercontent.com/rafasapiens/webscraping/HEAD/cams/cameras.json",
        "url": "https://raw.githubusercontent.com/rafasapiens/webscraping/HEAD/cams/cameras.json",
        "raw": RAW_DIR / "rafasapiens_cameras_2026-10.json",
        "extra_raw": {
            "csv": {
                "path": RAW_DIR / "rafasapiens_cameras_2026-10.csv",
                "url": "https://raw.githubusercontent.com/rafasapiens/webscraping/HEAD/cams/cameras.csv",
            }
        },
    },
}

ORDER = ("jrw", "godeye", "rafasapiens")


# --- sanitization: unescape → redact → defensive residual scrub -------------------------

_USERINFO_SCAN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@\s]*@")

# same key set as wfd.schema's scrubber; the ';' separator is accepted here as
# defense-in-depth (the shared redactor splits on '&' only)
_KEY_ALTERNATION = "|".join(
    re.escape(k) for k in sorted(_SENSITIVE_QUERY_KEYS, key=len, reverse=True)
)
_RESIDUAL_RE = re.compile(
    r"(?P<pre>^|[?&;])(?P<key>" + _KEY_ALTERNATION + r")=(?P<value>[^&;#]*)",
    re.IGNORECASE,
)


def _residual_sub(m: "re.Match") -> str:
    value = m.group("value")
    if value and value != REDACTED:
        return f"{m.group('pre')}{m.group('key')}={REDACTED}"
    return m.group(0)


def _scrub_residual(url: str) -> str:
    """Scrub any credential-shaped param the primary redactor left behind.

    No-op on all three current datasets (verified: 0 residual hits); kept so a
    future re-download with odd separators can never leak a credential.
    """
    return _RESIDUAL_RE.sub(_residual_sub, url)


def _secret_value_present(url: str) -> bool:
    """True when a NON-EMPTY credential value (userinfo or query param) exists."""
    if _USERINFO_SCAN.match(url):
        return True
    return any(m.group("value") for m in _RESIDUAL_RE.finditer(url))


def sanitize_url(raw) -> tuple[str, bool, bool]:
    """Normalize + redact one URL.

    Returns ``(redacted_url, was_redacted, secret_value_present)``.

    Order matters: HTML-unescape first — scraped datasets carry ``&amp;u=…``
    which would otherwise slip past the ``&``-splitting scrubber — then
    ``redact_and_flag`` (the mandated redactor), then the residual guard.
    Never log or store the input *or* the return's raw predecessor.
    """
    url = html.unescape(clean_str(raw))
    if not url:
        return "", False, False
    value_present = _secret_value_present(url)
    red, was_redacted, _cred = redact_and_flag(url)
    guarded = _scrub_residual(red)
    if guarded != red:
        was_redacted = True
    return guarded, was_redacted, value_present


# --- per-dataset field routing ----------------------------------------------------------

def detect_protocol(url: str) -> str:
    """URL-pattern protocol hint (NO contact — string analysis only)."""
    u = (url or "").lower()
    if u.startswith("rtsp://"):
        return "rtsp"
    if ".m3u8" in u:
        return "hls"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if any(k in u for k in ("mjpg", "mjpeg", "/video", "videostream", "axis-media", "action=stream")):
        return "mjpeg"
    if any(k in u for k in ("snapshot", ".jpg", ".jpeg", "jpeg", "image", "webcapture", "getdata", "action=snapshot")):
        return "jpeg"
    return "unknown"


def _tags(snapshot_date: str) -> list:
    compact = snapshot_date.replace("-", "")
    return ["exposed", f"snapshot_{compact}", "geo_approximate"]


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8-sig", errors="replace")
    return str(data)


def _dedupe(rows: list, key) -> tuple[list, int]:
    seen = set()
    kept: list = []
    dropped = 0
    for r in rows:
        k = key(r)
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        kept.append(r)
    return kept, dropped


def _finalize_result(res: IngestResult) -> IngestResult:
    res.finalize()
    return res


def _make_row(*, url: str, family: str, snapshot_date: str, source_ref: str, **kw) -> CameraRow:
    """One exposure-category row — the laws applied in a single place."""
    meta = kw.pop("meta", {}) or {}
    meta.setdefault("dataset", family)
    meta.setdefault("source_ref", source_ref)
    return CameraRow(
        url=url,
        source_family=family,
        provenance=PROVENANCE,
        status=STATUS,
        snapshot_date=snapshot_date,
        geo_confidence=GEO_CONFIDENCE,
        tags=_tags(snapshot_date),
        meta=meta,
        **kw,
    )


# --- parsers ----------------------------------------------------------------------------

def parse_jrw_tsv(
    data,
    *,
    source_ref: str = "",
    snapshot_date: str = "2019-02-21",
    family: str = "jrw-2019",
) -> IngestResult:
    """Parse the jrw 2019-02-21 TSV dump (header: ip:port, country, city, image feed link).

    The file uses ``\\r\\r\\n`` line terminators; dedupe key is ``ip:port``.
    """
    text = _decode(data)
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.reader(io.StringIO(text), delimiter="\t")

    res = IngestResult(
        family=family, provenance=PROVENANCE, snapshot_date=snapshot_date, source_ref=source_ref
    )
    source_rows = skipped = irregular = 0
    pairs: list = []  # (CameraRow, secret_value_present)
    for i, parts in enumerate(reader):
        if i == 0 and parts and parts[0].strip().lower() == "ip:port":
            continue  # header
        if len(parts) < 4:
            skipped += 1
            continue
        if len(parts) != 4:
            irregular += 1
        ip_port, country, city = (clean_str(p) for p in parts[:3])
        raw_url = parts[3]
        if not ip_port or not clean_str(raw_url):
            skipped += 1
            continue
        source_rows += 1
        url, was_redacted, value_present = sanitize_url(raw_url)
        if not url:
            skipped += 1
            continue
        pairs.append(
            (
                _make_row(
                    url=url,
                    family=family,
                    snapshot_date=snapshot_date,
                    source_ref=source_ref,
                    country=country,
                    city=city,
                    protocol=detect_protocol(url),
                    was_redacted=was_redacted,
                    credential_present=was_redacted,
                    meta={"ip_port": ip_port},
                ),
                value_present,
            )
        )
    pairs, duplicates = _dedupe(pairs, key=lambda p: p[0].meta.get("ip_port") or p[0].url)
    res.rows = [row for row, _vp in pairs]
    redacted_values = sum(1 for _row, vp in pairs if vp)
    res.stats.update(
        source_rows=source_rows,
        skipped=skipped,
        irregular=irregular,
        duplicates_dropped=duplicates,
        redacted_values=redacted_values,
    )
    res.notes = (
        f"jrw snapshot 2019-02-21 (stale historical corpus); "
        f"{duplicates} duplicate ip:port rows dropped; {redacted_values} URLs carried "
        f"non-empty credential values (redacted before storage)"
    )
    return _finalize_result(res)


def parse_godeye_json(
    data,
    *,
    source_ref: str = "",
    snapshot_date: str = "2026-05-27",
    family: str = "godeye-2026-05",
) -> IngestResult:
    """Parse the GODEYE 2026-05-27 JSON array (id, country, city, manufacturer, lat, lng, stream)."""
    records = json.loads(_decode(data)) if isinstance(data, (str, bytes)) else data
    if not isinstance(records, list):
        raise ValueError("godeye dataset must be a JSON array")

    res = IngestResult(
        family=family, provenance=PROVENANCE, snapshot_date=snapshot_date, source_ref=source_ref
    )
    source_rows = skipped = 0
    pairs: list = []  # (CameraRow, secret_value_present)
    for rec in records:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        raw_stream = rec.get("stream")
        if not clean_str(raw_stream):
            skipped += 1
            continue
        source_rows += 1
        url, was_redacted, value_present = sanitize_url(raw_stream)
        if not url:
            skipped += 1
            continue
        pairs.append(
            (
                _make_row(
                    url=url,
                    family=family,
                    snapshot_date=snapshot_date,
                    source_ref=source_ref,
                    country=clean_str(rec.get("country")),
                    city=clean_str(rec.get("city")),
                    lat=clean_float(rec.get("lat")),
                    lon=clean_float(rec.get("lng")),
                    protocol=detect_protocol(url),
                    was_redacted=was_redacted,
                    credential_present=was_redacted,
                    meta={
                        "id": clean_str(rec.get("id")),
                        "manufacturer": clean_str(rec.get("manufacturer")),
                    },
                ),
                value_present,
            )
        )
    pairs, duplicates = _dedupe(pairs, key=lambda p: p[0].url)
    res.rows = [row for row, _vp in pairs]
    redacted_values = sum(1 for _row, vp in pairs if vp)
    res.stats.update(
        source_rows=source_rows,
        skipped=skipped,
        duplicates_dropped=duplicates,
        redacted_values=redacted_values,
    )
    res.notes = (
        f"GODEYE snapshot 2026-05-27 (insecam-derived; HTML entities unescaped, "
        f"credentials redacted); {duplicates} duplicate stream URLs dropped"
    )
    return _finalize_result(res)


def _rafa_rows(
    records: Sequence[dict],
    *,
    source_ref: str,
    snapshot_date: str,
    family: str,
    res: IngestResult,
) -> None:
    source_rows = skipped = 0
    pairs: list = []  # (CameraRow, secret_value_present)
    for rec in records:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        raw_image = rec.get("image")
        if not clean_str(raw_image):
            skipped += 1
            continue
        source_rows += 1
        url, was_redacted, value_present = sanitize_url(raw_image)
        if not url:
            skipped += 1
            continue
        # view page = aggregator listing metadata; stored redacted, NEVER fetched
        view_page, view_redacted, _ = sanitize_url(rec.get("url"))
        pairs.append(
            (
                _make_row(
                    url=url,
                    family=family,
                    snapshot_date=snapshot_date,
                    source_ref=source_ref,
                    city=clean_str(rec.get("city")),
                    protocol=detect_protocol(url),
                    was_redacted=was_redacted or view_redacted,
                    credential_present=was_redacted or view_redacted,
                    meta={
                        "title": clean_str(rec.get("title")),
                        "location": clean_str(rec.get("location")),
                        "source": clean_str(rec.get("source")),
                        "view_page": view_page,
                    },
                ),
                value_present,
            )
        )
    pairs, duplicates = _dedupe(pairs, key=lambda p: p[0].url)
    res.rows = [row for row, _vp in pairs]
    redacted_values = sum(1 for _row, vp in pairs if vp)
    res.stats.update(
        source_rows=source_rows,
        skipped=skipped,
        duplicates_dropped=duplicates,
        redacted_values=redacted_values,
    )


def parse_rafasapiens_json(
    data,
    *,
    source_ref: str = "",
    snapshot_date: str = "",
    family: str = "rafasapiens-2026-10",
) -> IngestResult:
    """Parse the rafasapiens JSON array (title, url=view page, image=device URL, location, source, city)."""
    records = json.loads(_decode(data)) if isinstance(data, (str, bytes)) else data
    if not isinstance(records, list):
        raise ValueError("rafasapiens dataset must be a JSON array")
    res = IngestResult(
        family=family, provenance=PROVENANCE, snapshot_date=snapshot_date, source_ref=source_ref
    )
    _rafa_rows(records, source_ref=source_ref, snapshot_date=snapshot_date, family=family, res=res)
    res.notes = (
        "rafasapiens current-era snapshot (fetch date); insecam view pages stored as "
        "meta only and never fetched; device image URLs redacted"
    )
    return _finalize_result(res)


def parse_rafasapiens_csv(
    data,
    *,
    source_ref: str = "",
    snapshot_date: str = "",
    family: str = "rafasapiens-2026-10",
) -> IngestResult:
    """Parse the rafasapiens CSV mirror (same columns as the JSON)."""
    text = _decode(data)
    reader = csv.DictReader(io.StringIO(text))
    records = [dict(r) for r in reader]
    res = IngestResult(
        family=family, provenance=PROVENANCE, snapshot_date=snapshot_date, source_ref=source_ref
    )
    _rafa_rows(records, source_ref=source_ref, snapshot_date=snapshot_date, family=family, res=res)
    res.notes = (
        "rafasapiens current-era snapshot (CSV mirror); view pages stored as meta "
        "only and never fetched; device image URLs redacted"
    )
    return _finalize_result(res)


# --- era diff ---------------------------------------------------------------------------

def _row_key(row, key: str):
    if isinstance(row, dict):
        val = row.get(key)
        if val in (None, ""):
            val = (row.get("meta") or {}).get(key)
        return val
    val = getattr(row, key, None)
    if val in (None, "") and isinstance(getattr(row, "meta", None), dict):
        val = row.meta.get(key)
    return val


def diff_eras(rows_a, rows_b, key: str = "url") -> dict:
    """Diff two snapshots of ONE dataset → ``{'added': n, 'removed': n, 'common': n}``.

    ``key`` is looked up as an attribute on CameraRow first, then ``meta[key]``
    (so ``key='ip_port'`` works for jrw); dicts are supported too.
    """
    a = {k for k in (_row_key(r, key) for r in rows_a) if k}
    b = {k for k in (_row_key(r, key) for r in rows_b) if k}
    return {"added": len(b - a), "removed": len(a - b), "common": len(a & b)}


# --- acquisition + outputs --------------------------------------------------------------

def _file_date(path: pathlib.Path) -> str:
    """ISO date the local raw file was fetched (mtime; fallback: today)."""
    try:
        import datetime as _dt

        return _dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return today_iso()


def ensure_raw(name: str, *, refresh: bool = False) -> pathlib.Path:
    """Return the local raw path, downloading it (polite_get) if missing/refresh."""
    spec = DATASETS[name]
    path: pathlib.Path = spec["raw"]
    targets = [(path, spec["url"])]
    for extra in (spec.get("extra_raw") or {}).values():
        targets.append((extra["path"], extra["url"]))
    for p, url in targets:
        if refresh or not p.exists():
            body = polite_get(url)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
    return path


def snapshot_date_for(name: str) -> str:
    """Fixed snapshot (jrw/godeye) or fetch date of the raw file (rafasapiens)."""
    spec = DATASETS[name]
    if spec["snapshot_date"]:
        return spec["snapshot_date"]
    return _file_date(spec["raw"])


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest(name: str, *, refresh: bool = False) -> IngestResult:
    """Ingest one dataset from its local raw file (downloading first if needed)."""
    path = ensure_raw(name, refresh=refresh)
    spec = DATASETS[name]
    snap = snapshot_date_for(name)
    data = path.read_bytes()
    if name == "jrw":
        return parse_jrw_tsv(data, source_ref=spec["source_ref"], snapshot_date=snap)
    if name == "godeye":
        return parse_godeye_json(data, source_ref=spec["source_ref"], snapshot_date=snap)
    if name == "rafasapiens":
        return parse_rafasapiens_json(data, source_ref=spec["source_ref"], snapshot_date=snap)
    raise KeyError(name)


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(profile.REPO_ROOT)).replace("\\", "/")


def build_manifest_entry(name: str, res: IngestResult) -> dict:
    """Manifest entry for one dataset (sha256 of the raw file(s) actually parsed)."""
    spec = DATASETS[name]
    raw = spec["raw"]
    entry = {
        "family": res.family,
        "path": _rel(OUT_DIR / f"exposure-{res.family}.jsonl"),
        "source_ref": spec["source_ref"],
        "sha256": _sha256_file(raw),
        "fetched_at": _file_date(raw),
        "rows": len(res.rows),
        "format": spec["format"],
        "redactions": res.stats.get("redacted", 0),
        "snapshot_date": res.snapshot_date,
        "duplicates_dropped": res.stats.get("duplicates_dropped", 0),
        "skipped": res.stats.get("skipped", 0),
        "raw": _rel(raw),
    }
    for kind, extra in (spec.get("extra_raw") or {}).items():
        entry[f"sha256_{kind}"] = _sha256_file(extra["path"])
        entry[f"raw_{kind}"] = _rel(extra["path"])
    return entry


def write_outputs(results: dict, manifest_path: Optional[pathlib.Path] = None) -> dict:
    """Write JSONL per dataset + merge manifest entries. Returns the manifest dict."""
    manifest_path = manifest_path or (OUT_DIR / "manifest-exposure.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest.get("datasets"), dict):
            raise ValueError
    except (OSError, json.JSONDecodeError, ValueError):
        manifest = {"generated_at": today_iso(), "datasets": {}}
    for name, res in results.items():
        n = write_jsonl(OUT_DIR / f"exposure-{res.family}.jsonl", res.rows)
        assert n == len(res.rows), (n, len(res.rows))
        manifest["datasets"][res.family] = build_manifest_entry(name, res)
    manifest["generated_at"] = today_iso()
    manifest["datasets"] = dict(sorted(manifest["datasets"].items()))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --- CLI --------------------------------------------------------------------------------

def _print_stats(name: str, res: IngestResult) -> None:
    st = res.stats
    print(f"== {res.family} ==")
    print(f"   source_ref:    {res.source_ref}")
    print(f"   snapshot_date: {res.snapshot_date}   fetched: {_file_date(DATASETS[name]['raw'])}")
    print(
        f"   rows: {st.get('rows')}   (source_rows={st.get('source_rows')}, "
        f"skipped={st.get('skipped')}, duplicates_dropped={st.get('duplicates_dropped')})"
    )
    print(
        f"   redacted: {st.get('redacted')}   "
        f"(rows with non-empty credential values: {st.get('redacted_values')})"
    )
    top = list((st.get("by_country") or {}).items())[:10]
    if top:
        print("   top-10 countries: " + ", ".join(f"{c}={n}" for c, n in top))
    else:
        print("   top-10 countries: (source dataset carries no country field)")
    print(f"   output: {_rel(OUT_DIR / f'exposure-{res.family}.jsonl')}")


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="py -3.11 -m wfd.ingest.exposure",
        description="Ingest insecam-class exposure datasets (static files only; never contacts devices).",
    )
    parser.add_argument("target", nargs="?", default="all", choices=[*ORDER, "all"])
    parser.add_argument("--refresh", action="store_true", help="re-download raw files first (polite_get)")
    args = parser.parse_args(argv)

    names = list(ORDER) if args.target == "all" else [args.target]
    results = {}
    for name in names:
        res = ingest(name, refresh=args.refresh)
        results[name] = res
        _print_stats(name, res)
    manifest = write_outputs(results)
    print(f"manifest: {_rel(OUT_DIR / 'manifest-exposure.json')} "
          f"({len(manifest['datasets'])} datasets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

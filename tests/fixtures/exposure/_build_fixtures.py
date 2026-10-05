"""Build sanitized fixtures for the exposure-ingester tests (maintainer script).

For each dataset it takes a small sample (<=30 rows) and:

- runs every URL through the SAME redactor the ingester uses
  (``wfd.ingest.exposure.sanitize_url``) — no credential VALUE is ever written
  to a committed fixture (redacted rows keep only the ``<redacted>`` marker);
- replaces device hosts with RFC 5737 documentation ranges
  (192.0.2.0/24 / 198.51.100.0/24 / 203.0.113.0/24), including jrw's ``ip:port``
  column — a committed fixture must not carry live device addresses either;
- keeps countries/cities/manufacturers/titles/locations AS-IS (coarse metadata);
- keeps rafasapiens view-page URLs as-is (aggregator listing metadata, no
  device address, never fetched).

Raw-aspect preservation: rows whose URL needed no redaction are kept in their
original encoding form (godeye/rafasapiens carry ``&amp;`` entities) so the
parser's unescape step is exercised; redacted rows take the sanitized form.

Run (repo root):  py -3.11 tests/fixtures/exposure/_build_fixtures.py
Re-run is deterministic for unchanged raw files; datasets whose raw file is
absent (gitignored downloads) are skipped with a message.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from wfd.ingest.exposure import DATASETS, sanitize_url  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent


def mask_host(url: str, new_ip: str) -> str:
    parts = urllib.parse.urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    return urllib.parse.urlunsplit(
        (parts.scheme, new_ip + port, parts.path, parts.query, parts.fragment)
    )


def prep_url(raw_url: str, new_ip: str) -> str:
    """Redact if needed (mandated), else keep original form; then mask the host."""
    red, was_redacted, value_present = sanitize_url(raw_url)
    out = red if (was_redacted or value_present) else raw_url
    return mask_host(out, new_ip)


def pick(rows: list, is_cred, sample_n: int = 30, min_cred: int = 5):
    """First `sample_n` rows, trading tail slots for credential-bearing rows if sparse."""
    picks = list(rows[:sample_n])
    have = sum(1 for r in picks if is_cred(r))
    if have < min_cred:
        picked_ids = {id(r) for r in picks}
        for r in rows[sample_n:]:
            if have >= min_cred:
                break
            if is_cred(r) and id(r) not in picked_ids:
                picks[len(picks) - min_cred + have] = r  # replace a tail slot
                picked_ids.add(id(r))
                have += 1
    return picks


def _write_text(path: pathlib.Path, text: str) -> None:
    """LF-terminated writes — deterministic across platforms for committed fixtures."""
    path.write_text(text, encoding="utf-8", newline="\n")


def build_jrw() -> None:
    src = DATASETS["jrw"]["raw"]
    if not src.exists():
        print("SKIP jrw: raw file absent")
        return
    text = src.read_bytes().decode("utf-8").replace("\r\r\n", "\n").replace("\r\n", "\n")
    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    header, data = rows[0], rows[1:]
    picks = pick(data, is_cred=lambda r: sanitize_url(r[3])[1])
    lines = ["\t".join(header)]
    n_cred = 0
    for i, r in enumerate(picks, 1):
        ip_port = r[0].strip()
        _, _, port = ip_port.partition(":")
        new_ip = f"192.0.2.{i}"
        if sanitize_url(r[3])[1]:
            n_cred += 1
        ip_col = f"{new_ip}:{port}" if port else new_ip
        lines.append("\t".join([ip_col, r[1].strip(), r[2].strip(), prep_url(r[3], new_ip)]))
    out = FIX / "jrw_sample.tsv"
    _write_text(out, "\n".join(lines) + "\n")
    print(f"jrw_sample.tsv: {len(picks)} rows ({n_cred} credential-redacted)")


def build_godeye() -> None:
    src = DATASETS["godeye"]["raw"]
    if not src.exists():
        print("SKIP godeye: raw file absent")
        return
    recs = json.loads(src.read_text(encoding="utf-8"))
    picks = pick(recs, is_cred=lambda r: sanitize_url(r.get("stream"))[1], min_cred=3)
    out_recs = []
    n_cred = 0
    for i, r in enumerate(picks, 1):
        new_ip = f"198.51.100.{i}"
        if sanitize_url(r.get("stream"))[1]:
            n_cred += 1
        rec = dict(r)
        rec["stream"] = prep_url(rec["stream"], new_ip)
        out_recs.append(rec)
    out = FIX / "godeye_sample.json"
    _write_text(out, json.dumps(out_recs, indent=2, ensure_ascii=False) + "\n")
    print(f"godeye_sample.json: {len(out_recs)} records ({n_cred} credential-redacted)")


def build_rafasapiens() -> None:
    src = DATASETS["rafasapiens"]["raw"]
    if not src.exists():
        print("SKIP rafasapiens: raw file absent")
        return
    recs = json.loads(src.read_text(encoding="utf-8"))
    picks = pick(recs, is_cred=lambda r: sanitize_url(r.get("image"))[1], min_cred=3)
    out_recs = []
    n_cred = 0
    for i, r in enumerate(picks, 1):
        new_ip = f"203.0.113.{i}"
        if sanitize_url(r.get("image"))[1]:
            n_cred += 1
        rec = dict(r)
        rec["image"] = prep_url(rec["image"], new_ip)  # device URL → masked + redacted
        # rec["url"] (insecam view page) kept as-is: metadata only, never fetched
        out_recs.append(rec)
    _write_text(
        FIX / "rafasapiens_sample.json",
        json.dumps(out_recs, indent=2, ensure_ascii=False) + "\n",
    )
    with (FIX / "rafasapiens_sample.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["title", "url", "image", "location", "source", "city"], lineterminator="\n"
        )
        w.writeheader()
        w.writerows(out_recs)
    print(f"rafasapiens_sample.json/.csv: {len(out_recs)} records ({n_cred} credential-redacted)")


if __name__ == "__main__":
    build_jrw()
    build_godeye()
    build_rafasapiens()

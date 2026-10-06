"""wfd.ingest.gov.base — enumerator interface, registry + runner (build task C).

One ``Enumerator`` per agency enumeration endpoint. Enumeration NEVER claims
liveness (docs/ARCHITECTURE.md vocabulary rule): every row enters as
``status="unknown"``; agency service flags (Caltrans ``inService``, DelDOT
``status``/``enabled``, ...) stay in ``meta``. :func:`run_one` enforces this
with a hard check before anything is written — a non-``unknown`` row raises.
"""
from __future__ import annotations

import hashlib
import pathlib

from ..base import DATA_DIR, IngestResult, write_jsonl


class Enumerator:
    """One agency enumeration source. Subclass and implement :meth:`enumerate`."""

    name: str = ""
    source_ref: str = ""
    provenance: str = "public_by_design"
    attribution: str = ""

    def enumerate(self) -> IngestResult:  # pragma: no cover — interface
        raise NotImplementedError


_REGISTRY: dict = {}


def register(enumerator: Enumerator) -> Enumerator:
    if not enumerator.name:
        raise ValueError("enumerator needs a non-empty .name")
    _REGISTRY[enumerator.name] = enumerator
    return enumerator


def registry() -> dict:
    """Shallow copy of the name -> Enumerator registry."""
    return dict(_REGISTRY)


def get(name: str) -> Enumerator:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown enumerator {name!r}; known: {sorted(_REGISTRY)}") from None


def check_no_liveness(result: IngestResult) -> None:
    """Guard: enumeration must never claim liveness (rows all ``unknown``)."""
    offenders = [(r.url, r.status) for r in result.rows if r.status != "unknown"]
    if offenders:
        raise ValueError(
            f"enumeration may not claim liveness: {len(offenders)} row(s) not 'unknown', "
            f"e.g. {offenders[:3]}"
        )


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(enumerator: Enumerator, *, save: bool = True, out_dir=None) -> IngestResult:
    """Enumerate + finalize + liveness guard; optionally write the JSONL output.

    Output defaults to ``data/ingest/gov-<name>.jsonl`` (gitignored).
    """
    result = enumerator.enumerate().finalize()
    check_no_liveness(result)
    if save:
        base_dir = pathlib.Path(out_dir) if out_dir else (DATA_DIR / "ingest")
        path = base_dir / f"gov-{enumerator.name}.jsonl"
        written = write_jsonl(path, result.rows)
        result.stats["written"] = written
        result.stats["output"] = str(path)
        result.stats["sha256"] = _sha256_file(path)
    return result


def format_result(result: IngestResult) -> str:
    """Human-readable one-result report for the CLI."""
    stats = result.stats
    lines = [
        f"[{result.family}] rows={stats.get('rows', len(result.rows))} "
        f"provenance={result.provenance} source={result.source_ref}"
    ]
    if result.notes:
        lines.append(f"  notes: {result.notes}")
    if "output" in stats:
        lines.append(
            f"  output: {stats['output']} "
            f"({stats.get('written', '?')} rows, sha256 {stats.get('sha256', '?')})"
        )
    if "bytes" in stats:
        lines.append(f"  bytes: {stats['bytes']}")
    if "http" in stats:
        lines.append(f"  http: {stats['http']}")
    if stats.get("key_required"):
        lines.append("  key_required: yes — no request made (honest empty result)")
    for entry in stats.get("districts", []):
        lines.append(
            f"  {entry['district']}: OK rows={entry['rows']} streaming={entry.get('streaming', 0)}"
        )
    for entry in stats.get("districts_failed", []):
        lines.append(f"  {entry['district']}: FAIL {entry.get('error', '')}")
    if "cams_with_streaming" in stats:
        lines.append(
            f"  cams with streaming URL: {stats['cams_with_streaming']}/{stats.get('rows', '?')}"
        )
    if "camera_count_field" in stats:
        lines.append(f"  cameraCount field: {stats['camera_count_field']}")
    if "features" in stats:
        lines.append(f"  features: {stats['features']}")
    if "published" in stats:
        lines.append(f"  published: {stats['published']}")
    by_country = stats.get("by_country") or {}
    if by_country:
        top = list(by_country.items())[:10]
        lines.append("  by country (top 10): " + ", ".join(f"{k}={v}" for k, v in top))
    by_status = stats.get("by_status") or {}
    if by_status:
        lines.append(f"  by status: {by_status}")
    if "auth_header" in stats:
        lines.append(f"  auth header used: {stats['auth_header']}")
    return "\n".join(lines)

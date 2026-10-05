"""wfd.ingest.newsrc.base — new-source enumerator base + shared fetch cache.

Family modules under this package each expose a module-level ``ENUMERATOR``
(an :class:`Enumerator` instance) and are runnable directly::

    py -3.11 -m wfd.ingest.newsrc.<family>

The package runner (``py -3.11 -m wfd.ingest.newsrc <family|all>``) registers
every family module; see ``docs/ARCHITECTURE.md`` (build unit NS).

Enumeration NEVER claims liveness (docs/ARCHITECTURE.md vocabulary rule): every
row enters as ``status="unknown"`` — published operator flags (is_offline,
online, ...) stay in ``meta``. :func:`run_one` enforces this with a hard check
before anything is written.

``FetchCache`` makes long enumerations resumable: page/API bytes are cached
under ``data/ingest/cache/<family>/`` (gitignored with ``data/``) and re-runs
skip what is already on disk (``refresh=True`` / ``--refresh`` refetches).
"""
from __future__ import annotations

import hashlib
import json as _json
import pathlib

from ..base import DATA_DIR, IngestResult, polite_get, write_jsonl

CACHE_ROOT = DATA_DIR / "ingest" / "cache"


class Enumerator:
    """One new-source family endpoint. Subclass and implement :meth:`enumerate`."""

    name: str = ""                    # registry family name (may contain hyphens)
    source_ref: str = ""              # canonical list/API reference
    provenance: str = "public_by_design"
    attribution: str = ""
    refresh: bool = False             # honored by enumerators that use FetchCache
    limit: int | None = None          # optional cap for tests/debug (honor it)

    def enumerate(self) -> IngestResult:  # pragma: no cover — interface
        raise NotImplementedError


class FetchCache:
    """Per-family byte cache — long enumerations become resumable.

    One cache file per URL: ``<root>/<sha256(url)[:24]><suffix>``.
    """

    def __init__(self, root, *, refresh: bool = False):
        self.root = pathlib.Path(root)
        self.refresh = refresh
        self.hits = 0
        self.misses = 0

    def _path(self, url: str, suffix: str) -> pathlib.Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.root / f"{key}{suffix or '.bin'}"

    def get(self, url: str, *, headers=None, suffix: str = ".bin", timeout=None,
            min_interval=None) -> bytes:
        """Cached GET. Returns the raw bytes (from disk when cached)."""
        path = self._path(url, suffix)
        if not self.refresh and path.exists():
            self.hits += 1
            return path.read_bytes()
        raw = polite_get(url, headers=headers, timeout=timeout, min_interval=min_interval)
        self.misses += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(path)              # never leave a half-written cache file
        return raw

    def json(self, url: str, **kw):
        raw = self.get(url, suffix=".json", **kw)
        return _json.loads(raw.decode("utf-8-sig", errors="replace"))

    def text(self, url: str, **kw) -> str:
        raw = self.get(url, suffix=".html", **kw)
        return raw.decode("utf-8", errors="replace")

    def stats(self) -> dict:
        return {"cache_hits": self.hits, "cache_misses": self.misses}


def fetch_cache(family: str, *, refresh: bool = False) -> FetchCache:
    """FetchCache rooted at ``data/ingest/cache/<family>``."""
    return FetchCache(CACHE_ROOT / family, refresh=refresh)


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

    Output defaults to ``data/ingest/newsrc-<name>.jsonl`` (gitignored).
    """
    result = enumerator.enumerate().finalize()
    check_no_liveness(result)
    if save:
        base_dir = pathlib.Path(out_dir) if out_dir else (DATA_DIR / "ingest")
        path = base_dir / f"newsrc-{enumerator.name}.jsonl"
        written = write_jsonl(path, result.rows)
        result.stats["written"] = written
        result.stats["output"] = str(path)
        result.stats["sha256"] = _sha256_file(path)
    return result


def format_result(result: IngestResult) -> str:
    """Human-readable one-result report for CLI runs."""
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
    if "cache_hits" in stats or "cache_misses" in stats:
        lines.append(
            f"  cache: hits={stats.get('cache_hits', 0)} misses={stats.get('cache_misses', 0)}"
        )
    handled = {"rows", "redacted", "by_status", "by_country", "written", "output", "sha256",
               "cache_hits", "cache_misses"}
    for key in sorted(stats):
        if key in handled or isinstance(stats[key], (dict, list)):
            continue
        lines.append(f"  {key}: {stats[key]}")
    by_country = stats.get("by_country") or {}
    if by_country:
        top = list(by_country.items())[:10]
        lines.append("  by country (top 10): " + ", ".join(f"{k}={v}" for k, v in top))
    by_status = stats.get("by_status") or {}
    if by_status:
        lines.append(f"  by status: {by_status}")
    return "\n".join(lines)


def run_cli(enumerator: Enumerator, argv=None) -> int:
    """Argparse CLI for a family module's ``__main__``."""
    import argparse
    parser = argparse.ArgumentParser(
        prog=f"wfd.ingest.newsrc.{enumerator.name}",
        description="Enumerate one new-source family "
                    "(writes data/ingest/newsrc-<name>.jsonl).",
    )
    parser.add_argument("--no-save", action="store_true",
                        help="enumerate only; do not write the jsonl")
    parser.add_argument("--out", default=None,
                        help="directory for the output jsonl (default: data/ingest)")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the fetch cache and refetch everything")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of items enumerated (tests/debug)")
    args = parser.parse_args(argv)
    if args.refresh:
        enumerator.refresh = True
    if args.limit is not None:
        enumerator.limit = args.limit
    try:
        result = run_one(enumerator, save=not args.no_save, out_dir=args.out)
    except Exception as exc:  # noqa: BLE001 — report the failure, keep the CLI honest
        print(f"[{enumerator.name}] FAIL: {type(exc).__name__}: {exc}")
        return 1
    print(format_result(result))
    return 0

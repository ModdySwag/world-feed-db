"""wfd.ingest.base — shared ingest contracts + polite HTTP helpers.

Every ingester returns an :class:`IngestResult`. Enumeration NEVER claims liveness:
status stays ``unknown`` until a health check says otherwise (honest states only,
see PLAN A1).

Polite fetch defaults come from the active profile's settings
(``min_request_interval_s``, ``http_timeout_s``, ``user_agent``).
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .. import profile
from ..schema import CameraRow

DATA_DIR = profile.REPO_ROOT / "data"

_last_request_at: dict = {}


def today_iso() -> str:
    return _dt.date.today().isoformat()


def polite_get(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    retries: int = 2,
    backoff: float = 2.0,
    min_interval: Optional[float] = None,
) -> bytes:
    """One-request-at-a-time polite GET with UA and bounded retries.

    Retries transient failures (network errors, 5xx, timeouts); raises
    immediately on 4xx. Returns the raw body bytes.
    """
    conf = profile.settings()
    timeout_s = float(timeout if timeout is not None else conf.get("http_timeout_s", 25))
    interval = float(min_interval if min_interval is not None else conf.get("min_request_interval_s", 1.0))
    host = urllib.parse.urlsplit(url).netloc

    wait = interval - (time.monotonic() - _last_request_at.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": conf.get("user_agent", "world-feed-db/0.1"), **(headers or {})},
    )
    attempt = 0
    while True:
        try:
            _last_request_at[host] = time.monotonic()
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            attempt += 1
            if attempt > retries:
                raise
            time.sleep(backoff * attempt)
        except (urllib.error.URLError, OSError, TimeoutError):
            attempt += 1
            if attempt > retries:
                raise
            time.sleep(backoff * attempt)


def polite_json(url: str, **kw):
    raw = polite_get(url, **kw)
    return json.loads(raw.decode("utf-8-sig", errors="replace"))


@dataclass
class IngestResult:
    """Normalized result of one ingest/enumeration run."""

    family: str
    provenance: str = "public_by_design"
    snapshot_date: str = ""
    source_ref: str = ""                 # dataset URL / commit / directory reference
    notes: str = ""
    rows: list = field(default_factory=list)   # list[CameraRow]
    stats: dict = field(default_factory=dict)

    def add(self, row: CameraRow) -> CameraRow:
        self.rows.append(row)
        return row

    def finalize(self) -> "IngestResult":
        for r in self.rows:
            r.finalize()
        self.stats.setdefault("rows", len(self.rows))
        self.stats.setdefault("redacted", sum(1 for r in self.rows if r.was_redacted))
        self.stats.setdefault("by_status", tally(r.status for r in self.rows))
        self.stats.setdefault("by_country", tally(r.country for r in self.rows if r.country))
        return self


def tally(values: Iterable[str]) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def write_jsonl(path, rows: Iterable[CameraRow]) -> int:
    """Write rows to JSONL (one dict per line). Returns the count written."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            r.finalize()
            fh.write(json.dumps(r.as_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n


def clean_str(v) -> str:
    return "" if v is None else str(v).strip()


def clean_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

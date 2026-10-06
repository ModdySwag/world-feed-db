"""wfd.schema — registry row model, vocabulary enums, and URL redaction (S5 §B).

Law of the land (see PLAN D6 + research/osint/S5 §B):
- exposure_aggregator rows are NEVER probed; status stays ``unverified``;
  snapshot_date is required; geo_confidence is ``low``.
- credentials are redacted at parse time, BEFORE storage or logging;
  ``was_redacted`` records that it happened.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


class Provenance(str, enum.Enum):
    """Where a row came from."""

    PUBLIC = "public_by_design"       # operator / agency / API published
    EXPOSURE = "exposure_aggregator"  # insecam-class dataset aggregation (flagged category, D6)
    DIRECTORY = "aggregator_directory"  # third-party directory of public feeds (owner decision 2026-10-06)
    UNKNOWN = "unknown"


class Health(str, enum.Enum):
    """Honest states only — never fake a quiet state (S4/A1)."""

    LIVE = "live"
    STALE = "stale"
    DEAD = "dead"
    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"     # exposure rows: never verified by us (B0)
    QUARANTINED = "quarantined"   # lifecycle (S5 §C)
    RETIRED = "retired"


class Protocol(str, enum.Enum):
    HLS = "hls"
    MJPEG = "mjpeg"
    JPEG = "jpeg"
    RTSP = "rtsp"
    YOUTUBE = "youtube"
    IFRAME = "iframe"
    UNKNOWN = "unknown"


@dataclass
class CameraRow:
    """One camera/feed registry row (field set follows PLAN §C1: GEV + L-E-S merged)."""

    url: str = ""
    source_family: str = ""              # e.g. "jrw-2019", "godeye-2026-05", "les", "caltrans"
    provenance: str = Provenance.UNKNOWN.value
    name: str = ""
    country: str = ""
    city: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    protocol: str = Protocol.UNKNOWN.value
    status: str = Health.UNKNOWN.value
    snapshot_date: str = ""              # ISO date of the snapshot the row came from (exposure: required)
    fetch_date: str = ""                 # ISO date we fetched/enumerated it
    last_verified: str = ""
    geo_confidence: str = ""             # "low" for exposure_aggregator rows
    was_redacted: bool = False           # credentials stripped at ingest
    credential_present: bool = False     # a credential was present pre-redaction
    attribution: str = ""                # required for agency data (e.g. "Powered by TfL Open Data")
    official_url: str = ""               # canonical operator page where known
    tags: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    camera_id: str = ""                  # stable: sha256(source_family|url)[:16]

    def finalize(self) -> "CameraRow":
        if not self.camera_id:
            self.camera_id = stable_id(self.source_family, self.url)
        if not self.fetch_date:
            import datetime as _dt
            self.fetch_date = _dt.date.today().isoformat()
        return self

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def stable_id(source_family: str, url: str) -> str:
    """Stable camera id — same family+url always yields the same id."""
    return hashlib.sha256(f"{source_family}|{url}".encode("utf-8")).hexdigest()[:16]


# --- credential redaction (S5 B1/B2 — redact-then-store) -------------------------------

REDACTED = "<redacted>"

_SENSITIVE_QUERY_KEYS = frozenset({
    "u", "user", "username", "usr", "login", "p", "pass", "password", "pwd",
    "passwd", "credential", "auth", "token", "key", "apikey", "api_key",
    "secret", "session", "sessionid", "sig", "signature", "wmsauthsign", "otp",
})

_USERINFO_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@]+)@(?P<rest>.+)$"
)


def redact_url(url: str) -> tuple[str, bool]:
    """Strip embedded credentials from a URL.

    Removes ``user:pass@`` userinfo and scrubs values of sensitive query
    parameters (case-insensitive). Returns ``(redacted_url, was_redacted)``.
    """
    if not url:
        return url, False

    try:
        parts = urllib.parse.urlsplit(url)
        has_userinfo = parts.username is not None or parts.password is not None
    except ValueError:
        # weird netloc — fall back to a straight regex (userinfo only)
        m = _USERINFO_RE.match(url)
        if not m:
            return url, False
        return m.group("scheme") + m.group("rest"), True

    changed = False

    netloc = parts.netloc
    if has_userinfo:
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        netloc = f"{host}{port}"
        changed = True

    query = parts.query
    if query:
        pairs = []
        for piece in query.split("&"):
            key, sep, _value = piece.partition("=")
            if sep and key.strip().lower() in _SENSITIVE_QUERY_KEYS:
                pairs.append(f"{key}={REDACTED}")
                changed = True
            else:
                pairs.append(piece)
        query = "&".join(pairs)

    if not changed:
        return url, False
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)), True


def redact_and_flag(url: str) -> tuple[str, bool, bool]:
    """Returns ``(url, was_redacted, credential_present)`` for ingest callers."""
    red, was = redact_url(url)
    return red, was, was


# --- city display semantics (wfd.geo enrichment) ---------------------------------------

# Placeholder "cities" seen in source data that carry no information; treated as
# empty by the display and geocoding paths (never shown as a city name).
CITY_JUNK = frozenset({"", "-", "--", "n/a", "na", "none", "null", "unknown", "?", "??"})


def effective_city(city: str, city_geo: str = "") -> str:
    """The city to display: the source value when it is real, else the geocoded
    fallback (``wfd.geo``). Returns "" when neither carries a usable name."""
    for candidate in (city, city_geo):
        c = (candidate or "").strip()
        if c and c.lower() not in CITY_JUNK:
            return c
    return ""

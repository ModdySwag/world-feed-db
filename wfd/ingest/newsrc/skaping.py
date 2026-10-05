"""wfd.ingest.newsrc.skaping — Skaping webcam platform enumerator (build unit NS).

Skaping (skaping.com) is a vendor platform that publishes its customers'
(operators') own webcams through public player pages. Family ``skaping``.

Enumeration path (verified live 2026-10-05/06; re-verified live 2026-10-06 —
877 ``<loc>`` entries, incl. the three Grouse Mountain pages):

1. ``GET https://www.skaping.com/sitemap.players.xml`` — 877 player pages
   across 307 operator groups. NOTE (observed drift): 874 locs live on
   ``www.skaping.com/<group>/<slug...>`` and 3 are white-label Skaping players
   on other hosts (``wbcm.it``, ``weathercam.kystnor.no``) — those are kept,
   with ``meta["group"]`` set to the host and ``meta["slug"]`` to the path.
   Live-only pages are mostly excluded from the sitemap by the vendor, but
   NOT entirely — two ``/live`` pages ARE present (``saint-lary/les-merlans/live``,
   ``saint-lary/bouleaux/live``; ``StreamMedia`` ctor -> ``meta["media_kind"]="stream"``,
   og:image is a ``skaping2.quanteec.com`` live thumbnail).
2. Per player page (cache ``.html``; ~10 KB real payloads): parse
   ``<title>``, ``<link rel="canonical">``, ``<meta property="og:image">``
   (CURRENT latest capture — a timestamped
   ``skaping.s3.gra.io.cloud.ovh.net/<group>/<slug>/YYYY/MM/DD/large/HH-MM.jpg``),
   ``place:location:latitude/longitude`` and the inline
   ``Launcher.start($('#skaper'), '<style>', new ImageMedia(<id>, "<media>",
   DateUtil.dbDateToDate("<db date>"), ...), {<config JSON>})`` call.
3. The config's ``explore.data`` cams list carries per-view POV records
   (``type_of_view``, ``last_media_date``, ``is_online``, ``player_url``,
   ``last_media``). This page's OWN POV is the one whose ``player_url`` equals
   the page's canonical URL; its ``is_online`` goes to ``meta["is_online"]``
   (NEVER to ``row.status`` — enumeration never claims liveness). When a
   ``<canonical>/live`` sibling POV exists, its quanteec
   ``.../thumbnail.jpg`` is recorded in ``meta["live_thumbnail"]``.
   White-label pages carry no ``explore`` block (fields simply absent).

Row mapping: ``url`` = the CANONICAL PLAYER PAGE (e.g.
``https://www.skaping.com/grouse-mountain/peak-cam``), protocol ``jpeg`` (the
page shows a ~10-min-cadence refreshed JPEG; ``/video`` subpages serve an mp4 —
their media kind is kept in ``meta["media_kind"]``). The timestamped S3 capture
URL is NEVER the row URL (it drifts); it is recorded informational-only in
``meta["latest_capture_at_enumeration"]`` (+ ``meta["og_image"]``,
``meta["latest_capture_date"]``). All URLs are routed through
:func:`wfd.schema.redact_and_flag`. ``name`` = page title (fallback
``<group>/<slug>``). ``lat``/``lon`` come from the page's ``place:location``
meta (range-checked). ``country`` is set ONLY where cleanly inferable
(explicit hints: ``grouse-mountain`` -> ``CA``; host ``weathercam.kystnor.no``
-> ``NO``) — everything else stays ``""`` pending a geo pass (no guessing).

Resumability: every fetch goes through the per-family
:class:`~wfd.ingest.newsrc.base.FetchCache` (``data/ingest/cache/skaping/``,
one file per URL). A killed ~877-page run loses nothing: re-issue the same
command and cached pages are skipped (``--limit N`` caps players processed,
used to chunk long runs). 429/5xx are retried with backoff (:data:`RETRY_DELAYS`).

robots: skaping.com disallows only ``/ccl.php*``, ``/showroom/*``,
``/about/*?*``, ``/player/tv`` — player pages + the sitemap are allowed; those
paths are never fetched here.

Run::  py -3.11 -m wfd.ingest.newsrc.skaping
Writes:  data/ingest/newsrc-skaping.jsonl (gitignored)
"""
from __future__ import annotations

import html as _html
import json
import re
import time

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_float, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "skaping"
SITEMAP_URL = "https://www.skaping.com/sitemap.players.xml"
ATTRIBUTION = "Skaping (skaping.com) — operator webcam players"

# 429 / transient backoff between page-fetch attempts (seconds). Successful
# fetches are cached, so a killed run resumes with zero loss.
RETRY_DELAYS = (5.0, 15.0, 45.0)

# Country hints — ONLY where the mapping is cleanly inferable and verified.
# Everything else stays "" (country is deliberately not guessed while a geo
# pass over meta/lat-lon is pending).
GROUP_COUNTRY_HINTS = {
    "grouse-mountain": "CA",          # Grouse Mountain Resorts, North Vancouver BC
}
HOST_COUNTRY_HINTS = {
    "weathercam.kystnor.no": "NO",    # Norwegian operator host (Port of Alta, 69.98N 23.28E)
}

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"([A-Za-z:_-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_LAUNCHER_RE = re.compile(r"Launcher\.start\(")
_MEDIA_CTOR_RE = re.compile(r"new\s+(\w*Media)\(")
_MEDIA_ID_RE = re.compile(r"^\s*(\d+)")
_MEDIA_URL_RE = re.compile(r'"([^"]*)"')
_MEDIA_DATE_RE = re.compile(r'dbDateToDate\(\s*"([^"]*)"\s*\)')
_STYLE_ID_RE = re.compile(r"Launcher\.start\(\$\('#skaper'\),\s*'(\d+)'")


# --- pure helpers (fixture-testable) ------------------------------------------

def _collapse(text) -> str:
    return " ".join(_html.unescape(str(text or "")).split())


def _attrs(tag: str) -> dict:
    out = {}
    for m in _ATTR_RE.finditer(tag):
        out[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def _meta_content(html_text: str, prop: str) -> str:
    """First ``<meta property|name="prop">`` content value ("" when absent)."""
    for m in _META_TAG_RE.finditer(html_text or ""):
        a = _attrs(m.group(0))
        if (a.get("property") or a.get("name") or "").lower() == prop.lower():
            return _collapse(a.get("content"))
    return ""


def _link_href(html_text: str, rel: str) -> str:
    """First ``<link rel="rel">`` href value ("" when absent)."""
    for m in _LINK_TAG_RE.finditer(html_text or ""):
        a = _attrs(m.group(0))
        if a.get("rel", "").lower() == rel.lower():
            return _collapse(a.get("href"))
    return ""


def _norm_url(url) -> str:
    """Comparison/storage form: unescaped, fragment+query dropped, no trailing '/'."""
    u = _html.unescape(clean_str(url))
    u = u.split("#", 1)[0].split("?", 1)[0]
    return u.rstrip("/")


def split_url(url: str):
    """``(host, path_segments)`` for one URL (query/fragment stripped)."""
    raw = _norm_url(url)
    rest = raw.split("://", 1)[-1]
    host, _, path = rest.partition("/")
    return host, [s for s in path.split("/") if s]


def group_slug_parts(host: str, segs: list):
    """``(group, slug)`` split.

    ``www.skaping.com``: group = first path segment, slug = the rest joined
    (slugs may carry sub-paths, e.g. ``lorient/rade/port-kernevel``).
    White-label hosts: group = host (the operator brand), slug = whole path.
    """
    if not segs:
        return host, ""
    if host == "www.skaping.com":
        return segs[0], "/".join(segs[1:])
    return host, "/".join(segs)


def parse_sitemap(xml_text: str) -> list:
    """All unique ``<loc>`` URLs, document order (junk/dupes dropped)."""
    out, seen = [], set()
    for m in _LOC_RE.finditer(xml_text or ""):
        loc = _norm_url(m.group(1))
        if not loc.startswith("http") or loc in seen:
            continue
        seen.add(loc)
        out.append(loc)
    return out


def _scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index of the matching closer for ``text[start] == open_ch`` (-1 when none).

    JSON/JS string literals (double-quoted, backslash escapes) are skipped so
    braces/parens inside strings never break the balance.
    """
    depth = 0
    i = start
    in_str = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def extract_launcher(html_text: str):
    """Parse the inline ``Launcher.start(...)`` call (media args + config JSON).

    Returns ``None`` when the page has no Launcher call. Otherwise a dict:
    ``media_kind`` (``"image"``/``"video"``/``""``), ``media_id`` (int|None),
    ``media_url``, ``media_date``, ``style_id``, ``cfg`` (dict|None),
    ``cfg_error`` (str|None).
    """
    m = _LAUNCHER_RE.search(html_text or "")
    if not m:
        return None
    out = {"media_kind": "", "media_id": None, "media_url": "",
           "media_date": "", "style_id": "", "cfg": None, "cfg_error": None}
    try:
        seg = html_text[m.start():]
        style = _STYLE_ID_RE.search(seg)
        if style:
            out["style_id"] = style.group(1)
        ctor = _MEDIA_CTOR_RE.search(seg)
        if ctor:
            kind = ctor.group(1)
            out["media_kind"] = ("video" if kind.endswith("VideoMedia")
                                 else "image" if kind.endswith("ImageMedia")
                                 else "stream" if kind.endswith("StreamMedia")
                                 else kind.lower())
            open_idx = ctor.end() - 1
            close_idx = _scan_balanced(seg, open_idx, "(", ")")
            if close_idx < 0:
                raise ValueError("unbalanced media args")
            media_args = seg[open_idx + 1:close_idx]
            mid = _MEDIA_ID_RE.match(media_args)
            if mid:
                out["media_id"] = int(mid.group(1))
            mu = _MEDIA_URL_RE.search(media_args)
            if mu:
                mu = _html.unescape(mu.group(1))
                out["media_url"] = ("https:" + mu) if mu.startswith("//") else mu
            md = _MEDIA_DATE_RE.search(media_args)
            if md:
                out["media_date"] = md.group(1)
            after = seg[close_idx + 1:]
            comma = re.match(r"\s*,\s*", after)
            if comma:
                cfg_start = close_idx + 1 + comma.end()
                cfg_end = _scan_balanced(seg, cfg_start, "{", "}")
                if cfg_end < 0:
                    raise ValueError("unbalanced config object")
                try:
                    out["cfg"] = json.loads(seg[cfg_start:cfg_end + 1])
                except ValueError as exc:
                    out["cfg_error"] = f"JSONDecodeError: {exc}"
    except Exception as exc:  # noqa: BLE001 — a broken call must not kill the page parse
        out["cfg_error"] = out["cfg_error"] or f"{type(exc).__name__}: {exc}"
    return out


def _iter_povs(cfg):
    """Yield ``(pov_id, pov_dict)`` from the config's ``explore.data`` cams."""
    if not isinstance(cfg, dict):
        return
    data = ((cfg.get("explore") or {}).get("data")) if isinstance(cfg.get("explore"), dict) else None
    if not isinstance(data, list):
        return
    for cam in data:
        if not isinstance(cam, dict):
            continue
        povs = cam.get("povs")
        if not isinstance(povs, dict):
            continue
        for pid, pov in povs.items():
            if isinstance(pov, dict):
                yield pid, pov


def _coord(raw, limit: float):
    val = clean_float(raw)
    if val is not None and not (-limit <= val <= limit):
        return None
    return val


def _live_thumbnail(cfg, match_url: str) -> str:
    """Quanteec live thumbnail of this page's ``/live`` sibling POV ("" when none)."""
    if not match_url or not isinstance(cfg, dict):
        return ""
    want = match_url + "/live"
    for _pid, pov in _iter_povs(cfg):
        if _norm_url(pov.get("player_url")) == want:
            lm = clean_str(_html.unescape(pov.get("last_media")))
            if "skaping.quanteec.com" in lm and lm.lower().endswith((".jpg", ".jpeg", ".png")):
                return lm
            return ""
    return ""


def parse_player_page(html_text: str, url: str = "") -> dict:
    """Parse one Skaping player page into the fields the row mapper needs."""
    html_text = html_text or ""
    launch = extract_launcher(html_text)
    canonical = _norm_url(_link_href(html_text, "canonical"))
    match_url = canonical or _norm_url(url)
    tm = _TITLE_RE.search(html_text)
    title = _collapse(tm.group(1)) if tm else ""

    is_online = None
    if launch and isinstance(launch.get("cfg"), dict):
        for _pid, pov in _iter_povs(launch["cfg"]):
            if _norm_url(pov.get("player_url")) == match_url:
                if isinstance(pov.get("is_online"), bool):
                    is_online = pov["is_online"]
                break

    return {
        "url": clean_str(url),
        "canonical": canonical,
        "title": title,
        "og_title": _meta_content(html_text, "og:title"),
        "og_image": _meta_content(html_text, "og:image"),
        "lat": _coord(_meta_content(html_text, "place:location:latitude"), 90.0),
        "lon": _coord(_meta_content(html_text, "place:location:longitude"), 180.0),
        "has_launcher": launch is not None,
        "media_kind": launch.get("media_kind", "") if launch else "",
        "media_id": launch.get("media_id") if launch else None,
        "media_url": launch.get("media_url", "") if launch else "",
        "media_date": launch.get("media_date", "") if launch else "",
        "cfg_error": launch.get("cfg_error") if launch else None,
        "is_online": is_online,
        "live_thumbnail": _live_thumbnail(launch.get("cfg"), match_url) if launch else "",
    }


def country_for(host: str, group: str) -> str:
    """Country code ONLY when cleanly inferable (hints); "" otherwise."""
    if host in HOST_COUNTRY_HINTS:
        return HOST_COUNTRY_HINTS[host]
    if group in GROUP_COUNTRY_HINTS:
        return GROUP_COUNTRY_HINTS[group]
    return ""


def row_from_page(page: dict, *, family: str = FAMILY) -> CameraRow | None:
    """Map one parsed player page to a CameraRow (None when no usable URL).

    Every row enters ``status="unknown"``; the page's own ``is_online`` flag is
    meta-only. The canonical player page is the row URL — never the timestamped
    S3 capture URL (that is informational, in meta).
    """
    url_norm = _norm_url(page.get("canonical") or page.get("url") or "")
    if not url_norm:
        return None
    host, segs = split_url(url_norm)
    group, slug = group_slug_parts(host, segs)
    name = (page.get("title") or page.get("og_title")
            or (f"{group}/{slug}" if group else slug) or url_norm)

    url, was_red, cred = redact_and_flag(url_norm)
    og_image = clean_str(page.get("og_image"))
    capture = og_image or clean_str(page.get("media_url"))
    thumb = clean_str(page.get("live_thumbnail"))
    og_r = redact_and_flag(og_image) if og_image else ("", False, False)
    cap_r = redact_and_flag(capture) if capture else ("", False, False)
    thumb_r = redact_and_flag(thumb) if thumb else ("", False, False)

    meta = {
        "group": group,
        "slug": slug,
        "host": host,
        "title": page.get("title") or "",
        "og_image": og_r[0],
        # informational ONLY — the latest capture URL at enumeration time; it
        # drifts with every capture and must never be used as the row URL.
        "latest_capture_at_enumeration": cap_r[0],
        "latest_capture_date": page.get("media_date") or "",
        "media_kind": page.get("media_kind") or "",
        "media_id": page.get("media_id"),
    }
    if page.get("is_online") is not None:
        meta["is_online"] = bool(page["is_online"])
    if thumb_r[0]:
        meta["live_thumbnail"] = thumb_r[0]

    return CameraRow(
        url=url,
        source_family=family,
        provenance=Provenance.PUBLIC.value,
        name=name,
        country=country_for(host, group),
        lat=page.get("lat"),
        lon=page.get("lon"),
        protocol=Protocol.JPEG.value,     # page shows a refreshed JPEG (media_kind says mp4 for /video)
        status=Health.UNKNOWN.value,      # enumeration never claims liveness
        attribution=ATTRIBUTION,
        was_redacted=bool(was_red or og_r[1] or cap_r[1] or thumb_r[1]),
        credential_present=bool(cred or og_r[2] or cap_r[2] or thumb_r[2]),
        tags=["webcam"],
        meta=meta,
    )


def _fetch_with_retry(cache, url: str, *, suffix: str, delays=None) -> bytes:
    """``cache.get`` with 429/5xx backoff (honors Retry-After; capped at 60 s)."""
    seq = RETRY_DELAYS if delays is None else delays
    for attempt in range(len(seq) + 1):
        try:
            return cache.get(url, suffix=suffix)
        except Exception as exc:  # noqa: BLE001 — classify, retry transients
            code = getattr(exc, "code", None)
            if code not in (429, 500, 502, 503, 504) or attempt >= len(seq):
                raise
            retry_after = None
            headers = getattr(exc, "headers", None)
            if headers is not None:
                try:
                    retry_after = float(headers.get("Retry-After"))
                except (TypeError, ValueError):
                    retry_after = None
            time.sleep(min(retry_after, 60.0) if retry_after else seq[attempt])
    raise RuntimeError("unreachable")  # pragma: no cover


class SkapingEnumerator(Enumerator):
    """Enumerate Skaping player pages from ``sitemap.players.xml`` (~877 players)."""

    name = FAMILY
    source_ref = SITEMAP_URL
    provenance = Provenance.PUBLIC.value
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=self.provenance,
            snapshot_date=today_iso(),
            source_ref=self.source_ref,
            notes=("sitemap.players.xml + per-player-page parse (og:image, Launcher "
                   "config, own-POV is_online, live thumbnail); published flags stay "
                   "in meta, rows stay 'unknown'; captures recorded informational-only"),
        )

        sitemap_raw = _fetch_with_retry(cache, SITEMAP_URL, suffix=".xml")
        locs = parse_sitemap(sitemap_raw.decode("utf-8", errors="replace"))
        players_total = len(locs)
        if self.limit is not None:
            locs = locs[: max(0, int(self.limit))]
        if not locs:
            result.notes += "; WARNING: sitemap returned no player pages"
            result.stats["players_total"] = players_total
            result.stats.update(cache.stats())
            return result.finalize()

        seen: set = set()
        failures: list = []
        dupes = offline = online = no_capture = no_launcher = cfg_fail = non_skaping = 0
        for loc in locs:
            try:
                raw = _fetch_with_retry(cache, loc, suffix=".html")
            except Exception as exc:  # noqa: BLE001 — one dead page must not kill the run
                failures.append({"url": loc, "error": f"{type(exc).__name__}: {exc}"})
                continue
            try:
                page = parse_player_page(raw.decode("utf-8", errors="replace"), loc)
            except Exception as exc:  # noqa: BLE001 — parse guard
                failures.append({"url": loc, "error": f"parse: {type(exc).__name__}: {exc}"})
                continue
            row = row_from_page(page)
            if row is None:
                failures.append({"url": loc, "error": "no usable canonical URL"})
                continue
            if not page["has_launcher"]:
                no_launcher += 1
            if page["cfg_error"]:
                cfg_fail += 1
            if not page["og_image"] and not page["media_url"]:
                no_capture += 1
            if row.meta["host"] != "www.skaping.com":
                non_skaping += 1
            flag = row.meta.get("is_online")
            if flag is False:
                offline += 1
            elif flag is True:
                online += 1
            if row.url in seen:
                dupes += 1
                continue
            seen.add(row.url)
            result.add(row)

        # progress across the full sitemap (resume telemetry; read-only use of
        # the cache's key helper — base exposes no public path lookup)
        pages_in_cache = 0
        for u in parse_sitemap(sitemap_raw.decode("utf-8", errors="replace")):
            try:
                if cache._path(u, ".html").exists():
                    pages_in_cache += 1
            except Exception:  # noqa: BLE001
                pass

        if result.rows:
            probe = self._probe_capture(cache, result.rows)
            if probe:
                result.stats["verified_capture"] = probe

        result.stats.update({
            "players_total": players_total,
            "players_processed": len(locs),
            "pages_in_cache": pages_in_cache,
            "pages_failed": len(failures),
            "dupes_dropped": dupes,
            "offline_flags": offline,
            "online_flags": online,
            "pages_without_capture_url": no_capture,
            "pages_without_launcher": no_launcher,
            "config_parse_failures": cfg_fail,
            "non_skaping_hosts": non_skaping,
        })
        if failures:
            result.stats["failures"] = failures
        result.stats.update(cache.stats())
        return result.finalize()

    @staticmethod
    def _probe_capture(cache, rows) -> dict | None:
        """Mechanism proof (NOT a liveness claim): fetch ONE recorded capture URL.

        Confirms the timestamped S3 capture recorded at enumeration time serves
        JPEG bytes. Never touches any row's status.
        """
        for row in rows:
            url = row.meta.get("og_image") or row.meta.get("latest_capture_at_enumeration")
            if not url:
                continue
            out = {"row_slug": row.meta.get("slug") or row.name, "url": url}
            try:
                raw = _fetch_with_retry(cache, url, suffix=".jpg")
                out["bytes"] = len(raw)
                out["content_type"] = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "unknown"
            except Exception as exc:  # noqa: BLE001 — probe failure must not kill enumeration
                out["error"] = f"{type(exc).__name__}: {exc}"
            return out
        return None


ENUMERATOR = SkapingEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

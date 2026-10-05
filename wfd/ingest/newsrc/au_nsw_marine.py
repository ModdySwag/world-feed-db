"""wfd.ingest.newsrc.au_nsw_marine — NSW marine/boating webcams (Transport for NSW).

Enumeration path (verified live 2026-10-06):

1. Hub: ``GET .../conditions-weather-and-tides/webcams`` -> HTML gallery page.
   NSW is known to serve an HTML stub to non-browser User-Agents ("some
   endpoints", ops rule + health-module pattern), so the hub is fetched with a
   TWO-STAGE strategy: default UA first; if the page is stub-shaped (short or
   no ``.../webcams/<slug>`` links) it is retried with a plain browser UA, and
   the stage that worked is recorded in ``stats["hub_stage"]``
   ("polite" | "browser"; "stub" if both attempts stayed stub-shaped).
   At build time both UAs returned the full 157 KB page (stage "polite") — the
   two-stage path is kept as documented anti-bot insurance.
   Sub-pages get the same two-stage treatment (stub marker: no
   ``widget.coastalcoms.com/video/`` iframe).

2. Sub-pages: extract ``href=".../webcams/<slug>"`` slugs (21 single-segment
   pages + the multi-segment ``iluka/yamba`` at build time = 22; the dossier's
   iluka/yamba 404 no longer reproduces — it is a live page now, so no slug is
   hardcoded as dead: a page that fails to fetch is counted in
   ``pages_failed`` and skipped, which "excludes a 404 iluka/yamba if seen").
   Per page, parse the webcam iframe
   ``<iframe title="...webcam" src="https://widget.coastalcoms.com/video/<UUID>">``
   (pages also carry a ``/weather/`` iframe — only ``/video/`` widgets count).

3. Widget pages: ``GET https://widget.coastalcoms.com/video/<UUID>`` and regex
   the FIRST ``https?://[^"'<> ]*\\.m3u8`` -> the CURRENT HLS URL
   (``d1nm4r8e5x1rwd.cloudfront.net`` or ``streaming-au.coastalcoms.com``).
   Widget fetch failure -> counted (``widget_fetch_failed``); no m3u8 in the
   page -> counted (``no_m3u8``) and skipped, never guessed.

Row mapping: one row per location; ``url`` = the m3u8 (``protocol="hls"``),
``name`` = location (iframe title minus a trailing " webcam", slug fallback),
``country="AU"``; ``meta`` = widget_uuid, page_slug, page_url, hub_url +
``drift_note``. Rows dedupe by URL (first page kept; ``dupes_dropped``).

Drift + liveness doctrine: coastalcoms rotates streams, so the widget page is
the ground truth — re-resolve UUID -> m3u8 on every sweep (``drift_note``);
stored URLs are NOT probed here and every row enters ``status="unknown"``
(enumeration never claims liveness; health sweeps decide later). Research on
2026-10-06 measured ~17/21 derived stream URLs 404ing — expected to recur.

Fetch plumbing: ``FetchCache`` (per-family, resumable) is keyed by URL only,
so the browser-UA retry is cached under ``<url>#ua-browser`` — the fragment is
not sent on the wire and only separates the two variants on disk. A
module-local retry wrapper adds 429/Retry-After handling on top of
``polite_get`` (which raises 4xx immediately). Base package untouched.

No network at import; network only via ``fetch_cache`` / ``polite_get``.

Runnable directly::

    py -3.11 -m wfd.ingest.newsrc.au_nsw_marine
"""
from __future__ import annotations

import re
from time import sleep as _sleep

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

HUB_URL = ("https://www.nsw.gov.au/driving-boating-and-transport/boating-and-marine/"
           "using-waterways-boating-and-transport-information/conditions-weather-and-tides/webcams")
SUBPAGE_ORIGIN = "https://www.nsw.gov.au"
WIDGET_BASE = "https://widget.coastalcoms.com/video"
ATTRIBUTION = "NSW Government (Transport for NSW) — marine webcams"
DRIFT_NOTE = ("stream URLs drift — re-resolve UUID -> m3u8 via the coastalcoms "
              "widget page on every sweep")

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BROWSER_HEADERS = {"User-Agent": BROWSER_UA}
# Cache-key separator for the browser-UA fetch variant (fragment: never sent).
BROWSER_CACHE_MARK = "#ua-browser"

STUB_MIN_BYTES = 1500      # length floor: empty/aborted bodies; JS-shell stubs are
                           # caught by the marker checks (full pages are ~150 KB)
SUBPAGE_WIDGET_MARKER = "widget.coastalcoms.com/video/"

_SUBPAGE_RE = re.compile(
    r"href=[\"'](/[^\"']*?/conditions-weather-and-tides/webcams/([^\"'?#\s]+))[\"']", re.I)
_IFRAME_RE = re.compile(r"<iframe\b[^>]*>", re.I)
_VIDEO_RE = re.compile(r"widget\.coastalcoms\.com/video/([0-9a-fA-F-]{36})")
_TITLE_ATTR_RE = re.compile(r"\btitle\s*=\s*[\"']([^\"']*)[\"']", re.I)
_M3U8_RE = re.compile(r"https?://[^\"'<> ]*\.m3u8")
_WEB_SUFFIX_RE = re.compile(r"\s*webcam\s*$", re.I)


def extract_pages(html: str) -> list:
    """``[(slug, path), ...]`` from hub hrefs — order kept, dupes dropped.

    Multi-segment slugs (``iluka/yamba``) are kept whole. The hub/social/reader
    links carry no ``/webcams/<slug>`` suffix and never match.
    """
    out, seen = [], set()
    for m in _SUBPAGE_RE.finditer(html or ""):
        path, slug = m.group(1), m.group(2).rstrip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append((slug, path))
    return out


def parse_webcam_iframe(html: str):
    """First webcam (/video/) iframe on a sub-page -> ``{widget_uuid, title}``.

    ``None`` when the page carries no camera widget. The /weather/ iframe that
    each page also embeds never matches (different src path).
    """
    for tag in _IFRAME_RE.findall(html or ""):
        vm = _VIDEO_RE.search(tag)
        if not vm:
            continue
        tm = _TITLE_ATTR_RE.search(tag)
        return {"widget_uuid": vm.group(1), "title": clean_str(tm.group(1)) if tm else ""}
    return None


def first_m3u8(html: str):
    """First ``https?://...m3u8`` URL in a widget page (None when absent)."""
    m = _M3U8_RE.search(html or "")
    return m.group(0) if m else None


def location_name(title: str, slug: str) -> str:
    """Row name: iframe title minus a trailing ' webcam'; slug fallback."""
    t = _WEB_SUFFIX_RE.sub("", clean_str(title)).strip()
    if t:
        return t
    tail = clean_str(slug).rstrip("/").split("/")[-1]
    return tail.replace("-", " ").title() or clean_str(slug)


def hub_is_stub(html: str) -> bool:
    """Stub-shaped hub (short or without any sub-page links)."""
    return len(html or "") < STUB_MIN_BYTES or not extract_pages(html)


def subpage_is_stub(html: str) -> bool:
    """Stub-shaped sub-page (short or without the webcam-widget marker)."""
    return len(html or "") < STUB_MIN_BYTES or SUBPAGE_WIDGET_MARKER not in (html or "")


def _retry_wait(exc, backoff: float, attempt: int) -> float:
    """Backoff seconds for one retry; honors a Retry-After header when present."""
    wait = backoff * (attempt + 1)
    headers = getattr(exc, "headers", None)
    ra = headers.get("Retry-After") if headers is not None and hasattr(headers, "get") else None
    try:
        wait = max(wait, min(float(ra), 30.0))
    except (TypeError, ValueError):
        pass
    return wait


def _retry_get(cache, url: str, *, headers=None, suffix: str = ".html", attempts: int = 3,
               backoff: float = 3.0) -> bytes:
    """``cache.get`` with retries for 429/transients.

    ``polite_get`` already retries 5xx internally but raises 4xx (including
    429) immediately — this module-local wrapper adds 429 + Retry-After
    handling and a final bounded retry for transient transport errors. Other
    4xx (404 etc.) still raise on the spot. Base package untouched.
    """
    last = None
    for attempt in range(attempts):
        try:
            return cache.get(url, headers=headers, suffix=suffix)
        except Exception as exc:  # noqa: BLE001 — classify, don't swallow
            code = getattr(exc, "code", None)
            if code is not None and code != 429 and code < 500:
                raise                                  # hard 4xx: propagate
            last = exc
            if attempt < attempts - 1:
                _sleep(_retry_wait(exc, backoff, attempt))
    raise last


def fetch_two_stage(cache, url: str, *, is_stub, suffix: str = ".html"):
    """``(html, stage)`` — default UA first, browser UA on stub-shaped pages.

    Stage is "polite" (default UA was fine), "browser" (browser-UA retry fixed
    a stub) or "stub" (both attempts still stub-shaped — caller decides).
    The browser variant is cached under ``url + '#ua-browser'`` (distinct cache
    key; the fragment never leaves this process).
    """
    html = _retry_get(cache, url, suffix=suffix).decode("utf-8", errors="replace")
    if not is_stub(html):
        return html, "polite"
    html2 = _retry_get(cache, url + BROWSER_CACHE_MARK, headers=BROWSER_HEADERS,
                       suffix=suffix).decode("utf-8", errors="replace")
    return html2, ("browser" if not is_stub(html2) else "stub")


class NswMarineEnumerator(Enumerator):
    """Enumerate NSW marine webcams: hub -> sub-pages -> coastalcoms widgets -> m3u8."""

    name = "au-nsw-marine"
    source_ref = HUB_URL
    attribution = ATTRIBUTION

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=Provenance.PUBLIC.value,
            snapshot_date=today_iso(),
            source_ref=HUB_URL,
            notes=("hub (two-stage UA) -> sub-page slugs -> webcam iframe UUID -> widget "
                   "page -> first m3u8; rows status=unknown (enumeration never claims "
                   "liveness); page/widget fetch failures and widget pages without an "
                   "m3u8 are counted and skipped; drift rule: re-resolve via the widget "
                   "page per sweep"),
        )

        # -- 1) hub (two-stage: stub detection + browser-UA retry) --------------
        try:
            hub_html, hub_stage = fetch_two_stage(cache, HUB_URL, is_stub=hub_is_stub)
        except Exception as exc:  # noqa: BLE001 — hub is the entry point: fail loudly
            raise RuntimeError(
                f"NSW hub fetch failed ({HUB_URL}): {type(exc).__name__}: {exc}") from exc
        result.stats["hub_stage"] = hub_stage

        pages = extract_pages(hub_html)
        result.stats["slugs_extracted"] = len(pages)
        if not pages:
            raise RuntimeError(
                f"NSW hub yielded 0 webcam sub-page slugs (hub_stage={hub_stage})")
        if self.limit is not None:
            pages = pages[: int(self.limit)]
            result.stats["limit"] = int(self.limit)
        result.stats["slugs"] = len(pages)

        # -- 2)+3) sub-pages -> widgets -> m3u8 ---------------------------------
        pages_failed: list = []
        pages_no_widget: list = []
        widget_fetch_failed: list = []
        no_m3u8: list = []
        stage_tally: dict = {}
        widgets = 0
        seen: set = set()
        dupes = 0

        for slug, path in pages:
            page_url = SUBPAGE_ORIGIN + path
            try:
                html, stage = fetch_two_stage(cache, page_url, is_stub=subpage_is_stub)
            except Exception as exc:  # noqa: BLE001 — one dead page must not kill the run
                pages_failed.append((slug, f"{type(exc).__name__}: {exc}"))
                continue
            stage_tally[stage] = stage_tally.get(stage, 0) + 1

            widget = parse_webcam_iframe(html)
            if not widget:
                pages_no_widget.append(slug)
                continue
            widgets += 1

            widget_url = f"{WIDGET_BASE}/{widget['widget_uuid']}"
            try:
                widget_html = _retry_get(cache, widget_url, suffix=".html").decode(
                    "utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001 — widget down: count + continue
                widget_fetch_failed.append((slug, f"{type(exc).__name__}: {exc}"))
                continue

            raw_m3u8 = first_m3u8(widget_html)
            if not raw_m3u8:
                no_m3u8.append(slug)
                continue
            url, was_red, cred = redact_and_flag(raw_m3u8)
            if url in seen:
                dupes += 1
                continue
            seen.add(url)
            result.add(CameraRow(
                url=url,
                source_family=self.name,
                provenance=Provenance.PUBLIC.value,
                name=location_name(widget["title"], slug),
                country="AU",
                protocol=Protocol.HLS.value,
                status=Health.UNKNOWN.value,      # enumeration never claims liveness
                snapshot_date=today_iso(),
                attribution=ATTRIBUTION,
                was_redacted=was_red,
                credential_present=cred,
                tags=["webcam", "marine"],
                meta={
                    "widget_uuid": widget["widget_uuid"],
                    "page_slug": slug,
                    "page_url": page_url,
                    "hub_url": HUB_URL,
                    "drift_note": DRIFT_NOTE,
                },
            ))

        result.stats.update({
            "pages_failed": len(pages_failed),
            "pages_no_widget": len(pages_no_widget),
            "widgets": widgets,
            "widget_fetch_failed": len(widget_fetch_failed),
            "no_m3u8": len(no_m3u8),
            "dupes_dropped": dupes,
            "subpage_stages": stage_tally,
            **cache.stats(),
        })
        if pages_failed:
            result.stats["pages_failed_slugs"] = [s for s, _ in pages_failed[:25]]
            result.stats["pages_failed_examples"] = [
                {"slug": s, "error": e} for s, e in pages_failed[:5]]
        if pages_no_widget:
            result.stats["pages_no_widget_slugs"] = pages_no_widget[:25]
        if widget_fetch_failed:
            result.stats["widget_fetch_failed_slugs"] = [s for s, _ in widget_fetch_failed[:25]]
        if no_m3u8:
            result.stats["no_m3u8_slugs"] = no_m3u8[:25]
        result.stats["rows"] = len(result.rows)
        return result.finalize()


ENUMERATOR = NswMarineEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

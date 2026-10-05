"""wfd.ingest.newsrc.streamdays — Streamdays-hosted webcams (build unit NS).

Family ``streamdays``: the commercial vendor live.streamdays.com publishes
embedded player URLs ``https://live.streamdays.com/<code>`` for its customers.
The registry rows are **Edinburgh Zoo's animal cams** (RZSS publishes them
itself via Streamdays) plus confirmed third-party embedders on the same vendor
platform ("extras"), fetched from the embedders' own public pages.

Enumeration (verified live 2026-10-06):

1. Zoo cam pages (``https://www.edinburghzoo.org.uk/animals/webcams/<x>-cam``
   + ``/webcams/rockhopper-cam``, discovered via the hub
   ``/animals/webcams`` which links them all) each embed a
   ``<script src="https://live.streamdays.com/<code>">`` tag. The koala cam
   was offline (page renders "There appears to be a problem", no code) —
   skipped and counted, never guessed.
2. Extras: the dossier's vendor "bespoke-hosting" pages
   (``/bespoke-hosting/derbyperegrines/left.html``,
   ``/bespoke-hosting/lenpicktrust/camera01.html``) BOTH 404 as of
   2026-10-06. The module still probes them (recorded in stats) and then
   falls back to the embedder's own human page — Derby Cathedral's project
   page (two live codes) and Len Pick Trust's stream page (moved to YouTube —
   no code emitted, recorded as skipped).
3. Rows store the STABLE player identity ``https://live.streamdays.com/<code>``
   only. **Drift rule:** the fulfil chain
   (``script -> /<code>/iframe?authorization=... -> takeoff.jetstre.am -> jetstre
   CDN chunklist``) carries short-lived signed tokens; tokens are resolved
   on demand and NEVER stored — not in the row, not in ``meta``, not in the
   fetch cache, not in logs. The chain documentation lives in
   ``meta["chain"]`` as a note string; see :data:`CHAIN_NOTE`.
4. Build-time proof (2026-10-06, penguin ``xb1u3eln``): bare script fetch
   403; script with ``Referer: <zoo cam page>`` 200 (1694 bytes, emits the
   iframe URL); iframe 200 (10395 bytes, flowplayer config carries the
   takeoff URL); takeoff 200 → ``n1.cdn.jetstre.am`` master playlist (235
   bytes); chunklist 200 (368 bytes, ``#EXT-X-MEDIA-SEQUENCE:298560052``,
   ``media_298560054.ts``); first segment 200, 243272 bytes, first bytes
   ``0x47400011`` (TS sync byte 0x47). Each live run re-resolves the chain
   for ONE cam (``meta["verified_chain"]`` / ``stats["chain_proof"]``) with
   the same observables — again without persisting any tokenized URL.

The script/iframe/proof fetches deliberately use :func:`wfd.ingest.base.polite_get`
directly (bytes in memory only) — the responses carry authorization tokens and
must never reach the on-disk fetch cache. Plain pages (zoo hub/cam pages,
embedder pages) go through the resumable per-family :class:`FetchCache`
(``data/ingest/cache/streamdays/``).

Rows always enter ``status="unknown"`` (enumeration never claims liveness).

Run::  py -3.11 -m wfd.ingest.newsrc.streamdays
Writes:  data/ingest/newsrc-streamdays.jsonl (gitignored)
"""
from __future__ import annotations

import re
from html import unescape as _unescape

from .base import Enumerator, fetch_cache, run_cli
from ..base import IngestResult, clean_str, polite_get, today_iso
from ...schema import CameraRow, Health, Protocol, Provenance, redact_and_flag

FAMILY = "streamdays"
SOURCE_REF = "https://www.edinburghzoo.org.uk/animals/webcams"
ATTRIBUTION = "RZSS Edinburgh Zoo / Streamdays — live.streamdays.com"
PLAYER_BASE = "https://live.streamdays.com"
ZOO_SITE = "https://www.edinburghzoo.org.uk"
ZOO_HUB_URL = "https://www.edinburghzoo.org.uk/animals/webcams"
# Working referer for the tokenized playlist fetches (verified 2026-10-06).
PLAYLIST_REFERER = "https://live.streamdays.com/"
CHAIN_NOTE = ("script -> iframe?authorization -> takeoff.jetstre.am -> jetstre CDN "
              "chunklist; tokens short-lived — resolve on demand, never store")

# Known zoo cam pages (name = the camera's published name; expected_code is the
# build-time verified player code — a mismatch is reported as drift, the LIVE
# code from the page always wins).
ZOO_PAGES = [
    {"embedder": "edinburgh-zoo", "path": "/animals/webcams/penguin-cam",
     "name": "Penguin Cam — Edinburgh Zoo", "expected_code": "xb1u3eln"},
    {"embedder": "edinburgh-zoo", "path": "/animals/webcams/koala-cam",
     "name": "Koala Cam — Edinburgh Zoo", "expected_code": ""},
    {"embedder": "edinburgh-zoo", "path": "/animals/webcams/lion-cam",
     "name": "Lion Cam — Edinburgh Zoo", "expected_code": "2ej7o9e5"},
    {"embedder": "edinburgh-zoo", "path": "/animals/webcams/giraffe-cam",
     "name": "Giraffe Cam — Edinburgh Zoo", "expected_code": "mlhwz7bt"},
    {"embedder": "edinburgh-zoo", "path": "/animals/webcams/tiger-cam",
     "name": "Tiger Cam — Edinburgh Zoo", "expected_code": "y4trtxbp"},
    {"embedder": "edinburgh-zoo", "path": "/webcams/rockhopper-cam",
     "name": "Rockhopper Cam — Edinburgh Zoo", "expected_code": "67u7il21"},
]

# Vendor-wide extras (low weight). ``bespoke_url`` is the vendor page from the
# dossier (404 as of 2026-10-06); ``page_url`` is the embedder's own human
# page used as drift fallback.
EXTRAS = [
    {
        "embedder": "derby-cathedral",
        "attribution": "Derby Cathedral Peregrine Project / Streamdays — live.streamdays.com",
        "name_hint": "Derby Cathedral Peregrine Cam",
        "bespoke_url": f"{PLAYER_BASE}/bespoke-hosting/derbyperegrines/left.html",
        "page_url": "https://derbyperegrines.blogspot.com/p/our-webcams.html",
        "tags": ["animal", "wildlife"],
    },
    {
        "embedder": "len-pick-trust",
        "attribution": "Len Pick Trust / Streamdays — live.streamdays.com",
        "name_hint": "Len Pick Trust Barn Owl Cam",
        "bespoke_url": f"{PLAYER_BASE}/bespoke-hosting/lenpicktrust/camera01.html",
        "page_url": "https://www.lenpicktrust.org.uk/live-video-stream/",
        "tags": ["animal", "wildlife"],
    },
]

# <script src="https://live.streamdays.com/<code>"> and iframe srcs alike.
# The lookahead keeps path words ("bespoke-hosting", "…/iframe?…") out of the
# code slot; the reserved set is belt-and-braces for the "<code>/iframe" form.
_CODE_RE = re.compile(r"https://live\.streamdays\.com/([A-Za-z0-9]{6,12})(?![A-Za-z0-9-])")
_RESERVED_CODES = frozenset({"iframe", "bespoke", "assets", "player", "embed"})
_HUB_LINK_RE = re.compile(r'href="(/animals/webcams/[a-z0-9][a-z0-9-]*|/webcams/[a-z0-9][a-z0-9-]*)"')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_LABEL_RE = re.compile(r"<b>\s*([^<]{1,120}?)\s*</b>")
_LABEL_WINDOW = 1200                       # chars to look back for a <b> label

_IFRAME_RE_TMPL = r"https://live\.streamdays\.com/{code}/iframe\?authorization=[^'\"\s]+"
_TAKEOFF_RE = re.compile(
    r"https://takeoff\.jetstre\.am/\?account=streamdays[^'\"]*?output=playlist\.m3u8[^'\"]*"
)


# --- pure parsers (fixture-testable) -------------------------------------------

def extract_codes(html: str) -> list:
    """Harvest streamdays player codes from a page.

    Returns ``[{"code", "label"}]`` in page order, first occurrence per code
    wins. ``label`` is the nearest preceding ``<b>…</b>`` text (used by
    embedder pages that label their cams), ``""`` when none is close.
    """
    out: list = []
    seen: set = set()
    for m in _CODE_RE.finditer(html or ""):
        code = m.group(1)
        if code.lower() in _RESERVED_CODES or code in seen:
            continue
        seen.add(code)
        window = (html or "")[max(0, m.start() - _LABEL_WINDOW): m.start()]
        labels = _LABEL_RE.findall(window)
        label = clean_str(_unescape(labels[-1])) if labels else ""
        out.append({"code": code, "label": label})
    return out


def harvest_hub_links(html: str) -> list:
    """Cam-page paths linked from the zoo webcams hub (ordered, unique)."""
    seen: list = []
    for path in _HUB_LINK_RE.findall(html or ""):
        if path not in seen:
            seen.append(path)
    return seen


def page_title(html: str) -> str:
    m = _TITLE_RE.search(html or "")
    if not m:
        return ""
    title = clean_str(_unescape(m.group(1)))
    for suffix in ("| Edinburgh Zoo", "| RZSS"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def player_url(code: str) -> str:
    """The STABLE player identity for a code — the only streamdays URL stored."""
    return f"{PLAYER_BASE}/{clean_str(code)}"


def row_from_code(code: str, *, name: str, embedder: str, embedder_page: str,
                  attribution: str, tags=None, verified_chain: bool = False) -> CameraRow:
    """One CameraRow for a player code (tokens never involved — see module doc)."""
    url, was_redacted, credential_present = redact_and_flag(player_url(code))
    return CameraRow(
        url=url,
        source_family=FAMILY,
        provenance=Provenance.PUBLIC.value,
        name=clean_str(name) or f"Streamdays cam {code}",
        country="GB",
        protocol=Protocol.HLS.value,
        status=Health.UNKNOWN.value,            # enumeration never claims liveness
        attribution=attribution,
        was_redacted=was_redacted,
        credential_present=credential_present,
        tags=list(tags or ["animal", "zoo"]),
        meta={
            "code": code,
            "embedder": embedder,
            "embedder_page": embedder_page,
            "chain": CHAIN_NOTE,
            "verified_chain": bool(verified_chain),
        },
    )


def parse_master_playlist(text: str) -> str:
    """First variant/chunklist URL from a master playlist ("" when none).

    Line-split parsing (not anchored regexes) so CRLF playlists parse cleanly.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http") and ".m3u8" in line:
            return line
    return ""


def parse_chunklist(text: str) -> dict:
    """``{"media_sequence", "segment", "last_segment"}`` from a media playlist.

    ``segment`` is the oldest listed media line; ``last_segment`` the newest.
    Segment URLs purge quickly, so consumers should prefer ``last_segment``
    (the chain proof does, with a re-poll retry).
    """
    media_sequence = None
    segments: list = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                media_sequence = int(line.split(":", 1)[1].strip())
            except ValueError:
                media_sequence = None
        elif line and not line.startswith("#") and ".ts" in line:
            segments.append(line)
    return {"media_sequence": media_sequence,
            "segment": segments[0] if segments else "",
            "last_segment": segments[-1] if segments else ""}


class StreamdaysEnumerator(Enumerator):
    """Enumerate Streamdays-embedded cams: Edinburgh Zoo + vendor extras."""

    name = FAMILY
    source_ref = SOURCE_REF
    provenance = Provenance.PUBLIC.value
    attribution = ATTRIBUTION

    # --- token-safety helpers --------------------------------------------------

    @staticmethod
    def _code_script(code: str, referer: str) -> bytes:
        """Fetch ``/<code>`` WITH a Referer (bare fetch 403s).

        Deliberately via ``polite_get`` — the response embeds a short-lived
        ``iframe?authorization=`` token, so it must never be written to the
        fetch cache or any other persistent store.
        """
        return polite_get(player_url(code), headers={"Referer": referer})

    def _resolve_check(self, code: str, referer: str) -> dict:
        """Metadata-only record of one code's script fetch (no bytes kept)."""
        out = {"code": code, "referer": referer}
        try:
            raw = self._code_script(code, referer)
            out["ok"] = True
            out["bytes"] = len(raw)
            out["emits_iframe"] = bool(
                re.search(_IFRAME_RE_TMPL.format(code=re.escape(code)),
                          raw.decode("utf-8", "replace"))
            )
        except Exception as exc:  # noqa: BLE001 — a failed check never kills the run
            out["ok"] = False
            out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    def _prove_chain(self, row: CameraRow) -> dict:
        """Resolve the FULL chain live for one cam — observables only, no tokens kept.

        ``script -> iframe?authorization -> takeoff playlist -> jetstre chunklist
        -> newest .ts (sync 0x47)``. Every fetch is in-memory via polite_get;
        nothing here is persisted anywhere. The segment step uses the FRESHEST
        segment and re-polls the chunklist once on failure — live segments purge
        within seconds, so the oldest one 404s intermittently (observed).
        """
        code = row.meta["code"]
        referer = row.meta["embedder_page"]
        proof: dict = {"code": code, "url": row.url, "verified": False,
                       "referer": referer, "stages": {}}

        # 0) bare fetch must fail — the Referer gate, recorded.
        try:
            polite_get(player_url(code))
            proof["stages"]["bare_script"] = {"http": 200, "expected": 403,
                                              "note": "referer gate NOT enforced"}
        except Exception as exc:  # noqa: BLE001 — 403 expected
            proof["stages"]["bare_script"] = {
                "http": getattr(exc, "code", None), "expected": 403,
                "note": "referer required (bare fetch failed as expected)",
            }

        # 1) script WITH Referer -> iframe URL
        script = self._code_script(code, referer)
        proof["stages"]["script"] = {"ok": True, "bytes": len(script), "referer": referer}
        m = re.search(_IFRAME_RE_TMPL.format(code=re.escape(code)),
                      script.decode("utf-8", "replace"))
        if not m:
            proof["stages"]["script"]["error"] = "no iframe URL emitted"
            return proof
        iframe_url = m.group(0)

        # 2) iframe HTML -> takeoff playlist URL
        iframe = polite_get(iframe_url, headers={"Referer": referer})
        proof["stages"]["iframe"] = {"ok": True, "bytes": len(iframe)}
        m = _TAKEOFF_RE.search(iframe.decode("utf-8", "replace"))
        if not m:
            proof["stages"]["iframe"]["error"] = "no takeoff playlist URL in iframe"
            return proof
        takeoff_url = m.group(0)

        # 3) takeoff -> master playlist (urllib follows the 307 session redirect)
        master = polite_get(takeoff_url, headers={"Referer": PLAYLIST_REFERER})
        proof["stages"]["takeoff"] = {"ok": True, "bytes": len(master)}
        if not master.lstrip().startswith(b"#EXTM3U"):
            proof["stages"]["takeoff"]["error"] = "not a playlist"
            return proof
        variant_url = parse_master_playlist(master.decode("utf-8", "replace"))
        if not variant_url:
            proof["stages"]["takeoff"]["error"] = "no variant url in master playlist"
            return proof

        # 4) chunklist -> media sequence + the FRESHEST segment
        chunklist = polite_get(variant_url, headers={"Referer": PLAYLIST_REFERER})
        parsed = parse_chunklist(chunklist.decode("utf-8", "replace"))
        proof["stages"]["chunklist"] = {"ok": True, "bytes": len(chunklist),
                                        "media_sequence": parsed["media_sequence"]}
        if not (parsed["last_segment"] or parsed["segment"]):
            proof["stages"]["chunklist"]["error"] = "no media segment in chunklist"
            return proof

        # 5) newest segment -> bytes + TS sync byte; one fresh re-poll on failure
        base = variant_url.split("?", 1)[0].rsplit("/", 1)[0]
        for attempt in (1, 2):
            seg = parsed["last_segment"] or parsed["segment"]
            seg_url = seg if seg.startswith("http") else f"{base}/{seg}"
            try:
                segment = polite_get(seg_url, headers={"Referer": PLAYLIST_REFERER})
            except Exception as exc:  # noqa: BLE001 — re-poll once, then give up honestly
                proof["stages"]["segment"] = {"ok": False, "attempt": attempt,
                                              "error": f"{type(exc).__name__}: {exc}"}
                if attempt == 2:
                    return proof
                chunklist = polite_get(variant_url, headers={"Referer": PLAYLIST_REFERER})
                parsed = parse_chunklist(chunklist.decode("utf-8", "replace"))
                continue
            proof["stages"]["segment"] = {
                "ok": True, "bytes": len(segment), "attempt": attempt,
                "head_hex": segment[:4].hex(),
                "sync_0x47": segment[:1] == b"\x47",
            }
            break
        proof["verified"] = bool(proof["stages"]["segment"].get("sync_0x47"))
        return proof

    # --- enumeration -----------------------------------------------------------

    def enumerate(self) -> IngestResult:
        cache = fetch_cache(self.name, refresh=self.refresh)
        result = IngestResult(
            family=self.name,
            provenance=self.provenance,
            snapshot_date=today_iso(),
            source_ref=self.source_ref,
            notes=("Edinburgh Zoo cams via live.streamdays.com player codes; stable "
                   "code URLs stored, tokenized fulfil chain resolved on demand and "
                   "never stored; extras: vendor bespoke pages 404 → embedder-page "
                   "fallback; rows stay 'unknown'"),
        )

        known = {p["path"]: p for p in ZOO_PAGES}
        hub_error = ""
        hub_new_pages: list = []
        try:
            hub_html = cache.text(ZOO_HUB_URL)
            hub_new_pages = [p for p in harvest_hub_links(hub_html) if p not in known]
        except Exception as exc:  # noqa: BLE001 — known list still enumerates
            hub_error = f"{type(exc).__name__}: {exc}"

        candidates = list(ZOO_PAGES) + [
            {"embedder": "edinburgh-zoo", "path": p, "name": "", "expected_code": ""}
            for p in hub_new_pages
        ]
        if self.limit is not None:
            candidates = candidates[: max(0, int(self.limit))]

        offline: list = []
        page_failed: list = []
        code_drift: list = []
        resolved: list = []
        resolve_failures: list = []
        planned: list = []              # (name, embedder, page_url, code, check)
        seen_urls: set = set()
        dupes_dropped = 0

        for cand in candidates:
            page_url = ZOO_SITE + cand["path"]
            try:
                page_html = cache.text(page_url)
            except Exception as exc:  # noqa: BLE001 — skip the page, keep the run alive
                page_failed.append({"page": page_url, "error": f"{type(exc).__name__}: {exc}"})
                continue
            codes = extract_codes(page_html)
            if not codes:
                # e.g. the koala cam at build time: page renders a placeholder,
                # no streamdays code emitted — skipped + counted, never guessed.
                offline.append({"page": page_url, "name": cand["name"] or page_title(page_html)})
                continue
            if cand["expected_code"] and codes[0]["code"] != cand["expected_code"]:
                code_drift.append({"page": page_url, "expected": cand["expected_code"],
                                   "found": [c["code"] for c in codes]})
            for i, c in enumerate(codes):
                name = cand["name"] or page_title(page_html) or f"Edinburgh Zoo webcam {c['code']}"
                if i:
                    name = f"{name} ({c['code']})"
                check = self._resolve_check(c["code"], referer=page_url)
                if check.get("ok"):
                    resolved.append(check)
                else:
                    resolve_failures.append(check)
                planned.append((name, cand["embedder"], page_url, c["code"], check))

        for name, embedder, page_url, code, _check in planned:
            if player_url(code) in seen_urls:
                dupes_dropped += 1
                continue
            seen_urls.add(player_url(code))
            result.add(row_from_code(code, name=name, embedder=embedder,
                                     embedder_page=page_url, attribution=ATTRIBUTION,
                                     tags=["animal", "zoo"]))

        # --- vendor extras (bespoke page probe + embedder-page drift fallback) ---
        extras_rows = 0
        extras_skipped: list = []
        extras_probe: list = []
        for extra in EXTRAS:
            codes: list = []
            source_used = ""
            probe: dict = {"embedder": extra["embedder"],
                           "bespoke_url": extra["bespoke_url"]}
            try:
                bespoke_html = cache.text(extra["bespoke_url"])
                codes = extract_codes(bespoke_html)
                probe["bespoke"] = "ok" if codes else "no codes"
                if codes:
                    source_used = "bespoke"
            except Exception as exc:  # noqa: BLE001 — 404 drift is expected; record it
                probe["bespoke"] = f"{type(exc).__name__}: {exc}"
            if not codes:
                try:
                    page_html = cache.text(extra["page_url"])
                    page_codes = extract_codes(page_html)
                    probe["embedder_page"] = f"ok ({len(page_codes)} codes)" if page_codes \
                        else "no streamdays code"
                    if page_codes:
                        codes = page_codes
                        source_used = "embedder-page fallback"
                except Exception as exc:  # noqa: BLE001
                    probe["embedder_page"] = f"{type(exc).__name__}: {exc}"
            extras_probe.append(probe)
            if not codes:
                extras_skipped.append({"embedder": extra["embedder"],
                                       "reason": "no resolvable streamdays code"})
                continue
            for i, c in enumerate(codes):
                name = c["label"] or (f"{extra['name_hint']} {i + 1}"
                                      if len(codes) > 1 else extra["name_hint"])
                check = self._resolve_check(c["code"], referer=extra["page_url"])
                if check.get("ok"):
                    resolved.append(check)
                else:
                    resolve_failures.append(check)
                    extras_skipped.append({"embedder": extra["embedder"], "code": c["code"],
                                           "reason": "code did not resolve", "stage": source_used})
                    continue
                if player_url(c["code"]) in seen_urls:
                    dupes_dropped += 1
                    continue
                seen_urls.add(player_url(c["code"]))
                result.add(row_from_code(c["code"], name=name, embedder=extra["embedder"],
                                         embedder_page=extra["page_url"],
                                         attribution=extra["attribution"],
                                         tags=extra.get("tags")))
                extras_rows += 1

        # --- one full-chain proof per run (tokens in-memory only) ----------------
        zoo_rows = [r for r in result.rows if r.meta.get("embedder") == "edinburgh-zoo"]
        chain_proof = None
        chain_verified = 0
        proof_failures: list = []
        for row in zoo_rows:
            try:
                candidate = self._prove_chain(row)
            except Exception as exc:  # noqa: BLE001 — proof failure must not kill enumeration
                candidate = {"code": row.meta["code"], "url": row.url, "verified": False,
                             "error": f"{type(exc).__name__}: {exc}"}
            if candidate.get("verified"):
                row.meta["verified_chain"] = True
                chain_proof = candidate
                chain_verified = 1
                break
            proof_failures.append(candidate)
        if chain_proof is None and proof_failures:
            chain_proof = proof_failures[0]          # keep the first failure for evidence

        zoo_cams = sum(1 for r in result.rows if r.meta.get("embedder") == "edinburgh-zoo")
        result.stats.update({
            "cams": len(result.rows),
            "zoo_cams": zoo_cams,
            "extras_rows": extras_rows,
            "offline_skipped": len(offline),
            "chain_verified": chain_verified,
            "dupes_dropped": dupes_dropped,
            "codes_resolved": len(resolved),
            "hub_new_pages": hub_new_pages,
            "code_drift": code_drift,
            "offline": offline,
            "page_failed": page_failed,
            "resolve_failures": resolve_failures,
            "extras_probe": extras_probe,
            "extras_skipped": extras_skipped,
        })
        if hub_error:
            result.stats["hub_error"] = hub_error
        if chain_proof is not None:
            result.stats["chain_proof"] = chain_proof
        if proof_failures:
            result.stats["chain_proof_failures"] = proof_failures
        result.stats.update(cache.stats())
        return result


ENUMERATOR = StreamdaysEnumerator()

if __name__ == "__main__":
    raise SystemExit(run_cli(ENUMERATOR))

# PLAN — World Feed DB (living document)

Owner: Moddy. Created 2026-10-05. This plan is append-only: every wave folds in as a numbered addendum at the bottom (§7); earlier text is never rewritten. Decisions are dated.

## 1 · Goal

A fully functional, worldwide, updateable, self-healing database + viewing system for as many public live video feeds as can be found on the internet at this time (RTSP / HLS / MJPEG / JPEG-refresh / YouTube-live / webcam pages). Inbuilt mechanism for searching sources and adding/removing them ("just considered at this point" — design captured, build later). Immediate deliverable: **collate the sources and endpoints to start the build** — `SOURCES-CATALOG.md`.

Non-goal (default): accessing private/exposed cameras.

## 2 · Architecture sketch (v0 — confirm after waves)

- **C1 Source Registry** — DB of source families + endpoints (+ protocol, license, geo, tags, health history). Schema basis: GEV's georeferenced camera row {id, name, city, provider, sourceKind, feedType, url, lat, lon, headingDeg, pitchDeg, fovDeg, rangeM, mountHeightM, groundElevationM, license} + L-E-S fields {url_type, coordinates_quality, status, last_verified, resolution, source_url_requires}.
- **C2 Discovery / Ingest** — per-family enumerators (JSON APIs, sitemap crawls, page scrapes, YouTube search); periodic refresh; seeded by ready-made corpora (see §4).
- **C3 Liveness & Self-Heal** — probe tiers (ffprobe frame-grab; HLS manifest freshness; two-sample pHash for frozen detection), health state machine, retry/backoff, rotation pools per logical channel, re-discovery when a stream dies.
- **C4 Viewer** — map + wall UI; local restream engine (ffmpeg + go2rtc) for HLS/JPEG/YouTube; embed escape hatch; honest status badges (GEV vocabulary: `UNAVAILABLE · <source> · KEY REQUIRED` style).
- **C5 Management surface** — search / add / remove / curate (CLI + web). Add = paste URL → probe → classify → store with health. Remove = soft-delete + auto-retire after N consecutive fails.
- **C6 Config & Credential layer** (D7) — per-user settings + secure credential store (keyring/DPAPI; `.env` fallback), BYOK inputs for every key-gated source, `KEY REQUIRED` honest states, onboarding checklist from `ACCOUNTS-AND-KEYS.md`. Open-source-ready: zero secrets in the repo; a public user supplies their own keys. Profile system (D7.1): **clean template** (public, keyless, honest degraded states) + **private `moddy` overlay** (his keys/curation, never committed); the build resolves everything through the active profile.

Reuse candidates: zero-hud `world_feed.py` channel/health patterns; GEV app schema + serve-stale; go2rtc as restream engine.

## 3 · Decisions so far

- **D1** (10-05) "The lot" = aggregate ready-made corpora (a) + our own per-family enumeration (b). Start: collation of both; builds come after.
- **D2** (10-05) Pipeline basis = WV1's verified methods: direct HLS via ffmpeg; YouTube via yt-dlp (`bv*[height<=720]+ba/b`, channel `/live` URLs, `android_vr` fallback); image-refresh tier; go2rtc restream option. (Evidence: zero-hud WV1 dossier.)
- **D3** (10-05) Seed corpora shortlist: **Live-Environment-Streams** (5,997 entries; 4,226 active; downloaded), **Argus** (229k claim; 100 MB geojson — fetch later), **OpenTrafficCamMap** (7,515; per-state scraper library), **cctv-camera-database** (28,400 specs + RTSP URL patterns, CC0).
- **D4** (10-05) Reference systems to study/borrow: trafficvision.live (155k+ claim; real-time stream testing; map + route UX), Argus (scrapers→SQLite→layered JSON), camforge (connectors + policy module + PostGIS), GEV app (schema, serve-stale), livetrafficcam.com (rolling verified-live checks).
- **D5** (10-05) Default policy for the base layer: public-by-design only; insecam-class documented-not-scraped pending owner decision (S5 supplies inputs).
- **D6** (10-05, OWNER DECISION — supersedes D5's default for this layer) **insecam-class exposed cameras are INCLUDED** as an explicitly-flagged category: registry rows carry `provenance: exposed` + warning badge + their own filter (visible by default in the owner's build). Handling: prefer consuming existing public insecam-derived datasets over re-scraping; rate-polite against hosters; distribution caveat tracked — keep the flag so any future public build can differ.
- **D7** (10-05, OWNER) **Open-source-ready + credential layer.** Personal-first build, but designed so the repo can be published at any time: **no secrets in code or git**; all credentials via a per-user settings layer (secure store — OS keyring/DPAPI — with `.env` fallback); honest `UNAVAILABLE · KEY REQUIRED` states for every gated source; onboarding checklist driven by `ACCOUNTS-AND-KEYS.md`. Owner instruction: **prompt me along the way so I can create the needed accounts** — the checklist is the prompt surface.
- **D7.1** (10-05, owner clarification) **Two artifacts, one codebase:** ① **Clean template** — the public/repo version: ships with **no secrets and no personal curation**; runs degraded-but-honest (`KEY REQUIRED` states everywhere) so anyone can clone, supply their own keys, and go. ② **Moddy build** — the template **plus a private profile overlay** (keys, source curation, preferences, account-bound tokens): ready-to-go for the owner. Mechanics: profile system (`profiles/` loader — clean default + `moddy` overlay); the private overlay lives **outside git** (local `profiles/moddy/` gitignored now; can graduate to a separate private repo for multi-machine later); release gate = a secret-scan of the repo before any push (the template must be publishable at any time); `ACCOUNTS-AND-KEYS.md` is the input checklist for the moddy profile.

## 4 · Seed corpus headline numbers (2026-10-05)

- Live-Environment-Streams: 5,997 streams / 98 countries / 67 sources / 4,226 verified active / 4,229 directly usable. (Source: repo README + our parse of `streams.geojson`.)
- Argus: "229,000+ cameras" (README claim — verify from its data before use).
- OpenTrafficCamMap: 7,515 cameras (README; per-country JSON; USA.json 1.5 MB).
- OpenCCTV.com: 746 (668 active) — per L-E-S index.
- VDOT 1,168 · MD SHA 404 · DelDOT 261 · Autobahn NRW 252 · Iowa DOT 50 · NYSDOT 23 — per L-E-S index (indicative counts; per-source live checks pending in S2).
- Skyline Webcams: 1,684 (1,284 active) — page URLs only; expiring tokens (S1 to detail).
- YouTube layer: WV1 verified shortlist (NASA ISS, explore.org, Virtual Railfan, Monterey Bay Aquarium, sen 4K, USGS Kīlauea, auroras) + 475 YouTube entries inside L-E-S.

Full table: `SOURCES-CATALOG.md`.

## 5 · Waves log (dispatched 2026-10-05)

| Wave | Topic | Evidence file | Status |
|---|---|---|---|
| W1 | Aggregator networks (non-gov) | `research/sources/S1-aggregators.md` | done → folded (A5) |
| W2 | Government / institutional | `research/gov/S2-gov-institutional.md` | done → folded (A4) |
| W3 | Platforms / lists / datasets | `research/platforms/S3-platforms-lists.md` | done → folded (A3) |
| W4 | Verification / self-heal / scale | `research/ingest/S4-verification-selfheal.md` | done → folded (A1) |
| W5 | OSINT / policy / management | `research/osint/S5-osint-policy-mgmt.md` | done → folded (A2) |

### Batch 2 (owner: "there are more sites to ingest… make it HUGE", 2026-10-05 ~21:22–21:25)

- 22-tab sweep captured → `research/seed-tabs-2/` (TABS-LIST-2.md + per-site HTML captures: cruisingearth, San Diego Zoo, Smithsonian Zoo, Monterey official, Bondi SLSC, EarthCam Animal/EarthCamTV, EarthLive24, WorldLive.app, ArgosAtlas blog, Webcamera24, OpenWebcamDB, WorldCam.eu).
- Follow-up waves dispatched (same mechanics): **S6 aggregators-2** (`research/sources/S6-aggregators-2.md`), **S7 institutional-2** (`research/gov/S7-institutional-2.md`), **S8 insecam-direct + community** (`research/osint/S8-insecam-direct.md`).
- Recon notes: insecam.org = TLS cert error in the automation browser / TCP fail in curl from this host (→S8 handles); Reddit: r/geography post text captured, r/Cyberpunk TrafficVision thread = login wall (→S8 tries Wayback).

## 6 · Open questions (owner decisions)

- **Q1 (RESOLVED 10-05)** Scope of "the lot": insecam-class exposed-camera corpora **INCLUDED** as a flagged category — see D6. (Grey edge noted: keep provenance flags so any future public release can diverge.)
- **Q2 Naming / home**: folder currently `C:\Users\user\world-feed-db`. Keep? Rename? Standalone repo vs fold into zero-hud GEV / moddys.net?
- **Q3 Keys / quotas**: Windy Webcams API key? webcams.travel key? Nimble quota exhausted (402 "trial quota finished" during research — top up if future crawls want it). Hound MCP works as fallback.
- **Q4 Viewer target**: desktop app (GEV-style)? web on moddys.net? zero-hud panel? all three (shared backend)?
- **Q5 YouTube grey zone**: keep "personal/local, non-redistributed" stance per WV1, or adjust?
- **Q6 Exposure ingest route**: datasets-only [recommended] vs also the live directory crawl (`/en/bycountry/{CC}`, `/en/bytype/{Type}`, polite rate + kill-switch); and which dataset first — OpenEyes (7,170, newer, has manufacturer) vs jrw (17.4K, 2019-stale). (see A2)
- **Q7 No-probe rule for exposure entries**: [recommended: keep — status `unverified` + snapshot date shown; never contact listed devices]
- **Q8 Exposure display**: metadata + click-through warning [recommended] vs blurred thumbnail vs inline preview.
- **Q9 Distribution**: private build first [recommended — `PRIVATE_EXPOSURE_SURFACE` gate] vs plan a public exposure surface (then: noindex + warnings + takedown SLA + legal review).
- **Q10 Takedown workflow**: public contact point, response SLA, hard-remove + tombstone; dataset refresh cadence (monthly?).
- **Q11 trafficvision.live data files**: robots.txt disallows `/camera-data/` + ToS bans automated access (the 853 `*-cameras.json` files are otherwise public/unauthenticated). Options: respect it and re-derive from the named original agencies [recommended] / contact them for permissioned API access / other owner call. (see A3)

## 7 · Addenda (wave fold-ins)

### A1 · Wave S4 — verification / liveness / self-heal / scale tech (folded 2026-10-05)

> Trigger: "design creative ways to determine and ultimately ingest as many 'WORKING' 'LIVE' feeds you can" (owner, 2026-10-05).

Status: evidence file read end-to-end; load-bearing claims spot-checked by parent (8 repos/releases + local toolchain + livetrafficcam page — all OK; ffmpeg n9.0.1 & yt-dlp 2026.08.19 confirmed on this host). File: `research/ingest/S4-verification-selfheal.md` (18 entries). Labels: [V]=verified (tested locally or spot-checked), [C]=cited, [P]=proposed.

- Liveness = two steps [V]: (1) structure probe — ffprobe must show a video track; (2) decode proof — `ffmpeg -t 1 -f null -` exit 0. 200-OK HTML fails; a still JPEG PASSES decode → camera tiers need step (3).
- Step 3 — motion/freshness: `freezedetect`/`blackdetect` combined pass (~1 CPU-s per 20 s; synthetic + live tested [V]); image tier: two-sample pHash (live pair Hamming 22 vs identical 0 [V tooling]; protocol + thresholds [P] to calibrate).
- HLS staleness [V]: poll playlist; `EXT-X-MEDIA-SEQUENCE` must advance (~2× target duration). Caltrans serves ETag/no Last-Modified → sequence tracking is the portable method.
- YouTube [V]: `yt-dlp --simulate --break-match-filter "is_live"` → rc 0 = live, 101 = not. Needs a JS runtime installed (warning observed → install deno).
- Engines [V]: go2rtc v1.9.14 = restream core; MediaMTX v1.21.1 = upgrade path (always-available + hooks). streamlink = wrong tool (RTSP wontfix [C]).
- Catches: L-E-S CI is an HTTP-200 check only [V code read] — its "active" overstates; livetrafficcam is the real model — 21,580 tracked / 74.9% live / 2,412 stale / 3,012 dead [V page]; adopt its vocabulary (verified-live/stale/dead/unknown, never fake a quiet state). iptv-org CI does NOT liveness-test (separate script; copy timeout/concurrency/error taxonomy) [V].
- Self-heal [C+V]: ZM zmwatch (heartbeat, startup grace, systemic-stall guard) + Frigate (restart budget 5/60 s, segment-derived stale thresholds, retry_interval) → state machine + rotation pools + re-discovery + mandatory serve-stale [P].
- Storage [P]: SQLite + FTS5 + WAL primary; Datasette viewer; PostGIS/DuckDB = upgrade paths.
- Open items: RTSP timeout flag on this build; pHash threshold calibration (needs real data); DuckDB RTREE status; livetrafficcam check cadence granularity.

Next moves: install deno for yt-dlp (quick host task); fold §1–§5 checks into the `verify` module design when build starts; calibration harness post-first-ingest.

### A2 · Wave S5 — OSINT / policy / management surface (folded 2026-10-05)

> Trigger: "include insec-class exposed cams" (owner, 2026-10-05) — sent as a mid-flight steer; the wave was reframed from decide-whether → how-to-include-responsibly and landed that way.

Status: evidence file read end-to-end; dataset counts parent-verified (jrw 17,398 rows; OpenEyes 7,170 records; virtualpeephole 2,806 rows / 2,805 cams — child count confirmed; a naive line count misled first, resolved via embedded-newline check). File: `research/osint/S5-osint-policy-mgmt.md` (20 entries + sections B/C).

- The line that stays: dataset aggregation IN (static third-party snapshots; NO device contact; `status=unverified` + snapshot date); active scanning/probing/credential-testing OUT (documentation-only, no code adopted).
- Exposure datasets (7): jrw 17,398 (2019-02-21); OpenEyes 7,170 (manufacturer+geo); virtualpeephole 2,805; rackcams 1,089; giasuddin 210; insecamRoulette 50; feedtv 12. All unlicensed → private-use/reference; credential-bearing URLs redacted at ingest; store flagged + versioned (new/removed diffs on refresh).
- Directory route [conditional]: mechanics documented (`/en/bycountry/{CC}/`, `/en/bytype/{Type}/`, `?page=N`); polite-rate + kill-switch; datasets preferred.
- Found: opencctv.org — claims 160,703 streams / 169 countries / 460+ registered sources, "deactivate not delete" lifecycle, camera-type taxonomy [V site up; counts are their moving claims]. opencctv.com unreachable from this host [V]. Reconcile vs the L-E-S index "opencctv 746" entry.
- Management surface: 10 precedents → proposed: Add = URL/dataset → GATE (provenance classify + credential redact) → PROBE (public-by-design only) → STORE+HEALTH; Remove = soft-delete + auto-quarantine (N=10) + tombstone + takedown; Search = provenance/geo/protocol/status/tag/source + free text. Exposure display defaults [P]: click-through warning, no autoplay, noindex, private-build-first.

Owner decisions open: Q6–Q10 (§6). Next moves: build the dataset ingesters (TSV/CSV/JSON/JSONL) + redaction linter + provenance gate as the first small build artifacts; Q6 gates ingest order.

### A3 · Wave S3 — platforms / datasets / test-fixtures (folded 2026-10-05)

> Trigger: the original brief — "comprehensive… YouTube-live… the lot" — plus the mid-flight trafficvision.live steer.

Status: read end-to-end; parent spot-checks all OK (robots.txt ✓ `Disallow: /camera-data/`; oktraffic HEAD → 200, 528,235 B, Last-Modified same-day ✓; yt-dlp live gate on @SanDiegoWebCam → `is_live=True` ✓). File: `research/platforms/S3-platforms-lists.md` (20 entries).

- trafficvision.live reverse-mapped [V]: **853 per-source `*-cameras.json` files** behind `data.trafficvision.live/camera-data/` (sampled oktraffic: 683 cams; schema incl. `videoUrl` HLS + `imageUrl` + `feedType` + make/model); `changelog.json` public (199 entries, 315 KB); `/api/catalog/manifest` session-gated (401). BUT robots disallows `/camera-data/` + ToS bans automated access → REFERENCE + possible permission contact; the 853 file names are a source-name goldmine to re-derive from originals. → Q11.
- YouTube: keyless discovery VERIFIED — `ytsearchN:"…"` + `--match-filter is_live` found 24 live cam channels in 3 sweeps (rail/airport/city/wildlife/surf); Data-API route documented (`search.list eventType=live` = 100-unit/day bucket); still needs deno JS-runtime for yt-dlp.
- iptv-org: structural-only validation confirmed (no ffprobe anywhere in the org); reuse = `freearhey/iptv-checker` (ffprobe CLI, 625★); no public-cam entries inside its catalog.
- Fixtures: public RTSP demo servers effectively extinct (rtsp.stream / viomic / wowza / Hessdalen all dead; port-quiz proves no local block) → self-host MediaMTX as the RTSP fixture; HLS fixtures verified (Apple bipbop, Mux x36xhzz + pts_shift).
- Community: r/webcams = hardware sub (not feeds); no "awesome-webcams" list exists; no Wikipedia list → the curated-list niche is OPEN (positioning note for us).
- CAM2 (Purdue): service dead (register 404; API hosts unreachable) — historical reference only.
- Synthesis (entry 20): four liveness patterns to copy (pre-display gating / scheduled probing / human repair loop / data-shape discipline); the differentiation gap to own = a public global ffprobe sweep + auto-failover.

Owner decision: Q11. Next moves: none build-blocking; feed the trafficvision source-name list into the discovery backlog.

### A4 · Wave S2 — government / institutional sources worldwide (folded 2026-10-05)

> Trigger: "comprehensive… all publicly available… worldwide" + the seed inventories (L-E-S / Argus / OpenTrafficCamMap).

Status: read end-to-end; spot-checks OK. File: `research/gov/S2-gov-institutional.md` (19 family entries; ~60 polite live fetches by the child, all byte-counted and dated).

- Flagship verified: Caltrans 12-district JSONs (D12 = 419 cams; D03 HTTP 500 — skip); VDOT 1,168 + MD SHA 404 + DelDOT JSON now 361 cams w/ direct HLS (all HLS verified HTTP 200); Ohio OHGO 1,161 cams + direct JPEGs; WSdot 1,706 features (latin-1 encoding!); Iowa ArcGIS count 1,260; DriveBC 1,066 (1,045 on); Ontario 511 = 925 cams (Iteris `List/GetData` pattern; GA/AB same family, 500s from host); TfL 890; NZ trafficnz 313; SG data.gov.sg (8 at check — partial).
- Endpoint menu captured for ~30 more US systems (TX special: `GetCctvSnapshotByIcdId`; MO/NV/NM/UT/HI/OK/TN/KY/ND/SD/SC/IL/WV; FL/LA/AK/AZ/WI/MN/MS; KS/NE/CO/IN GraphQL-511 family) + Road511 multi-state (now key-gated; broken-host list: trafficwise.org, kdot-sfs, actis.idrivearkansas.com, api.trafficland.com).
- International: Vegvesen new image API `kamera.atlas.vegvesen.no/api/images/<id>` + DATEX (registered) [V migration observed]; Autobahn.de API shape (empty at check — re-test w/ browser); NSW + QLD need free keys (both 401); TW geo-blocked from this host; TH/KR/JP = event/manual.
- Institutional verified: USGS HVO V1cam 200/56 KB; AVO ashcam URL pattern; NPS + Pixelcaster (snapshot 200/20.9 KB; HLS token-gated); USAP XHR API (McMurdo / South Pole / Palmer + weather); ski — Jackson Hole JSON + direct JPG 200/269 KB, Ischgl 200/187 KB; Roundshot/Panomax = provider patterns.
- Keys needed (free): Windy, Road511, NSW, QLD, LTA DataMall alt.

Next moves: catalog §1 updated with the verified menu; at build start, code enumerators in S2's "QUICK BUILD NOTES" order (registry → liveness exemptions → viewer tiers).

### A5 · Wave S1 — non-government aggregator networks (folded 2026-10-05)

> Trigger: the original brief — "all publically available… public cam or absolutely any other internet camera or webcam stream… find 'the lot'".

Status: read end-to-end; parent spot-checks OK — EarthCam `network_search` (Canada) → HTTP 200, 7 cams ✓ (with the documented Referer); Windy keyless → 403 ✓; Skyline hub 200 ✓; Roundshot → 561 (469 working · 53 broken · 32 idle · 6 late · 1 error — one cam drifted since the child's check) ✓; explore.org → 101 groups / 1,141 feeds live (child 1,137; live drift) ✓. File: `research/sources/S1-aggregators.md` (18 entries).

- Skyline: full crawl = 2,447 cam pages / 71 countries / 217 regions (richest keyless directory); stream layer = JS token player (spike needed). ADOPT registry.
- EarthCam: 365 cams enumerated keylessly (36 countries + 45 US states); endpoints `network_search.php` + `playlist.php` (tokenized HLS, `cam_state`); 429s without Referer; ≥1.5 s spacing proven. ADOPT.
- Windy v3: key required; full endpoint list documented; webcams.travel + lookr permanently 302 → Windy (one key covers all three brands). ADOPT (metadata layer, images expire 10 min).
- explore.org: keyless omega API (101 groups / ~1,140 feeds) with `video_id`, `is_offline`, `current_viewers`. ADOPT.
- Roundshot: 561 livecams with per-cam `status` (perfect liveness model) + per-site JSON. ADOPT.
- Others: WebcamTaxi 1,950 · CamGuide 5,052 pages · BalticLiveCam 1,278 (+ admin-ajax token flow) · WorldCams 775 · webcamera.pl 600+ (`latest.mp4` imageserver) · earthTV 495 places · AfriCam 43 lodges · Skyline-YouTube 580 composites · IPCamLive / CamStreamer = viewer notes.
- **Correction: opencctv.com is DEAD** (parked; last Wayback 2025-07-12) — the 746 `opencctv` records in the L-E-S index point at a dead domain; opencctv.**org** is a different live site (S5 A.18). Flag dead-source.
- Patterns: YouTube-embed prevalence → yt-dlp = highest-leverage shared component for this slice; token-gated players everywhere → resolve-on-demand adapters, never store tokenized URLs; ≈14,000 keyless records enumerated in this slice before dedupe.

Next moves: token-extraction spikes (Skyline, BalticLiveCam) at build time; Windy free key (Q3); EarthCam / explore.org / Roundshot importers → discovery backlog.

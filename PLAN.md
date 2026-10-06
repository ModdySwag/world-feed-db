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

**D8** (2026-10-05, owner) **Build phase opened — Q2–Q11 closed or defaulted:** Q2 keep repo as-is · Q4 shared backend + local web UI first (other surfaces later) · Q6 exposure = datasets first, polite listing crawl later · Q8 exposure display = metadata + click-through warning · Q11 = respect robots, re-derive from originals. Quiet defaults: Q3 no Nimble top-up · Q5 YouTube stance kept · Q7 no-probe kept · Q9 private-first · Q10 deferred. Sprint 1: credential/settings layer + exposure dataset ingesters (GODEYE → rafasapiens era chain) + L-E-S/gov enumerator scaffolds.

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
- **Q2 (RESOLVED 2026-10-05, owner)**: keep as-is — standalone repo at `C:\Users\user\world-feed-db`; no rename, no fold-in.
- **Q3 Keys / quotas**: Windy Webcams API key? webcams.travel key? Nimble quota exhausted (402 "trial quota finished" during research). Hound MCP works as fallback. **Default taken 2026-10-05: no Nimble top-up for now — Hound MCP is the working fallback for crawls; the Windy key already covers webcams.travel/lookr brands; revisit Nimble only if a build crawl needs it.**
- **Q4 (RESOLVED 2026-10-05, owner)**: shared backend + simple local web UI first; desktop / moddys.net / zero-hud surfaces decided later.
- **Q5 YouTube grey zone (default kept 2026-10-05)**: keep "personal/local, non-redistributed" stance per WV1.
- **Q6 Exposure ingest route**: datasets-only [recommended] vs also the live directory crawl (`/en/bycountry/{CC}`, `/en/bytype/{Type}`, polite rate + kill-switch); and which dataset first — OpenEyes (7,170, newer, has manufacturer) vs jrw (17.4K, 2019-stale). (see A2) **UPDATE 10-05 evening: owner "and 3 go" read as approval — baseline sitemap census captured (2,271 current IDs → `research/exposed/insecam-census-2026-10-05.json`; 1 request, robots-allowed, no device contact). Next: ingest GODEYE + rafasapiens era snapshots; listing-level crawl timing at build.** **RESOLVED 2026-10-05 (owner, re-confirmed): datasets first — GODEYE + rafasapiens era chain now; the polite listing crawl is its own separate later step (not in the first build sprint).**
- **Q7 No-probe rule (default kept 2026-10-05)**: [keep — status `unverified` + snapshot date shown; never contact listed devices].
- **Q8 (RESOLVED 2026-10-05, owner)**: metadata + click-through warning; no autoplay, no preview (private build default).
- **Q9 Distribution (default kept 2026-10-05)**: private build first — `PRIVATE_EXPOSURE_SURFACE` gate; no public exposure surface planned.
- **Q10 Takedown workflow (deferred 2026-10-05)**: revisit only if/when a public exposure surface is actually planned.
- **Q11 trafficvision.live data files**: robots.txt disallows `/camera-data/` + ToS bans automated access (the 853 `*-cameras.json` files are otherwise public/unauthenticated). **RESOLVED 2026-10-05 (owner): respect robots — re-derive the 853 source names from the original agencies; no automated access to `/camera-data/`.** (see A3)

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

### A6 · Wave S6 — batch-2 aggregators & new directories (folded 2026-10-05)

> Trigger: owner batch-2 sweep — "there are more sites to ingest in my brave browser might as well make it HUGE!"

- **webcamera24.com**: 6,570 cams / 67 countries (sitemap 121,296 URLs → de-dup ×14 langs); inline RSC payload carries direct HLS `streamLink` + `youtubeCode`; per-cam `isWork` liveness. ADOPT (registry/discovery/viewer/liveness).
- **openwebcamdb.com**: 1,881 cams, keyed API — **SKIP for ingest** (ToS explicitly bans competing directories/harvesting). Monitor only.
- **worldcam.eu**: country dirs 25/page (DE 1,592 · UK 754 · FR 712 sampled; operator counter 32,330); date-stamped snapshot images keyless (staleness-detectable) + static/streaming badge. ADOPT (registry + image tier).
- **earthlive24.com**: 414 cams (parent-verified: sitemap 1,134 URLs / 414 camera locs); SSR YouTube embeds; 2 ids live-proven. ADOPT.
- **earthcamtv/EarthCam**: playlist 12 live; animal cams 13 (camshots keyless; HLS tokenized resolve-on-demand). ADOPT.
- Skyline mosaic `EFum1rGUdkk`: live (385 viewers) — viewer-filler tier.
- **ARGOS ATLAS**: keyless stats API (parent-verified: cams 220,449 / video 20,781) — benchmark; closest peer; data pro-gated, don't take.
- **CruisingEarth ships**: 274 ship pages / 22 lines (sitemap) + **Panomax** provider (keyless image API; Last-Modified gate mandatory — one cam stale 7.5 months while another fresh). ADOPT-lite.
- worldlive.app: SKIP (Wix + app-only). Wave total: ≈7,100+ new enumerable records before dedupe.

### A7 · Wave S7 — institutional / nature / animal / ship layer (folded 2026-10-05)

- **San Diego Zoo**: 13 cams → Camzone keyless HLS (`<channel>.hls.camzonecdn.com/CamzoneStreams/<channel>/Playlist.m3u8`; zssd-* channels; 4 decode-verified); Safari Park +8 channels (16 total); panda = email-gated (manual tier). ADOPT.
- **Smithsonian NZP**: own Wowza HLS, keyless, failover pair (nzp-wowza01/02), 6 streams incl. panda ABR 1080p — 3 decode-verified. ADOPT flagship.
- **Monterey Bay Aquarium**: 10 cams, all YouTube — full id table captured (otter/kelp/shark is_live-verified); site WAF-walled (don't scrape). ADOPT via YouTube adapter.
- **Bondi SLSC**: 2 ipcamlive aliases → direct keyless HLS incl. HEVC 3200×1800 (parent re-checked: master.m3u8 200); snapshots keyless. ADOPT + ipcamlive resolver.
- Cruise Earth mechanics: Panomax iframes / YouTube / proxied-JPG 30 s / decommissioned placeholders — honest-states required; Sky Princess 1920×1080 369 KB verified.
- **Panomax** provider: keyless image API `panodata.panomax.com/cams/<id>/recent_reduced.jpg` + preview_og.jpg; freshness gate (Last-Modified).
- **BAS Sir David Attenborough**: official `latest.jpg` verified fresh 1080p. ADOPT.
- OSU fleet / OET Nautilus / Greenpeace = event-mode reference. EarthCam Animal: 13 curated + partner leads.
- New resolvers to build: **Camzone · ipcamlive · Panomax · EarthCam-token · YouTube**.

### A8 · Wave S8 — insecam direct recon + new datasets + community (folded 2026-10-05)

- Direct access SOLVED for recon: `http://www.insecam.org` + browser UA (https cert = self-signed/expired; default UA → 403; **robots allows crawling at crawl-delay 0.1**; no ToS exists). Directory ≈ **2.2–2.3k cams now** (sitemap = 2,271 IDs; US ≈576; AQ/GL not covered). **Polite census FEASIBLE** — full current ID set = 1 sitemap request; listing-level ~1.5–2 h at 1 req/2 s; **gated on Q6**; rules: redact img src, never fetch device URLs or `/en/view/` pages, kill-switch.
- New datasets beyond the 7: **GODEYE 1,775 (2026-05-27)** + **rafasapiens 2,100 (2026-10)** (parent re-counted GODEYE = 1,775 ✓) — plus reconeyes (OpenEyes-lineage, log) and EyeFinder 256 (77 insecam). **Era chain now 2019 → 2022 → 2026** — unique value = timeline diffs ("gone dark" views).
- Community: **AAD Mawson (Antarctica) cam verified** — remote-stations class opened (naocam.com Greenland airports, overwatch.earth, DOT-mapper leads queued).
- Housekeeping: children's stray scratch files were removed (commit 39610be); practice rule going forward: subagent waves do not run git commands — the parent commits.

### A9 · Owner decisions Q2–Q11 closed → build phase opened (folded 2026-10-05)

> Trigger: owner resumed ("continue world-feed-db") and re-read + re-picked the five build-forking questions; all five landed on the recommended options.

- Locked: **Q2** keep standalone repo · **Q4** shared backend + simple local web UI first (desktop / moddys.net / zero-hud later) · **Q6** datasets-first exposure ingest — GODEYE + rafasapiens era chain now, polite listing crawl = separate later step · **Q8** exposure display = metadata + click-through warning, no autoplay/preview · **Q11** respect robots — re-derive the 853 source names from originals.
- Quiet defaults kept: **Q3** no Nimble top-up (Hound fallback) · **Q5** YouTube personal/local stance · **Q7** no-probe · **Q9** private-first gate · **Q10** takedown deferred.
- Build phase opens — sprint 1: (a) credential/settings layer (profiles loader, keyring/DPAPI + `.env` fallback, honest `KEY REQUIRED` states); (b) exposure dataset ingesters (credential redaction + provenance flags per S5 §B); (c) L-E-S + government enumerator scaffolds per S2's "QUICK BUILD NOTES".
- Small wins queued alongside: Road511 param discovery · QLD email draft (`qldtraffic@tmr.qld.gov.au`) · deno install for yt-dlp · Shodan camera-search dry run (search-only, credit-budgeted).

### A10 · Build phase — sprint 1 delivered (folded 2026-10-05, late)

> Trigger: owner "continue world-feed-db" → Q2–Q11 closed (A9) → build phase opened; 3 parallel build units dispatched, parent-verified, and committed.

- **Core** (7f413c1): `wfd` package — `schema` (CameraRow + redaction), `profile` (clean template + private overlay; secret order store→.env→env; honest `KEY REQUIRED` states), `db` (SQLite+FTS5), `ingest.base` (IngestResult + polite HTTP), `cli` (`py -3.11 -m wfd status`), contracts `docs/ARCHITECTURE.md`, tests 6/6.
- **Task A — credential/settings layer** (15e54cc): `wfd/creds.py` (keyring → DPAPI file → warned plaintext; values never printed; `wfd creds` CLI) + `wfd/onboarding.py` (`wfd keys` checklist from `ACCOUNTS-AND-KEYS.md`). Tests 11/11 + 7/7; active backend on this host = keyring (Windows Credential Locker).
- **Task B — exposure ingesters** (8a0295f): era chain as static datasets only — **jrw-2019 17,034 rows** (3,836 redactions) · **GODEYE-2026-05 1,775** (38) · **rafasapiens-2026-10 2,072** (96) = **20,881 rows**; all `exposure_aggregator`/`unverified`/`geo_confidence=low`; parent-verified **0 credential values** in any output; manifest + sha256s at `data/ingest/manifest-exposure.json`; raw downloads gitignored (`research/exposed/raw/`). Tests 9/9.
- **Task C — L-E-S + gov scaffold** (ac09a62): `les` 5,994 rows · `caltrans` 3,591 (12/12 districts; D03 recovered from its 500s) · `deldot` 361 · `nsw` 241 (key-gated, honest `KEY REQUIRED` when absent). Enumerated rows never claim liveness (status `unknown`). Tests 9/9 + 10/10.
- **Small wins:** Road511 VERIFIED — `X-API-Key` header → HTTP 200 (2274fdc) · deno 2.9.7 installed (yt-dlp: `JS runtimes: deno-2.9.7`) · QLD email draft at `outreach/QLD-traffic-api-email-draft.md` (owner to fill + send) · Shodan key alive (free `/host/count` probes only).
- **Parent verification on record:** all six suites re-run (6/6, 11/11, 7/7, 9/9, 9/9, 10/10); independent credential scan of 16 files = 0 violations; output sha256s match task reports; `profiles/moddy` untouched by tests.
- Next moves: fill the registry DB (`wfd.db`) from ingest outputs · first health-check pass (A1 probe tiers) · viewer spike (shared backend + local web UI, Q4) · more enumerators from the S2 menu (TfL, DriveBC, OHGO, WSdot, Iowa, Ontario) · discovery connector (Shodan search-only, credit-budgeted).

### A11 · Sprint 2 step 1 — registry database filled (folded 2026-10-05, late)

> Trigger: owner "go with next logical step" — the registry DB every downstream piece (health checks, search, viewer) writes into.

- NEW `wfd/registry.py` + `wfd db load|stats|search` CLI (registered via the wfd.cli extension pattern). Loads `data/ingest/*.jsonl` into `data/worldfeed.db`; idempotent by `camera_id`; tolerant of bad lines/unknown keys.
- First full load: **31,061 rows** (31,068 read — 7 Caltrans shared-stream duplicate URLs collapse by design; same (family,url) ⇒ same row). Split: **20,881 `exposure_aggregator` + 10,180 `public_by_design`**; statuses `unverified`/`unknown` only. FTS5 search live.
- Perf fix en route: FTS maintenance is now rowid-keyed (a `WHERE camera_id` delete on the FTS table was a per-row scan) — full 31k-row load: **1.4 s** (previously multi-minute).
- Overlap map (same URL in >1 family — consolidation backlog + era-diff material): **1,806 URLs** — exposure era chain 1,514 (703 godeye↔rafasapiens · 407 triple-era jrw↔godeye↔rafasapiens · 225 jrw↔rafasapiens · 179 jrw↔godeye) + LES↔gov 292 (261 deldot · 31 caltrans).
- Queued cleanups: country normalization (LES carries ISO codes "IT"/"TH"; exposure datasets carry names "Italy"; "US" vs "United States") and cross-family feed consolidation (one row per physical feed, lineage preserved) — later phase.
- Verification: registry 5/5 + core 6/6 re-run; independent raw-SQL recount (total / family / provenance) matches file-derived expectations exactly; FTS↔cameras rowid join 31,061/31,061; DB 28.2 MB.
- Next moves: (b) first health-check pass on public rows · (c) viewer spike · (d) more enumerators · (e) discovery connector; plus the queued cleanups above.

### A12 · Sprint 2 step 2 — first health-check pass (pilot) (folded 2026-10-05, late)

> Trigger: owner "go" — the A1 liveness doctrine gets its first real-data sweep.

- NEW `wfd/health.py` + `wfd health probe|run`: streams = structure → decode → freeze/black motion pass; stills = two-sample pHash (~20s gap); YouTube = yt-dlp live gate. Resumable sweeps; write-back (`status`, `last_verified`); evidence JSONL per run in `data/health/` (gitignored); public rows only (SQL-enforced); per-host gate (cap + spacing); all subprocesses windowless.
- **Pilot results — 602 cams probed (NSW 241/241 JPEG · DelDOT 361/361 HLS):** NSW **131 live · 110 stale · 0 dead**; DelDOT **305 live · 41 stale · 15 dead** (combined 436 live / 151 stale / 15 dead). Exposure rows untouched (0 status/last_verified changes); db integrity ok.
- Calibration (real data): NSW refresh is fast (sample cams move within 20s; hamming 6–24) — the 20s gap is a strict separator; the NSW stale-subset rechecked at 60s drifts hamming 2–8 (slow-refresh/static scenes, not placeholders — queue a longer-window refinement). DelDOT freeze pass clean (1/8 sample flagged; keep d=1.0). NSW's image host serves an HTML stub to non-browser UAs → probes now do a two-stage UA fallback (polite → browser), recorded in evidence. `last_verified` semantics: LES rows carry the corpus's own check date from ingest; our probes overwrite with probe time (informational, never a liveness claim by us).
- Fixes en route: `db.connect(check_same_thread=False)` + sweep write-lock (threaded writes); sweeps chunk ≤ ~400s (tool cap) — resumability makes chunking free.
- Verification: suites green (health 7/7 incl. synthetic pHash + image sniff; core 6/6; registry 5/5); evidence files 602/602 rows; final splits SQL-verified; `PRAGMA quick_check` ok.
- Queued: Caltrans D12 (~419 mixed) · LES HLS + YouTube samples · full-family passes · then the schedule/self-heal layer (A1 state machine + rotation pools + re-discovery).

### A13 · Sprint 2 step 3 — sweep set finished + LOCAL VIEWER UP (folded 2026-10-05, late)

> Trigger: owner "go" (viewer plan) — finish the health sweeps, then the viewer per Q4 (shared backend + local web UI).

- **Sweep set finished** (`wfd health run`, child-run + parent-verified): **1,144 rows swept today, all `public_by_design`** (exposure untouched: 0). Caltrans **D12 417 → 209 live · 158 stale · 50 dead** (all 50 dead on wzmedia.dot.ca.gov — partial, not host-wide) · **LES HLS sample 100 → 39/10/51** (dead clustered: 35/51 on host 62.113.210.7 — host-level death, honest) · **LES YouTube sample 25 → 5 live · 1 dead · 19 unknown** (yt-dlp rc=1 "not available" → unknown by design; refinement queued). Registry now: **689 live · 319 stale · 117 dead · 9,055 unknown · 20,881 unverified**.
- Calibration notes: D12 stills read 153/166 stale at the 30s gap — Caltrans stills refresh ~2 min → per-family gap calibration queued (measure cadence first, as done for NSW 20s). Every dead row failed at the probe stage; none reached decode.
- **Viewer delivered:** `wfd/viewer.py` (stdlib-only ThreadingHTTPServer, 127.0.0.1, default :8773, read-only DB; `/api/stats`, `/api/cameras` GeoJSON with bbox/status/family/q/limit, `/api/camera/<id>`) + `wfd/web/index.html` (single-file dark/teal UI: clustered Leaflet map, status-colored markers, live wall with JPEG refresh + hls.js preview + YouTube link-out, filters, detail panel). Exposure law end-to-end: surface gated by `private_exposure_surface`; exposure rows = metadata + click-through warning only — no url, no preview, no autoplay; `noindex`. Run: `py -3.11 -m wfd viewer` → http://127.0.0.1:8773/.
- Verification: viewer tests 11/11 (parent re-run) + regressions green; the frontend task ran real-browser E2E (clusters; wall 11/12 HLS feeds playing; exposure modal flow; error states; screenshots); parent browser pass confirmed the live page (chips read the real totals; markers/clusters + wall tiles render).
- Queued: per-family gap calibration (caltrans stills) · probe-stage retry depth for the wzmedia dead set · yt rc=1 mapping · full-family sweeps + schedule/self-heal layer · country normalization · restream engine (go2rtc) for CORS-blocked HLS.

### A14 · Sprint 2 step 4 — self-heal core: consecutive-failure accounting + auto-quarantine (folded 2026-10-06, early)

> Trigger: owner "continue world-feed-db" — A13's queued schedule/self-heal layer (A1 doctrine, S5 §C state machine), first slice.

- `cameras.fail_count` (INTEGER NOT NULL DEFAULT 0) — the consecutive-failure streak — added by the idempotent migration `db.ensure_health_columns()` (runs on every `init_db()`; covers fresh + pre-existing DBs). Deliberately kept OUT of `_DDL`/`_COLUMNS`: ingest upserts can never clobber the streak (fresh inserts take the column default; re-ingest leaves it untouched).
- NEW `health.apply_result(conn, camera_id, state, checked_at)` — one atomic UPDATE per verdict: live/stale → status + `fail_count=0` (restores a quarantined row); dead → streak+1, flips to `quarantined` at `QUARANTINE_N=10` consecutive deads; unknown → status only, streak kept (no verdict). Stamps `last_verified` (resumability). Wired into `run_sweep` under the existing write lock; evidence JSONL lines now carry `fail_count` for the audit trail.
- Viewer: already anticipates `quarantined`/`retired` (chips in `wfd/web/index.html`); rows show the literal status, map dot falls back to the unknown shade — no viewer change needed.
- Tests: health **14/14** (7 new: dead-increment, quarantine-at-threshold, live-restore, stale-reset, unknown-keep, old-DB migration cycle, run_sweep write-back + evidence) + full regression green (core 6/6 · creds 11/11 · exposure 9/9 · gov 10/10 · ingest-les 9/9 · onboarding 7/7 · registry 5/5 · viewer 11/11). Temp DBs only — `data/worldfeed.db` never opened by tests.
- Context: the 2026-10-06 ~01:26 network outage killed the previous session mid-flight, leaving 30 outage-false `dead`s (and 8 `unknown`s) in the D12 stills slice; the D12 re-probe (queued fold) corrects them with the calibrated 330 s gap.

### A15 · Sprint 2 step 4b — Caltrans D12 stills re-probe at 330 s gap (folded 2026-10-06, early)

> Trigger: owner "continue world-feed-db" — the gap-30 baseline inflated stale (153/166), and the 01:26 outage left 30 false deads in the registry. Full re-probe with the calibrated 330 s cadence, on top of the A14 self-heal code.

- **Calibrated cadence:** 12 random D12 stills sampled at t0/t+150s/t+330s; 4/12 changed by 150s, all 12 changed by 330s → chosen gap = 330 s (≤5 min refresh).
- **166 rows re-probed** (83+83 halves at camera_id split `8fe3a2fcd0050321`), gap 330 s, `--recheck`, 8 workers, 8 host-cap; launched detached via WMI→wscript after the outgoing session was outage-killed at 01:26. Evidence: `data/health/health-caltrans-20261006-014512.jsonl` + `…-014518.jsonl`.
- **Corrected splits: 107 live · 59 stale · 0 dead · 0 unknown** (previous gap-30: approximately 153 stale).
- **Flips from original baseline (13 live/153 stale):** 97 stale→live · 56 stayed stale · 10 stayed live · 3 live→stale.
- **Outage damage repaired:** all 30 false deads corrected (21→live, 9→stale); all 8 unknowns corrected (14→live, 2→stale — counting across evidence, not exact distribution). All 166 rows now `fail_count=0`.
- **Hamming distribution** (pHash across the 330 s gap): mean 8.48, min 0, max 32; `JPEG_STATIC_MAX=5` cleanly separates live from stale.
- **Verification vs registry:** union 166/166, no coverage gaps; final registry D12 status matches evidence exactly. Cross-referenced both evidence files (83+83, no duplicates).
- **D12 cadence + fail_count machinery** now sets per-family refresh policy — this was the validation run for the A14 write-back (apply_result + quarantine). The 30 false deads from the outage provided a natural test of the quarantine lifecycle; all rows now restored.

### A16 · New-sources research wave NS1–NS4 (folded 2026-10-06, early)

> Trigger: owner — camera sites collected in Brave tabs; "send some sub agents to crawl and ingest a lot more working cams".

- 4 research dossiers + synthesis at `research/new-sources/` (NS1 directories · NS2 AU-institutional · NS3 resorts · NS4 nature/vendor) — 14 sites, ≈5,400 camera pages/feeds enumerated; every feed claim live-fetched (status/content-type/bytes; HLS playlist + TS-segment proofs); parent re-verified a sample per dossier (all pass).
- **ADD NOW families (ranked build menu):** `explore-omega` (≈239 feeds, open JSON API) · `openwebcamdb` (1,882, sitemap + JSON-LD) · `webcamtaxi` (≈2,230, scrape) · `jungfrau-roundshot` (10; list + status + image APIs) · `vailresorts-brownrice` (8 Whistler + 5 Vail verified; multiplier: all Vail properties) · `aus-airservices` (39 airports; AJAX + JPEG) · `streamdays` (Edinburgh Zoo + other zoos; HLS token chain) · `skaping` (vendor sitemap, 877 pages) · `youtube-live-cams` (Steamboat 9 + SPI 4 + all YouTube-embed sources) · `au-goldcoast-beach` (JSON API, 27 beaches) · `au-nsw-marine` (21 HLS widgets) · `camsecure-webcams` (30 HLS, vendor-demo). **LATER:** `au-tas-traffic` (5, Referer-gated) · `ozolio` (robots Disallow — review first).
- Cross-cutting: YouTube-live embeds dominate (one adapter services OWD/WCT/explore/Steamboat/SPI ≈4,300 feeds); vendor multipliers (Brownrice = Vail chain, Skaping 877 pages, Roundshot, Streamdays) let single adapters cover hundreds of cams; directory-provenance decision queued; drift rule: cloudfront/widget/token URLs re-resolved per sweep (404 → `unknown`, never `dead`).
- Next moves: owner picks build order (suggest explore-omega → openwebcamdb → jungfrau-roundshot → vailresorts-brownrice) → per-vendor ingesters under `wfd/ingest/` → per-family health sweeps.


### A17 · Sprint 3 unit NS — twelve new-source ingesters + runner + health-state fix (folded 2026-10-06, pre-dawn)

> Trigger: owner resume — "build the new-source ingesters, starting with the top four" (b23190e directive); session opened by rescuing the reboot-killed sweep chain (03:26 reboot; chain r3b relaunched), then "complete the build to the end" arrived mid-night.

- **newsrc package** (`wfd/ingest/newsrc/`): shared base (Enumerator + resumable FetchCache + run_one/run_cli; base tests 6/6) + auto-discovery runner (`py -3.11 -m wfd.ingest.newsrc list|<family>|all`; modules self-register on landing). Twelve families built with offline fixture suites: **explore-omega 236** (101 groups / 239 feeds; 3 simulcast pairs collapse by (family,url)) · **openwebcamdb 1,089** (1,882 pages fetched; 793 no-feed skipped; `aggregator_directory`) · **jungfrau-roundshot 10** · **vailresorts-brownrice 13** (13/13 snapshot verify) · **aus-airservices 146** (39 airports; 2 honest failures) · **au-goldcoast-beach 21** · **au-nsw-marine 22** (iluka back online vs dossier) · **streamdays 7** (full token chain proven once; tokens never stored) · **camsecure-webcams 30** (30/30 dossier cross-check) · **youtube-live-cams 13** (13/13 oembed) · **skaping 877** (sitemap.players.xml; 874 player pages + 3 customer-host pages inline in the sitemap) · **webcamtaxi 2,016** (2,219 pages fetched; 195 no-embed skipped; 400 channel + 1,616 video-id embeds). Family suites ≈200 checks; full 22-suite regression green.
- **Health-state fix (05d477f)**: a registry load had wiped ~8k sweep verdicts (upsert updated every column). `db.upsert` now preserves `status`/`last_verified` on conflict (INSERT still sets them; `--reset` rebuilds). Verdicts restored from `data/health/` evidence (nsw back to 131 live / 110 stale; deldot 305/41/15). Registry regression test added (6/6).
- **Overnight health**: chain r3b completed — LES-HLS remainder 1,607 probed; LES-YouTube 475 → 53 live / 6 dead / 416 honest-unknown (yt-dlp rc=1 mapping; refinement still queued). Chain r4 launched: per-family pilot sweeps (jungfrau 600s gap · vail 120s · airservices sample · au coastal HLS · camsecure · youtube-live-cams · sampled explore/openwebcamdb/webcamtaxi). **skaping + streamdays excluded from sweeps pending resolve-on-demand probers** (their urls are pages/token chains, not media).
- At fold time: registry now: 33530 rows · by_provenance={'aggregator_directory': 1094, 'exposure_aggregator': 20881, 'public_by_design': 11555}.

### A18 · Sprint 3 — the showpiece viewer (viewer v0.3) (folded 2026-10-06, pre-dawn)

> Trigger: owner directive (asleep): "complete the build to the end and final stage… showpiece… a user wowed and impressed… fully integrated top menu bar… save/delete favourites… varied intelligent ways of viewing… group multi-watch… a personal page… full help menu… sounds, animations… clinical. I trust you."

- **Backend v0.2 (b012ffe)**: `wfd.prefs` store (favourites add/remove/label/reorder + settings; atomic JSON) · `/api/overview`, `/api/facets` (live counts under current filters), `/api/prefs` GET/POST (hardened: `X-WFD-Viewer: 1` + local-origin) · extended `/api/cameras` filters (protocol/country/tag/favourites/sort/order/geo=any) · viewer tests 17/17.
- **v0.3 prep (901922f)**: `docs/VIEWER-SPEC.md` (the showpiece contract) + vendored Leaflet/hls.js (`wfd/web/vendor/`; zero runtime CDN) + explicit JS mimetypes on the static server.
- **Frontend v0.3 (de1bec0)** ≈6,400 lines (`index.html` 149 · `css/app.css` 802 · `js/app.js` 1,815 · `js/views.js` 1,520 · `js/player.js` 885 · `js/sound.js` 147): top menu bar (View/Filters/Tools/Help — every item functional) + status bar; 7 views — Overview / Map (status clusters, "search this area", honest 2,500 cap note) / Wall (poster-first, load-more, skeletons) / **Watch multi-watch** (1×1/2×2/3×3, mixed formats side-by-side, live cap, persisted stage) / Search (debounced FTS + live facet counts + multi-select → Watch) / Personal (favourites: labels, drag reorder, export) / Help (10 sections); universal multi-format player with honest fallback panels (Retry / Open original / Copy URL); command palette; settings (14 persisted); synthesized WebAudio sounds; animations; keyboard map; exposure law end-to-end.
- **Verification**: node --check ×4 · live API curls (403 guard, favourites round-trip, facets) · child real-Chromium smoke = **zero console errors** across flows (exposure modal, palette export, stage persistence) · **parent visual pass** (Map + Watch screenshots — clusters/facets correct; JPEG fallback tile honest in the multi-watch grid).
- Notes: exposure surface ON in the owner build (20,881 metadata-only rows, as designed) · sounds verified by state only (headless) · favourites mouse-drag untested (POST + Alt-arrow verified).

### A19 · Viewer v0.4 — live relay + poster pipeline for no-embed sources; drawer close fix (folded 2026-10-06, afternoon)

> Trigger: owner — screenshots of the wall with "IFRAME · no poster" / "YT no poster" tiles: "is there a way to enable the 'blank' cameras … to have the stream come through … the blank spots on the page look bad i want them all filled with cam views" + "the right hand info module does not close with the x toggle".

- **Diagnosis (live-reproduced)**: drawer X (`#drawer-close`) had never been wired in `app.js` — only Esc closed it. Blank tiles = two classes: 1,684 skylinewebcams `iframe` rows (viewer embeds nothing for iframes by design) + 406 YouTube channel-live rows without an id in the URL (no poster). Parent proved the skyline player page exposes its real HLS stream (page → `source:'livee.m3u8?a=TOKEN'` → `hd-auth…live.m3u8` with cookie jar + Referer; real live frame pulled and vision-verified).
- **Server (wfd/resolve.py new; viewer v0.3 → 0.3 banner, resolve-capable)**: per-host resolver registry — skylinewebcams (token+cookies, og:image poster captured from the same fetch) · youtube-live (yt-dlp id → ytid + i.ytimg poster). Endpoints: `GET /api/poster/<cid>` (12 h positive / 1 h negative cache; skyline coverage 6/6) · `GET /api/live/<cid>/index.m3u8` + `/api/live/<cid>/seg/<name>` — a same-origin HLS relay: playlist rewritten to local segments, upstream headers replayed, 600 s→300 s live TTL, token/cookie redaction (sha1[:8]) in every output. Row fields (full-display rows only, additive): `resolvable`, `live_url`, `poster_url`; `wfd viewer --no-resolve` disables everything (clean-template switch); exposure law unchanged (never resolvable / never relayed). CLI: `wfd resolve warm [--kind poster|live|both] [--family|--host|--limit|--refresh]` (resumable, HostGate cap 2/0.5 s, evidence JSONL) + `wfd resolve show <cid>`.
- **Integration gotcha (found + fixed during parent E2E)**: an expired skyline token is answered with a *dead* playlist — 6 lines, `#EXT-X-TARGETDURATION:0` + `#EXT-X-ENDLIST`, zero segments (a third failure form, distinct from the `copyright_violation` filler). Fix: `is_dead_playlist()` treated like filler → one forced re-resolve + retry (playlist and segment paths); every relay fetch/rewrite/segment call now has a hard no-raise guard (0-byte upstream segment = failed fetch). New regression tests: dead-playlist detection + fake-stale-token recovery through the HTTP handler. Suite: resolve 19/19 · viewer 17/17 · core 6/6.
- **Frontend**: relayed iframe rows behave exactly like HLS everywhere (play, hover preview, stage, offscreen pause, live cap, budget); `posterInfo` fills `poster_url` / lazy `/api/poster/<cid>` probes for iframe+unknown tiles (YouTube rows once resolved) — wall tiles show real cam imagery, zero placeholder boxes on the les/iframe wall (60/60 tiles, filling progressively); drawer X wired + slide-out transition confirmed; help formats row updated.
- **Live verification (parent, on the real viewer)**: modal player on `507b64f69e709039` (Arvi/Viannos, GR) = **playing 1280×720** hls.js through the relay; hover preview = playing; wall `family=les protocol=iframe` = 60 tiles / 0 `ph` placeholders; stale-token curl test = 200 + 8 segments after auto-refresh; segment relay byte-exact (67,304 B, repeatable).
- **Probe findings (read-only)**: YouTube no-id rows — 3/8 sampled resolve (@dailyseoul · @OurLawaiBeachResort · UCcjlnrL3…); 4/8 handles hard-404 (incl. @exploreorg — **gone**, not offline; no-/live test distinguishes); 1 legitimately not-live. Small iframe hosts: hessen = direct MP4 but byte-identical placeholder files for both cams (no reclassify) · cctvc.freeway.gov.tw = direct MJPEG (live) while cctv-ss0x hosts are NXDOMAIN (prune candidates) · wetmet = widget page with signed HLS inside (extractor candidate, 11 rows) · vegvesen & rtsp.me = HTML · ktict = hard-400 (20 rows) · quebec511 = Cloudflare 403.
- **Options needing verification (next)**: (1) prune/re-resolve the 406 YouTube no-id rows before any ytid warm (4/8 sampled are dead handles); (2) wetmet HLS extractor as a second resolver; (3) freeway cctvc MJPEG reclassification; (4) hover live previews were switched ON in viewer settings during verification — toggle off in Settings → Playback if unwanted.

### A20 · Viewer v0.4.1 — skaping stills, stream-tile snapshots, channel-live resolve (folded 2026-10-06, late afternoon)

> Trigger: owner — "fix the No embeddable id error on some cam views and still did not load errors" + "and HLS no poster message" (screenshots: skaping "Still did not load", "HLS · no poster" tile).

- **Skaping (877 rows; url = HTML player page misclassed as jpeg):** new resolver `skaping.com` → page og:image = newest 10-min S3 JPEG (960×540…1280, no gating). New `GET /api/still/<cid>` relay (resolve + ~90 s bytes memo + one refresh-retry; `?refresh=1`; HEAD-safe 404 or image) + `still_url` row field; frontend stills use `still_url` (fresh rows resolve on first play, never point `<img>` at a page). LIVE: fresh row `c838cd050cc1fed7` (Bromont) modal loaded the current still (1280px, caption "updated 14:56:31").
- **HLS/MJPEG "no poster" tiles:** `get_poster` captures a single ffmpeg frame now (source `snapshot`; SNAPSHOT_GATE cap 2 / 0.3 s; ~3.3 s/row measured; 12 h cache) and the frontend probes `/api/poster/<cid>` for hls/mjpeg (+ youtube no-id, og-first then ytimg). Hls-heavy walls trickle on first load (browser 6-conn queue × snapshot cost) — family warms make them instant; `wfd resolve warm` now includes raw-stream candidates only under an explicit `--host/--family/--protocol`.
- **YouTube no-id ("No embeddable id"):** payloads gain `yt_id`; new `GET /api/resolve/<cid>` (`{ok, kind, yt_id?, live_url?, still_url?, poster_url?, reason?}`; cache-aware, `?refresh=1`; displayable rows only, never a token). Frontend `startYT` = url-id `||` `yt_id`, else resolve-on-demand (loading state → embed, 75 s client guard) with honest "Channel stream not resolved" fallback. LIVE: @dailyseoul `cdded9a05d2c497f` → `RVvYQghFCXk` embedded, state=playing, zero JS errors.
- **Tests:** resolve **26/26** (7 new — skaping og parse on a real-page fixture, still flow + route, snapshot offline, resolve route, image/ytid fields, live skaping e2e) · viewer 17/17 · core 6/6. Parent E2E: node --check clean; fresh skaping still OK; channel-live embed OK; snapshot endpoint 14 ms cached / 3.3 s fresh.
- **Options needing verification (next):** YouTube no-id warm still gated on dead-handle pruning (4/8 sampled 404); skaping 252 "video"-kind rows could get a real video path if their pages expose one (stills serve meanwhile); client-side probe queue for very large hls walls if the first-load trickle annoys.

### A21 · Viewer v0.4.2 — the World Map: Google-Earth-type 3D globe view (folded 2026-10-06, evening)

> Trigger: owner — "align camera location to a world map mesh … a fully navigable 'google earth' type layout on button toggle … rotatable and searchable globe with cameras pinpointed … use the open tabs in my brave browser to research … one up the other similar websites. ideally a dedicated 'WORLD MAP' view." (Brave tab cluster: CesiumJS, GeoLibre, earthenterprise, OpenDataCube, GE-alternatives lists, free-satellite-imagery providers, Mapillary, NASA Earth glTF.)

- **Research first (both banked)**: `research/globe/00-tab-ingest.md` (13 tab sources ingested; feature inventory; imagery table; NASA glTF = model-viewer tech read) + `research/globe/01-stack-decision.md` (evidence-backed stack decision + working proof harness `research/globe/proof/`). Stack call: **MapLibre GL JS v5.24.0** vendored (1.03 MB js + 70 KB css + 76 KB glyph + licence ≈ 1.15 MiB; single-file UMD, no build step) with globe projection + `sky` atmosphere; imagery = **Esri World Imagery** (all zoom, CORS-verified) + **NASA GIBS BlueMarble** z0-8 + optional GIBS labels / VIIRS today / Black Marble night / EOX S2 (off by default, CC-BY-NC-SA). Rejected: CesiumJS (21.7 MB vendored, ion-gated defaults, terrain/3D-Tiles unused) and globe.gl/three.js (no tiling ⇒ no orbit→street zoom).
- **Server**: `GET /api/globe-points` — compact GeoJSON of all geo-valid rows (14,065 of 35,541; short props c/n/s/p/f/y/v; null-island + no-geo excluded; exposure rows only while the surface is on) — 3.41 MB, 0.14 s, cached client-side once per session. Viewer tests 19/19 (2 new: shape/count from the same db + exposure gating).
- **The view (`wfd/web/js/globeview.js`; nav "World Map" hotkey 3; lazy-loaded — maplibre loads only on first open, zero maplibre requests on other views verified)**: clustered pins (supercluster: clusterRadius 55, expansion-click dives in), status-coloured single pins → popup (name · family · protocol · status; [Watch] player modal / [Details] drawer / [★] favourite; metadata-only rows get text, no actions), fly-to search (`#globe-q`, FTS → flyTo z≈13 + popup), random-live-cam teleport ('r'), global-filter linkage (status/protocol/family/country client-side `setFilter` + favourites-only toggle + honest note when q= text search active), viewport "what's here" count + list, URL hash state (`#/globe?lat&lng&z&b&p` + copy-link), auto-rotate toggle, layers popover (labels/night/today/EOX persisted `globe_*` settings), attribution line always on, WebGL2 fallback panel, `window.__globe` debug hook, Help section.
- **Verification**: build child ran node --check (with positive control) + tests 19/19 + its own real-Chromium smoke (`research/globe/02-worldmap-smoke.png`: Blue Marble globe, atmosphere, cluster bubbles 2.6k/957/346…, 144 FPS, WebGL2) incl. lazy-load negative + destroy checks. Parent re-verified on the real viewer (port 8787): hook ready·14065·globe, v5.24.0, attribution exact, View menu "World Map3", search "sydney" → 8 hits → flyTo 1.60→12.88 Sydney + popup with [watch, details, fav], errors 0.
- **Options needing verification (next)**: stretch six from the decision doc (terminator, VIIRS date picker, tours over favourites/stage, ruler, Leaflet mini-map inset, density heatmap); a `fmt=min`/gzip variant of /api/globe-points if 3.4 MB ever feels heavy; confirm frame-rate on the owner's real GPU. NOTE: the globe shows ~14k of 35.5k rows — geocoding coverage, never claim otherwise.

### A22 · World Map stretch six — terminator, date picker, tours, ruler, minimap, heatmap (folded 2026-10-06, evening)

> Trigger: owner — "yes make it great" (approval of the A21 stretch list).

- **Delivered (all in `globeview.js` + CSS + help; no server changes)**: day/night **terminator** (NOAA-style solar math, night-hemisphere fill + glow line, 60 s refresh while on, `globe_terminator`); **"today's Earth" date picker** on the VIIRS layer (path-date WMTS, `globe_today_date` clamped/validated, 1–2 day latency noted); **cinematic tours** (favourites-in-order → stage fallback, flyTo z11.5 / pitch 50 / 6.5 s + 5 s dwell overlay with k/n + Next/Stop, loops, Esc stops, auto-rotate held; coords via `/api/cameras?favourites=1&geo=only`); **great-circle ruler** (top-down ease, vertex dots + dashed line, km+mi readout incl. per-segment, haversine cross-checked to 0.004 %, Done/Esc restores camera); **Leaflet mini-map inset** (260×130, same Esri tiles, viewport rect / centre-dot at z≥7, click-to-fly, `globe_minimap` default ON); **density heatmap** (`globe_heat`, non-clustered copy of the cached points, pins dimmed while on) + **coverage honesty chip** ("14,065 geocoded of 35,541 rows", total from /api/stats).
- **Two real bugs caught + fixed in smoke**: vendored MapLibre v5 has NO `map.distance()` (replaced with a local haversine); Leaflet renders zero tiles at negative fractional zoom (minimap bumped to 260 px so z0 fits).
- **Verification**: strict `node --input-type=module --check` (plain `--check` false-negatives on ESM — noted for future waves) · viewer tests 19/19 (no server delta) · child real-Chromium smoke drove every feature with raw asserts (terminator render-level night/day point sampling; date 2026-10-06→10-01 persisted; tour z11.5 → Esc stop toast; measure readout vs independent haversine 7814.72 vs 7815 km; minimap recentre lng 84 z6; heat layer + dimming; repeated enter/leave zero console errors; prefs restored byte-identical) — `research/globe/03-stretch-smoke.png` · parent spot-check on :8789 (ready · flags · coverage chip · terminator toggle → fill+glow layers, 0 errors) — prefs reverted to defaults after (terminator back off).
- **Next options**: tour un-smoked paths (stage fallback / Next button) code-only; pole caps unshaded beyond ±85° (mercator clamp); MapLibre v6 upgrade path (ESM 3-file swap) when desired.

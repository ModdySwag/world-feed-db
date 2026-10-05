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

Reuse candidates: zero-hud `world_feed.py` channel/health patterns; GEV app schema + serve-stale; go2rtc as restream engine.

## 3 · Decisions so far

- **D1** (10-05) "The lot" = aggregate ready-made corpora (a) + our own per-family enumeration (b). Start: collation of both; builds come after.
- **D2** (10-05) Pipeline basis = WV1's verified methods: direct HLS via ffmpeg; YouTube via yt-dlp (`bv*[height<=720]+ba/b`, channel `/live` URLs, `android_vr` fallback); image-refresh tier; go2rtc restream option. (Evidence: zero-hud WV1 dossier.)
- **D3** (10-05) Seed corpora shortlist: **Live-Environment-Streams** (5,997 entries; 4,226 active; downloaded), **Argus** (229k claim; 100 MB geojson — fetch later), **OpenTrafficCamMap** (7,515; per-state scraper library), **cctv-camera-database** (28,400 specs + RTSP URL patterns, CC0).
- **D4** (10-05) Reference systems to study/borrow: trafficvision.live (155k+ claim; real-time stream testing; map + route UX), Argus (scrapers→SQLite→layered JSON), camforge (connectors + policy module + PostGIS), GEV app (schema, serve-stale), livetrafficcam.com (rolling verified-live checks).
- **D5** (10-05) Default policy: public-by-design only; insecam-class documented-not-scraped pending owner decision (S5 supplies inputs).

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
| W1 | Aggregator networks (non-gov) | `research/sources/S1-aggregators.md` | in flight |
| W2 | Government / institutional | `research/gov/S2-gov-institutional.md` | in flight |
| W3 | Platforms / lists / datasets | `research/platforms/S3-platforms-lists.md` | in flight (steered: dissect trafficvision.live) |
| W4 | Verification / self-heal / scale | `research/ingest/S4-verification-selfheal.md` | in flight |
| W5 | OSINT / policy / management | `research/osint/S5-osint-policy-mgmt.md` | in flight |

## 6 · Open questions (owner decisions)

- **Q1 Scope of "the lot"**: include insecam-class exposed-camera corpora, or exclude? (default: exclude; grey edge: third-party redistributions of such data).
- **Q2 Naming / home**: folder currently `C:\Users\user\world-feed-db`. Keep? Rename? Standalone repo vs fold into zero-hud GEV / moddys.net?
- **Q3 Keys / quotas**: Windy Webcams API key? webcams.travel key? Nimble quota exhausted (402 "trial quota finished" during research — top up if future crawls want it). Hound MCP works as fallback.
- **Q4 Viewer target**: desktop app (GEV-style)? web on moddys.net? zero-hud panel? all three (shared backend)?
- **Q5 YouTube grey zone**: keep "personal/local, non-redistributed" stance per WV1, or adjust?

## 7 · Addenda (wave fold-ins)

*(empty — A1… appended as waves deliver; each opens with trigger + labels recovered/verified/estimated; never rewrites earlier text)*

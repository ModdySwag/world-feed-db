# World Feed DB

Research + build program: a comprehensive, worldwide, updateable, **self-healing** database and viewing system for public "live" video feeds — traffic cameras, webcams, HLS/RTSP/MJPEG streams, refreshing-image cams, and 24/7 YouTube-live channels. End goal: an access point for as many working live video feeds as exist on the internet, with an inbuilt mechanism for searching sources and adding/removing them.

Owner: Moddy. Started: 2026-10-05 (seeded by a Brave tab-gathering session; see `research/seed-tabs/TABS-LIST.md`).

## Status

- **2026-10-05 — Research phase.** Seed ingest complete: all 19 open Brave tabs + session extras fetched and saved under `research/seed-tabs/`. Five research waves dispatched (S1 aggregators · S2 government · S3 platforms · S4 verification/self-heal · S5 OSINT/policy) — evidence lands under `research/<area>/S<n>-*.md`. Catalog + plan are living documents.
- The collation of sources + endpoints: `SOURCES-CATALOG.md`.
- Decisions + waves log + open questions: `PLAN.md` (addenda appended per wave; earlier text never rewritten).

## Map

| Path | What |
|---|---|
| `SOURCES-CATALOG.md` | THE collation: source families, endpoints, scale, licenses, status |
| `PLAN.md` | Living plan: architecture sketch, decisions, open questions, addenda |
| `research/seed-tabs/` | Brave tab corpus (TABS-LIST.md + per-page evidence: topics JSON, repo READMEs/trees, issues, reddit captures) |
| `research/seed-tabs/data/LES-streams.geojson` | Live-Environment-Streams corpus (5,997 streams; 4,226 active) — best ready-made dataset found so far |
| `research/seed-tabs/data/LES-sources.json` | L-E-S source-family index (67 families with counts) |
| `research/sources/` · `research/gov/` · `research/platforms/` · `research/ingest/` · `research/osint/` | Wave evidence files (S1–S5) |

## Related prior art (local)

- `C:\Users\user\zero-hud\reference\world\WV1-live-video-sources.md` — verified ingestion methods M1–M7 + 25-source catalog (2026-10-03).
- `C:\Users\user\zero-hud\server\world_feed.py` — live world-feed sidecar (:8772): 5 curated channels, lazy ffmpeg → MJPEG proxy, honest health states.
- `C:\pinokio\api\gods-eye-view.git` — God's Eye View reference app (:42011): georeferenced CCTV schema, proxy+cache+serve-stale pattern, per-source licensing discipline.

## Policy line (default — owner decision pending, inputs in S5)

Owner decision 2026-10-05: scope **includes insecam-class exposed cameras** as an explicitly-flagged category (`provenance: exposed` + warning badge + own filter). Everything else stays public-by-design. Handling rules for the flagged layer: consume existing public datasets where they exist instead of re-scraping; stay rate-polite against hosters; keep the provenance flag intact so any future public release can diverge.

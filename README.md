# World Feed DB

Research + build program: a comprehensive, worldwide, updateable, **self-healing** database and viewing system for public "live" video feeds — traffic cameras, webcams, HLS/RTSP/MJPEG streams, refreshing-image cams, and 24/7 YouTube-live channels. End goal: an access point for as many working live video feeds as exist on the internet, with an inbuilt mechanism for searching sources and adding/removing them.

Owner: Moddy. Started: 2026-10-05 (seeded by a Brave tab-gathering session; see `research/seed-tabs/TABS-LIST.md`).

## Status

- **2026-10-05 — Research phase: all five waves DONE and folded.** Seed ingest: 19 Brave tabs + session extras (`research/seed-tabs/`). Waves S1–S5 executed by subagents; every evidence file read + spot-checked by the parent and folded into `PLAN.md` as addenda A1–A5, with the catalog updated per wave (all committed to git).
- The collation of sources + endpoints: `SOURCES-CATALOG.md` — gov/institutional verified menu (§1), aggregator measurements (§2), platforms/fixtures (§3), reference systems (§4), ready-made corpora (§5), flagged exposure category (§6).
- Decisions + waves log + open questions **Q2–Q11**: `PLAN.md` (living; earlier text never rewritten).
- Next: owner decisions on Q2–Q11, then build-phase framing — first small artifacts are the dataset ingesters + provenance/redaction gate, and the enumerator set from the S1/S2 endpoint menus.

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

## Build principles (locked 2026-10-05)

- **Personal-first, open-source-ready.** The initial build is for Moddy alone, but the repo must be publishable at any time: no secrets ever in code or git; everything config-driven; setup docs kept current.
- **Credentials in, keys out.** The app ships a credential/settings layer (per-user secure store + config file) for website logins, API keys and tokens — every key-gated source shows an honest `KEY REQUIRED` state until its credential is supplied, and the app ships an onboarding checklist. The live list of accounts to create: `ACCOUNTS-AND-KEYS.md` (the owner is prompted as the build proceeds).
- **Two artifacts, one codebase (D7.1).** ① *Clean template* — public/open-source-ready: no secrets, keyless, runs degraded with honest `KEY REQUIRED` states; anyone can clone + configure. ② *Moddy build* — template + a **private profile overlay** (keys, curation, preferences; never committed) that is ready to go on Moddy's machine.

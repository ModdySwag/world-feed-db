# ACCOUNTS & KEYS — owner checklist (living)

**Build principle (D7):** personal-first, open-source-ready. All credentials live OUTSIDE the repo in a per-user settings/credential layer (secure store + config file; never hardcoded). Every key-gated source shows an honest `UNAVAILABLE · KEY REQUIRED` state until its credential is supplied. When the app's settings surface exists, keys go straight into it (or a local `.env` it reads) — **never into chat, never into git**.

How this works: as each build stage needs an account, it appears here with a signup link and a status box. Owner creates the account; the key lands in the app config. These credentials all belong to the **`moddy` profile** (the ready-to-go build); the public **clean template** ships without them and runs degraded until a user supplies their own.

## Priority 1 — create when convenient (unlocks big ingest)

| # | Service | Unlocks | Signup | Status |
|---|---------|---------|--------|--------|
| 1 | **Windy Webcams API** (free tier) | 70k+ webcam metadata / discovery layer (S1) | https://api.windy.com/webcams/ → "Get API key" | ⬜ to create |
| 2 | **Road511 API** (free key) | 20-state US traffic-cam gateway (S2) | https://road511.com (API/developer signup) | ⬜ to create |
| 3 | **Transport for NSW Open Data** (free key) | NSW live traffic cams, CC-BY (S2) | https://opendata.transport.nsw.gov.au | ⬜ to create |
| 4 | **QLDTraffic API** (free registration) | Queensland webcams (S2) | https://api.qldtraffic.qld.gov.au | ⬜ to create |

## Priority 2 — optional discovery lanes (metered, policy-gated)

| # | Service | Unlocks | Signup | Status |
|---|---------|---------|--------|--------|
| 5 | Shodan (free API plan) | candidate discovery (wrapped in provenance gate; never device-touch) | https://account.shodan.io/register | ⬜ optional |
| 6 | Censys Platform (Free) | secondary discovery | https://accounts.censys.io/register | ⬜ optional |

## Priority 3 — bulk/rate lanes (only if wanted)

| # | Service | Unlocks | Signup | Status |
|---|---------|---------|--------|--------|
| 7 | YouTube Data API v3 key | bulk live-channel enumeration quota (yt-dlp stays keyless default) | https://console.cloud.google.com/apis/credentials | ⬜ optional |
| 8 | LTA DataMall AccountKey (SG) | alt bulk lane (data.gov.sg keyless covers basics) | https://datamall.lta.gov.sg | ⬜ optional |
| 9 | TfL app key | raises TfL rate limit | https://api-portal.tfl.gov.uk | ⬜ optional |
| 10 | NASA FIRMS MAP_KEY | fire layer (if integrated, GEV-style) | https://firms.modaps.eosdis.nasa.gov/api/map_key/ | ⬜ optional |
| 11 | Launch Library 2 token | >15 req/h lane | https://thespacedevs.com/llapi | ⬜ optional |
| 12 | TomTom API key | traffic layer (if integrated) | https://developer.tomtom.com | ⬜ optional |

Separate (my tooling, not the app): Nimble top-up — see PLAN Q3.

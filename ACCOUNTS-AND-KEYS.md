# Accounts & keys — acquisition guide

**Principle:** all credentials live OUTSIDE the repo in the per-profile settings/credential layer (a secure store plus a gitignored `.env`). Every key-gated source shows an honest `UNAVAILABLE · KEY REQUIRED` state until its key is supplied — the app runs fine keyless, just with those lanes dark. **Never commit keys; never paste them anywhere public.**

How keys resolve: `wfd creds` keyring store → the active profile's `.env` (e.g. `profiles/<your-profile>/.env`, gitignored) → environment variables. Status any time: `py -3.11 -m wfd keys` (status only — values are never printed).

## Key-gated lanes (create when you want them)

| # | Service | Unlocks | Signup | Notes |
|---|---------|---------|--------|-------|
| 1 | **Windy Webcams API** (free tier) | 70k+ webcam metadata / discovery layer (S1) | https://api.windy.com/webcams/ → "Get API key" | env `WINDY_API_KEY` |
| `X-API-Key` header, or `api_key` query param; env `ROAD511_API_KEY` |
| 3 | **Transport for NSW Open Data** (free key) | NSW live traffic cams, CC-BY (S2) | Log in at opendata.transport.nsw.gov.au → **profile icon → "API Tokens" → name → CREATE API TOKEN** (shown once) → paste as `NSW_API_KEY`. Header usage: `apikey <token>`; product = Live Traffic Cameras (`api.transport.nsw.gov.au/v1/live/cameras`) | env `NSW_API_KEY` |
| 4 | **QLDTraffic API** (free registration) | Queensland webcams (S2) | **No self-serve:** email `qldtraffic@tmr.qld.gov.au` with: Organisation name · Contact person · Email · Application name → admin issues the key (spec v1.10: key passed **in the URL**, not header) | env `QLDTRAFFIC_API_KEY` |

## Optional lanes

| # | Service | Unlocks | Signup | Notes |
|---|---------|---------|--------|-------|
| 5 | Shodan (free plan) | candidate discovery (provenance-gated; never device-touch) | https://account.shodan.io | search-only use; env `SHODAN_API_KEY` |
| 6 | Censys Platform (Free) | secondary discovery | https://accounts.censys.io/register | — |

## Bulk / rate lanes (only if wanted)

| # | Service | Unlocks | Signup | Notes |
|---|---------|---------|--------|-------|
| 7 | YouTube Data API v3 key | bulk live-channel enumeration quota (yt-dlp stays keyless default) | https://console.cloud.google.com/apis/credentials | — |
| 8 | LTA DataMall AccountKey (SG) | alt bulk lane (data.gov.sg keyless covers basics) | https://datamall.lta.gov.sg | — |
| 9 | TfL app key | raises TfL rate limit | https://api-portal.tfl.gov.uk | — |
| 10 | NASA FIRMS MAP_KEY | fire layer (if integrated) | https://firms.modaps.eosdis.nasa.gov/api/map_key/ | — |
| 11 | Launch Library 2 token | >15 req/h lane | https://thespacedevs.com/llapi | — |
| 12 | TomTom API key | traffic layer (if integrated) | https://developer.tomtom.com | — |

Note: keys live in the active profile's `.env` (gitignored; a placeholder-only `.env.example` ships with the `clean` profile).

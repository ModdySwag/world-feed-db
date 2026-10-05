# S1 · Non-government webcam aggregator networks — sources + endpoints (research wave S1, 2026-10-05)

Scope: commercial/community webcam aggregator networks worldwide — the "non-government" slice of the world-feed-db build. Per network: scale (count + date + source), access mechanism, concrete endpoint patterns, licensing/ToS note, verification method, verdict + build component.

**Policy line (hard):** public-by-design sources only. No probing/scanning of private or exposed cameras (insecam-style or Shodan-based "OpenCCTV" tools were deliberately NOT used). Everything below was collected by fetching public pages/APIs that these operators publish for the public, with polite rate limits and an identification UA.

**Method + tooling:** curl (MSYS bash), Python 3.11 (urllib crawls), yt-dlp (channel enumeration), browser tool (JS-rendered pages + network-resource capture), Wayback CDX (dead-domain forensics). All counts below were measured **2026-10-05 ACST** unless a different date is stated next to the number. Counts marked **(verify)** are from third-party statements, not independently reproduced.

**Status legend:** ADOPT = build on it now · REFERENCE = useful pattern/secondary source · SKIP = do not build on it.

---

## Snapshot table

| # | Network | Measured scale (2026-10-05) | Access | Verdict |
|---|---------|------------------------------|--------|---------|
| 1 | Skyline Webcams | 2,447 cam pages / 71 countries / 217 regions (full crawl) | HTML crawl; JS token player | **ADOPT** — registry/discovery |
| 2 | Windy Webcams API v3 | 40K (2021) → 70,000+ (2026) claimed | REST API, key required | **ADOPT** — discovery/registry |
| 3 | webcams.travel | merged into Windy (302) | redirect only | **REFERENCE** |
| 4 | Lookr | merged into Windy (302) | redirect only | **REFERENCE** |
| 5 | OpenCCTV.com | DOMAIN DEAD (parked) | — | **SKIP** |
| 6 | EarthCam | 365 cams via keyless enumeration (36 countries + 45 US states); app claims 1,500+ | 2 keyless JSON endpoints | **ADOPT** — registry/discovery/liveness |
| 7 | WebcamTaxi | 1,950 cam URLs / 67 listing pages | HTML crawl → YouTube embeds | **ADOPT** — registry |
| 8 | CamGuide.net | 5,052 unique pages (25,260 with translations) | sitemap → iframes/YouTube | **ADOPT** — registry |
| 9 | webcamera.pl | 600+ cams claimed; per-cam subdomains + MP4 image server | HTML + imageserver | **REFERENCE** |
| 10 | BalticLiveCam | 435 cams / 91 countries (site counter); 1,278 camera pages (sitemap) | HTML crawl; token-gated HLS player | **ADOPT** — registry (viewer needs token flow) |
| 11 | WorldCams.tv | 775 cam-card URLs across 38 sections | HTML crawl → YouTube embeds | **REFERENCE** |
| 12 | explore.org | 1,137 feeds / 101 cam groups (keyless JSON API) | omega.explore.org JSON | **ADOPT** — registry/discovery/liveness |
| 13 | Roundshot | 561 livecams w/ per-cam status (470 working) | keyless JSON directory + per-site JSON | **ADOPT** — registry/liveness |
| 14 | earthTV | 495 places (API); 278 webcam pages (EN sitemap) | keyless places API; tokenized player | **REFERENCE** |
| 15 | AfriCam | 43 lodge/location pages, 6 countries | HTML scrape → YouTube embeds | **REFERENCE** |
| 16 | Skyline YouTube | 580 stream entries (composite mosaics) | yt-dlp | **REFERENCE** — viewer |
| 17 | IPCamLive | no public directory; per-alias hosting | per-cam pages + AJAX state | **REFERENCE** — viewer |
| 18 | CamStreamer Live gallery | not quantified (endpoint not found) | web gallery (client-side) | **REFERENCE** — discovery idea |

---

### 1 · Skyline Webcams
- https://www.skylinewebcams.com/ · directory: https://www.skylinewebcams.com/en/webcam.html · cam example: `https://www.skylinewebcams.com/en/webcam/italia/sicilia/catania/etna-nord.html`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** full crawl of the EN directory found **2,447 camera pages across 71 countries / 217 regions**. Top countries: Italia 989 · United States 317 · España 247 · Ellada 226 · United Kingdom 77 · Malta 70 · Deutschland 65 · Norge 37. (Method: crawled country → region → city pages; per-country table saved in `skyline_counts.json`.) Cross-ref: prior project inventory (LES, 2026-10-03) counted 1,684 stream URLs w/ 1,284 active — different scope (ingested streams vs. live directory pages).
- KEY FACTS — **Access:** pure HTML crawl; server-rendered, stable URL pattern. Listing pages: `/en/webcam/<country>.html` → `/en/webcam/<country>/<region>.html` → cam pages `/en/webcam/<country>/<region>/<city>/<slug>.html`. Region pages use **relative hrefs without leading slash** (`href="en/webcam/..."`) — normalise before parsing. No JSON API, no sitemap (`/sitemap.xml` empty=22 B; `/sitemap_index.xml` empty; other sitemap paths 404).
- KEY FACTS — **Stream side (PARTIAL):** the player is JS-only (`cdn.jsdelivr.net/gh/SkylineWebcams/web@v2/sky.js`); the cam page HTML contains **no** static `.m3u8`, `hd-auth`, or token strings (checked on etna-nord.html). Prior dossier reports a tokenized pattern `hd-auth.skylinewebcams.com/live.m3u8?a=<token>`; not reproduced statically this pass → stream resolution needs a real browser/page-execution extractor (or an iframe embed of their player page).
- KEY FACTS — **License/ToS:** free public viewing site; fair-use/attribution posture; ads-supported; do not re-stream. Polite crawl worked fine at ~6 concurrent fetches (~2,400 pages, no blocks).
- **Verification:** executed full directory crawl (script `skyline_crawl.py`, log + `skyline_counts.json`); spot-checked 5 country/region pages manually.
- **VERDICT: ADOPT** — richest single keyless directory in this slice. Build: **registry + discovery** (directory crawler); **viewer** = separate token-extraction spike (M effort); pairs with entry 16 for a no-token video tier.

### 2 · Windy Webcams API v3
- https://api.windy.com/webcams/docs · pricing: https://api.windy.com/webcams/pricing · consumer: https://www.windy.com/webcams
- KEY FACTS — **Scale (third-party statements):** "around **40K** active webcams available via API" — Windy staff, community.windy.com topic 16443, **2021-05-10**; "we talk about **70 000+** of webcams" — Windy staff, community topic 44535, **2026-05-25**. Docs call it "the largest repository of webcams worldwide". Exact current count is dynamic; both attributable figures above (still marked **(verify)** for "today's" number — needs a key to enumerate).
- KEY FACTS — **Access:** REST JSON, key required. Header: `x-windy-api-key: <API_KEY>`; keyless calls return **HTTP 403** (re-verified 2026-10-03 in WV1 dossier). Free tier = rate-limited; keys self-serve ("It may take a few minutes before your newly created API key is accessible").
- KEY FACTS — **Endpoints (from the v3 docs page, 2026-10-05):** `GET https://api.windy.com/webcams/api/v3/webcams` (filter by country/category/bbox/limit/offset) · `/webcams/api/v3/webcams/{webcamId}` · `/webcams/api/v3/categories` · `/webcams/api/v3/countries` · `/webcams/api/v3/regions` · `/webcams/api/v3/cities` · `/webcams/api/v3/continents` · `/webcams/api/v3/map/clusters`. Pricing page: "Get a list of all available webcams, refreshed regularly… via a single API call."
- KEY FACTS — **Image/stream note:** image URLs are **tokenized** — expire **10 min (free tier) / 24 h (professional)**; expired URL → HTTP 401. Docs recommend re-calling `/webcams` per page load. Webcams are image/timelapse data (not usually video HLS); it's the world's best "where are cams + conditions" metadata layer.
- KEY FACTS — **License/ToS:** Windy API terms; attribution required; free tier rate caps; commercial use = paid tier. Brand note: webcams.travel + lookr.com were merged into this API (see entries 3–4) — one key covers all three brands.
- **Verification:** fetched docs + pricing pages (2026-10-05); keyless probe returns 403 (matches prior wave); community statements retrieved with dates.
- **VERDICT: ADOPT** — the single best cross-check/discovery layer. Build: **discovery + registry cross-validation** (store free key in config; treat image URLs as short-lived → refresh ≤10 min or store only metadata).

### 3 · webcams.travel (merged into Windy)
- https://www.webcams.travel → HTTP 302 → `https://www.windy.com/webcams` · old API host https://api.webcams.travel → 302 → same.
- KEY FACTS — **Status (VERIFIED, 2026-10-05):** brand redirected into Windy; no independent service remains. Redirect chain captured with curl -I today. Historical: founded **2007** by Jörg Eugster (Switzerland); "Windy joins forces with Webcams.travel" (community.windy.com/topic/10269); account migration emails went out around **Dec 2019**; "both websites (webcams.travel, lookr.com) should be redirected to Windy.com/webcams". Windy's own API v2→v3 migration guide explicitly targets former webcams.travel API users.
- KEY FACTS — **Access:** none (redirect). Scale = Windy repository (see entry 2).
- **Verification:** live redirect test + Windy community posts (dates above).
- **VERDICT: REFERENCE** — record only: any scraper built around webcams.travel's old API must move to Windy API v3. Build: **mgmt** (dead-source list; redirect-domain sentinel).

### 4 · Lookr
- https://lookr.com → HTTP 302 → `https://www.windy.com/webcams` (verified 2026-10-05).
- KEY FACTS — **Status:** same story as webcams.travel — Lookr (founded **2013** by the same operator; modern "weather cam" consumer site) merged into Windy ~2019–2020; old accounts/favourites migrated to Windy; site now a permanent redirect. Source: community.windy.com topic 10269 + topic 11365 (migration notice, Dec 2019) + topic 10442 ("old lookr is not available anymore… all webcams now accessible through windy").
- KEY FACTS — **Access:** none (redirect). 
- **Verification:** live redirect test + Windy community posts with dates.
- **VERDICT: REFERENCE** — same as entry 3; note for the registry that both dead brands funnel to Windy. Build: **mgmt** (dead-source list).

### 5 · OpenCCTV.com — DOMAIN DEAD
- https://opencctv.com → redirects to HugeDomains sale page: `https://www.hugedomains.com/domain_profile.cfm?d=opencctv.com` (verified 2026-10-05, both apex and www). Page title: "OpenCctv.com is for sale | HugeDomains".
- KEY FACTS — **Status:** the 746-stream public-feed aggregator listed in the project's seed inventory (LES-sources.json, `opencctv` 746 records / 668 active) is **no longer online**. Wayback CDX shows snapshots through **2025-07-12**; none in 2026. Timestamped evidence: fetch of opencctv.com on 2026-10-05 landed on a HugeDomains parked page (HTTP 200 via hugedomains.com).
- KEY FACTS — **Do not confuse with:** GitHub "OpenCCTV" repos (e.g. `nak0823/OpenCCTV`, a Shodan-based tool for finding *unsecured* cameras) — **out of policy**, never to be used or mirrored by this program.
- KEY FACTS — **Action for the registry:** purge/flag the 746 stored `opencctv` stream URLs as DEAD-SOURCE (domain lapsed); keep the stream records only as historical evidence.
- **Verification:** live fetch + redirect chain (curl), Wayback CDX query (last snapshot 2025-07-12).
- **VERDICT: SKIP** — dead source. Build: **mgmt** (dead-source purge + domain-health checks; this is exactly the failure mode a self-healing registry must catch).

### 6 · EarthCam network
- https://www.earthcam.com/ · https://www.earthcam.com/network/ · app site https://www.earthcamtv.com/
- KEY FACTS — **Scale (VERIFIED today + attributable claims):** keyless enumeration of the network page's own search endpoint returned **365 cams**: **70 across 36 country tabs + 295 across 45 US state tabs** (2026-10-05; per-location counts saved `s1_crawl_results.json` + `earthcam_us.json`). Top US states: NY 44 · FL 41 · TX 16 · PA 15 · NC 11 · CA 10. Top world: Aruba 7 · Canada 7 · Taiwan 5. Separately, EarthCamTV app pages claim "**over 1,500 worldwide destinations**" (earthcamtv.com, fetched 2026-10-05; EarthCam press releases: +200 cams for Earth Day 2022, "more than 1,500 destinations" then) — the app catalog is bigger than what network_search exposes; treat 1,500+ as vendor claim **(verify)**.
- KEY FACTS — **Access (two keyless JSON endpoints, found in page JS vars):**
  1. **Network search:** `https://www.earthcam.com/api/dotcom/network_search.php?r=ecn&a=fetch&country=<Country>` (+ `&state=<XX>` with `country=US` for states; `&state=america250` special). Returns `{"status":"200","data":{"cam_count":N,"cam_items":[{id, city, state, country, title, description, cam_state, thumbnail, thumbnail_large, url, ...}]}}`. Send `Referer: https://www.earthcam.com/network/` — without it the endpoint **429s immediately**; with it + ~1.5 s spacing, 81 calls completed cleanly today (0 errors).
  2. **EarthCamTV playlist:** `https://www.earthcam.com/api/ectv/player/playlist.php?r=playlist&a=fetch` → 27.8 KB JSON (`playlist_trending` 4 + `playlist_featured` 8 items), each item carries a **tokenized HLS URL**: `https://videos-3.earthcam.com/fecnetwork/<id>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>` + static thumbnails `https://static.earthcam.com/camshots/512x288/<hash>.jpg` + lat/long + timezone + `cam_state`.
- KEY FACTS — **Schema quality:** item fields include lat/long, timezone, `cam_state` (1=live) — excellent for a liveness layer. Tokens are time-stamped (`td=`), assume short-lived → refresh playlist on demand.
- KEY FACTS — **License/ToS:** commercial network; site says cams are for viewing; tokens + rate limits imply no bulk abuse; don't re-stream. Crawl politely (≥1.5 s between calls).
- **Verification:** found endpoints in inline JS of /network/; executed full crawl of world+US tabs with counted results; parsed playlist JSON; measured 429 behavior.
- **VERDICT: ADOPT** — the best *structured* commercial source in the slice. Build: **registry + discovery** (network_search enumerator by country/state), **liveness** (cam_state), **viewer** (playlist HLS with refresh).

### 7 · WebcamTaxi
- https://www.webcamtaxi.com/en/ · sitemap: https://www.webcamtaxi.com/sitemap.xml
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** sitemap lists **175 URLs → 67 listing pages** (countries + topical categories). Crawl of all listing pages found **1,950 unique camera URLs** of the pattern `/en/<country-or-category>/<place>/<slug>.html`. Largest pages: usa 707 · japan 134 · russia 133 · spain 106 · netherlands 95 · england 83 · italy 79 · canada 66 · germany 56 · norway 54. (Count = unique cam-detail URLs discovered; site's own counters not published.)
- KEY FACTS — **Access:** static HTML crawl; server-rendered. Cam pages embed players — verified sample `/en/austria/vienna/am-himmel.html` contains `iframe src="https://www.youtube.com/embed/live_stream?channel=UC8mM8VHZGjdVMldeowGb2Bw&autoplay=1"` → **YouTube channel-live embeds** (plus Google-maps iframes for location). Pipeline: listing crawl → cam page → extract iframe → resolve YouTube channel/video via yt-dlp.
- KEY FACTS — **License/ToS:** "all world cams are free to view"; aggregator of third-party feeds incl. "live breaking news" cams; attribution + fair use; don't re-stream.
- **Verification:** sitemap fetched; crawled 67 pages; total computed; sample cam page inspected (iframe pattern).
- **VERDICT: ADOPT** — large keyless directory; pipeline is HTML → YouTube (needs the yt-dlp layer). Build: **registry + discovery**.

### 8 · CamGuide.net
- https://camguide.net/ · sitemap: https://camguide.net/sitemap.xml
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** sitemap = **25,260 URLs = 5,052 unique location pages × 5 language variants** (default + es/fr/de/ru). Regional segments: **usa 3,218 · europe 956 · canada 333 · mexico 208 · asia 158 · oceania 75 · costa-rica 17 · bahamas 17** (+ long tail). URL pattern: `/usa/<state>/<city>/<topic>/` e.g. `/usa/idaho/boise/road/`, `/usa/iowa/des-moines/traffic/`.
- KEY FACTS — **Access:** sitemap XML for full discovery; cam pages embed third-party sources. Verified sample `/usa/idaho/boise/road/` embeds a US DOT cam via iframe: `https://511.idaho.gov/map/Cctv/4115--3`; their player JS `/js/webcam.js` handles **YouTube embeds** (`youtube.com/embed/`). So: page → iframe/src → upstream system (DOT feeds, YouTube, ipcamlive-class players).
- KEY FACTS — **License/ToS:** aggregator of public feeds; ads; per-embed rights belong to upstream. Small site (single dev) — crawl politely.
- **Verification:** full sitemap download + segment counting (script); sample page + player JS inspected.
- **VERDICT: ADOPT** — biggest *page-count* directory here and mostly derivable to upstream (DOT) sources. Build: **registry** (seed importer from sitemap) + **discovery** (follow embeds upstream).

### 9 · webcamera.pl
- https://webcamera.pl/ ("największy portal z kamerami w Polsce" — Poland's biggest cam portal)
- KEY FACTS — **Scale:** site claim (og:description, fetched 2026-10-05): "**ponad 600 kamer w Polsce**" (over 600 cameras in Poland) **(verify)**. Homepage links **34 distinct cam subdomains** of the form `https://<slug>.webcamera.pl/` (e.g. `zakopane-krupowki-kamera-na-zywo.webcamera.pl`). Main sitemap has 5,311 URLs but is mostly articles/tags, not cam pages.
- KEY FACTS — **Access:** per-cam **subdomain sites** (self-contained player pages), plus a **rolling MP4 image server**: verified `https://imageserver.webcamera.pl/rec/<slug>/latest.mp4` → HTTP 200, `video/mp4`, byte-range fetch returned a real MP4 header (3,001-byte chunk, "ISO Media, MP4 Base Media"). No `.m3u8` in static cam page HTML (player is JS/ads-heavy). So a robust build eats the `latest.mp4`/thumbnail pattern rather than the live player.
- KEY FACTS — **License/ToS:** commercial portal; regional cams; fair use; the imageserver pattern is per-public-cam. Polish-language.
- **Verification:** homepage + og meta + subdomain page + imageserver byte-range test (all 2026-10-05).
- **VERDICT: REFERENCE** — nice regional addition; use as **registry** seeds + **viewer** via `latest.mp4` snapshot loop (when a stable per-cam slug list is exported from their site).

### 10 · BalticLiveCam
- https://balticlivecam.com/ · cam example: https://balticlivecam.com/cameras/bulgaria/burgas/burgas-beach/
- KEY FACTS — **Scale (both measured 2026-10-05, discrepancy noted):** homepage live counters: **91 countries · 735 cities · 435 cameras**; sitemap (`page-sitemap1..12.xml`) lists **1,278 `/cameras/` URLs**. Interpretation: counters likely show *currently online*, sitemap = all-time pages (incl. offline). Record both; the sitemap number is the enumerable ceiling.
- KEY FACTS — **Access:** HTML crawl of `/cameras/<country>/<city>/<cam>/`; player is a **token-gated HLS flow**: cam page inline JS carries `var data = { action: 'auth_token', id: <camId>, embed:0, main_referer: document.referrer }` → POSTed to WP `https://balticlivecam.com/wp-admin/admin-ajax.php` → token → **video.js + videojs-contrib-hls** (`themes/Blc/videojs/plugins/videojs-contrib-hls/...`) plays the HLS. No static `.m3u8` in HTML (verified on burgas-beach page). Pipeline: crawl directory statically; stream requires executing the auth_token handshake.
- KEY FACTS — **License/ToS:** free viewing, ad-supported; WordPress + plugins (WPML, AdOcean ads). Attribution; no redistribution; please pace crawls (WP shared hosting).
- **Verification:** homepage counters + 12 sitemap files counted (1,278); cam page inline-script analysis (token flow found).
- **VERDICT: ADOPT (registry) / viewer = M-effort token spike** — solid EU/Baltic+world directory with clean sitemap; stream layer needs the token flow reproduced (documented above).

### 11 · WorldCams.tv
- https://worldcams.tv/ · example: https://worldcams.tv/canada/toronto/city-views
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** crawl of 38 public sections (country + category pages, with `?page=N` pagination) found **775 unique cam-card URLs**. Largest sections: united-states 300 · cities 188 · water 93 · beaches 87 · airports 76 · trains 76 · 4k 72 · united-kingdom 60 · japan 49 · bars 45. Count = card links (some category-page overlap possible — treat as discovery hints).
- KEY FACTS — **Access:** cam pages embed **YouTube iframes** — verified sample `/canada/toronto/city-views` → `youtube.com/embed/bbjwotvAvDM?autoplay=1&rel=0` (plus related-cam embeds in page). Site shares infrastructure/ops with earthTV (robots.txt disallows `/earthtv`; both serve "The World Live"-class content). **robots.txt restrictions: `/player`, `/list/`, `/ajax/`, `/go`, `/?tab=` are disallowed** — avoid those paths in the production crawler (use country pages).
- KEY FACTS — **License/ToS:** aggregator ("we actively search the net"); YouTube-embedded streams; ads. Respect robots; treat as a YouTube-id discovery layer.
- **Verification:** homepage nav crawl + 38 sections paginated + sample cam page inspection; robots.txt read.
- **VERDICT: REFERENCE** — medium value; but it's another cheap source of **YouTube live IDs** for the liveness/viewer tier. Build: **registry** seeds (low priority).

### 12 · explore.org
- https://explore.org/livecams · API: https://omega.explore.org/...
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** keyless API `https://omega.explore.org/api/initial?contenttype=livecams` → **101 cam groups, 1,137 feeds** (sum of `feed_count`, all groups active). Channels: Birds 25 groups · Zen Cams 16 · Oceans 15 · Featured 11 · Multi-View 7 · Dog Bless You 7 · Africa 6 · Bears 6 · Sanctuaries 4 · Cat Rescues 3 · All Cams 1. The consumer site's "Currently Live" page then filters to live-now (section counters ~83/10/4/3/5 streams…).
- KEY FACTS — **Access (KEYLESS JSON API — a flagship find):**
  - Directory: `https://omega.explore.org/api/initial?contenttype=livecams` (groups + feeds + countries + channels + `snapshotToken`).
  - Per-cam detail: `https://omega.explore.org/api/get_livecam_info.json?id=<feedId>` → includes **`video_id` (YouTube video id)**, `stream_id`, `current_viewers`, `is_offline`, `is_inactive`, latlong, weather, `canonical_url`. Verified id=44 → `video_id=-m_nQT62B4Y`, `stream_id=84`; id=79 group endpoints also exist: `get_cam_group_info.json?id=79`, `get_cam_group_snapshots.json?id=79`.
  - So: enumerate (API) → resolve each feed's YouTube video (yt-dlp/embed) → viewer tier; no HTML scraping needed at all.
- KEY FACTS — **License/ToS:** explore.org is a philanthropic (Annenberg Foundation) network; "cams are meant to be watched"; stills served from `files.explore.org` / `media.explore.org`; casual viewing + attribution fine; keep request volume modest.
- **Verification:** API responses fetched + parsed today (counts above); page load network capture confirmed the endpoints; sample cam info parsed.
- **VERDICT: ADOPT** — cleanest non-government pipeline after Roundshot. Build: **registry + discovery + liveness** (current_viewers/is_offline) + **viewer** (video_id → yt-dlp).

### 13 · Roundshot (Seitz Phototechnik AG)
- https://www.roundshot.com/ · references: https://www.roundshot.com/en/livecam-references.html/102 · directory JSON: https://backend.roundshot.com/schema_list/12/list_frame.json
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** the backend JSON lists **561 livecams with per-cam status: 470 working · 53 broken · 32 idle · 5 late · 1 error**. Categories: Ski resorts 257 · Tourism associations 82 · Villages 42 · Corporates 40 · Hotels 38 · Construction 18 · Airports 14 · Cities 13 · Harbors 13 · Weather 8. Regions: Switzerland 438 · USA 34 · France 31 · Spain 18 · Germany 12 · Finland 7 · Canada 6 · Australia 4. (The references HTML page embeds 362 `*.roundshot.com` subdomains.) It's a *hardware* network (Roundshot Livecam cameras, up to ~144 MP panoramas, 10-min update cadence).
- KEY FACTS — **Access (two layers, both keyless):**
  - **Global directory:** `https://backend.roundshot.com/schema_list/12/list_frame.json` → array of `{picture, link, name, status: working|broken|idle|late, generation, date, altitude, cam_name, customer_name, category, region}`. `status` = ready-made liveness feed. Thumbnails: `https://backend.roundshot.com/cams/<id>/thumbnail`.
  - **Per-install self-describing JSON:** each `https://<customer>.roundshot.com/` serves `structure.json` (image history + tile pyramid: `storage2.roundshot.com/<hash>/<YYYY-MM-DD>/<HH-MM-SS>/<...>_full3.jpg` with `%x%_%y%` tiles), `settings.json` (name/colours/ids), `i18n.json`. Verified on `lustdorf.roundshot.com`.
- KEY FACTS — **License/ToS:** images published on customer sites for public viewing; vendor-run network; attribution; no documented open data license → fair use, low-volume polling (10-min cadence makes this cheap: one JPEG per cam per ~10 min).
- **Verification:** list_frame.json fetched + parsed (counts/status/categories); per-site structure/settings JSONs fetched; browser network capture confirmed endpoints.
- **VERDICT: ADOPT** — exemplary self-healing source: directory + per-cam status + tiled image URLs. Build: **registry + liveness** (status field) + **viewer** (JPEG panorama tier; snappy "near-live" wall tile).

### 14 · earthTV
- https://www.earthtv.com/en/webcams · places API: https://www.earthtv.com/api/v1/places · player host: https://player.earthtv.com · media: livecloud.earthtv.com
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** keyless `GET https://www.earthtv.com/api/v1/places` → `{"count": 495, "items": [...]}` (20 items per response; `page`/`limit`/`offset` query params did NOT change paging in tests — pagination mechanism unresolved, note for the importer). Items carry `id, slug, title, published, isLive, city, country, coordinates, channels, views, metaDescription`. EN sitemap (`/en/sitemap.xml`) lists **561 URLs incl. 278 individual `/webcam/` pages** + 263 `/webcams/<continent>/<country>` category pages; the human `/en/webcams` index surfaced 21 cams.
- KEY FACTS — **Access:** places API for discovery; consumer player flow (captured via browser network) = `https://livecloud.earthtv.com/api/v1/media.getPlayerConfig?playerToken=<token>` → player config; still/preview images: `https://livecdn-de-earthtv-com.global.ssl.fastly.net/preview/streams/earthtv/<streamId>.jpg?token=<token>`; player JS `player.earthtv.com/player/<hash>-etv-player.js`. So stream layer = **tokenized**; discover/track via places API, resolve playback tokens per-session.
- KEY FACTS — **License/ToS:** commercial broadcaster ("world live" TV programs, ads); cities/landmarks network; ToS — no redistribution; low-volume use.
- **Verification:** places API fetched + parsed; sitemap counted; browser network capture found player-token flow.
- **VERDICT: REFERENCE** — use the places API as a landmark-cam **discovery** net; stream layer is tokenized (viewer = M/uncertain). Build: **discovery** (+ registry cross-check).

### 15 · AfriCam
- https://africam.com/ · locations: https://africam.com/our-locations/ 
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** WordPress sitemap exposes `lodge-sitemap.xml` = **43 lodge/location pages** across **6 countries** (Tanzania, Kenya, Namibia, Zimbabwe, Botswana, South Africa); camera-type taxonomy: wildlife/landscape/conservation. Historic brand (since 1998) — the original "African waterhole cam" network; several lodges carry live cams (e.g. Nkorho Bush Lodge).
- KEY FACTS — **Access:** no JSON API. Lodge pages load **YouTube embeds** via the YouTube iframe API — network capture on `/lodge/nkorho-bush-lodge/` showed live iframes: `youtube.com/embed/EaTgbLz2E9E`, `E3M4SUbpqc8`, `r099JKmOj5I` (muted autoplay). Pipeline: crawl lodge pages (sitemap) → extract YouTube video ids → yt-dlp.
- KEY FACTS — **License/ToS:** commercial wildlife-streaming business (memberships/alerts app), cams free to watch; blog/news content; attribution; scrape only lodge pages.
- **Verification:** sitemaps fetched; lodge page browser capture (video ids above).
- **VERDICT: REFERENCE** — small but high-quality wildlife tier + brand recognition. Build: **registry** (43 lodges) + **viewer** via YouTube layer.

### 16 · Skyline's YouTube presence (@skylinewebcams)
- https://www.youtube.com/@skylinewebcams/streams
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** yt-dlp flat-playlist of the `/streams` tab = **580 stream entries**. Content is **composite mosaic streams** (their own aggregation product): titles include "**600 TOP LIVE CAMS from Italy** with Dolce Vita relaxing Music", "**1200 TOP LIVE WEBCAMS around the World** with relaxing music and Map", "200 TOP LIVE CAMS from Spain", "VENICE LIVE 24/7". These are single YouTube lives containing grids of many Skyline cams + music.
- KEY FACTS — **Access:** standard YouTube layer — `yt-dlp -f "bv*[height<=720]+ba/b" -g "https://www.youtube.com/@skylinewebcams/live"` (use channel-live URLs; per prior dossier, `bv*+ba` selector required for live). Individual cams are NOT individually streamable here — single mosaic feed per program.
- KEY FACTS — **License/ToS:** YouTube ToS; Skyline-owned production; personal/local viewing per this program's stance; keep yt-dlp updated.
- **Verification:** yt-dlp channel enumeration + sample titles (2026-10-05).
- **VERDICT: REFERENCE** — excellent zero-token **viewer** filler ("world wall" mosaic tiles) and a fallback when per-cam token extraction (entry 1) isn't ready. Build: **viewer** tier.

### 17 · IPCamLive
- https://www.ipcamlive.com/ · FAQ (public pages): https://www.ipcamlive.com/faqs
- KEY FACTS — **Scale:** **no public directory** — verified 2026-10-05: `/streams`, `/gallery`, `/map`, `/publics` all HTTP 302 → homepage; `/cameras` returns empty 200. It is a hosting platform: each customer camera has a "public page" (per FAQ) and an embed snippet; discovery happens off-site (owners share links). Scale not enumerable here (do not guess).
- KEY FACTS — **Access (per-camera patterns):** state endpoint verified keyless: `https://www.ipcamlive.com/ajax/getcamerastreamstate.php?cameraalias=<alias>` → JSON `{id, alias, state, streamavailable, address: "http://s33.ipcamlive.com/", groupaddress: "http://g1.ipcamlive.com/"}`; player hosts `g1.ipcamlive.com` / `s33.ipcamlive.com` (`player/player.php?alias=<alias>` responds 200; body empty to non-JS clients). Also documents RTSP/ONVIF setup knowledge (rtspdatabase page) — useful RTSP URL reference table for a future private-cam tier.
- KEY FACTS — **License/ToS:** commercial SaaS (free trial for owners; viewer pages public-by-owner). Face-blur/privacy features exist. Never enumerate aliases by brute force — alias must come from an owner-published link (policy line).
- **Verification:** directory-path probes; ajax endpoint call; FAQ read.
- **VERDICT: REFERENCE** — not a discovery source; a **viewer/embed handler** for cam links arriving from elsewhere. Build: **viewer** (embed + state check).

### 18 · CamStreamer Live gallery
- https://camstreamer.com/live/map · search: https://camstreamer.com/live/search
- KEY FACTS — **Scale:** not quantified this pass. CamStreamer (Czech, commercial streaming service for Axis cams) runs a public **"Live gallery"** with an interactive Google-map view and a search page (GET form `/live/search`; filter UI has country/category selects). The gallery itself is public; stream count unknown **(verify on next pass)**.
- KEY FACTS — **Access:** pages render client-side (Google Maps + markerclusterer libs loaded); the marker data endpoint was NOT identified in this pass (browser resource capture showed only CSS/JS libs; grep of page source found no JSON URL; 3 attempts max — logged as open question). Next-pass plan: CDP `Network.enable` while interacting with the map to catch the XHR.
- KEY FACTS — **License/ToS:** commercial vendor; gallery = customer streams published by owners; fair use, attribute.
- **Verification:** page fetches + browser network capture (negative result recorded).
- **VERDICT: REFERENCE** — promising discovery pool once its data endpoint is captured; do not block on it. Build: **discovery** (deferred spike).

---

## Dead ends & negative findings (kept so nobody re-discovers them the hard way)

1. **opencctv.com is dead** — parked on HugeDomains (2026-10-05); last Wayback snapshot 2025-07-12. Purge its 746 URLs from the registry. (Also: never use Shodan/"unsecured cam" OSINT tools — policy.)
2. **Skyline has no sitemap** (`/sitemap.xml` 22 B, `/sitemap_index.xml` empty, `/sitemap/italia.xml` empty) — the country→region crawl is the only discovery path found.
3. **Skyline's stream URL is not in static HTML** — player is JS (`sky.js`); no `hd-auth`/`m3u8`/token strings anywhere in the cam page source. Token extraction needs page execution (spike; prior-wave reports say the tokenized `live.m3u8?a=` exists).
4. **webcams.travel & lookr are permanently redirected** → windy.com/webcams; old APIs gone. Any old scraper/tutorial referencing them is stale.
5. **EarthCam 429s fast**: the network_search endpoint rejected a bare call immediately; must send `Referer: https://www.earthcam.com/network/` and space calls ≥1.5 s (81 calls done cleanly at that rate).
6. **earthTV API pagination unresolved**: `?page=`, `?limit=`, `?offset=`, `?start=` all returned the same first 20 items; its `/places/<id>/views` sub-endpoint 404'd to curl (works in-browser) — importer must solve paging (maybe POST or headers).
7. **CamStreamer map data endpoint not found** (only Google Maps libs load); needs a deeper CDP network capture pass.
8. **IPCamLive has no public directory** (all directory-ish paths 302 → homepage). Alias-brute-forcing = out of policy.
9. **WorldCams.tv**: no sitemap (404), and robots.txt disallows `/list/`, `/ajax/`, `/player`, `/go`, `/?tab=` — production crawler must stick to country/section pages (note: our discovery run touched `/list/` before reading robots; exclude it going forward).
10. **webcamera.pl** directory paths (`/kamery`, `/mapa`, `/wszystkie-kamery`) 302; cam discovery is via homepage subdomain links only.
11. **BalticLiveCam**: no static `.m3u8` (auth_token handshake via admin-ajax + videojs-contrib-hls); homepage counter (435) vs sitemap (1,278) mismatch — likely online-vs-all.
12. **Reddit** was bot-walled/not used (per brief); no Reddit-derived numbers in this file.

## Cross-cutting patterns (what this means for the build)

- **Windy is the consolidated incumbent** for the webcams.travel/lookr brand family — one API key, two dead domains. Prefer building the Windy importer once.
- **YouTube-embed prevalence is the dominant access mechanism** across consumer aggregators (WebcamTaxi, WorldCams, AfriCam, CamGuide's non-DOT cams, explore.org feeds via `video_id`, Skyline's composites). A robust yt-dlp resolution/refresh subsystem is the highest-leverage shared component for the "non-government" slice (matches WV1 dossier's M2 method).
- **Token-gated players everywhere**: Skyline (JS), BalticLiveCam (admin-ajax auth_token), EarthCam (time-stamped m3u8 tokens), earthTV (playerToken), Windy (10-min image tokens). Design rule: store **resolve-on-demand** adapters; never store tokenized URLs as durable records.
- **Best structures to copy right now**: Roundshot (directory JSON with per-cam `status` — perfect liveness model), explore.org omega API (directory + per-cam detail + viewers/offline), EarthCam (`cam_count` + `cam_state`), Windy (rich filters). These 4 cover registry + discovery + liveness with minimal scraping.
- **Roughly-measured keyless enumeration totals (2026-10-05, non-government slice):** Skyline 2,447 · WebcamTaxi 1,950 · explore.org 1,137 · BalticLiveCam 1,278 · CamGuide 5,052 · WorldCams 775 · Roundshot 561 · earthTV 495 (places) · EarthCam 365 (site enumeration) — ≈14,000 records before dedupe, all from public pages; government slice (prior waves) will add the DOT-scale numbers.
- **Rate/politeness tier:** EarthCam and Skyline proven tolerant at ~1 call/1.5 s and 6-way concurrency respectively (today, from this host); BalticLiveCam is WP on shared hosting — keep it gentlest.

## Evidence artifacts (all this wave)

- `C:\Users\user\world-feed-db\research\sources\S1-aggregators.md` (this file)
- Scratch (session): `skyline_counts.json` (per-country table), `s1_crawl_results.json` (EarthCam world + WebcamTaxi + WorldCams), `earthcam_us.json` (45 states), `ec-pl.json` (EarthCam playlist sample), `exp-init.json` (explore.org directory), `rs-list.json` (Roundshot 561), `etv-places.json` (earthTV places), `skyline_crawl.py` / `s1_crawl.py` / `ec_us.py` (re-runnable crawlers), `skyline_crawl.log` / `s1_crawl.log` / `ec_us.log`.
- Prior context used (not duplicated): `zero-hud\reference\world\WV1-live-video-sources.md` (2026-10-03), `world-feed-db\research\seed-tabs\data\LES-sources.json`.

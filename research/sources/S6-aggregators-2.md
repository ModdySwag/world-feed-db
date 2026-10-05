# S6 · Batch-2 aggregators & new non-government directories — deep-dive (research wave S6, 2026-10-05)

Scope: the NEW non-government directories from Moddy's batch-2 tabs (TABS-LIST-2.md), plus every additional lead those sites surfaced that S1–S5 did not cover. Per source: scale measured today, enumeration mechanism/exact endpoints, stream/frame URL patterns, license/ToS note, verdict + build component.

**Policy line (hard):** public-by-design sources only; no probing/scanning of private/exposed devices; polite rates + identifying UA (`world-feed-db-research/0.1`); robots-respecting — disallowed paths were NOT crawled (webcamera24 `/api/v1/*`, `/camera/*/*/stream/`, `/*?`; earthlive24 `/api/`, `/ctrl-e24x`). Reddit not used (bot-walled). ≤3 attempts/page.

**Method + tooling:** curl (MSYS bash), Python 3.11 (urllib), yt-dlp (liveness proofs + playlist counts), real browser (RSC payload / DOM inspection on webcamera24), iTunes lookup API. All counts measured **2026-10-05 ACST** unless dated otherwise. `(verify)` = third-party/operator claim not independently reproduced.

**Status legend:** ADOPT = build on it now · REFERENCE = useful pattern/secondary source · SKIP = do not build on it.

---

## Batch summary table

| # | Name | Measured scale (2026-10-05) | Access | Verdict |
|---|------|------------------------------|--------|---------|
| 1 | webcamera24.com | **6,570 cams / 67 countries** (unique; 91,980 URLs = ×14 languages; sitemap 121,296 URLs) | sitemap index → HTML; inline RSC payload (HLS `streamLink` + `youtubeCode`) | **ADOPT** — registry/discovery/viewer |
| 2 | openwebcamdb.com | **1,881 cams / 59 countries** (site counter; 1,881 detail pages in sitemap) | keyed REST API `/api/v1` (keyless → 302 login) | **SKIP** — ToS prohibits competing directories |
| 3 | worldcam.eu | sampled: **Germany 1,592 · UK 754 · France 712 · NY 255**; operator counter 32,330 (worldcam.pl) | HTML country dirs, 25/page `/p/N`; img.worldcam.pl snapshots | **ADOPT** — registry (image tier) |
| 4 | earthlive24.com | **414 camera pages** (claim "300+"); 64 countries / 321 city pages | sitemap → HTML; SSR YouTube embeds | **ADOPT** — registry (+YouTube viewer) |
| 5 | worldlive.app | app claims **15,000 cams** (verify); no web data | Wix marketing site; product = iOS/Android app | **SKIP** — app-only, no scrapeable surface |
| 6 | earthcamtv.com (+ EarthCam animal subset) | playlist **12 live items** (trending 4 + featured 8); animalcams **11 named cams** | `earthcam.com/api/ectv/player/playlist.php` (keyless); tokenized HLS | **ADOPT** (verify pass; S1) — registry/liveness |
| 7 | Skyline YouTube mosaic family | **580 stream entries**; **6+ mosaic programs** | yt-dlp; single-live composites | **REFERENCE** — viewer filler tier |
| 8 | argosatlas.com blog | lead list: 9 named networks (all gov/port/urban) | article (read) | **REFERENCE** — lead list only |
| 9 | CruisingEarth ship/port webcams | **151 ship cam pages / 21 lines**; 15 port regions | HTML index → ship pages → Panomax iframes | **REFERENCE** — registry (ships) |
| 10 | Panomax (lead via CruisingEarth) | public per-cam image pattern verified; directory spike TODO | `<customer>.panomax.com`; `live-image.panomax.com/cams/<id>/...` | **REFERENCE** — provider, image tier |
| 11 | San Diego Zoo live cams | **13 cams** | HTML → cam sites; YouTube player (JS key) | **REFERENCE** — institutional tier |
| 12 | Smithsonian National Zoo | **4 cams** | HTML; YouTube channel `SmithsonianNZP` | **REFERENCE** — institutional tier |
| 13 | Monterey Bay Aquarium | site WAF-blocked; YouTube route **live verified** | YouTube channel | **REFERENCE** — viewer via YouTube |
| 14 | North Bondi SLSC | **2 owner-published IPCamLive embeds** (aliases captured) | HTML iframes → ipcamlive player | **REFERENCE** — viewer/embed pattern |
| 15 | ARGOS ATLAS (argosatlas.com) | keyless stats: **cams 220,449 / video 20,781**; claim 205,057 / 190+ countries | keyless stats API; cam data behind Pro | **REFERENCE** — benchmark/yardstick |

---

### 1 · webcamera24.com ("Live world webcams")
- https://webcamera24.com/ · sitemap index: https://webcamera24.com/sitemap.xml → `sitemap1.xml … sitemap7.xml` · example cam: `https://webcamera24.com/camera/czech/prg/`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** 7 sitemap files totalling **229.9 MB / 121,296 URLs**: **91,980 camera URLs = 6,570 unique cameras × 14 language variants** (en, ru, pt, es, de, fr, it, ko, nl, ja, zh, tr, vi, pl — 6,570 each). **67 countries**; top: Russia 1,346 · USA 1,081 · Germany 483 · Ukraine 310 · Bulgaria 258. Non-camera URLs = 29,316: per-language geography pages (`/countries/` 2,030/language, `/countries/russia` 369, `/countries/germany` 220, `/countries/usa` 149…), `/categories/` (59/language: beaches, hotels, ptz, traffic, ski-resorts, sport, sea-views, squares…), `/popular/`, `/latest/`.
- KEY FACTS — **Stream resolution (VERIFIED in browser + live fetch):** Next.js/Turbopack site; the cam page's inline RSC payload carries the player object:
  - direct HLS: `"video":{"streamLink":"https://www.intek-m.ru/live/yaroslavskoye_sh_2/s.m3u8","streamLinkType":"m3u8"},"isWork":true` — the referenced m3u8 was fetched today: **HTTP 200, `#EXTM3U … #EXT-X-TARGETDURATION:3` with live `s7.ts` segments** (real HLS pass-through of upstream).
  - YouTube: `"youtubeCode":"t3vs5WuuGsw"` + `"embedUrl":"https://www.youtube-nocookie.com/embed/<code>"` (samples: t3vs5WuuGsw Prague plane-spotting, YIXDnrSl9EE falconcam, 2Xn1Bb697A0 massabielle).
  - **Liveness:** per-cam `isWork:true|false` in payload + "Webcam online/offline" labels on every nearby-cam card (23 live/false flags counted on one page).
  - Their thumbnails/CDN: `cdn.webcamera24.com/static/image/camera/detail/<id>-<slug>/thumbnail/380x254/<id>_<ts>_<hash>.webp`. Upstream credits visible in slugs (e.g. `…-webcamtaxi`, `…-uastreaming`, hosts like intek-m.ru) → webcamera24 is itself an aggregator.
- KEY FACTS — **Robots/ToS:** robots.txt disallows `/*?`, `/api/v1/*`, `/account/*`, `/*/account/*`, **`/camera/*/*/stream/`** (the resolver path) — not crawled here. Commercial ad-supported portal; fair-use viewing; crawl politely.
- **VERIFIED TODAY:** sitemap index + all 7 files downloaded and counted; duplicate-stripped (6,570 unique); cam page fetched; RSC payload parsed in-browser; direct m3u8 fetched live (200 + segments); 3 sample cam pages' player objects compared (YouTube vs HLS variants).
- **VERDICT: ADOPT** — biggest *new* keyless directory this wave, and the cleanest dual stream tier (direct HLS where upstream provides it; YouTube elsewhere) + built-in `isWork` liveness. Build: **registry + discovery** (sitemap importer, de-dup on country/slug), **viewer** (HLS tier + YouTube tier), **liveness** (`isWork`). Do not touch `/api/v1/*` or `/camera/*/*/stream/` (robots).

### 2 · openwebcamdb.com ("Global Directory of Live Webcams and Streaming Cameras")
- https://openwebcamdb.com/ · API docs: https://openwebcamdb.com/api/docs · interactive spec: https://openwebcamdb.com/docs/api (OpenAPI JSON at `/docs/api.json`) · example: `https://openwebcamdb.com/webcams/vienna-panorama-from-am-himmel-heights`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** sitemap = **1,881 webcam detail pages** + 18 category pages + 64 country pages + 6 static; site counters: "**1,881 live streams · 59 countries**" (footer, same run). Laravel + Livewire app (`livewire-913796a2`; browse page ships a `wire:snapshot` with paginators). Browse: `/webcams` (+ `/popular` `/random`), `/categories`, `/countries`, `/submit` (crowd-submission).
- KEY FACTS — **API (documented, keyed):** base `https://openwebcamdb.com/api/v1`; endpoints: `GET /webcams` (sort/order/per_page), `/webcams/map` (bbox required), `/webcams/popular`, `/webcams/trending`, `/webcams/recently-viewed`, `/webcams/random`, `/webcams/{slug}` (**returns `stream_url` + `stream_type`**), `/categories[/{slug}]`, `/countries[/{isoCode}]`, `/widget/random` (50 random cams for widgets). Auth: `Authorization: Bearer ***`; **keyless call → 302 → /login** (verified). Free tier 25 req/day, 5/min; Pro $50/mo 10k/day.
- KEY FACTS — **Textbook example of the non-government directory. **License/ToS — CRITICAL:** free tier = "non-commercial use only"; **prohibited uses explicitly include "Creating competing webcam directories or aggregators", "commercial applications", "reselling or redistributing API data", "excessive scraping or data harvesting"**. Free tier requires visible "Powered by OpenWebcamDB.com" attribution; data caching capped at 1 h (free) / 24 h (Pro).
- KEY FACTS — **Stream resolution:** detail pages embed YouTube (`youtube.com/embed/omcPYHHDNyQ?autoplay=1&mute=1`, verified on the Vienna cam), cookie consent gates YouTube embeds; `stream_type` field suggests mixed types in the API layer.
- KEY FACTS — **Who runs it:** footer "© 2026 **Titans of Industry**"; App Store listing for `OpenwebcamDB` (id6754088601) has the same seller, Travel genre, 0 ratings; analytics via `stats.titans.sh` (Titan). robots.txt points to `http://openwebcamdb.test/sitemap.xml` (dev-config leftover — a Laravel `APP_URL` leak, worth noting).
- **VERIFIED TODAY:** sitemap fully parsed (1,881+84 URLs); footers read; `/docs/api.json` OpenAPI spec fetched (53.8 KB, 11 paths); keyless API probe (302 → /login); detail page embed inspected; App Store metadata via iTunes lookup.
- **VERDICT: SKIP (for ingest)** — its free API is **contractually off-limits** for a competing directory like world-feed-db, and bulk scraping is prohibited; note it as an industry peer to monitor, and (if ever needed) the only legitimate path is a commercial license. Build: **mgmt** (add to license-blocked list; do not crawl beyond public page counts).

### 3 · worldcam.eu (WorldCam)
- https://worldcam.eu/ · continents: `/webcams/europe|asia|africa|north-america|south-america|australia-oceania|poles` · example: `https://worldcam.eu/webcams/europe/france/1059-nice-promenade-des-anglais` · sibling (operator's home site): https://www.worldcam.pl/
- KEY FACTS — **Scale (VERIFIED samples + operator counter, 2026-10-05):** no sitemap (robots has no Sitemap line; `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap1.xml`, `/en/sitemap.xml` all 404; `/sitemap/` 301→404). Country directories paginate at **25 cams/page** (`/webcams/<continent>/<country>/p/<N>`); measured: **Germany 1,592 cams (64 pages) · United Kingdom 754 (31) · France 712 (29) · New York state 255 (11)**. The Polish home site (same database) shows a live counter: "**Statystyki Kamer: 32330**" (32,330 cameras) + 30,629 users / 56,875 comments — this is the best available site-wide scale figure **(operator claim)**. Language mirrors: `de|fr|es|it|lt.worldcam.eu`.
- KEY FACTS — **Structure:** URL pattern `/webcams/<continent>/<country-or-region>/<numericID>-<slug>` (US states are their own "countries": `north-america/california-usa`, `north-america/new-york-usa`; Poland is a top-level segment family `/webcams/poland/...`). Listing cards carry a type badge: **`type-streaming`** (film icon) vs **`type-static`** (image icon) — a ready-made stream/image classifier per cam.
- KEY FACTS — **Frame/stream patterns (VERIFIED on samples):** date-stamped snapshot images `https://www.img.worldcam.pl/webcams/<48x48|96x96|200x113|400x226>/<YYYY-MM-DD>/<camId>.jpg` (e.g. `/2026-10-05/16363.jpg`) + older `www.worldcam.pl/images/webcams/<slug>.jpg`; cam pages show "Refresh: **Live stream**" + a gallery link (`/gallery/1059`); per-cam source credit + Wikipedia link; `https://www.worldcam.pl/maps/getmap.php?id=<camId>&lang=en` returns a **PNG map** (keyless); the `/map` page renders via `js/maps2.js` + Google Maps (geo-IP country "Map of United Kingdom…"); search works keyless: `/search?q=<term>` (25 results/page).
- KEY FACTS — **License/ToS:** robots allows everything (empty `Disallow:`); long-running Polish community portal (ads-supported); cams = member/operator submissions, EU viewers; fair use, attribution, no re-streaming. Keep page-crawl polite.
- **VERIFIED TODAY:** robots + 5 sitemap paths probed; continent pages + 4 country samples paged out (first+last pages to compute exact totals); cam page + search page fetched; snapshot images and getmap PNG verified; worldcam.pl counter read.
- **VERDICT: ADOPT** — large community directory (32K claim; EU-heavy) with a snapshot-image tier that needs no tokens, plus a per-cam static-vs-streaming badge. Build: **registry** (country crawler; store counter figure as claim), **viewer** (image-refresh tier; stream cams as second pass), **liveness** (date-stamped images make staleness detectable: fetch today's dated URL).

### 4 · earthlive24.com
- https://earthlive24.com/ · sitemap: https://earthlive24.com/sitemap.xml · example: `https://earthlive24.com/camera/cam_002` · sections: `/cameras/{cities,nature,beaches,landmarks,airports,space,wildlife,transport,news,events}`, `/live`, `/launch`, `/world-cup-2026`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** sitemap = **1,134 URLs**: **414 camera detail pages** (`/camera/cam_002` … `cam_556`, IDs with gaps) + 30 category pages + 64 country + 321 city + 19 events + 26 launch + 11 live + 220 blog + 11 world-cup-2026 + space/iss/aurora. Claim "300+ cameras" → **verified and exceeded: 414 pages today**.
- KEY FACTS — **Stream resolution (VERIFIED):** server-rendered **YouTube embeds** in the page HTML — `<iframe src="https://www.youtube.com/embed/<id>?autoplay=1&mute=1&rel=0">` (e.g. cam_002 = `dfVK7ld38Ys` "Shibuya Crossing"; cam_551 = `tuNC0ot0j9I`). Related cam thumbnails are `i.ytimg.com/vi/<id>/…` — the whole site is a YouTube-layer aggregator. Liveness check via yt-dlp: **dfVK7ld38Ys is_live=True (178 viewers)**, tuNC0ot0j9I is_live=True (1 viewer) — both 2026-10-05.
- KEY FACTS — **Robots/ToS:** robots disallows `/api/` and `/ctrl-e24x` (not fetched); public consumer site; aggregator of public streams; fair use + attribution; YouTube ToS for playback.
- **VERIFIED TODAY:** full sitemap downloaded/parsed (per-segment counts above); 3 cam pages fetched; 2 embedded YouTube videos liveness-proven with yt-dlp.
- **VERDICT: ADOPT** — clean sitemap → 414-page directory with SSR YouTube ids (no tokens, no JS needed for discovery). Build: **registry + discovery** (sitemap importer), **viewer** (yt-dlp tier; dedupe against other YouTube sources by video id), **liveness** (yt-dlp `--match-filter is_live`).

### 5 · worldlive.app
- https://www.worldlive.app/ · app: https://apps.apple.com/us/app/id1534109973
- KEY FACTS — **What it actually is (VERIFIED, 2026-10-05):** a **Wix marketing site** (whole page is wix-thunderbolt; the "13 api-ish hits" are Wix platform calls like `/_api`). The product is a mobile app: **"World Live – Discover Places" by KMA Tech Holding Limited** (App Store id1534109973, Travel, 21 ratings, 4.67★, 2026-10-05).
- KEY FACTS — **Scale claim:** site copy claims "**15,000 cameras**" **(verify)** — not enumerable from the web; the app description advertises an interactive map + "share streams and comments". No public web data endpoints/bundles exist to mine (Wix renders client-side; no camera JSON).
- KEY FACTS — **License/ToS:** commercial app (KMA Tech Holding); no web reuse surface. 
- **VERIFIED TODAY:** live fetch (459 KB) analyzed — Wix platform only; App Store metadata via iTunes lookup API; no stream/data endpoints found.
- **VERDICT: SKIP** — not a scrapeable directory; record as a consumer-app competitor with a 15K claim to re-check later. Build: **mgmt** (watch-list; if the app's map endpoint ever surfaces, revisit).

### 6 · earthcamtv.com / EarthCam app-side catalog + animal subset (S1 verification pass)
- https://www.earthcamtv.com/ · playlist: `https://www.earthcam.com/api/ectv/player/playlist.php?r=playlist&a=fetch` · animalcams: https://www.earthcam.com/events/animalcams/
- KEY FACTS — **Playlist verified again (2026-10-05):** returns **12 items — `playlist_trending` 4 + `playlist_featured` 8 — all `cam_state=1` (live)**. Item schema: `stream` = tokenized HLS `https://videos-3.earthcam.com/fecnetwork/<camId>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>` (e.g. camId 8891/22640/13908/6391/43379/7132), thumbnails 256x144 / 512x288 / 1816x1024, `group_id`, `name`, `hasaudio`, `offline_image`. Tokens are time-stamped → refresh on demand.
- KEY FACTS — **"Fuller app catalog" hunt (VERIFIED negative):** `r=channels&a=fetch`, `r=playlist&a=list`, `r=trending&a=fetch` all → `{"status":"400","msg":"Request Type Error"}`; only `r=playlist&a=fetch` works; www.earthcamtv.com homepage is a static landing page (jQuery only, no endpoints). New endpoint seen but unverified: `/api/dotcom-search/html/autocomplete` (returned `[]` for `q=manatee` / `query=manatee` — param name unknown).
- KEY FACTS — **Animal-cams subset (VERIFIED):** `/events/animalcams/` gallery = **11 named cams**: Hideaways Camp Kuzuma · Michigan Snowman · Meerkat · Flamingo · Bali Elephant (Bathing Pool + Trail Path) · Giraffe (Paddock + Barn) · Falcon Cam Omaha NE · Manatee Lagoon · Osprey Cam Boston MA (+13 camshot thumbnails). Spot-checked: `usa/florida/miami/meerkat/` and `usa/massachusetts/boston/osprey/` pages carry **`cam_state":"1"` AND tokenized `playlist.m3u8?t=…&td=20261005…`** → live and resolvable from plain HTML.
- **VERIFIED TODAY:** playlist fetched + parsed (item counts, token format, all live); 4 variant requests; animalcams page parsed; 2 animal cam pages fetched with live tokens.
- **VERDICT: ADOPT (as in S1; this pass = verification + the animal tier)** — 12 live app channels + 11 animal cams, all keyless-enumerable with per-cam `cam_state`. Build: **registry** (animal cams as high-quality seeds), **liveness** (`cam_state`), **viewer** (tokenized HLS, refresh ≤ tokens' cadence).

### 7 · Skyline's YouTube mosaic programs (@skylinewebcams)
- https://www.youtube.com/watch?v=EFum1rGUdkk · channel family: https://www.youtube.com/@skylinewebcams/streams
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** `yt-dlp --flat-playlist` on `/streams` = **580 stream entries** (matches S1). **Mosaic programs** (single YouTube live = composite grid of many Skyline cams + relaxing music + map): "**1200 TOP LIVE WEBCAMS around the World**" (**EFum1rGUdkk — is_live=True, 385 viewers today**), "600 TOP LIVE CAMS from Italy", "200 … Spain", "200 … Greece", "TOP LIVE CAMS USA-UK-CANADA", "VENICE LIVE 24/7 with Piano Music"; plus a singles family branded "Live cameras around the world" (Etna, Rome, Faroe, Maldives, NY, Canazei).
- KEY FACTS — **Mechanism / how to consume:** one live video per program (`watch?v=` or channel `/live`), resolved with `yt-dlp -f "bv*[height<=720]+ba/b" -g <url>`; zero tokens, zero per-cam extraction. It's a **viewer-filler tier**: drop-in "world wall" tiles / fallback when per-cam tokens (Skyline entry #1 in S1) aren't wired.
- KEY FACTS — **License/ToS:** YouTube ToS; Skyline-owned production; personal/local viewing per program stance; keep yt-dlp updated. 
- **VERIFIED TODAY:** EFum1rGUdkk liveness + title + viewer count via yt-dlp (is_live=True, 385); /streams count re-run (580); mosaic title set extracted.
- **VERDICT: REFERENCE** — keep as the **viewer** filler tier (no changes to S1 verdict), now with live proof of the flagship mosaic.

### 8 · argosatlas.com blog — "Live Webcams from Around the World on One Map"
- https://argosatlas.com/en/blog/webcams-en-directo-del-mundo/ (ES original `/blog/webcams-en-directo-del-mundo/`)
- KEY FACTS — **Article (VERIFIED read, 2026-10-05):** published **2026-06-10**, updated **2026-09-27**, author Elena Castel ("Verification & Open-Source Intelligence"); ~8 min read; it is a funnel to their own ARGOS ATLAS map. **Every named network/source it recommends (the requested list):**
  1. **Norwegian Public Roads Administration** (Statens vegvesen) — "hundreds of cameras focused on mountain passes and Arctic roads" (already covered: S2 gov slice);
  2. **US state 511 traveller-information systems** — "road agencies … publish cameras" (covered: S2; e.g. VDOT/511 family);
  3. **UK National Highways** — strategic road network feeds (new-ish lead: UK national roads; TfL covered separately);
  4. **Port of Rotterdam** — public port feeds lead;
  5. **Port of Singapore** — public port feeds lead;
  6. **Port of Los Angeles** — public port feeds lead;
  7. **Times Square, New York** — public urban feed (aligns with earthTV/EarthCam coverage);
  8. **Tower Bridge area, London** — public urban feed lead;
  9. **Shibuya Crossing, Tokyo** — public urban feed (now confirmed via earthlive24's embed of the actual YouTube live, this file §4).
  Also: the four-family taxonomy (traffic / weather+mountain / port+coastal / urban+panoramic) and the key line "most official traffic and weather cameras refresh a fixed image every few minutes instead of streaming continuous video" — matches our image-tier design.
- KEY FACTS — **Outbound links:** none to the named portals (SEO-style article; only its own YouTube channel `youtube.com/watch?v=j-3BYsG5DoA`). So the list is *prose leads*, not linkable endpoints.
- **VERIFIED TODAY:** full article text extracted from capture; name scan (Norwegian ×2, National Highways ×1, Rotterdam/Singapore/LA ×2 each, Times Square/Tower Bridge/Shibuya ×1); outbound-domain scan (only fonts + their YouTube).
- **VERDICT: REFERENCE** — capture as a **lead list** (ports/urban items are the actionable ones for gaps in Class G); no non-government sources surfaced by it beyond what's covered. Build: **discovery** (intake queue).

### 9 · CruisingEarth ship & port webcams (batch-2 tab)
- https://www.cruisingearth.com/ship-webcams/ · ports: https://www.cruisingearth.com/port-webcams/ (+ `/map/`) · example: `https://www.cruisingearth.com/ship-webcams/viking/viking-jupiter/`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** ship-webcams index = **21 cruise lines → 151 ship webcam pages** (counted line-by-line: Viking 14 · AIDA 33 · Norwegian 22 · Princess 26 · Costa 18 · TUI 8 · Crystal 6 · Hapag-Lloyd 5 · Phoenix Reisen 4 · Explora 3 · Ocean Exploration Trust 3 · Oregon State Univ 3 · Greenpeace 2 · Hurtigruten 2 · BAS 1 · Holland America 1; Carnival/Cunard/MSC/PO/Royal Caribbean yielded 0 parseable ship links — structure or coverage gap, re-check with a browser). Port side: **15 port regions** (Africa, Antarctica, Arctic, Asia, Atlantic, Australia, Canada, Caribbean, Central America, Europe, Mexican Riviera, Middle East, Pacific, South America, United States) + map page.
- KEY FACTS — **Stream resolution (VERIFIED):** ship pages embed **Panomax** panoramic cameras via iframe — `<iframe id="webcam-image" src="https://viking.panomax.com/jupiter" …>` — plus "Additional Webcams Onboard" section and a live ship tracker. So the actual stream tier = Panomax per-ship panoramas (see §10). Port pages = region lists (HTML).
- KEY FACTS — **License/ToS:** independent cruise fan/community site (ads); webcams embed owners'/Panomax feeds; ship tracking via public AIS aggregations; fair use, attribution; crawl ship pages politely (XenForo site).
- **VERIFIED TODAY:** index + all 21 line pages fetched & counted (151 ships); port index fetched (15 regions + map); one ship page fetched incl. iframe src extraction.
- **VERDICT: REFERENCE** — niche but real registry (151 ship cams + 15 port regions); the value is (a) ship-cam seeds, (b) it leads to **Panomax** (§10). Build: **registry** (ship/port tier), **viewer** (iframe/Panomax handler).

### 10 · Panomax (provider lead surfaced via CruisingEarth)
- https://www.panomax.com/ (GmbH, Henndorf, Austria) · explore: https://explore.panomax.com/en · per-cam example: https://viking.panomax.com/jupiter
- KEY FACTS — **What it is:** vendor of 360° panoramic webcam systems (like Roundshot/feratel tier); customer cams live on `<customer>.panomax.com/<site>` subdomains (cruise lines, cable cars, tourism, ports — see their markets menu). The player loads `hls-0.7.6.min.js` → per-cam **video/HLS capability** exists.
- KEY FACTS — **Keyless image pattern (VERIFIED today — previously "not established" in S2):** cam id (e.g. 2046 for Viking Jupiter) drives: `https://live-image.panomax.com/cams/2046/preview_og.jpg` → **HTTP 200 image/jpeg** (~60 KB), and `https://panodata.panomax.com/cams/2046/preview_og.jpg?x=<ts>` → **200 image/jpeg**. Both fetched live — that's a tokenless snapshot tier.
- KEY FACTS — **Directory status:** `www.panomax.com/en/sitemap` = marketing pages only (no cam list); `explore.panomax.com/en` = public live map/directory (JS app — its data endpoint NOT captured this pass; TODO spike); `api.panomax.com` common paths (`/cams`, `/v1/cams`, …) → 404; Apple app "Panomax Live – 360° Webcams" exists (www link).
- KEY FACTS — **License/ToS:** commercial vendor; per-customer cameras published for public viewing; fair use + attribution; polling cheap (image cadence).
- **VERIFIED TODAY:** per-cam iframe extracted from CruisingEarth; `preview_og.jpg` image pattern proven on both hosts (cam 2046); api 404 probes; explore page fetched (35 KB).
- **VERDICT: REFERENCE (provider, on deck)** — image tier adoptable per-cam now; full directory enumeration needs the `explore.panomax.com` endpoint spike (deferred; don't block). Build: **viewer** (image tier), **discovery** (deferred spike), **registry** (camId capture from partner sites).

### 11 · San Diego Zoo live cams (batch-2 tab)
- https://animals.sandiegozoo.org/live-cams · cams on `zoo.sandiegozoo.org/cams/*` + `sdzsafaripark.org/*`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** **13 cam pages**: Ape · Baboon · Burrowing Owl · Condor · Elephant · Giraffe · Hippo · Koala · Panda (archive) · Penguin · Platypus · Polar · Tiger. Player = YouTube (page references `youtubeApiKey`; JS-driven embed; static cam page did not expose the video id to curl — browser pass needed for id extraction).
- KEY FACTS — **License/ToS:** zoo conservation content; free viewing; credit "San Diego Zoo Wildlife Alliance"; YouTube ToS for playback.
- **VERIFIED TODAY:** live-cams index fetched; 13 cam links enumerated; one cam page inspected (player = JS/YouTube-key).
- **VERDICT: REFERENCE** — small institutional registry (13 seeds); resolve video ids at viewer time. Build: **registry**.

### 12 · Smithsonian National Zoo webcams (batch-2 tab)
- https://nationalzoo.si.edu/webcams · YouTube: `youtube.com/SmithsonianNZP`
- KEY FACTS — **Scale (VERIFIED, 2026-10-05):** **4 webcam pages**: Elephants · Panda Cam · Naked Mole-Rat Cam · Lion Cam. Player = YouTube channel embeds (`SmithsonianNZP`).
- KEY FACTS — **License/ToS:** Smithsonian (quasi-public institution; free viewing; attribution); YouTube ToS.
- **VERIFIED TODAY:** page fetched (99.7 KB), cam links enumerated, YouTube channel reference captured.
- **VERDICT: REFERENCE** — tiny institutional registry; pairs with SD Zoo/Monterey for the "animal/Zen" tier. Build: **registry**.

### 13 · Monterey Bay Aquarium live cams (batch-2 tab)
- https://www.montereybayaquarium.org/cams-videos/live-cams · YouTube: `youtube.com/@MontereyBayAquarium/live`
- KEY FACTS — **Site is WAF-walled (VERIFIED 2026-10-05):** the live-cams page returns AWS WAF "Human Verification" to plain HTTP clients (2,557 B challenge page) — **don't scrape the site**; the working route is YouTube.
- KEY FACTS — **YouTube route (VERIFIED LIVE):** `yt-dlp` on `@MontereyBayAquarium/live` resolved today → "**Live Aviary Cam**" `AWJi0LgyA28`, **is_live=True, 51 viewers** (2026-10-05). Matches WV1's prior use of this channel for the aquarium tier (with `youtube:player_client=android_vr` worked historically).
- KEY FACTS — **License/ToS:** aquarium non-profit; free viewing; YouTube ToS; don't bypass the WAF.
- **VERIFIED TODAY:** curl attempt (WAF, documented); yt-dlp liveness proof (AWJi0LgyA28).
- **VERDICT: REFERENCE** — viewer via YouTube only; do not build a site scraper (blocked by design). Build: **viewer** (YouTube tier).

### 14 · North Bondi Surf Life Saving Club webcam (batch-2 tab) + IPCamLive pattern
- https://northbondisurfclub.com/webcam/
- KEY FACTS — **Stream resolution (VERIFIED, 2026-10-05):** two **owner-published IPCamLive embeds** in page HTML: `<iframe src="https://g3.ipcamlive.com/player/player.php?alias=669243ec21d29&skin=white">` and a second `<iframe src="https://g3.ipcamlive.com/player/player.php?alias=687a39cf71c58&skin=white&autoplay=1&mute=1&disableframecapture=1…">`. Aliases are 24-hex — exactly the owner-shared alias model IPCamLive documents (S1 §17).
- KEY FACTS — **Value:** confirms the IPCamLive discovery pattern "clubs/owners publish alias on their own site → registry picks up alias → viewer embeds `g3.ipcamlive.com/player/player.php?alias=…`". Policy-safe (never brute-force aliases). 
- KEY FACTS — **License/ToS:** surf-club public webcam page; IPCamLive viewer pages public-by-owner; embed + attribute; no alias enumeration beyond owner-published links.
- **VERIFIED TODAY:** page fetched; both iframes + aliases captured; player host pattern re-confirmed.
- **VERDICT: REFERENCE** — a worked example for the **viewer/embed handler** (IPCamLive) + one registry seed. Build: **viewer** + **registry**.

### 15 · ARGOS ATLAS (argosatlas.com) — the aggregator its blog funnels to
- https://argosatlas.com/ · map: https://argosatlas.com/map/ · stats API: https://argosatlas.com/api/landing/stats · sources page: https://argosatlas.com/en/fuentes-y-metodologia/
- KEY FACTS — **Scale (VERIFIED keyless API, 2026-10-05):** `GET /api/landing/stats` → `{"cams":220449,"camsVideo":20781,"ships":21758,"flights":12303,"ports":1081,"airports":47927,…, "ts":1791198630}`. Homepage copy (same day, updated ~per minute): "**205,057 public cameras** … in **190+ countries**; **18,838 stream live video**; the rest, an image that refreshes on its own" — counter/API drift noted (they update continuously).
- KEY FACTS — **Access:** stats endpoint keyless (tiny JSON); `api/pro/geo` keyless returns only country view/extent metadata (`ask:true` — cams behind Pro); cam data itself is in their map app (auth/paid). Sources page: everything from **official public portals** ("public-sector information reuse rules"; credits per portal; only latest frame kept; no history; takedown contact); context layers OSM/Natural Earth/OurAirports + open ADS-B/AIS.
- KEY FACTS — **Directory:** sitemap = 1,691 URLs (site/blog pages; no per-cam pages); robots allow; ES/EN; commercial product (ARGOS PRO pricing, affiliates). **This is the closest peer to world-feed-db's ambition** seen so far.
- KEY FACTS — **License/ToS:** their reuse posture mirrors ours; do not take their derived data; treat as benchmark.
- **VERIFIED TODAY:** stats API fetched; homepage claims extracted; robots/sitemap fetched & parsed; geo endpoint probed; sources/methodology page read.
- **VERDICT: REFERENCE** — competitive benchmark + a useful yardstick (a functioning 200K-cam aggregator = proof the catalog scale target is real; their "75–80% still-image, 20% video" split informs our viewer tiers). Not an ingest source (no keyless cam payload; Pro gates). Build: **mgmt/benchmark** (track their published counts; compare our coverage).

---

## Dead ends & negative findings (so nobody re-discovers them)

1. **openwebcamdb free-tier API is off-limits for this program** — ToS prohibits "creating competing webcam directories or aggregators", commercial use, and "excessive scraping/data harvesting"; keyless calls 302 → /login. Only a commercial license would unlock legit use. (robots.txt leaks a `openwebcamdb.test` dev URL.)
2. **earthcamtv "fuller catalog" not found** — beyond `playlist.php?r=playlist&a=fetch` (12 items), all probed request-type variants return `400 Request Type Error`; www.earthcamtv.com is a static landing page; `/api/dotcom-search/html/autocomplete` exists but returned `[]` for tested params.
3. **worldlive.app has no web data surface** — pure Wix marketing + mobile app (KMA Tech Holding); came only from the tab list, claims 15,000 cams (verify). 
4. **worldcam has no sitemap** (5 paths probed, .eu and .pl) — enumeration must go country → `/p/N` (25/page).
5. **Monterey Bay Aquarium site is AWS-WAF-walled to non-browsers** — use the YouTube channel (verified live) instead; don't grind the site.
6. **Panomax global directory endpoint not captured (yet)** — `explore.panomax.com` is a JS map; `api.panomax.com` probed paths 404; per-cam image pattern found instead (cams/<id>/preview_og.jpg).
7. **CruisingEarth: 5 of 21 lines returned 0 ship links** (Carnival, Cunard, MSC, PO, Royal Caribbean) — likely structure/JS difference; re-check with browser before concluding those lines lack cams.
8. **webcamera24 robots blind spots honored** — `/api/v1/*`, `/camera/*/*/stream/`, `/*?` were NOT crawled; stream resolution evidence was obtained from page payloads + the upstream m3u8 (no disallowed paths touched).
9. **earthlive24 `/api/` is robots-disallowed** — not fetched; sitemap + SSR HTML were sufficient (414 cams + YouTube ids).
10. **ARGOS Pro geo endpoint gives no cams keyless** — `ask:true` gate; don't poke further.

## Cross-cutting patterns (what this means for the build)

- **Stream-resolution taxonomy is now 6 types, all seen today:** (a) inline app payload with direct HLS link (webcamera24 `streamLink`), (b) inline app payload with YouTube code (webcamera24 `youtubeCode`), (c) SSR YouTube embeds (earthlive24, openwebcamdb, zoos), (d) tokenized HLS with timestamped token (EarthCam `?t=&td=`), (e) owner-published platform embeds (IPCamLive `player.php?alias=`), (f) panorama-provider iframes/images (Panomax, Roundshot). Build adapters per type; never store tokenized URLs as durable records.
- **Liveness signals available keyless across the batch:** webcamera24 `isWork`; EarthCam `cam_state`; worldcam date-stamped snapshot paths; YouTube `is_live` via yt-dlp; openwebcamdb counters; Roundshot `status` (S1). That's five independent liveness layers for the registry.
- **New enumerable records this wave (non-overlapping with S1–S5):** webcamera24 6,570 · earthlive24 414 · worldcam (samples; claim 32,330 across DB) · ships 151 · zoos 17 (13+4) · animalcams 11 · IPCamLive aliases 2 — **≈7,100+ new records before dedupe**, plus the 220K-class benchmark from ARGOS.
- **License radar (must-keep):** openwebcamdb = blocked for competitors; ARGOS = pro-gated; worldcam/webcamera24/earthlive24 = fair-use + robots-aware; Reddit/Insecam stay out (policy).
- **Highest-leverage next spikes:** (1) worldcam.eu country-crawler (32K-claim DB, image tier); (2) `explore.panomax.com` endpoint capture (panorama provider #2 after Roundshot); (3) CruisingEarth 5-line browser re-check.

## Evidence artifacts (all this wave)

- `C:\Users\user\world-feed-db\research\sources\S6-aggregators-2.md` (this file; 15 entries)
- Scratch (session `$TMPDIR/s6`): `wc24-s1..7.xml` (webcamera24 sitemaps, 229.9 MB), `owdb-sitemap.xml`, `owdb-openapi.json` (OpenAPI spec), `owdb-api.html`/`owdb-docs.html`, `e24-sitemap.xml` + `e24-cams.txt` (414), `ectv-playlist.json`, `skyline-streams.txt` (580), `ce-*.html` (CruisingEarth), `pm-*.html` (Panomax), `argos-*.html/json` (ARGOS stats/sitemap/sources), `tab2-*.html` (zoos/bondi/monterey), `ce-jupiter.html` (Panomax iframe evidence), `wc-pl counter` in `wcpl-home.html`.
- Prior context used (not duplicated): `research/sources/S1-aggregators.md`; `research/gov/S2-gov-institutional.md` (panomax TODO line); `zero-hud\reference\world\WV1-live-video-sources.md`.

# NS3 — Mountain / Coastal Resort Webcams (research dossier)

- **Cluster:** Whistler Blackcomb, Grouse Mountain, Steamboat, Jungfrau, South Padre Island (5 sites)
- **Checked:** 2026-10-05 16:30–16:45 UTC (live curl + real-browser verification)
- **Prepared for:** world-feed-db `research/new-sources/` — enumeration + ingester handoff
- **Evidence artifacts:** raw HTTP responses cached in scratch `ns3/` (page HTML, image samples, JSON status payloads); byte counts below are from those live fetches.

## Vendor map (what one ingester can cover)

| Vendor | Used by (this cluster) | Public feed pattern | Multiplier |
|---|---|---|---|
| **Brownrice** | Whistler Blackcomb (8 stations) + Vail.com (5 stations observed) | `https://player.brownrice.com/snapshot/<station>` (static JPEG) ; HLS player via `https://live4.brownrice.com/?sn=<station>` ; iframe `https://player.brownrice.com/embed/<station>` | All Vail Resorts properties (same AEM component `webcam_brownrice` / `webcambrownrice.css`, confirmed on whistlerblackcomb.com AND vail.com) |
| **Skaping** | Grouse Mountain (3 photo cams + 1 live) | `https://skaping.s3.gra.io.cloud.ovh.net/<group>/<slug>/YYYY/MM/DD/large/HH-MM.jpg` ; live thumbs `https://skaping.quanteec.com/.../thumbnail.jpg` ; player pages `https://www.skaping.com/<group>/<slug>` | `https://www.skaping.com/sitemap.players.xml` = **877 player pages** across all customers (verified) |
| **Ozolio** | Grouse Mountain (5 cams) | embed `https://relay.ozolio.com/pub.api?cmd=embed&oid=<OID>` ; poster image `https://relay.ozolio.com/pub.api?cmd=poster&oid=<OID>` | ozolio hosts many tourism/beach cams; **caution: relay.ozolio.com/robots.txt = `Disallow: /`** |
| **Roundshot** | Jungfrau (10 cams, ids in `cp-api`) | `https://backend.roundshot.com/cams/<roundshot_id>/<size>` (302 → `storage2.roundshot.com/.../<ts>_<size>.jpg`) ; sizes: `full`, `optional`, `medium` | Roundshot instances are common in CH/AT; Jungfrau uses shared instance `jungfrau.roundshot.com` + `maennlichen.roundshot.com` |
| **YouTube live** | Steamboat (9 resort cams, channel @SteamboatResort) ; South Padre Island (4 cams) | `https://www.youtube.com/embed/<videoId>` ; verify via `https://www.youtube.com/oembed?url=...&format=json` | Any tourism board / resort that streams to YouTube (SPI + Steamboat both do) |

---

### Whistler Blackcomb — https://www.whistlerblackcomb.com/the-mountain/mountain-conditions/mountain-cams.aspx

- **Scale:** 8 cams. Counted live in-browser: 8 `iframe[src*="brownrice"]` elements with matching titles on the cams page (page is JS/AEM-rendered; curl gets an Akamai error page).
- **Feed types:** stream (HLS inside Brownrice player) + picture (vendor snapshot JPEG endpoint — the same image the public player shows as poster).
- **Enumeration path:**
  - Render the cams page in a real browser and collect `iframe[src*="player.brownrice.com/embed/"]`. Verified stations (title ↔ station, paired by DOM order):
    1. Roundhouse Lodge, Whistler Mountain → `whistlerroundhouse`
    2. Whistler Peak → `whistlerpeak`
    3. Rendezvous Lodge, Blackcomb Mountain → `whistlerblackcomb`
    4. BIKE PARK CAM, Whistler Mountain → `Whistleraline`
    5. Whistler Village Cam → `whistlervillagefitz`
    6. Blackcomb Base, Upper Village → `whistlervillage`
    7. Creekside Camera → `whistlercreekside`
    8. 7TH HEAVEN, BLACKCOMB MOUNTAIN → `whistler7thheaven`
  - Ingest/poll: `https://player.brownrice.com/snapshot/<station>` → `image/jpeg` still, no auth/referrer needed.
  - Player page (one station example) also references: `https://live4.brownrice.com/?sn=<station>&em=1&framed=true` (HLS player JS) and `https://live9.brownrice.com/cam-images/<station>.jpg` (same bytes as snapshot for the tested station).
  - Vail Resorts multiplier — same vendor/component confirmed on https://www.vail.com/the-mountain/mountain-conditions/mountain-cams.aspx (browser render): stations `vailch11`, `vailch21`, `vailch2`, `vaileaglesnest`, `vailsnowsummit`. Expect the same pattern on Breckenridge/Park City/Keystone/etc. (each needs its own station-ID harvest).
- **Sample verification (all fetched live 2026-10-05):**
  - `curl -s -o snap.jpg -w "%{http_code} %{content_type} %{size_download}" https://player.brownrice.com/snapshot/whistlerroundhouse` → **200 image/jpeg 59065 bytes**
  - same command: `whistlerpeak` → 200 image/jpeg 26017 B; `whistlerblackcomb` → **200 image/jpeg 114961 B**; `Whistleraline` → 200 47500 B; `whistlervillagefitz` → 200 66672 B; `whistlervillage` → 200 468468 B; `whistlercreekside` → 200 538966 B; `whistler7thheaven` → 200 55362 B (all 8/8 OK)
  - `curl -s -o x.jpg -w "..." https://live9.brownrice.com/cam-images/whistlerroundhouse.jpg` → 200 image/jpeg 59065 B
- **Provenance:** public_by_design — Vail Resorts (operator) publishes the cam page; snapshots/HLS are the vendor feeds shown to the public.
- **Constraints:** whistlerblackcomb.com HTML is Akamai bot-managed for plain curl (returns a "system cannot process your request" page from reservations.snow.com); use a rendering client for DISCOVERY only. `player.brownrice.com/robots.txt` returns 404 (no policy); snapshot endpoint is public and referrer-free. Keep poll ≥60 s (site convention; snapshots refresh on the order of minutes).
- **Fold-in verdict:** **ADD NOW** — registry family **`vailresorts-brownrice`** (station slugs; start with the 8 whistler-* + 5 vail.com stations; extend per property).

### Grouse Mountain — https://www.grousemountain.com/web-cams

- **Scale:** 9 cams on the page: 4 Skaping (`peak-cam`, `zips-cam`, `adrenalin-cam`, gravity live) + 5 Ozolio (Bear Habitat Cam – Front, Bear Yard Cam, "Grouse Mountain", Peak Cam, Bear pond). Counted from page iframes + Skaping's embedded "explore" config (which lists sibling cams of the operator group).
- **Feed types:** mixed — Skaping 360 photo cams (JPEG, ~10-min cadence) + 2 live (Quanteec HLS with public `thumbnail.jpg`); Ozolio = their player streams + public `poster` JPEG endpoint.
- **Enumeration path:**
  - Page `https://www.grousemountain.com/web-cams` iframes → `https://www.skaping.com/grouse-mountain/{peak-cam|zips-cam|adrenalin-cam}` and `https://www.skaping.com/grouse-mountain-gravity-cam/live`; Ozolio embeds listed below.
  - Skaping latest-image trick: each player page's `<meta property="og:image">` (and inline `Launcher.start(...)` config) contains the **newest capture URL**: `https://skaping.s3.gra.io.cloud.ovh.net/grouse-mountain/<slug>/YYYY/MM/DD/large/HH-MM.jpg` (also `/mini/HH-MM.jpg`). Cadence observed: captured every ~10 min (…18-20, 18-30, 10-50).
  - Skaping vendor-wide sitemap: `https://www.skaping.com/sitemap.players.xml` (877 `<loc>` entries — the enumeration source for ALL Skaping customers; grouse entries: `grouse-mountain/zips-cam`, `grouse-mountain/adrenalin-cam`, `grouse-mountain/peak-cam`).
  - Ozolio OIDs (embed → poster): `EMB_HHVH0000061A` (Bear Habitat – Front), `EMB_IZXT00000462` (Bear Yard), `EMB_KCRL0000012E` ("Grouse Mountain"), `EMB_QEXW000010C9` (Peak Cam), `EMB_YXJY00001010` (Bear pond). Poster URL: `https://relay.ozolio.com/pub.api?cmd=poster&oid=<OID>`.
- **Sample verification:**
  - `curl -s -o s.jpg -w "%{http_code} %{content_type} %{size_download}" "https://skaping.s3.gra.io.cloud.ovh.net/grouse-mountain/peak-cam/2026/10/02/large/10-50.jpg"` → **200 image/jpeg 142979 B** (real 3847×720 JPEG)
  - zips latest `.../grouse-mountain/zips-cam/2026/10/05/large/18-30.jpg` → **200 image/jpeg 232365 B** (fresh)
  - `https://skaping.quanteec.com/contents/encodings/live/02964f66-...-6f575613c132d/thumbnail.jpg` (zips live) → 200 image/jpeg 20694 B; gravity live thumb → 200 image/jpeg 7486 B
  - `curl -s -o p.jpg -w "..." "https://relay.ozolio.com/pub.api?cmd=poster&oid=EMB_HHVH0000061A"` → **200 image/jpeg 865491 B**; also `EMB_IZXT00000462` → 210168 B; `EMB_KCRL0000012E` → 226267 B; `EMB_QEXW000010C9` → 1606486 B; `EMB_YXJY00001010` → 105075 B (all 5 OK)
  - Skaping per-cam status from player config: peak-cam **stale/offline** (`is_online:false`, last media 2026-10-02); zips-cam, adrenalin-cam, gravity live OK.
- **Provenance:** public_by_design — operator (Grouse Mountain Resorts) embeds vendor cams; Skaping/Ozolio feeds are the public display feeds.
- **Constraints:** skaping.com robots allows player pages (disallows only `/ccl.php*`, `/showroom/*`, `/about/*?*`, `/player/tv`; sitemap provided). grousemountain.com robots disallows `/api*`, `/cart*`, `/account*` etc. — the web-cams page itself is allowed. **relay.ozolio.com robots.txt = `Disallow: /` → treat Ozolio automated polling as needs-review** (flag; prefer Skaping part first).
- **Fold-in verdict:** **Skaping part → ADD NOW** (family `skaping`; covers Grouse + 874 other pages vendor-wide). **Ozolio part → LATER** (robots flag; ingest only after review/approval).

### Steamboat — https://www.steamboat.com/the-mountain/live-cams

- **Scale:** ~9 resort cams (Steamboat Square, Four Points Lodge, Christie Peak Express & Wild Blue Gondola, Thunderhead, Mid-Mountain Snow Stake, Champagne Powder® Snow Cam, Rendezvous, Thunderhead Lodge, Christie Base). Counted from verified live-stream IDs on the resort's own YouTube channel.
- **Feed types:** stream — YouTube live embeds (resort runs YouTube-based cams; confirmed by third-party caption "Camera feeds courtesy of Steamboat Ski Resort" and community discussion that Steamboat streams to YouTube unlike most resorts). No direct JPEG/hls URL found on the origin site.
- **Enumeration path:**
  - Source of truth A: `https://www.steamboat.com/the-mountain/live-cams` + subpages `/live-cams/christie-cam`, `/live-cams/mid-mountain-snow-stake-cam`, `/live-cams/champagne-powder-snow-cam` (listed in `https://www.steamboat.com/sitemap.xml`, which IS retrievable via curl). Origin site is behind Imperva Incapsula JS challenge (see constraints) — needs a real browser when scraping.
  - Source of truth B (recommended): YouTube channel `https://www.youtube.com/@SteamboatResort` — live tab lists the resort's live cams. Verified IDs (all `oembed` 200, author = "Steamboat Resort"):
    - `2UJDLWcSADk` Steamboat Square Cam
    - `evs4diWVKiY` Four Points Lodge
    - `fI30YzAmCHw` Christie Peak Express & Wild Blue Gondola Cam
    - `KJka6pGArbc` Thunderhead
    - `lKc9xwndUK4` Mid-Mountain Snow Stake Cam
    - `PD9MoCKRwCA` Champagne Powder® Snow Cam
    - `PinqovlSY-o` Rendezvous
    - `qjAqCiwCW34` Thunderhead Lodge
    - `VQ37fu8sd9M` Christie Base
    - (Excluded: `iJlOcnEbWMY` "FITH – Steamboat 2019…" — author Jeff Carlson, not a resort cam.)
  - Embed URL: `https://www.youtube.com/embed/<videoId>` (note: IDs were recovered from the public steamboatpilot.com/webcams page which embeds the resort's feeds; the same videos are used by the resort site).
- **Sample verification:**
  - `curl -s "https://www.youtube.com/oembed?url=https%3A//www.youtube.com/watch%3Fv%3D2UJDLWcSADk&format=json"` → **200 application/json 780 B** `{"title":"Steamboat Square Cam","author_name":"Steamboat Resort","author_url":"https://www.youtube.com/@SteamboatResort",...}`
  - Same for all 9 IDs above → all 200 (760–844 B each) with cam titles. Liveness re-check at ingest time (oembed confirms existence; the channel page shows which are currently live).
- **Provenance:** public_by_design — resort-operated YouTube live cams, embedded publicly.
- **Constraints:** steamboat.com origin is Imperva Incapsula-protected: first browser load OK, subsequent quick loads served the JS challenge (noindex `/_Incapsula_Resource`); plain curl also blocked. sitemap.xml fetchable. Wayback machine rate-limited (429) during research. **Correction to cluster assumption: Steamboat is an Alterra Mountain Company resort, NOT Vail Resorts** — no shared backend with Whistler; its cam system is YouTube-based.
- **Fold-in verdict:** **ADD NOW** — family **`youtube-live-cams`** (entries: steamboat-<id>; liveness/polling via oembed + embed page), with the WAF note.

### Jungfrau (Switzerland) — https://www.jungfrau.ch/en-gb/live/webcams/

- **Scale:** 10 cams. Counted from the site's own public API `cp-api/webcams` (returns 10 entries).
- **Feed types:** picture — Roundshot high-res JPEGs (~10-min cadence, `lastImageAt` exposed) + Roundshot player pages per cam.
- **Enumeration path (best-in-class for the registry):**
  - **List:** `https://www.jungfrau.ch/cp-api/webcams/?site=en` → JSON `{data:[{id, slug, title, altitude_m, coordinates, roundshot_id, roundshot_url, ...}]}`. The key field is `roundshot_id` (32-hex md5). Verified map (title | roundshot_id | instance):
    - Jungfraujoch | `584c8f65bd7b360eed6ffd43226cca8a` | webcams.jungfrau.ch/top-of-europe-jungfraujoch
    - Männlichen | `877919abdb23eb59f63908ab8b300f1f` | maennlichen.roundshot.com
    - Eiger Express | `8ebf876ae226aa03b0c65b0985e6f60e` | webcams.jungfrau.ch/top-of-europe-eiger-express
    - Eigergletscher | `486d6b1c471c581a99233dc3e4cc3ab7` | webcams.jungfrau.ch/eigergletscher
    - Grindelwald-First (Schreckfeld) | `c7f0edeec13d52b6c3cf91485d982548` | webcams.jungfrau.ch/first-schreckfeld
    - Grindelwald Terminal | `034de41e47b30dde0362b86b42d9fb61` | webcams.jungfrau.ch/grindelwald-terminal
    - Harder Kulm | `8acf8be16f88a36a1646ea3208f4fbea` | webcams.jungfrau.ch/interlaken-harderkulm
    - Jungfraujoch (Ostgrat) | `dbb5da2713c66505f2004b60c6c56609` | webcams.jungfrau.ch/top-of-europe-jungfrau-ostgrat
    - Kleine Scheidegg | `527f953c3776c0552355d4a154c2b4e8` | webcams.jungfrau.ch/lauberhorn
    - Schynige Platte | `9e425745e5de8732e6417c934111cb09` | webcams.jungfrau.ch/schynige-platte
  - **Status:** `https://www.jungfrau.ch/api/live-data/webcams/status?ids=<id1>,<id2>,...` → `{ "<id>": {online: bool, lastImageAt, ageSeconds, reason} }` (batch; used by the site itself).
  - **Image:** `https://backend.roundshot.com/cams/<roundshot_id>/full` → 302 → `https://storage2.roundshot.com/<hash>/YYYY-MM-DD/HH-MM-SS/YYYY-MM-DD-HH-MM-SS_full.jpg`. Sizes: `full` (largest), `optional`, `medium` (also `?t=<ms>` cache-buster seen in browser). Follow redirects.
  - Player pages: `https://webcams.jungfrau.ch/<cam>/` (redirects to `https://jungfrau.roundshot.com/<cam>`).
- **Sample verification:**
  - `curl -sL -o img.jpg -w "%{http_code} %{content_type} %{size_download} %{url_effective}" "https://backend.roundshot.com/cams/584c8f65bd7b360eed6ffd43226cca8a/full"` → **200 image/jpeg 647025 B**, final `https://storage2.roundshot.com/5e568a0aaea5b0.54147912/2026-10-05/18-30-00/2026-10-05-18-30-00_full.jpg`
  - Status batch (10 ids) → **200 application/json 325 B**: 9× `online:true, lastImageAt:2026-10-05T16:30:00Z`; 1× `online:false, reason:"stale"` (Jungfraujoch Ostgrat, last image 2026-10-02).
  - `curl -s -w "%{http_code} -> %{redirect_url}" ".../cams/584c.../optional"` → 302 → `.../2026-10-05-18-30-00_optional.jpg` (same storage pattern)
- **Provenance:** public_by_design — Jungfrau Railways publishes cams + structured public APIs.
- **Constraints:** jungfrau.ch robots.txt = explicit `Allow: /` (including GPTBot, ClaudeBot, PerplexityBot etc. — operator welcomes bots); `backend.roundshot.com/robots.txt` = `Disallow:` (empty → allow). No auth on any endpoint used. Update cadence ~10 min; poll accordingly.
- **Fold-in verdict:** **ADD NOW** — family **`jungfrau-roundshot`** (id list from cp-api; poll status API for online/age; fetch `full` for images; the Roundshot `backend.roundshot.com/cams/<id>/<size>` pattern generalizes to other Roundshot operators).

### South Padre Island (Texas) — https://visitsouthpadreisland.com/live-webcams/

- **Scale:** 4 cams across the hub + 3 subpages. Counted: hub `/live-webcams/` + subpages `north-beach-webcam/`, `queen-isabella-causeway/`, `south-beach-webcam/`, each embedding exactly one YouTube live video (4 unique IDs).
- **Feed types:** stream — YouTube live embeds on a Simpleview CMS site (no direct JPEGs).
- **Enumeration path:**
  - Sitemap `https://visitsouthpadreisland.com/sitemap.xml` lists all `/live-webcams/*` pages; each page contains `https://www.youtube.com/embed/<id>?...`. Also CMS event anchors: `/live-webcams/<hash>/#eventList` (not needed).
  - Verified IDs:
    - `kJ_EXhKsH30` — "South Padre Island LIVE – North Beach Webcam at Sand Rose Beach Resort" (hub `/live-webcams/`)
    - `dzylsC0KcOE` — "Live HD Stream – Courtyard by Marriott South Padre Island Live Beach Webcam" (`north-beach-webcam/`)
    - `bvL_3W7F4Fk` — "Live Stream – Queen Isabella Memorial Causeway … Realtime Webcam" (`queen-isabella-causeway/`)
    - `0FaRaPPTS8M` — "South Padre Surf Cam 4K Isla Blanca Beach Park" (`south-beach-webcam/`) — operator/author: South Padre Surf Company (business stream embedded by the CVB)
  - Related (same CVB content): `https://www.sopadre.com/about-us/live-webcams/` embeds the same hub video (`kJ_EXhKsH30`); no additional IDs.
- **Sample verification:**
  - `curl -s "https://www.youtube.com/oembed?url=https%3A//www.youtube.com/watch%3Fv%3DkJ_EXhKsH30&format=json"` → **200 application/json 913 B** `{"title":"South Padre Island LIVE - North Beach Webcam at Sand Rose Beach Resort","author_name":"South Padre Island","author_url":"https://www.youtube.com/@enjoyspi"}`
  - Same for `dzylsC0KcOE` → 200 885 B; `bvL_3W7F4Fk` → 200 897 B; `0FaRaPPTS8M` → 200 942 B (all 4 OK; author channels: @enjoyspi ×3, @spadrevideo ×1).
- **Provenance:** public_by_design (mixed observers) — CVB (tourism board) publishes the gallery; three streams are run by the CVB's @enjoyspi channel, one by a local business — all embedded publicly for viewing. No aggregator of private cams.
- **Constraints:** robots.txt = `Allow: /` with `Crawl-delay: 2` (respect it); YouTube embeds public. Cadence: continuous streams — poll liveness cheaply via oembed (existence) and embed page for live status.
- **Fold-in verdict:** **ADD NOW** — family **`youtube-live-cams`** (entries: spi-<id>). Same family as Steamboat → one YouTube ingester covers both.

---

## Dead ends

- **whistlerblackcomb.com via plain curl** — every request (page + robots.txt) returned a 740-byte Vail "system cannot process your request" error page (Akamai/bot mgmt, routing via reservations.snow.com). Rendered browser worked; discovery only.
- **vail.com via plain curl** — 403 (bot manager). Browser render OK (used for the multiplier check).
- **steamboat.com via curl and via browser retries** — Imperva Incapsula JS challenge (`/_Incapsula_Resource`, `noindex,nofollow`). First browser load succeeded (title + clean resource list, but cams load lazily and weren't in DOM); subsequent loads were challenged. Stopped after repeated attempts; pivoted to the resort's YouTube channel + public third-party embed page for IDs. sitemap.xml fetched OK separately.
- **Wayback Machine** for the Steamboat cams page — HTTP 429 (rate limited); not retried further.
- **`https://www.jungfrau.ch/api/live-data/webcams` (bare list)** — 404; the real listing endpoint is `cp-api/webcams` (found via captured browser network traffic). Slug-based status probe (`/status` with a slug) returns a generic `{"online":false,"reason":"error"}` — only the md5 `roundshot_id`s give real statuses.
- **`https://cp.jungfrau.ch/cp/collections/webcams/...` (direct Cockpit)** — 302 (Cloudflare/login). Use the jungfrau.ch `cp-api` proxy instead.
- **Brownrice `/api` (live1/live4.brownrice.com/api)** — documented as their RADIO playlist API (station call signs), not cams; no cam value. Their `cam-control/*` endpoints look like PTZ/admin surfaces → not touched.
- **Grouse peak-cam** — currently stale/offline at source (`is_online:false`, last capture 2026-10-02); page + archived image still serve. Include but expect stale until operator fixes.
- **Skaping gravity live page** — not in `sitemap.players.xml` (live-only pages are excluded); reachable directly at `https://www.skaping.com/grouse-mountain-gravity-cam/live` and via the quanteec thumbnail (verified 200).
- **YouTube embed pages via curl** — no `isLiveNow`/`hlsManifestUrl` strings for plain curl (consent/shell responses); liveness must be checked via channel page or at ingest runtime. oembed used as the existence check.

## Method notes

- **Verification convention used:** every feed counted as verified only after a live fetch: HTTP status + `content-type` + `size_download` via `curl -s -o <file> -w "%{http_code} %{content_type} %{size_download}"`; YouTube items via `oembed` JSON; Jungfrau via its public status API. All checks run 2026-10-05 16:30–16:45 UTC.
- **Client choices:** plain curl for everything unless the site is bot-walled. Whistler/Vail/Steamboat discovery required a real (CDP-driven) browser; the extracted facts are from rendered DOM + `performance.getEntriesByType('resource')` (caught the Jungfrau `backend.roundshot.com` calls and the Brownrice iframes this way).
- **One-ingester-covers-many priorities (biggest wins first):** 1) **Brownrice snapshot** (`player.brownrice.com/snapshot/<station>`) — trivially simple, covers all Vail properties; just needs per-property station-ID lists (harvest per cams page). 2) **Jungfrau Roundshot** — fully structured (list API + status API + deterministic image URL). 3) **Skaping** — deterministic S3 pattern + 877-page sitemap; og:image on each player page gives the current capture without parsing dates. 4) **YouTube family** — oembed for existence, channel live tab for liveness (covers SPI + Steamboat and any future YouTube-based source).
- **Suggested registry family names:** `vailresorts-brownrice`, `jungfrau-roundshot`, `skaping`, `youtube-live-cams` (SPI + Steamboat), `ozolio` (hold for review).
- **Polling cadences to bake in:** Brownrice snapshots = on the order of minutes (refresh ≥60 s); Skaping captures ~10 min; Roundshot ~10 min (use `lastImageAt`/`ageSeconds` before storing); YouTube = liveness check every 5–15 min.
- **Robots/ToS flags to carry into the registry:** relay.ozolio.com = `Disallow: /` (review before ingest); skaping.com allows player pages and publishes a sitemap; jungfrau.ch explicitly allows bots; visitsouthpadreisland.com allows with crawl-delay 2; grousemountain.com restricts only API/cart/account paths; steamboat.com allows except `/sitecore`; whistlerblackcomb.com/robots.txt not retrievable via curl (bot blocker) — check in browser if needed.

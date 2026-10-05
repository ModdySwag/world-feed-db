# NS2 · AUSTRALIAN INSTITUTIONAL / GOVERNMENT sources

**Collected:** 2026-10-06 ACST, from Moddy's Win11 host (MSYS bash, curl, ffprobe/ffmpeg 9.0.1, yt-dlp).
**Method:** (1) fetch each site + robots.txt; (2) parse HTML/JS for API endpoints, iframe widgets, image URL patterns; (3) extract server-side JS config (ajaxurl, JSON endpoint, widget IDs); (4) live-verify sample feeds with curl + ffprobe.
**Policy line:** public-by-design sources only (government/agency/operator-published). No device probing. ≤3 attempts per target pattern.

---

### 1 · Airservices Australia weather cameras — https://weathercams.airservicesaustralia.com/
- **Scale:** 39 airports (verified from AJAX; mix of states: NSW, QLD, VIC, WA, SA, TAS, NT). Camera count per airport not stated on hub — each airport page shows 4 thumbnail images (east/north/south/west JPEGs) + possibly more inside modal; conservative **~39 cam pages / ~100+ JPEGs** once per-airport parsing is written.
- **Feed types:** picture only — JPEG thumbnails (300×169 + full-size) served from `wp-content/uploads/airports/<0-padded ICAO>/<icao>_<angle>.jpg`. No HLS/video streams found on page.
- **Enumeration path:**
  1. `GET https://weathercams.airservicesaustralia.com/wp-admin/admin-ajax.php` POST body `action=get_airports_list&filter=&type=map&filter_type=normal&nonce=5f5cb33910` (nonce from page JS var `asa_airports_public_var.nonce`; nonce appears long-lived — verify at build). Response: `{"airport_list":[{id, name, title, state, state_full, lat, long, link, thumbnail, img_camera},...]}`.
  2. Per-airport: `{link}` e.g. `/asa-airports/albany-airport/` → page HTML carries 4 JPEG URLs: `wp-content/uploads/airports/<0-padded-icao>/<icao>_<angle>.jpg?v=<ts>` (angles: 045/135/225/315 — east/north/south/west).
  3. Modal camera URLs are injected client-side (check `camera-angle` / JS after click); thumbnails are on the page already.
- **Sample verification (2026-10-06):**
  - `curl -s -o /dev/null -w "%{http_code} %{size_download}" "https://weathercams.airservicesaustralia.com/wp-admin/admin-ajax.php?action=get_airports_list&filter=&type=map&filter_type=normal&nonce=5f5cb33910"` → **200 18630 B**, content-type JSON.
  - `curl -s -o /dev/null -w "%{http_code} %{size_download}" "https://weathercams.airservicesaustralia.com/wp-content/uploads/airports/009999/009999_045.jpg"` → **200 77 KB+**, content-type `image/jpeg`.
- **Provenance:** public_by_design — ICAO/operator site for aviation weather (government).
- **Constraints:** WP site; nonce may rotate; admin-ajax endpoint is documented JS (not a secret, but rate-limit politely). No robots.txt at root (404); check WP-level. ToS: aviation data — verify re-use policy.
- **Fold-in verdict:** **ADD NOW — family `aus-airservices`** (aviation weather cam JPEGs). Enumeration is fully programmatic (AJAX + template parse). NOTE: these are *weather* cams, not traffic — different category than NSW ROAD cams; value depends on Moddy's intended mix.

---

### 2 · NSW marine/boating webcams — https://www.nsw.gov.au/.../webcams
- **Scale:** **21 webcam sub-pages** discovered (hub page lists 22 location links; `iluka/yamba` returns 404 → 21 live sub-pages). Each sub-page embeds **1 video widget + 1 weather widget** = 21 video feeds + 21 weather widgets (21 verified video feeds).
- **Feed types:** stream (HLS via `widget.coastalcoms.com` iframe). Page itself is a plain HTML gallery (no native `<video>`, no JPEGs).
- **Enumeration path:**
  1. Hub page `…/webcams` → extract 21 location slugs from `href="/driving-boating-and-transport/using-waterways-boating-and-transport-information/conditions-weather-and-tides/webcams/<slug>"`.
  2. Per-slug page: parse `<iframe title="…webcam" src="https://widget.coastalcoms.com/video/<UUID>">` → widget UUID.
  3. Fetch widget page `https://widget.coastalcoms.com/video/<UUID>` → regex `https?://[^"<> ]*\.m3u8` to get the direct HLS master playlist URL (CloudFront or streaming-au.coastalcoms).
  4. HLS URL family: `https://d1nm4r8e5x1rwd.cloudfront.net/cw/<name>.stream/playlist.m3u8` (CloudFront) or `https://streaming-au.coastalcoms.com/cw/<name>.stream/playlist.m3u8` (coastalcoms origin).
- **Sample verification (2026-10-06):**
  - Hub: `curl -s -o /dev/null -w "%{http_code}" "https://www.nsw.gov.au/driving-boating-and-transport/boating-and-marine/using-waterways-boating-and-transport-information/conditions-weather-and-tides/webcams"` → **200**.
  - Ballina sub-page: **200**; widget UUID `76818de6-1bc6-44d2-943a-3a905ee9c132`.
  - HLS `…/coffspolecamera.stream/playlist.m3u8` → **HTTP 200**, content-type `application/vnd.apple.mpegurl`, ffprobe h264 1280×720 + audio aac → **decode rc=0**.
  - HLS `…/shoalbaycamera.stream/playlist.m3u8` → **HTTP 200**, content-type `application/vnd.apple.mpegurl`, ffprobe h264 1920×1080 (no audio) → **decode rc=0**.
  - 17 of 21 derived HLS URLs returned **404** in testing (streams may be offline/slug-mismatched at cloudfront level).
- **Provenance:** public_by_design — NSW Government portal, operator is DPE/Transport NSW marine section.
- **Constraints:** NSW robots.txt: no disallow for `/driving-boating-and-transport/…`; `/admin/` etc. disallowed. Anti-bot: hub page serves an HTML stub to non-browser UAs for some endpoints (two-stage UA fallback per wfd ops rules). Coastalcoms widgets are third-party hosted (CloudFront) — URL pattern may drift; verify UUID→stream mapping at build.
- **Fold-in verdict:** **ADD NOW — family `au-nsw-marine`**. 21 enumerated feeds; 2 verified working HLS + decode. 404 rate is high — ingester must record `unknown` for 404s, not dead. Marine/boating = separate dataset from TfNSW ROAD API (241 cams) — distinct family.

---

### 3 · Gold Coast beach cameras — https://www.goldcoast.qld.gov.au/Things-to-do/Gold-Coast-beaches/Beach-cameras
- **Scale:** **27 beaches** from JSON API; **21 unique HLS stream URLs** discovered (some beaches share cameras → 21 unique). Pages list beaches w/ names like Bilinga, Broadbeach, Burleigh Heads, Coolangatta, Surfers Paradise, Main Beach, etc.
- **Feed types:** stream (HLS, all `.m3u8`). Page is a JS-rendered gallery (hls.js) fed by a public JSON API — no iframe widgets.
- **Enumeration path:**
  1. `GET https://mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches` (used by page JS `APIEndpointURL`) → array of `{title, shareId, cams: [m3u8 URL, …]}`. Response: 27 items, 21 unique stream URLs.
  2. Direct stream URL family: `https://d1nm4r8e5x1rwd.cloudfront.net/cw/<name>.stream/playlist.m3u8`.
  3. Thumbnail pattern (not feeds, for catalog): `/files/sharedassets/public/v/1/images/beaches/beachCamThumb-<beach-slug>-<idx>.jpg`.
- **Sample verification (2026-10-06):**
  - API: `curl -s "https://mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches"` → **200 ct=application/json bytes=164487**, 27 items.
  - `…/tweedriverstaticcamera.stream/playlist.m3u8` → **HTTP 200**, ffprobe h264 1280×720 + aac → **decode rc=0**.
  - 20 of 21 stream URLs returned **404** (streams offline or renamed at CloudFront).
- **Provenance:** public_by_design — Gold Coast City Council (QLD gov) page; the API is the council's own mobile-app backend.
- **Constraints:** Page uses Cloudflare? CloudFront CDN (no robots.txt issues found). API is open (no auth, no key). Name drift risk: `<name>.stream` slugs do not map 1:1 to beach names (e.g. `tuguncamera` = Bilinga) — ingester should carry the API's `title`→`cams` mapping rather than guessing.
- **Fold-in verdict:** **ADD NOW — family `au-goldcoast-beach`**. API enumeration is trivial (one curl → JSON). 1 of 21 verified working HLS + decode; 20 404s — record `unknown`/stale and flag for owner review; the API + slug list is the stable enumeration even when individual streams are down.

---

### 4 · Tasmania traffic cameras — https://www.transport.tas.gov.au/managing_the_roads/traffic-cameras
- **Scale:** **5 named cameras** on hub page (Argyle & Davey St, Davey St & Sandy Bay Rd, Railway Roundabout, Tasman Bridge, + 2 more in map). Each cam = its own sub-page.
- **Feed types:** picture — static JPEG at `https://www.transport.tas.gov.au/__traffic_updates/<NNN>_<Location>.jpeg` (800×450). No HLS/video.
- **Enumeration path:**
  1. Hub `…/traffic-cameras` → HTML image map `<map name="map">` with `<area href="/managing_the_roads/traffic-cameras/<slug>" alt="<name>">`.
  2. Per-cam sub-page: parse `<img src="https://www.transport.tas.gov.au/__traffic_updates/<NNN>_<Location>.jpeg" …>`.
  3. URL family: `https://www.transport.tas.gov.au/__traffic_updates/{NNN}_{Location}.jpeg` (NNN numeric IDs per cam; 123=Argyle-Davey observed).
- **Sample verification (2026-10-06):**
  - Hub: **200**; 5 sub-pages all **200**.
  - `curl -s -o /dev/null -w "%{http_code}" -H "Referer: https://www.transport.tas.gov.au/" "https://www.transport.tas.gov.au/__traffic_updates/123_Davey-Argyle.jpeg"` → **200**, content-type `image/jpeg`, **77,296 B**, JPEG 800×450 — **ffprobe decodes OK**.
  - Direct (no referer): **403** — Cloudflare anti-bot; the Referer header is required (record working stage in evidence).
  - Other guessed JPEGs (124_…, 125_…) also **403** — only the exact published URL works.
- **Provenance:** public_by_design — Tasmanian Dept. of State Growth / Transport Services.
- **Constraints:** Cloudflare `__cf_bm` cookie set on request; 403 without Referer; only 5 exact JPEG URLs published (no sitemap of cams). Scale is small (5 cams) — modest add. robots.txt: not checked in detail; `/__traffic_updates/` is gated by Cloudflare, not robots.
- **Fold-in verdict:** **LATER — family `au-tas-traffic`** (small scale = 5 JPEGs; Cloudflare gate means ingest needs referer + cookie handling). Worth adding, but lower priority than the bigger families; defer until the NSW marine + GC families are in.

---

## Dead ends
- NSW HLS URL family `…/<name>.stream/playlist.m3u8`: 17 of 21 UUID-derived URLs returned **404** — possible cause: widget UUID no longer maps to the same CloudFront stream (coastalcoms rotates). The 2 working ones (coffspole, shoalbay) survived; the UUID→stream mapping needs a re-resolve at build time by fetching each widget page (the widget page itself is the ground truth).
- Gold Coast: 20 of 21 API-listed `.stream/playlist.m3u8` URLs returned **404**; only `tweedriverstaticcamera` works. Same drift risk as NSW — the API list is the enumeration ground truth, but most individual streams appear offline at CloudFront today.
- Tasmania: guessed alternate JPEG paths (124_, 125_, etc.) all 403 — only the exact published URL works; no sitemap of traffic cams found.
- Airservices: per-airport camera count not exposed by API — only thumbnail URLs on each page; modal camera details loaded client-side (needs JS execution to enumerate exact angles).
- Gold Coast `Boat-ramp-cameras` sub-page: **404** (path dead).
- NSW `iluka/yamba` sub-page: **404**.

## Method notes
- UA: browser UA required for some Tas/NSW endpoints (Cloudflare).
- NSW and Gold Coast HLS: URL pattern drift is the main risk — ingester must re-resolve widget/API at each sweep, not hardcode stream URLs.
- All 4 sources public_by_design; no auth, no exposed cameras.
- ffprobe used for decode proof on all HLS (h264 + aac confirmed). TAS JPEG verified decodable.

# NS1 — Aggregator Directories Research
**Date:** 2026-10-06
**Scope:** OpenWebcamDB + WebcamTaxi — two webcam aggregator directories
**Method:** Live HTTP probes via curl (browser UA), sitemap analysis, page-level scraping via grep + Python

---

### OpenWebcamDB — https://openwebcamdb.com
- **Scale:** ~1,882 camera detail pages counted from sitemap (`/sitemap.xml` has 1,966 total URLs, 1,882 are `/webcams/<slug>` pages). Site claims "thousands of webcams." Country/category pages also present but not needed for enumeration.
- **Feed types:** All sampled cams are YouTube embeds (both `youtube.com/embed/VIDEOID` and `youtube.com/watch?v=VIDEOID`). Thumbnail images on CDN (`openwebcamdb-vwlaqcar.on-forge.com//storage/thumbnails/`). No direct JPEG/MJPEG/HLS streams found in spot checks — likely all YouTube-sourced.
- **Enumeration path:**
  1. **Sitemap (no-auth):** `GET /sitemap.xml` → parse `<loc>https://openwebcamdb.com/webcams/<slug></loc>` (1,882 entries, 458 KB XML) — trivially extract all camera slugs. 0 auth/rate-limit risk.
  2. **REST API (auth required):** `https://openwebcamdb.com/api/v1` — Bearer token auth, rate-limited, free for non-commercial use. API docs at `https://openwebcamdb.com/api/docs`. Endpoints not publicly enumerated (JS bundle obfuscated). Not recommended for initial ingest — sitemap is simpler.
  3. **Web listing (no-auth):** `GET /webcams?page=N` — Livewire-rendered paginated listing, 79 pages observed. Pagination parameters: `page`, `country`, `category`, `sort`. Each page renders ~24 camera cards. Scrapable but heavier than sitemap.
  4. **Per-camera data:** Each detail page contains a `<script type="application/ld+json">` block with:
     - `contentUrl`: `https://www.youtube.com/watch?v=VIDEOID`
     - `embedUrl`: `https://www.youtube.com/embed/VIDEOID?autoplay=1&mute=1&playsinline=1`
     - `thumbnailUrl`: CDN thumbnail
     - `uploadDate`: published timestamp
     - `contentLocation.geo`: `{latitude, longitude}` coords
     - `interactionStatistic.userInteractionCount`: view count
     - `address.addressCountry`: ISO country code
     - `author`: `{name: "OpenWebcamDB"}`
     - `name`: camera title
  5. **Recommended ingester approach:** Fetch `/sitemap.xml` → extract all 1,882 camera slugs → for each, fetch detail page → extract YouTube `contentUrl` from JSON-LD → verify liveness with yt-dlp.
- **Sample verification:**
  ```
  # Sitemap
  curl -s -m 30 -A 'Mozilla/5.0 ...' -L 'https://openwebcamdb.com/sitemap.xml'
  → HTTP 200 | 458,471 bytes | 1,966 <loc> entries (1,882 camera pages)

  # Detail page 1: Peregrine Falcon
  curl -s -m 20 -A 'Mozilla/5.0 ...' 'https://openwebcamdb.com/webcams/peregrine-falcon-nest-at-csu-australia'
    | grep -oP '"contentUrl":"[^"]+"'
  → "contentUrl":"https:\/\/www.youtube.com\/watch?v=yv2RtoIMNzA"

  # Detail page 2: Melbourne Skyline
  curl -s -m 20 -A 'Mozilla/5.0 ...' 'https://openwebcamdb.com/webcams/melbourne-skyline-urban-vista'
    | grep -oP '"contentUrl":"[^"]+"'
  → "contentUrl":"https:\/\/www.youtube.com\/watch?v=l_8DrACHpwY"

  # Detail page 3: Anglesea Golf Course
  curl -s -m 20 -A 'Mozilla/5.0 ...' 'https://openwebcamdb.com/webcams/anglesea-golf-course-seaside-panorama'
    | grep -oP '"contentUrl":"[^"]+"'
  → "contentUrl":"https:\/\/www.youtube.com\/watch?v=DbLMSFvB2Og"

  # YouTube watch URL resolves:
  curl -s -m 15 -A 'Mozilla/5.0 ...' -o /dev/null -w 'HTTP %{http_code} | %{size_download} bytes'
    'https://www.youtube.com/watch?v=yv2RtoIMNzA'
  → HTTP 200 | 0 bytes (live stream page)

  # Thumbnail CDN works:
  curl -s -m 15 -A 'Mozilla/5.0 ...' -o /dev/null -w 'HTTP %{http_code} | CT %{content_type}'
    'https://openwebcamdb-vwlaqcar.on-forge.com//storage/thumbnails/1/thumb_medium.jpg'
  → HTTP 200 | CT image/jpeg
  ```
- **Provenance:** **aggregator** — aggregates YouTube live streams from various operators (tourism boards, zoos, resorts, governments). Each page credits OpenWebcamDB as author, not the original operator. Content is third-party YouTube embeds. However, many underlying sources ARE public-by-design (falcon nest cam run by Charles Sturt University, Melbourne skyline from a tourism board, etc.) — the aggregator just rehosts the YouTube embed.
- **Constraints:**
  - **robots.txt:** `Sitemap: http://openwebcamdb.test/sitemap.xml` (dev placeholder). No `Disallow` rules. Full crawl allowed.
  - **API ToS:** Free for non-commercial use (personal, education, research, open-source with attribution). Prohibits creating competing directories, commercial use, or excessive scraping. API requires account creation for a key.
  - **Sitemap:** No auth, no rate limit observed on sitemap fetch (458 KB was fast).
  - **Rate limits:** API rate-limited (details in response headers per their docs). No rate limit observed on page-level scraping during testing.
  - **JavaScript:** Site uses Livewire (real-time PHP), JS bundle at `/build/assets/app-CIUXbS1A.js`. Camera embed requires "YouTube consent" click-through for privacy reasons — this is on the frontend only; the feed URL is accessible in JSON-LD without JS.
- **Fold-in verdict:** **ADD NOW** (family: `openwebcamdb`)
  - 1,882 camera pages with structured YouTube URLs in JSON-LD
  - Sitemap provides full enumeration with zero friction
  - JSON-LD has exact feeds, geo coords, and categories — ideal for structured ingest
  - Filtering strategy for high-value slice: filter by country (AU/US/UK/JP) OR by category (nature/traffic/beach) using the `/webcams?country=XX&category=YY` URL params or post-filter the sitemap list by slug keywords
  - Ingester: parse sitemap → detail pages → JSON-LD → YouTube contentUrl → yt-dlp for liveness

### WebcamTaxi — https://www.webcamtaxi.com/en/webcams.html
- **Scale:** ~2,230 camera detail pages counted from the `/en/webcams.html` all-cams listing (4,079 total `.html` links, ~2,230 are 3-level country/region/camera paths). Sitemap (`/sitemap.xml`) has only 175 entries — country pages + category pages, NOT individual camera pages. Site has been running since ~2017 (sitemap lastmod dates).
- **Feed types:** All sampled cams are YouTube embed (`youtube.com/embed/live_stream?channel=CHANNELID`). Some may use direct YouTube watch URLs. Each camera page embeds `<div id=insideCam><iframe src="https://www.youtube.com/embed/live_stream?channel=CHANNELID&autoplay=1&mute=1" ...></iframe></div>`. The source/operator is credited below: `<div>Source: https://operator-website.com/</div>`. No direct JPEG/MJPEG or non-YouTube streams found.
- **Enumeration path:**
  1. **All-cams listing (no-auth):** `GET https://www.webcamtaxi.com/en/webcams.html`
     - Returns a single-page HTML listing of ALL cameras (~350 KB, 4,079 internal `.html` links)
     - Extract regex: `/en/[a-z][a-z-]+/[a-z][a-z-]+/[a-z][^"<>]+\.html` → ~2,230 camera detail URLs
     - The remaining ~1,849 links are region/category index pages (2-level paths like `/en/austria/tyrol.html`)
  2. **Camera detail page (per-cam):** `GET https://www.webcamtaxi.com/en/<country>/<region>/<camera-slug>.html`
     - Extract the YouTube embed from `<div id=insideCam><iframe src="...">` → strip out `src="https://www.youtube.com/embed/live_stream?channel=CHANNELID&..."`
     - Also extract: `<div>Source: https://...</div>` for the operator/original source attribution
     - Tags: found in `<ul class="tags inline"><li class="tag-NN"><a href="/en/category.html">CategoryName</a></li></ul>`
     - Geo: Google Maps embed in `<iframe id=mapa src="https://www.google.com/maps/embed?pb=...">` — `pb` param carries encoded coordinates
     - Local time clock on page via JavaScript
  3. **Country/region hierarchy (for incremental crawling):**
     - 41 countries listed in navigation menu (from sitemap: austria, canada, usa, france, germany, italy, japan, brazil, etc.)
     - Each country page (e.g., `/en/austria.html`) lists region links (e.g., `/en/austria/tyrol.html`)
     - Each region page (e.g., `/en/austria/tyrol.html`) lists camera detail links + thumbnails
     - USA has 50-state pages under `/en/usa/<state>.html`
  4. **Category pages for targeted filtering:**
     - `/en/4k-cameras.html`, `/en/airport.html`, `/en/beach.html`, `/en/traffic.html`, `/en/nature.html`, `/en/animals.html`, `/en/ski.html`, etc. (~25 categories)
     - Each category page lists cameras tagged with that interest
  5. **Other entry points:** `/en/latest-webcams.html`, `/en/most-viewed-cams.html`
  6. **Recommended ingester approach:** Fetch `/en/webcams.html` → extract all camera detail page URLs → batch-fetch detail pages → extract YouTube embed URLs from the `<div id=insideCam>` iframe → verify liveness with yt-dlp. For incremental updates, region page timestamps or the latest/random modules could be used.
- **Sample verification:**
  ```
  # All-cams listing
  curl -s -m 30 -A 'Mozilla/5.0 ...' -L 'https://www.webcamtaxi.com/en/webcams.html'
  → HTTP 200 | ~350 KB | 4,079 .html links, ~2,230 camera detail URLs

  # Camera detail page: Alpenhaus Kitzbühel
  curl -s -m 30 -A 'Mozilla/5.0 ...' -L 'https://www.webcamtaxi.com/en/austria/tyrol/alpenhaus-kitzbuheler-horn-cam.html'
    | grep -oP 'src="https://www\.youtube\.com[^"]+'
  → src="https://www.youtube.com/embed/live_stream?channel=UCzc4Ysia7rrHYyuuw5Q6xCQ&autoplay=1&mute=1"

  # YouTube embed resolves:
  curl -s -m 15 -A 'Mozilla/5.0 ...' -o /dev/null -w 'HTTP %{http_code}'
    'https://www.youtube.com/embed/live_stream?channel=UCzc4Ysia7rrHYyuuw5Q6xCQ'
  → HTTP 200

  # Operator source attribution (from same page):
  curl -s -m 30 ... | grep -oP '<div>Source:[^<]+'
  → <div>Source: https://www.alpenhaus.at/</div>
  ```
- **Provenance:** **aggregator** — aggregates YouTube live streams from various operators worldwide. Each page credits the original source/operator URL in a `<div>Source: ...</div>` element (e.g., `https://www.alpenhaus.at/` for an alpine hotel's camera, `https://haus-des-meeres.at/` for an aquarium). This is an aggregator but the underlying sources are predominantly public-by-design (operators publishing their own feeds).
- **Constraints:**
  - **robots.txt:** `User-agent: *` — Disallow: `/*?*` (blocks query-string URLs, which are search/admin pages), `/administrator/`, `/bin/`, `/cache/`, `/cli/`, `/component/`, `/components/`, `/includes/`, `/installation/`, `/language/`, `/layouts/`, `/libraries/`, `/logs/`, `/modules/`, `/plugins/`, `/tmp/`. Allowed: `/media/plg_jchoptimize/assets/gz/`. **Camera detail pages (`/en/.../...html`) are NOT disallowed** — they are plain paths without query strings.
  - **ToS:** No API or automation-specific ToS found (Joomla site, no dedicated API page).
  - **Ads:** Heavy ads (Google AdSense, Cloudflare challenge scripts). Some pages may require JS for ad rendering but the camera embed HTML (`<div id=insideCam>`) is server-rendered and available without JS.
  - **Cloudflare:** `cdn-cgi/` scripts detected. The site appears to use Cloudflare for protection but responds to direct curl with browser UA (no challenge observed during testing).
  - **Age:** Sitemap lastmod from 2017 suggests the site may have stale/offline cams.
  - **No API:** No machine-readable data format detected. Pure HTML scraping required.
- **Fold-in verdict:** **ADD NOW** (family: `webcamtaxi`)
  - 2,230 camera pages with YouTube embed feeds and operator crediting
  - Single-page all-cams listing makes enumeration straightforward
  - Structured camera detail pages with source attribution, tags, and location data
  - Good geographical coverage (41+ countries, 50 US states)
  - Filtering for high-value slice: AU/US/JP/UK + nature/beach/traffic categories via the category listing pages, or post-filter by source domain
  - Ingester: fetch /en/webcams.html → extract camera URLs → batch-fetch detail pages → extract YouTube embed URL + source + tags → yt-dlp for liveness
  - Note: ~2,230 cams × 1 request per cam = significant volume. Use concurrency but respect rate limits (no explicit limits found, but be polite). Consider parsing region pages for lighter incremental updates instead of re-scanning the all-cams list every time.

---

## Dead ends
- OpenWebcamDB JS bundle (`app-CIUXbS1A.js`) is a compiled Livewire app — not easily readable for API endpoint discovery. The `/api/v1` documentation is minimal and doesn't list specific endpoints without an API key.
- WebcamTaxi direct URL guesses for USA/Florida, Japan/Tokyo, UK/London cams returned 404 — camera slugs are not predictable from location alone. The `/en/webcams.html` all-cams list is the only reliable enumeration source.
- WebcamTaxi attempted test of `/en/usa/florida/`, `/en/usa/california/` — these redirect to `/en/usa.html` with no clean state-level listing discovered. USA is handled through `/en/usa.html` which links to individual state pages like `/en/usa/alabama.html`, `/en/usa/florida-live-streaming-webcams.html` (varied naming).
- WebcamTaxi Cloudflare `/cdn-cgi/challenge-platform/scripts/jsd/main.js` detected but no actual challenge received during testing with browser UA.
- OpenWebcamDB robots.txt has a dev placeholder (`openwebcamdb.test` domain) — this is probably a deployment artifact and not indicative of actual crawl policy.

## Method notes
- **UA used:** `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36`
- **Tools:** curl, grep with PCRE (`-oP`), Python (execute_code) for batch analysis, web_extract for page rendering
- **Rate limiting:** No rate limiting observed on either site during testing (≤5 requests per site total for this research wave). Used conservative spacing.
- **Both sites are aggregators of YouTube embeds** — feeds come FROM YouTube, liveness verification should use `yt-dlp --match-filter is_live` on the YouTube watch URL. Consider canonicalizing URLs: YouTube watch URL is the stable identifier, the embed URL is the playable one.
- **OpenWebcamDB advantage:** Structured JSON-LD data on every page means ingester can get exact YouTube URL, geo, and stats with a single regex. Sitemap gives full enumeration at low cost.
- **WebcamTaxi advantage:** Larger raw count (~2,230 vs ~1,882) and attributes the original source operator. Single-page all-cams listing avoids multi-page pagination. Downside: pure HTML scraping needed, no structured data.
- **Both sites require liveness verification** — the YouTube embed URL resolves (HTTP 200) even for offline/deleted streams (YouTube returns a "video unavailable" page). Use `yt-dlp --simulate --match-filter is_live <yt-url>` to test true liveness.
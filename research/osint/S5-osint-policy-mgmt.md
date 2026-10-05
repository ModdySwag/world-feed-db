# S5 — OSINT/scanner layer, legal/ethical boundary, management-surface precedents

**Program:** worldwide, updateable, self-healing DB + viewer of PUBLIC live video feeds (owner: Moddy)
**Scope of this wave:** OSINT/scanner projects, discovery-service options (Shodan/Censys/ZoomEye/FOFA), policy decision inputs, management-surface precedents.
**Date:** 2026-10-05 (ACST). **Method:** repo files fetched via `gh` API (READMEs, source, trees, blob previews); docs extracted where reachable; no accounts created, no scans run, no devices probed. Numbers re-verified where possible (noted inline); anything not verified is marked `(verify)`.
**Policy line carried in (hard):** legitimate, public-by-design sources only. Insecam-style "exposed private camera" aggregation is DOCUMENTED here as a category with mechanics/scale/risks — it is NOT scraped, NOT probed, NOT recommended.
**Section A: 18 entries.** Section B: 6 policy decisions. Section C: 10 precedents + proposed mechanism.

---

## (A) ENTRIES

### 1 · scan-for-webcams (JettChenT) — deep dive
- https://github.com/JettChenT/scan-for-webcams
- Files read: `sfw/cams.json`, `sfw/search.py`, `sfw/cam.py`, `sfw/rtsp.py`, `sfw/rtsp_dict/tries.txt`, `sfw/places_mod.py`, README (274★, MIT, last push 2023-10-29).

**KEY FACTS:**
- **What it finds / how:** Shodan-backed presets in `sfw/cams.json`: `webcamXP` (`product:webcamXP`, capture `{url}/cam_1.jpg`), `MJPG` (Streamer; snapshot `{url}/?action=snapshot`, stream `{url}/?action=stream`), `yawCam` (`Server: yawcam Mime-Type: text/html`, capture `{url}/out.jpg`), `hipcam` (`hash:1842228279`, stream `{url}/11`), and `rtsp` (`"RTSP" screenshot.label:webcam has_screenshot:1 -screenshot.label:blank`).
- `Scanner.scan()` runs `shodan.Shodan(key).search(query)`, filters matches by `camera_type` in the banner, then per match: `check_accessible` (HTTP 200 on base URL) → snapshot `requests.get(...); Image.open` → **blank-frame check** `check_empty()` (PIL `getextrema`, tolerance 5; uniform frames skipped) → GeoIP (geo.ipify.org: country, region, local time) → tag via Clarifai concepts (cloud) or **local Places365** → optional vLLM (`llava 7b` via llama.cpp) natural-language captions. Threaded parallel; `--gui` grid wall; `sfw play {url}` (cv2 GUI for RTSP).
- **Places365 classification (from `sfw/places_mod.py`):** WideResNet18 (`resnet18(num_classes=365)`) fine-tuned on Places365, weights pulled from `places2.csail.mit.edu`; outputs top-5 **scene categories** (365 classes), indoor/outdoor vote, top-9 **scene attributes** — fully on-device (torch). This is the reusable classifier shape.
- **RTSP Shodan enumeration (README labels it "DANGER"):** `sfw/rtsp.py` `attack()` iterates **`sfw/rtsp_dict/tries.txt` — 193 non-empty common vendor stream paths** (e.g. Axis `axis-media/media.amp`; Hikvision `Streaming/Channels/1`, `Streaming/Unicast/channels/101`; Dahua `cam/realmonitor?channel=1&subtype=0`; generic `live/ch0`, `h264`, `mjpeg`, `video1`; a few templates contain `user=admin&password=…` placeholders), builds `rtsp://ip:port/<path>`, and tests each with `cv2.VideoCapture().isOpened()` until one opens. **No credential brute-force in code**, but it *does* contact and enumerate third-party devices after a Shodan hit.
- **What data you'd get:** ip:port, snapshot/stream URL, geo + local time, scene tags/attributes/captions, blank-frame flag — i.e. a *verification + classification layer over Shodan hits*.

**License/ToS:** MIT (code). Pulls API data from Shodan/Clarifai/geo.ipify — each has its own ToS.
**Risk/legal:** the search half is licensed API use; the second half (direct per-device HTTP + RTSP path enumeration on Shodan hits) is exactly what our policy line excludes — reachable ≠ authorized (CFAA §1030 / AU Criminal Code s 478.1 / EU 2013/40 Art. 3 all key off authorization/security measures, not reachability).
**VERDICT: REFERENCE — adopt the classification/QA pipeline shape (blank detection → Places365-style scene tagging → geo → viewer grid); SKIP device contact and RTSP enumeration entirely.** Build component: **ingest classifier & health-QA module** (not the scanner).

### 2 · seeallthethings (baywolf88) — OSINT webcam mapping methodology
- https://github.com/baywolf88/seeallthethings (119★, **no license**, last push 2018-01-30)
- Files read: README; tree; blob heads of `South Carolina` (88 KB) and `DC Area` (424 KB).

**KEY FACTS:** Explicit methodology: bulk of feeds from **state DOT traffic feeds** ("SCDOT Feed… requires m3u8/rtmp player"), plus "google site searches of insecam.org by state", plus travel/tourism sites. Data files are plain text with sections: `Shodan Search Queries` (e.g. `has_screenshot:true product:"D-Link/Airlink IP webcam http config" state:"SC"`, `product:"hipcam"`), `Google Dorks (Cam Sites)` (`site:insecam.org South Carolina`, `site:ip-24.net`, `site:opentopia.com`), then per-camera entries: coordinates, TMC/name, stream URL (SCDOT m3u8/rtmp), agency, city. Goal: "gather video feeds in all 50 states and aggregate into a searchable interactive directory."
**What data you'd get:** per-state curated catalogue mixing DOT feeds with exposure-aggregator links; usable field model (name/title, coords, stream URL, agency, city).
**License/ToS:** none — can't reuse code/data; treat as reference only.
**Risk/legal:** entries derived via insecam/opentopia site searches = exposed-camera aggregation; not to be re-scraped.
**VERDICT: REFERENCE — copy the *field model* + DOT-first sourcing, drop the insecam-derived entries.** Build component: **catalogue schema + curation workflow** (name, coords, stream URL, agency, city, local time).

### 3 · 2l7b/public-camera-indexing-insights — Google-dork corpus
- https://github.com/2l7b/public-camera-indexing-insights (7★, MIT, created 2025-10-03) — "resource for identifying internet exposed webcams using Google Dorking techniques to promote privacy and defensive security awareness."

**KEY FACTS:** ~140 camera Google-dorks (classic AXIS/NetCam/webcamXP/yawcam/DVR era corpus), e.g. `inurl:view/view.shtml`, `inurl:axis-cgi/jpg`, `intitle:"webcam 7" inurl:8081`, `intext:"powered by webcamXP 5"`, `intitle:i-Catcher Console Web Monitor`, Mobotix/Sony/EverFocus/Edr1680 patterns; plus a "shodan" section listing search-term names (DCS-5220 IP camera, Foscam old Web UI, webcamxp, IQeye, Netwave, Hikvision…). Corpus is awareness-oriented (privacy/defensive framing).
**What data you'd get:** candidate-URL *patterns* per vendor class — finds cams not in directories.
**License/ToS:** MIT (repo). Google dorking is bound by search-engine ToS/rate limits.
**Risk/legal:** the surfaced URLs point at devices; running this as a discovery pipeline means contacting/aggregating exposed private cams → excluded.
**VERDICT: REFERENCE (documented corpus only) — keep as a pattern checklist for identifying operator-published webcam *pages* (tourism/operator sites) and as an anti-patterns list; never automate against devices.** Build component: **docs/reference only** (no pipeline). If ever used, manual + rate-limited + allowlist.

### 4 · CamXploit (spyboy-productions)
- https://github.com/spyboy-productions/CamXploit (1,178★, **AGPL-3.0**, last push 2026-01-06)

**KEY FACTS:** active recon tool v2.0.2: scans common CCTV ports incl. alt ports (81-89, 1024-1030), RTSP detection on non-standard ports (443, 8000), service-name identification, login-page detection, brand detection (Hikvision/Dahua/Axis/Sony/Bosch/Samsung/Panasonic/Vivotek/CP Plus), **RTSP/HTTP credential testing with "100+ default credentials"**, ONVIF support, multipart-stream detection; ships a Colab notebook; supplies manual search links (Shodan/Censys/ZoomEye/dorks).
**What data you'd get (for an authorized target):** open ports/services, candidate brand, whether default creds work — intrusion-adjacent output.
**License/ToS:** AGPL-3.0. Tool's own terms: "strictly on systems you own or have explicit authorization to test."
**Risk/legal:** credential testing against third-party devices is squarely unauthorized-access territory (CFAA / s 478.1 / Directive 2013/40 Art. 3), regardless of "non-intrusive" framing.
**VERDICT: SKIP — excluded by the policy line; retained only as evidence of ecosystem mechanics.** Build component: **none** (use as a test case for the ingest gate: credential-bearing sources must be rejected).

### 5 · Project Eyes On (Y0oshi)
- https://github.com/Y0oshi/Project-Eyes-On (244★, MIT, last push 2026-08-26)

**KEY FACTS:** "unified intelligence tool for mass IP camera scanning" (v4): two engines — (1) **web dorking** across Yahoo/Bing/Mojeek/DuckDuckGo with per-engine pacing/cooldowns ("anti rate-limiting"), (2) **Insecam directory scraper** (country code + pages); plus path probing for JS-hidden streams, GeoIP (city/country), dedupe stripping cache-busters, live verification of stream type (MJPEG/JPEG/Video), JSON/CSV/HTML export, arrow-key TUI. Topics include `insecam`.
**What data you'd get:** mass candidate lists with geo + stream-type verification.
**License/ToS:** MIT (repo). Scraping Insecam/engines is ToS-hostile and the output is an exposed-camera list.
**Risk/legal:** Insecam scraping + mass harvesting/verification = the excluded category; "educational/auditing" disclaimer does not change third-party effects.
**VERDICT: SKIP for any pipeline. REFERENCE for two *concepts*: polite search-engine pacing, and stream-type verification.** Build component: **stream-type detection concept** (used only on sources that passed the publish-signal gate).

### 6 · Pantheon (josh0xA)
- https://github.com/josh0xA/Pantheon (190★; README claims MIT, **no license file detected on GitHub — (verify)**; last push 2024-07-30)

**KEY FACTS:** GUI (Python) app: an "API crawler" over camera directory APIs — README: original Insecam scraping was replaced because "Google TOS kept getting in the way"; country lists + integrated live-feed for "non-protected cameras"; per-IP geolocation on a map; HTTP-data viewer; login-page results flagged "**Do NOT attempt to login**".
**What data you'd get:** IP:port lists per country with geo + quick live view.
**License/ToS:** README says MIT; GitHub license detection = none (flag).
**Risk/legal:** the author's own pivot (scrape → API) + the login warning acknowledge the line; viewing reachable third-party cams is still legally risky.
**VERDICT: REFERENCE (UI concepts: map + list + detail pane + explicit login-page warnings); SKIP feed sourcing.** Build component: **viewer/UI pattern** only.

### 7 · kamerka (woj-ciech) — v2/FIST, archived
- https://github.com/woj-ciech/kamerka (1,265★, **no license**, archived; last push 2020-06-28)

**KEY FACTS:** builds an interactive map of cameras/printers/ICS from Shodan by lat/lon/radius or country; modules `--camera/--rtsp/--mqtt`; **recursive mode "check each host for open ports and more information"**; Elasticsearch output; requires **paid Shodan**; "Do not test on devices you don't own."
**What data you'd get:** geospatial exposure maps of cameras + ICS by area.
**License/ToS:** none (archived) — no reuse.
**Risk/legal:** direct host checks + ICS context; excluded for our pipeline.
**VERDICT: REFERENCE — early precedent for geo-centric camera mapping; do not run.** Build component: none (pattern precedent only).

### 8 · Kamerka-GUI (woj-ciech)
- https://github.com/woj-ciech/Kamerka-GUI (871★, MIT, last push 2026-06-07)

**KEY FACTS:** Django + Celery dashboard over Shodan for ICS/IoT/medical/**camera categories**; country or coordinate searches; stores searches/devices in a local DB; **Search History, dashboards & statistics, Favorites, screenshot Gallery (with country filter), clustered Map, per-search results, per-device Locate/Intel/Exploit tabs**; **"Filter Honeypots" toggle** in device tables; device "Indicator" field derived from parsed banners/protocol responses/**screenshot labels**; global search over discovered devices; keys.json (shodan, google_maps, whoisxmlapi); ships **exploit helpers** (Hikvision, Amcrest unauthenticated A/V, etc.) explicitly "controlled validation only."
**What data you'd get:** a working analyst UX over exposure data (search history, favorites, honeypot filtering, indicator fields, gallery, maps).
**License/ToS:** MIT (repo); Shodan/Google/Whois ToS apply.
**Risk/legal:** exploit helpers are dangerous and excluded; screenshots of third-party devices remain third-party imagery.
**VERDICT: REFERENCE — mine the *management surface patterns* for our admin UI (history, favorites, filters, indicator provenance, gallery, per-source stats), exclude the scan/exploit halves.** Build component: **admin/search UX patterns + indicator-field concept**.

### 9 · webcamX (x64vbhv)
- https://github.com/x64vbhv/webcamX (10★, GPL-3.0, last push 2022-12-27; **no README** — code-only)

**KEY FACTS:** ~120-line script: fetches `http://www.insecam.org/en/bycountry/{CC}` across a hard-coded list of **140+ country codes**; pagination via regex `pagenavigator("?page=", N)`; extracts `div.thumbnail-item__preview` img `src` values → prints direct image URLs; self-updates from the upstream `EvilGeek/WebcamX` repo.
**What data you'd get:** direct Insecam image links by country.
**License/ToS:** GPL-3.0 (code); scraping Insecam has no sanctioned ToS basis.
**Risk/legal:** insecam scraping + exposure aggregation = excluded category.
**VERDICT: SKIP — retained as evidence of the category's mechanics (country pagination + thumbnail extraction) and of how trivially it's done (why the gate matters).** Build component: none.

### 10 · totalynothackedijokeyounot (justrandomwebcams) — 17K insecam-sourced dump
- https://github.com/justrandomwebcams/totalynothackedijokeyounot (6★, **no license**, created/pushed 2019-03-01)
- Verified by download: `190221dump_alphabetical.csv` = **17,399 rows (17,398 cameras + header)**; columns `ip:port`, `country`, `city`, `image feed link`; sample rows show MJPEG/cgi snapshot URLs, some with **credentials embedded** (`.../cgi-bin/snapshot.cgi?chn=0&u=admin&p=…`). README repeats Insecam's claim: "This site contains no hacked webcams, all of them just freely acceptable from all of the internet" (**claim unverified by us**).

**What data you'd get:** a static ~17K target list with geo.
**License/ToS:** none; no ToS to respect, but also **no permission and no license** → not redistributable.
**Risk/legal:** canonical example of an "already-public list" that still fails a publish-signal gate; credential-bearing URLs make it actively harmful to republish; stale since 2019.
**VERDICT: SKIP — default-exclude.** Build component: **test fixture for the ingest gate** (must reject URL-embedded credentials and aggregator provenance).

### 11 · ch-bas/cctv-camera-database — camera spec DB (reference)
- https://github.com/ch-bas/cctv-camera-database (276★; repo license detected as NOASSERTION, **README asserts the dataset is CC0 "and always will be"**; last push 2026-10-01)

**KEY FACTS:** 28,400 camera models / 230 brands as committed JSON + CSV (no key, no rate limit); static JSON API (`/api/brands.json`, `/api/cameras/{id}.json`); per-camera schema includes `protocols` (`onvif`, `rtsp`), resolution, night vision, PoE, IP/IK ratings, `sources[]` + `last_verified`; **`data/rtsp-patterns.json` = CC0 brand-level RTSP URL reference: 203 brands / 143 verified / 60 unverified / 422 stream templates, "confirmed against the manufacturer's own documentation — never copied from aggregators"**; Frigate/Home Assistant configs for 22,196 models; weekly dead-link checker; QA tooling.
**What data you'd get:** a vendor-doc-derived RTSP/spec taxonomy — the right way to recognize and validate camera endpoints *by pattern* without touching a device.
**License/ToS:** CC0 (dataset, per README) — low risk; attributions included in records.
**Risk/legal:** negligible (no feeds, no IPs of devices); code license needs a closer pass if we vendor any scripts (verify).
**VERDICT: ADOPT (as reference data).** Build component: **camera taxonomy + RTSP pattern reference + ingestion validator** (stream-type detection by pattern).

### 12 · Purdue CAM2 (Continuous Analysis of Many CAMeras)
- https://www.cam2project.net/ + https://github.com/PurdueCAM2Project (reachable; org 37 repos)

**KEY FACTS:** academic system (Purdue HELPS lab, NSF grant ACI-1535108; "Big Visual Data" origin): **discovered public cameras from consolidated sites** (e.g. DOT sites), extracted metadata (location, **orientation**, indoors/outdoors, frame size/rate), mapped them; camera count exceeded **50,000** at one point (history page). Current state: `CAM2API-Obsolete` ("Home of the Purdue CAM2 Camera Database API"), `CAM2RetrieveData` README: "**This repository is obsolete. DO NOT USE IT.**", `CameraDatabaseClient` last active 2023; site now serves CM2WebUI docs. Research themes included "Camera Discovery + **Reliability**" and an image database with object-detection indexing.
**What data you'd get (historically):** largest academic public-camera catalogue + orientation metadata + reliability research; **API obsolete**; do not depend on it.
**License/ToS:** mostly no license (some Apache-2.0/MIT); research use.
**Risk/legal:** a public-camera research precedent; no live service to consume.
**VERDICT: REFERENCE — concept carrier: orientation metadata, reliability scoring, "discover from consolidated sites" pattern.** Build component: **reliability-scoring + orientation metadata design inputs** (no code).

### 13 · Shodan — discovery service (search syntax for cams, free tier, API)
- Docs: https://help.shodan.io/the-basics/search-query-fundamentals · https://help.shodan.io/the-basics/credit-types-explained · https://developer.shodan.io/pricing · https://datapedia.shodan.io/property/screenshot.html · https://www.shodan.io/search/advanced

**KEY FACTS:**
- **Syntax:** filters `filtername:value` (no space; quotes for multi-word, e.g. `country:SG`, `org:"SingTel Mobile"`); default search is banner text. **Screenshot filters:** `has_screenshot:true`, `screenshot.label:<ML label>` (image classified by ML), `screenshot.hash:<n>`, plus OCR text (`screenshot.text`); datapedia documents the screenshot property (base64 data, hash, labels, mime, OCR text).
- **Camera-shaped queries witnessed in the wild (from sfw cams.json):** `product:webcamXP`; `Server: yawcam Mime-Type: text/html`; `"RTSP" screenshot.label:webcam has_screenshot:1 -screenshot.label:blank`; `hash:1842228279` (hipcam).
- **API/credits:** `/shodan/host/search` consumes 1 query credit if a filter is used **or** page ≥2 is requested; 1 credit = up to 100 results; `/shodan/host/count` consumes **no** query credits. **Free API plan exists on signup** ("All Shodan accounts come with a free API plan" — pricing FAQ); **Membership $49 one-time = 100 query credits/mo**, 100 scan credits, filters except `vuln`/`tag`, 20 search pages. API plans: Freelancer $69/mo (10k credits, ~1M results), Small Business $359/mo, Corporate $1099/mo; **rate limit 1 request/second stated for API plans**. Scan credits = 1 IP scanned each (active scanning API is paid-plan only).
**What data you'd get:** banner-level service data, screenshots + ML labels, OCR text, geo/org/ports — candidate streams at internet scale.
**License/ToS:** API ToS + credit metering; respect rate limits; data licensing constraints for redistribution **(verify for commercial display)**, attribute Shodan where required.
**Risk/legal:** searching is fine; **acting on hits by contacting devices is where we stop.** Never use the scan API against third-party hosts; treat every hit as a candidate requiring a publish signal before it enters the catalogue.
**VERDICT: ADOPT (search/read only, metered + cached) — primary discovery source, wrapped in the policy gate.** Build component: **discovery connector (query allowlist, credit budget, cache, policy gate)**; use `screenshot.label:webcam`/`has_screenshot` + product fingerprints to find candidates, and `country:`/`port:` facets for triage.

### 14 · Censys — discovery service
- Docs: https://docs.censys.com/docs/censys-query-language · https://docs.censys.com/docs/platform-quickstart-guide · transition guides for free tier

**KEY FACTS:** current = **Censys Platform** with **CenQL**: field-value queries with datasets `host.` / `web.` / `cert.` (e.g. `host.location.city="Ann Arbor"`, `host.services.port=8880 and host.services.protocol=HTTP`); operators `:` (contains), `=` (exact), `=~` regex, comparisons, `not`; query validator; legacy syntax → converter. **Free tier: "Free tier users will have a balance of 100 credits in the new Platform"** (Credit Management); Free = "basic internet visibility, access to basic protocols and certificates, and limited web property data such as root endpoints"; some Platform API endpoints (asset lookup) usable by Censys Free, others Starter/Search/Core only; unauthenticated users get a smaller action set + limited data.
**What data you'd get:** host/service banners (RTSP/HTTP), web-property data (banners, titles, bodies), certificates — camera-candidate detection via service fields.
**License/ToS:** tier limits + API ToS; PAT for Platform API.
**Risk/legal:** reading is fine; same "no acting on hits" rule; 100-credit cap bounds automation.
**VERDICT: REFERENCE/ADOPT-as-secondary — useful for protocol/service queries with a hard credit budget (Free tier = pilot only).** Build component: **optional discovery connector, tier-limited**; don't put it on the critical path.

### 15 · ZoomEye — discovery service
- https://www.zoomeye.ai/doc (API v2) + https://www.zoomeye.ai/help + https://github.com/zoomeye-ai/mcp_zoomeye

**KEY FACTS:** API v2: `POST https://api.zoomeye.ai/v2/search` with `API-KEY` header; required `qbase64` (base64-encoded query string); params `fields`, `sub_type` (v4/v6/web), `page`, `pagesize` (**docs say max 10,000; the official MCP README says max 1,000 — flag**), `facets` (country, subdivisions, city, product, service, **device**, OS, port), `ignore_cache` (Business plan+). SDK example `zm.search('country=cn')`; syntax is case-insensitive with quoted strings, `==` for strict exact match. Account is **points-based** (`/v2/userinfo` returns subscription + current points). Promo: 7-day free MCP trial. Pricing page is JS-rendered — **free-tier quota numbers (verify)**.
**What data you'd get:** IPv4/IPv6/web assets with product/device/service facets — `device:` facet is directly useful for camera classification.
**License/ToS:** API key required; quota/points; rate limits by plan.
**Risk/legal:** same rule — search only, never probe; points/quota bound usage.
**VERDICT: REFERENCE (key-required, points model; free-tier limits unverified) — stub connector with quota guard; adopt only if Shodan/Censys leave coverage gaps.** Build component: **optional connector stub**.

### 16 · FOFA — discovery service
- https://en.fofa.info/api · https://en.fofa.info/vip · https://github.com/FofaInfo/GoFOFA (USER_GUIDE.md)

**KEY FACTS:** API is account-based (**email + key**, e.g. `https://fofa.info/?email=&key=&version=v1`); queries are **qbase64**-encoded; default return fields `ip,port`; `size` max **10,000** per query; `deductMode` selects f-points vs free quota ("uses free quota by default"); **F Points are FOFA's virtual currency** for querying/downloading. VIP page (via search snapshot; page is JS-rendered — mark): plans quoted with **query credits 10,000 / 80,000 / 900,000 per month** (entry plan snippet shows $25/mo) and "FOFA AI+ Free trial: 5 / 10 / 50 uses per day" across tiers. Camera-style dorks (`app="webcamXP"`, product/title/body queries) are its idiom.
**What data you'd get:** Shodan/Censys-like IPv4 asset banners with strong IoT fingerprints.
**License/ToS:** API key required beyond tiny free quota; ToS + quota.
**Risk/legal:** search-only use; quota constraints; free quota exact numbers **(verify)**.
**VERDICT: REFERENCE — late-stage optional connector; not on the critical path (key-gated, quota-limited).** Build component: **optional connector (later)**.

### 17 · Insecam — the excluded category (dossier only, NOT scraped, NOT probed)
- Referenced via: webcamX (#9), Project Eyes On (#5), Pantheon (#6), seeallthethings (#2), jrw dump (#10). No direct access made.

**KEY FACTS (documented from secondary sources only):** insecam.org is the best-known aggregator of openly reachable camera streams; dumps of it exist (jrw: **17,398 cams, dated 2019-02-21**, verified by us); tools scrape it by country with trivial pagination (webcamX: 140+ country codes); observed corpus properties: MJPEG/JPEG snapshot URLs, geo grouping by country/city, **some dumped URLs carry embedded credentials**. Related aggregator names seen in methodology files: `ip-24.net`, `opentopia.com`. Insecam's own claim "no hacked webcams… freely accessible" is repeated by third parties and **unverified by us**.
**Scale:** tens of thousands of endpoints per dump (17K in 2019); multiple such sites form a whole category.
**Risk/legal:** this is the boundary our policy line draws: reachable-without-credentials ≠ published-for-the-public; scraping/probing/re-publishing exposes third-party devices and some entries are credential-bearing.
**VERDICT: DOCUMENT ONLY — default-exclude; zero build component.** Used in (B) as the excluded-category test case for the ingest gate.

### 18 · opencctv.org — public-by-design aggregator (positive precedent)
- https://opencctv.org/ · https://opencctv.org/how-we-source · https://opencctv.org/about

**KEY FACTS:** "world's largest public camera network" directory; site states **160,703 live streams / 169 countries** (counts vary by page: 146,681 / 159 countries on another — cite as the site's own, moving numbers). Sourcing page: **"460+ registered sources"** — US state DOTs, Canadian provincial road authorities, European highway operators, Asian traffic systems, national weather/meteorological services, port authorities, national parks, ski resorts, observatories, space agencies (GOES, Himawari, EUMETSAT, NASA). Explicit policy: **"We do not scrape private cameras, and we do not host or operate cameras of our own — we link to and embed feeds their operators already make public."** Continuous ingestion, duplicate detection/normalization, coordinate validation, and lifecycle: **"Cameras are never silently deleted — they are deactivated when they go dark and restored."** Type taxonomy visible: traffic & highway 93,215; ski 8,832; weather 6,099; nature & wildlife 5,749; aviation 4,279; airport 2,378; beach & coast 2,186; port & harbor 1,165.
**What data you'd get:** a ready-made public-by-design catalogue model (and a candidate cross-check source).
**License/ToS:** site terms for scraping/embedding not assessed **(verify before consuming)**; their source-registry + attribution chain is the model to copy.
**Risk/legal:** low relative risk (operator-published feeds), subject to their terms and per-source attribution.
**VERDICT: ADOPT as the reference model (and evaluate as a pilot discovery source, honoring their terms).** Build component: **source registry pattern, deactivate/restore lifecycle, attribution chain, camera-type taxonomy**.

---

## (B) POLICY DECISION INPUTS

**D1 — Exposed-camera corpora: include or exclude?**
Options: (a) exclude entirely from the product (default); (b) include as a metadata-only "exposure registry" (no feeds, no probing); (c) include feeds. Evidence: dumps like jrw (#10) contain credential-bearing URLs; tools like CamXploit (#4)/Eyes-On (#5) show the ecosystem norm is credential testing + mass scraping; our hard policy line already draws the boundary at Insecam-style aggregation (#17).
**Recommendation: (a) exclude by default** — keep them out of the catalogue schema entirely; owner may keep the dossier evidence. **Build impact:** ingest gate requires a `publish_signal` (operator page / source API / gov open-data / opt-in) recorded per camera; `provenance_class` enum (`public_by_design | exposure_aggregator | unknown`) — only `public_by_design` may be `active`; URL linter rejects credential-bearing URLs (`user:pass@`, `u=admin`, `password=` params).

**D2 — "Already-public lists" (e.g. the 17K insecam dump): do they count as public?**
Options: (a) treat as excluded like any exposure corpus; (b) allow into a separate research-only store (never joined to the viewer, never probed); (c) allow into the product. Evidence: #10 — no license, no consent, stale since 2019, some URLs credential-bearing; "already published elsewhere" ≠ "published for the public".
**Recommendation: (a)/(b) — never in the product DB; at most a physically separate `exposure_research` store used for awareness reporting, never probed, never shown with feed URLs.** **Build impact:** two-schema separation with hard isolation (no FK join path to the live catalogue); automated rejection stated in CI.

**D3 — Machine-behavior rules for the crawler (rate limits, robots.txt, ToS).**
Proposed rules: one bounded request per candidate at add-time (no retries storm; exponential backoff on 429/5xx; honor `Retry-After`); per-host floor ≥60 s between stills; single stream connection at a time per camera, capped concurrency globally; cache + ETag; robots.txt honored for HTML directory/sitemap scraping (not meaningful for camera endpoints, so HTML-side rules govern discovery crawling); per-source ToS reviewed and snapshotted (`terms_snapshot`, reviewer, date) before enabling a connector; UA identifies the project with a contact URL; **structurally no code path that authenticates to a device, brute-forces, or port-scans** (CamForge's `policy.ts` precedent shows this can be enforced in code); never contact non-listed hosts.
**Recommendation: adopt as a written Fetch Policy module + per-source budgets + audit log; it is cheaper to enforce in code than in prose.** **Build impact:** policy engine (budgets, backoff, robots cache), ToS registry per source, CI test that fails if probing/auth code paths appear.

**D4 — Attribution obligations.**
**Recommendation: mandatory at ingest — every camera carries `attribution.text`, `attribution.url` (operator/official page), `source_id`, and `license/terms`; viewer and API must display them (`source_url` field for citation, following the LiveTrafficCam MCP precedent #C9); where a source allows linking but not embedding, fall back to link-out only (livetrafficcam-homeassistant precedent #C6).** **Build impact:** schema fields + API `source_url` + UI attribution line + a per-source `display_policy` (`embed | link_only | metadata_only`).

**D5 — Jurisdiction notes (one line each; counsel review recommended before launch).**
- **US (CFAA, 18 U.S.C. § 1030):** accessing a "protected computer" without authorization is an offence; DOJ charging policy (JM 9-48.000) says ToS violations alone don't create "exceeds authorized access" liability, but **circumventing a security measure to reach a camera does** — so the rule is: never bypass auth, never touch cams with a security measure. [justice.gov/jm/jm-9-48000-computer-fraud]
- **Australia (Criminal Code Act 1995 (Cth) s 478.1):** unauthorised access to, or modification of, "restricted data" (data protected by an access-control system) — up to 2 years; applies to conduct in Australia. [legislation.gov.au; cdpp.gov.au/cybercrime]
- **EU (Directive 2013/40/EU Art. 3):** criminalises intentional access "without right… where committed by infringing a security measure"; plus **GDPR** applies to personal data in frames (faces/plates) regardless of the feed being public. [eur-lex.europa.eu]
**Recommendation: catalog only security-measure-free, operator-published feeds; adopt detection-not-recognition for any vision processing (no face recognition, no LPR, don't persist third-party imagery beyond ephemeral thumbnails — CamForge precedent).** **Build impact:** vision policy config + no-persistence defaults + audio strip.

**D6 — Opt-out / takedown and auto-retire.**
**Recommendation: implement a published removal contact + `takedown` workflow (permanent removal + tombstone so it can't be re-ingested; audit log), and auto-lifecycle: `quarantined` after N consecutive failed checks (suggest 10 over ~24h — tune with owner), `retired` after sustained death, restore-on-recovery (OpenCCTV's "deactivated, not deleted" model #18).** **Build impact:** lifecycle states (`active/quarantined/retired/removed`), health checker with consecutive-failure counter, tombstone table, public "remove this camera" endpoint.

---

## (C) MANAGEMENT SURFACE — precedents and a proposed mechanism

**Precedents: how camera NVR/platform products add / remove / enable / disable sources**

**C1 · Frigate** (https://docs.frigate.video/configuration/cameras) — cameras added **in the YAML config** under `cameras:` with `ffmpeg.inputs` + roles (`detect/record/audio`); no camera-add UI; a camera is **disabled with `enabled: False`** ("will not appear in the Frigate UI and will not consume system resources"); PTZ via per-camera `onvif:` block (host/port/user/password); extra cameras = extra YAML entries. *Lesson: config-as-source-of-truth; an explicit enable/disable flag with resource semantics.*

**C2 · ZoneMinder** (https://zoneminder.readthedocs.io/en/stable/userguide/definemonitor.html + subpages `definemonitor_add/general/source`) — **web Console `+ADD`**; also `SCAN NETWORK`, **Monitor Probe**, **ONVIF Probe**, and **Presets** fill partial config; Source Types: FFmpeg / Remote / Local / File / **Web Site** / VNC; **Capturing: None / On Demand / Always** and Decoding modes give true pause/resume semantics; Monitors can be in **Groups** for scoped views. *Lesson: rich add-by-probe wizard, capture modes as first-class states, grouping for browsing.*

**C3 · Shinobi** (https://docs.shinobi.video/) — web UI, "**Shinobi can scan your network and find your cameras for you**"; per-camera record modes/schedules; live view in browser. (Monitor add/remove dialog specifics were unreachable in our fetch — **(verify)**.) *Lesson: network discovery as the add-flow front door.*

**C4 · iSpy / Agent DVR** (https://www.ispyconnect.com/docs/agent/adding-cameras, /video-source-types, /server-settings) — "New Device" under Server/Devices; **Network Camera Wizard**; ONVIF option; auto-discover local devices; after selecting an address it **scans for video endpoints and offers a pick list ("Use")**; per-device Live/Record URLs with override; server-level **ONVIF Discovery toggle** and NDI groups; rescan button. *Lesson: discovery → endpoint pick-list → confirm; discovery itself can be toggled.*

**C5 · Home Assistant — Generic Camera** (https://www.home-assistant.io/integrations/generic/) — **Settings > Devices & services > Add Integration > Generic Camera** (UI config flow); requires Still Image URL and/or Stream Source URL (templates allowed, credentials allowed in URL or separate fields); validation at config time; camera served via proxy endpoint `/api/camera_proxy/camera.[name]`. Entity-level enable/disable comes from HA's entity registry. *Lesson: config-flow add + entity lifecycle + own the proxy (never expose raw upstream).*

**C6 · livetrafficcam-homeassistant** (https://github.com/bzsasson/livetrafficcam-homeassistant, HACS integration) — **one config entry per "place"** (state → place → pick ≤25 cameras for highways; passes/bridges/tunnels/airports bring all); each camera = a `camera.*` entity with `live_status`, `last_live_at`, `route`, `official_url`, agency attribution, plus a **"verified live" binary sensor per camera** ("use it to hide stale cameras"); stale entries read `unavailable`, **not off**; **cameras whose agency only allows linking appear as a URL sensor, never as an image**; refresh budgets: stills ≤1/min, data 5 min. *Lesson: per-source display policy enforced structurally; staleness as a first-class, visible state; attribution carried on every entity.*

**C7 · Argus** (seed: GoSlowPoke168/Argus README; 20★ MIT) — dashboard reads a static payload; **Filters, settings, and a country/sector browser**; "jump to random camera"; **in-app data sync** button (local control server, live progress); 3-tier payload (`core` positions → `labels` → `detail/` chunks) keeps first paint fast at 229k cameras. *Lesson: browse-by-geo + incremental detail loading + a manual "sync now" control for curation.*

**C8 · CamForge** (seed: SoCloseSociety/camforge README; MIT per README) — **`GET /api/cameras/search` (bbox · type · source · q · region · city · limit)** plus `/api/stats`, `/api/thumb/:id` (SSRF-safe thumbnail proxy that re-resolves expired previews); **public-by-design ingest gate (`src/lib/policy.ts`) reject-and-log** on credential-bearing sources; pluggable connectors (one file per source) + registry; OSINT module scope-gated and metadata-only. *Lesson: the exact search-API shape + structural gate + connector registry to copy.*

**C9 · LiveTrafficCam site + MCP/API** (seed: bzsasson/livetrafficcam-mcp README) — queries by state, route, or named entity (pass/bridge/tunnel); **`camera_status`** (verified-live status, last live time, official source); **`state_uptime`** (live/stale/dead counts + 14-day check success rate); API capped at 200 cams/query; every result carries its agency attribution line ("keep it when you display the data"). *Lesson: status taxonomy live/stale/dead + uptime metrics + per-query caps + attribution as data.*

**C10 · OpenTrafficCamMap** (seed: AidanWelch/OpenTrafficCamMap README + tree; 61★ MIT) — US traffic-cam map with documented open API/data endpoints (seed-captured; see seed README for exact routes). *Lesson: geo-bbox query precedent; reuse endpoints pattern only per its license.*

**Proposed mechanism sketch (PROPOSED — design input, not inherited from any single project):**
- **Add** = `URL paste (or connector import) → GATE → PROBE → CLASSIFY → STORE+HEALTH`.
  - GATE: source registry lookup (operator/agency/API/gov open-data/opt-in); reject credential-bearing URLs; reject `exposure_aggregator`/`unknown` provenance; record `policy_verdict` + reviewer in audit log.
  - PROBE: **one** bounded request (timeout, UA, no auth): capture status/content-type/size/hash; detect protocol — MJPEG (multipart/x-mixed-replace), JPEG still, HLS (m3u8), YouTube/iframe embed, RTSP (**classify by vendor pattern only — never connect**); blank-frame check (sfw's extrema trick); scene classify (local Places365-class model → tags + indoor/outdoor); geo resolve (IP → coarse, manual override allowed; never claim exact location from IP).
  - STORE: `cameras` + `sources` + `health` + `audit` rows; `status=active`; tags; `attribution` + `official_url` + `display_policy` required (D4); `added_by`.
- **Remove** = soft-delete `retired` (+ reason, `removed_by`) → tombstone so re-ingest is blocked; **auto-quarantine after N consecutive fails** (default N=10, tune) → `retired` after sustained death → restore on recovery; takedown request = `removed` + publish contact page (D6).
- **Search** = filter by **country / region / city / bbox-radius / protocol (mjpeg·jpeg·hls·iframe·rtsp) / status (live·stale·dead·quarantined·retired) / tag (scene·type) / source_id / free-text (name·operator)**; every result returns `status`, `last_checked`, `uptime_14d`, `attribution`, `source_url` (C8/C9 shape). Status model: live / stale / dead (C9) + quarantined / retired (lifecycle).
- Roles (owner / curator / viewer) encoded even for a single user (`added_by`/`removed_by` fields), so the surface is ready for delegation.

**Dead ends / limitations (as per rules):**
- `K3ysTr0K3R/Webanator` — 404 at capture (from seed TABS-LIST); no evidence obtained.
- `x64vbhv/webcamX` — no README (404 via API); analyzed `webcamX.py` directly instead.
- ZoomEye pricing/help pages — JS-rendered/blocked to extractor; **free-tier quota numbers unverified**.
- FOFA `en.fofa.info/api` — JS placeholder only; syntax taken from the GoFOFA repo + VIP-page search snapshot (quota figures marked).
- `docs.shinobi.video/monitors` — extractor failures (quota); Shinobi add/remove specifics partly **(verify)**.
- Purdue CAM2 API — obsolete repos (`CAM2API-Obsolete`, `CAM2RetrieveData` "DO NOT USE"); treated as dormant.
- `docs/userguide/console.rst` not found in ZoneMinder repo docs — used `definemonitor/*.rst` instead.
- Web-search backend intermittently rate-limited (Exa/Nimble quotas); empty first returns were retried where load-bearing.

**Number provenance:** jrw row count = verified by download (17,399 rows). Repo stars/licenses/push dates = GitHub API at capture time. Shodan pricing/credits, Censys 100 credits, FOFA plan figures = extracted/snapshot from vendor pages (FOFA/ZoomEye marked). OpenCCTV counts = the site's own claims (moving numbers).

**OPEN QUESTIONS FOR OWNER**
- Does the viewer ever display frames from published-by-design cams that routinely show bystanders (GDPR/privacy posture)? Default proposed: display stills only, detection-not-recognition, no face/LPR, ephemeral thumbnails — or link-out-only for person-dense scenes?
- What is the approval bar for automated ingest: gov/DOT/open-data allowlist only at first, with per-source manual review for commercial/tourism sources? Who signs off on ambiguous "publish signal" cases?
- For exposure-aggregator material (incl. the 17K dump): permanent exclusion from the product DB, or a quarantined research store for awareness reporting (never probed, never joined)?
- Discovery budget: free tiers only (Shodan Membership $49 one-time = 100 credits/mo; Censys Free 100 credits) vs. a paid API for scale — who owns the account and the monthly quota?
- Auto-retire thresholds and takedown SLA: is "10 consecutive fails over ~24h → quarantine, restore on recovery" the right default, and what response window do we promise on removal requests?

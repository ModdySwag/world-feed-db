# S5 — OSINT/scanner layer, legal/ethical boundary, management-surface precedents

**Program:** worldwide, updateable, self-healing DB + viewer of PUBLIC live video feeds (owner: Moddy)
**Scope of this wave:** OSINT/scanner projects, discovery-service options (Shodan/Censys/ZoomEye/FOFA), policy-design inputs, management-surface precedents.
**Date:** 2026-10-05 (ACST). **Method:** repo files fetched via `gh` API (READMEs, source, trees, blob downloads); docs extracted where reachable; dataset files downloaded and counted; no accounts created, no cameras probed, no scans run. Counts re-verified where possible and dated; anything unverified is marked `(verify)`.

> **OWNER DECISION (2026-10-05, supersedes the earlier default-exclude line):** insecam-class exposed cameras are **INCLUDED** in scope as an **explicitly-flagged category**. Standing constraints unchanged: **scanner tools remain documentation-only — no live scanning/brute-forcing of third-party devices, no probing of devices.** Section B defines how to include the category responsibly.

**Section A: 20 entries.** Section B: how to include responsibly (incl. the dataset-vs-scanner distinction). Section C: 10 precedents + proposed mechanism.

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
**Risk/legal:** credential testing against third-party devices is squarely unauthorized-access territory (CFAA / s 478.1 / Directive 2013/40 Art. 3), regardless of "non-intrusive" framing — unchanged by the INCLUDE decision (that covers dataset aggregation, not device contact).
**VERDICT: SKIP (never run — credential testing stays excluded under the standing constraints); retained as ecosystem evidence.** Build component: **none** (test case for the ingest linter: credential-bearing URLs must be redacted/flagged).

### 5 · Project Eyes On (Y0oshi)
- https://github.com/Y0oshi/Project-Eyes-On (244★, MIT, last push 2026-08-26)

**KEY FACTS:** "unified intelligence tool for mass IP camera scanning" (v4): two engines — (1) **web dorking** across Yahoo/Bing/Mojeek/DuckDuckGo with per-engine pacing/cooldowns ("anti rate-limiting"), (2) **Insecam directory scraper** (country code + pages); plus path probing for JS-hidden streams, GeoIP (city/country), dedupe stripping cache-busters, live verification of stream type (MJPEG/JPEG/Video), JSON/CSV/HTML export, arrow-key TUI. Topics include `insecam`.
**What data you'd get:** mass candidate lists with geo + stream-type verification.
**License/ToS:** MIT (repo). Scraping Insecam/engines is ToS-hostile and the output is an exposed-camera list.
**Risk/legal:** mass harvesting + live device verification = active scanning; the standing constraint keeps this documentation-only (the INCLUDE decision covers dataset aggregation, not device contact).
**VERDICT: SKIP for any pipeline. REFERENCE for two *concepts*: polite search-engine pacing, and stream-type verification.** Build component: **stream-type detection concept** (applied only to public-by-design entries).

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
**Risk/legal:** live scraping = active scanning; documentation-only (the mechanics inform A.19; the scraper is not adopted).
**VERDICT: SKIP as a tool (documentation-only) — mechanics extracted into A.19; the dataset route is preferred.** Build component: **URL/pagination mechanics reference only**.

### 10 · totalynothackedijokeyounot (justrandomwebcams) — 17K insecam-sourced dump
- https://github.com/justrandomwebcams/totalynothackedijokeyounot (6★, **no license**, created/pushed 2019-03-01)
- Verified by download (2026-10-05): `190221dump_alphabetical.csv` = **17,399 rows (17,398 cameras + header)**, 1,724,567 bytes; **TSV** columns `ip:port`, `country`, `city`, `image feed link`; sample rows show MJPEG/cgi snapshot URLs, some with **credentials embedded** (`.../cgi-bin/snapshot.cgi?chn=0&u=admin&p=…`). README repeats Insecam's claim "This site contains no hacked webcams, all of them just freely acceptable from all of the internet" (**claim unverified by us**).
- **Fetch command:** `curl -L https://raw.githubusercontent.com/justrandomwebcams/totalynothackedijokeyounot/HEAD/190221dump_alphabetical.csv`

**What data you'd get:** ~17.4K camera endpoints with country/city — the largest single ingest candidate (snapshot dated 2019-02-21, stale → liveness `unverified`).
**License/ToS:** none — no permission; private-use/reference only; do not redistribute.
**Risk/legal:** credential-bearing URLs must be **redacted before storage**; entries are exposure-category (flag per Section B); no device contact.
**VERDICT: INCLUDE (flagged category, dataset route) — ingest with `provenance_class=exposure_aggregator`, snapshot date, credential redaction, warnings; never probe the listed devices.** Build component: **dataset ingester (TSV) + redaction linter + provenance flags** (fixture for the gate).

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

### 17 · Insecam — the flagged category (overview; mechanics in A.19, datasets in A.20)
- Referenced via: webcamX (#9), Project Eyes On (#5), Pantheon (#6), seeallthethings (#2), jrw dump (#10), OpenEyes/others (A.20). No device contact made at any point.

**KEY FACTS (sourced, with dates):** insecam.org is the best-known aggregator of openly reachable camera streams — Wikipedia: launched 2014 by an anonymous programmer, Russian-hosted, initially **~73,000 feeds across 152 countries**; categories by manufacturer, country, popularity, scenery; **as of 2025 "over 2,000 live feeds could still be accessed"** (per Wikipedia, citing Digital Camera World). Academic measurement (PAM 2018 study, Northwestern — paper PDF): in an 18-day window (2017-09-25→10-12) **28,386 unique active cameras** from **136 countries / 25 manufacturers**; **≥560,293 unique cameras ever listed** (metadata recovered for 290,344); estimate ~20,000–25,000 active, ~215 new/day; all feeds unauthenticated. Location precision: insecam itself warns locations are "very approximative… accuracy in hundreds of miles" (per Northeast Bylines). Dumps exist (e.g. #10: 17,398 rows, 2019).
**Scale/risk summary:** tens of thousands of endpoints per era; some dumped URLs carry embedded credentials; site's own claim of "filtered"/"no hacked" cameras is **unverified by us**.
**License/ToS:** none of our own to rely on; the site has no ToS we could verify — treat any interaction conservatively (Section B4).
**Risk/legal (unchanged constraints):** no device access, no credential use, no probing anywhere in the pipeline. Data-protection exposure attaches to the imagery (GDPR/APPs), and insecam is a third-party Russian-hosted directory whose posture is not ours.
**VERDICT: INCLUDE AS FLAGGED CATEGORY (owner decision 2026-10-05) — via dataset aggregation and/or documented directory mechanics (A.19/A.20), with provenance flags, credential redaction, display warnings, and the distribution caveats in Section B.** Build component: **exposure ingest pipeline (flagged partition) + warnings + lifecycle**.

### 18 · opencctv.org — public-by-design aggregator (positive precedent)
- https://opencctv.org/ · https://opencctv.org/how-we-source · https://opencctv.org/about

**KEY FACTS:** "world's largest public camera network" directory; site states **160,703 live streams / 169 countries** (counts vary by page: 146,681 / 159 countries on another — cite as the site's own, moving numbers). Sourcing page: **"460+ registered sources"** — US state DOTs, Canadian provincial road authorities, European highway operators, Asian traffic systems, national weather/meteorological services, port authorities, national parks, ski resorts, observatories, space agencies (GOES, Himawari, EUMETSAT, NASA). Explicit policy: **"We do not scrape private cameras, and we do not host or operate cameras of our own — we link to and embed feeds their operators already make public."** Continuous ingestion, duplicate detection/normalization, coordinate validation, and lifecycle: **"Cameras are never silently deleted — they are deactivated when they go dark and restored."** Type taxonomy visible: traffic & highway 93,215; ski 8,832; weather 6,099; nature & wildlife 5,749; aviation 4,279; airport 2,378; beach & coast 2,186; port & harbor 1,165.
**What data you'd get:** a ready-made public-by-design catalogue model (and a candidate cross-check source).
**License/ToS:** site terms for scraping/embedding not assessed **(verify before consuming)**; their source-registry + attribution chain is the model to copy.
**Risk/legal:** low relative risk (operator-published feeds), subject to their terms and per-source attribution.
**VERDICT: ADOPT as the reference model (and evaluate as a pilot discovery source, honoring their terms).** Build component: **source registry pattern, deactivate/restore lifecycle, attribution chain, camera-type taxonomy**.

### 19 · insecam.org directory mechanics — discovery-pipeline option
- Mechanics documented from tool sources (webcamX code #9, apockill `Websites.txt`, Eyes-On README #5) + published sources (Wikipedia; PAM 2018; Northeast Bylines). **Site itself not scraped by us.**

**KEY FACTS:**
- **URL structure:** country dimension `/en/bycountry/{CC}/` (140+ ISO-style codes per webcamX); **type/vendor dimension** `/en/bytype/{Type}/` — observed values include `Axis`, `Axis2`, `Foscam`, `Android-IPWebcam`, `Toshiba`, `Yawcam`, `WIFICam`, `WebcamXP`, `Vivotek`, `TPLink`, `Streamer`, `Sony`, `Sony-CS3`, `Panasonic`, `PanasonicHD`, `Mobotix`, `Megapixel`, `Linksys`, `Hi3516`, `Canon`, `D-Link`… (apockill `Websites.txt`, 906 B).
- **Pagination:** `?page={N}` with the last-page number exposed in-page via a `pagenavigator("?page=", N)` JS hook (webcamX regex). Listing thumbnails marked up as `div.thumbnail-item__preview` with `<img src=…>` (webcamX extraction target). Categories also include manufacturer/popularity/scenery (Wikipedia).
- **Scale claims (dated):** 2014: ~73,000 feeds / 152 countries (Wikipedia). 2017 (18-day study): 28,386 active / 136 countries / 25 manufacturers; ≥560,293 ever; ~20–25k active est.; ~215 new/day (PAM 2018). 2025: "over 2,000 live feeds" (Wikipedia). Dumps: 17,398 cams dated 2019-02-21 (#10).
- **Discovery-pipeline options:** (A) **dataset route (recommended, A.20)** — copy published dumps; no live scraping of the directory at all; (B) **directory route (conditional)** — crawl `/en/bycountry/{CC}/` + `/en/bytype/{Type}/` listings with pagination, polite budget, metadata only; **never follow the outbound camera URLs**. Directory listings expose thumbnail URLs + geo; dumps additionally expose some credential-bearing URLs.
- **Compliance notes:** ToS/robots for insecam unknown **(verify; default conservative)**; exposure entries must carry `provenance_class=exposure_aggregator`, snapshot/fetch dates, and Section B warnings; geo is approximate (site's own "hundreds of miles" caveat) — store `geo_confidence=low`.

**VERDICT: REFERENCE + (conditional) EXECUTE as a documented pipeline option — prefer the dataset route; if the directory route is used, it runs at polite rates and never touches listed devices.** Build component: **directory-crawler spec (bycountry/bytype + pagination) marked `flag=exposure`, gated behind owner approval + kill-switch**.

### 20 · insecam-derived datasets / repos — enumeration (verified 2026-10-05)
All counts verified by download on 2026-10-05; fetch commands are raw-file URLs. **Dataset aggregation ≠ active scanning:** these are *static snapshots* someone else produced from an aggregator directory — ingesting them involves **no contact with any camera**; only the aggregator site was contacted by the dataset author, not by us. Active scanners (#4, #5, #9, A.1) *enumerate/verify/contact devices or scrape the directory live* — those remain documentation-only. Refresh for the dataset route = re-download the file (cheap, safe); refresh for the directory route = polite crawl (B4).

**Datasets with committed data (path / format / count / size / fetch):**
1. `justrandomwebcams/totalynothackedijokeyounot` — `190221dump_alphabetical.csv` — TSV, cols `ip:port, country, city, image feed link` — **17,399 rows (17,398 cams)**, 1,724,567 B — snapshot 2019-02-21 — `curl -L https://raw.githubusercontent.com/justrandomwebcams/totalynothackedijokeyounot/HEAD/190221dump_alphabetical.csv`
2. `GeorgePatsias/OpenEyes` — `app/markers.json` — JSON array of dicts — **7,170 records**, 2,067,534 B — fields `id, country, country_code, region, city, zip, timezone, manufacturer, lat, lng, stream` — README: "Open IP Cameras, with default credentials – publicly accessible, scrapped from http://www.insecam.org/" — `curl -L https://raw.githubusercontent.com/GeorgePatsias/OpenEyes/HEAD/app/markers.json`
3. `carolinebuttet/virtualpeephole` — `data/webcams_headers.csv` — CSV, header `Url,Country,Country Code,Region,City,Lat,Lng,ZIP Code` — **2,806 rows (2,805 cams)**, 435,819 B — `curl -L https://raw.githubusercontent.com/carolinebuttet/virtualpeephole/HEAD/data/webcams_headers.csv`
4. `saulocatharino/rackcams` — `cameras.txt` — CSV `country,city,url` — **1,089 non-empty lines (1,088 cams)**, 92,440 B — samples include credential-bearing URLs (`u=admin&p=`) — `curl -L https://raw.githubusercontent.com/saulocatharino/rackcams/HEAD/cameras.txt`
5. `giasuddin2548/Insecam-Scraper-Discord` — `db/list.json` — **JSONL, 210 records**, 133,607 B — fields `ip, port, geolocation{city, region, country, loc, org}` — `curl -L https://raw.githubusercontent.com/giasuddin2548/Insecam-Scraper-Discord/HEAD/db/list.json`
6. `ratemypraxis/insecamRoulette` — `public/mjpegLinks.json` — dict, **50 entries** (`"State, US" → mjpeg URL`), 4,296 B — `curl -L https://raw.githubusercontent.com/ratemypraxis/insecamRoulette/HEAD/public/mjpegLinks.json`
7. `vicalejuri/insecam-feedtv` — `app/assets/cameras.feed.json` — JSON array, **12 records** (`country, uri, city`), 1,295 B — `curl -L https://raw.githubusercontent.com/vicalejuri/insecam-feedtv/HEAD/app/assets/cameras.feed.json`

**Tool/pipeline repos (no committed dataset; mechanics reference only):** `apockill/InsecamScraper` (scrapes insecam → ML person-detection → saves frames "to generate large datasets of 'in the wild' footage"; `Websites.txt` used for A.19), `matiasraisanen/insecrawl` (still-image downloader), `mvarhola/insecam-live`, `Hidden-Layer-Media/ghostcam-finder`, `public-collaboration-evercam/scrapper`, `wilian-hack/insecam`, `erfangolpour/EagleEye` (YOLO on insecam streams), plus scanner repos #5/#9.
**Unavailable/dead:** `oz0977776/Insecam_ImageScrapper` — tree 404 on 2026-10-05 (repo gone/private; ~165 MB at search-index time — likely an image set; **(verify)** if it resurfaces).
**Academic reference:** PAM 2018 measurement study of insecam (28,386 active / 136 countries / ≥560,293 ever; metadata for 290,344) — PDF at users.eecs.northwestern.edu/~hxb0652/HaitaoXu_files/PAM2018.pdf
**Storage note for ingest:** record per dataset: source URL, commit/SHA if possible, download date, row count, format, license (all of the above are **unlicensed** → private-use/reference; do not redistribute), credential-URL redaction applied (yes/no).

**VERDICT: ADOPT (dataset route) — the concrete ingest targets for the flagged category; store flagged, redacted, snapshot-dated; refresh by re-download.** Build component: **multi-format dataset ingesters (TSV/CSV/JSON/JSONL) + redaction + provenance + diff-on-refresh** (new/removed camera counting per dataset version).

---

## (B) HOW TO INCLUDE RESPONSIBLY — owner has decided INCLUDE

**B0 · Dataset aggregation vs. active scanning (the line that stays):**
- **Dataset aggregation (IN):** copy static third-party snapshots (A.20) and/or crawl aggregator *directory* pages (A.19, conditional). No contact with any camera device; staleness is explicit; refresh = re-download/re-crawl. Legal exposure = handling/re-publishing someone else's aggregation (data-protection + reputational), manageable with flags/warnings/redaction/private scope.
- **Active scanning (OUT, unchanged):** tool-driven device contact — path enumeration (sfw RTSP), credential testing (CamXploit), mass live verification (Eyes-On), live scraping (webcamX). Documentation-only; no code adopted from these paths; no probing of devices, ever.
- **Design consequence:** liveness for exposure entries is **not verified by us** (status = `unverified`, with snapshot date). Public-by-design entries keep normal health checks (B4).

**B1 · Provenance flagging (mandatory at ingest).**
Fields: `provenance_class ∈ {public_by_design, exposure_aggregator, unknown}`; `provenance_source` (dataset name + URL + commit/SHA or directory URL pattern) and `snapshot_date`/`fetch_date`; `credential_present` (boolean; after redaction `was_redacted=true`); `liveness_verified=false` for exposure; `geo_confidence` (low for aggregator entries — the site's own locations are "hundreds of miles"-accurate); `exposure_reason` (e.g. `no_auth_claimed`, `default_credentials_likely`). **Recommendation: no entry may be `active` in the catalogue without a `provenance_class` + source record; the classifier runs before storage and the verdict is immutable (a new verdict = a new row).** Build change: provenance schema + classifier step + audit log.

**B2 · Storage & tagging.**
Store exposure entries in a distinct partition (`exposure_cameras`) or with an indexed `provenance_class` so the whole category can be filtered/exported/disabled in one move; tags: `exposed`, `unsecured_claim`, `default_credentials_likely`, `snapshot_<YYYYMMDD>`, `geo_approximate`; **never store credentials** — redact URL userinfo and `u=/p=/password=` style params to `<redacted>` at parse time and keep the redaction record; keep the raw dataset file + hash outside the DB for re-parse/diff; version rows on refresh and keep a removal diff (which cameras disappeared per dataset version). **Recommendation: redact-then-store, partition, version everything.** Build change: parser redaction + partition + dataset version table.

**B3 · Display warnings (every exposure entry, everywhere it appears).**
Per-camera warning strip: "**Unsecured camera listed by a public aggregator — may capture private scenes; location approximate; unverified.**" + source dataset name + snapshot date + "report/remove" link. Preview policy: **click-through warning before any live view; no autoplay; blurred thumbnail until click (optional); no search-engine indexing (`noindex`) on exposure pages; no exposure URLs in public sitemaps.** Recommendation: warnings + click-through + noindex + no autoplay; the viewer never auto-refreshes exposure feeds (avoid ongoing proxying of third-party streams by default). Build change: warning component + `display_policy` per provenance class + robots meta.

**B4 · Refresh & rate-limit rules.**
- Exposure (dataset route): refresh = re-download on a schedule (suggest monthly; confirm with owner); **no device probing**; no auto-refresh of individual exposure feeds in the UI (at most click-through link / on-demand snapshot with a per-camera cooldown — `(verify)` with owner).
- Exposure (directory route, if approved): ≤1 request / 2 s per host, single connection, honor 429/`Retry-After`, off-peak, cache; record robots/ToS status; abort on blocks; keep a **kill-switch** to disable the crawler and the whole exposure ingest.
- Public-by-design: normal health checks — per-host ≥60 s between stills, exponential backoff on errors, global concurrency caps, UA with contact info.
**Recommendation: two rate regimes (crawl-police for directories; health checks for public-by-design), one kill-switch.** Build change: fetch-policy module with per-source budgets + kill-switch flag.

**B5 · Distribution caveats (private build vs any public release).**
- **Private build / owner-only (recommended scope for the exposure category):** inclusion OK with B1–B4 safeguards. Rationale: reference/research use, no mass re-publication, removal requests handled directly.
- **Any public release:** recommend the public surface **excludes live links/frames for exposure entries** (metadata-only, or excluded entirely): re-publication amplifies privacy harm and data-protection exposure (GDPR erasure/objection; AU APPs), and the datasets are **unlicensed** (jrw, OpenEyes, virtualpeephole, rackcams, giasuddin, roulette, feedtv all show no license) — redistributing their content publicly is legally murkier than private use. If the owner chooses public exposure entries anyway: noindex, warnings, takedown SLA, per-source consent review, legal sign-off.
- **Attribution:** always cite dataset/source + snapshot date; never present exposure data as our own collection.
**Recommendation: keep the exposed category in the private build first; decide public scope separately.** Build change: build-profile flag (`PRIVATE_EXPOSURE_SURFACE=on/off`) + export gates.

**B6 · Jurisdictional one-liners (inclusion-oriented).**
- **US (CFAA, 18 U.S.C. § 1030):** the offence is *access without authorization* to a protected computer; **listing metadata or displaying a link is not itself access**, but any server-side connection to a camera could be — so the pipeline never connects. DOJ charging policy (JM 9-48.000) focuses on security-measure circumvention, not mere reachability. [justice.gov/jm/jm-9-48000-computer-fraud]
- **Australia (Criminal Code Act 1995 (Cth) s 478.1):** unauthorised access to, or modification of, *restricted data* (protected by an access-control system) — up to 2 years; the act of access is the offence, not possessing metadata. [legislation.gov.au; cdpp.gov.au/cybercrime]
- **EU (Directive 2013/40/EU Art. 3):** criminalises intentional access "without right… where committed by infringing a security measure"; **GDPR applies to personal data in frames regardless of feed publicity** — erasure/objection rights support warnings + takedown + minimal display. [eur-lex.europa.eu]
- **Cross-border note:** insecam is a Russian-hosted third party (Wikipedia); consuming its data shifts some risk to us via data-protection + reputational channels; mitigate by keeping exposure data private-build, flagged, redacted, and takedown-responsive.
**Recommendation: private scope + no device access + warnings/takedown = defensible posture; get counsel review before any public exposure surface.** Build change: policy doc embedded as code comments + `legal_review_required` flag on public release.

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

**Proposed mechanism sketch (PROPOSED — design input; updated for the INCLUDE decision):**
- **Add** = `URL paste / dataset import / connector → GATE → (PROBE) → STORE + HEALTH`.
  - GATE: provenance classifier — `public_by_design` (operator/agency/API/gov open-data/opt-in) vs `exposure_aggregator` (dataset/directory import, owner decision) vs `unknown`; **credential-bearing URLs are redacted + flagged (never stored raw)**; record `policy_verdict` + reviewer in audit log; assign `display_policy` (`embed | link_only | metadata_only`).
  - PROBE: **public-by-design only** — one bounded request (timeout, UA, no auth): status/content-type/size/hash; protocol detect (MJPEG multipart, JPEG still, HLS m3u8, iframe embed, RTSP **by vendor pattern only — never connect**); blank-frame check (sfw's extrema trick); scene classify (Places365-style model → tags + indoor/outdoor); geo resolve (IP → coarse, manual override; never claim exact location from IP). **Exposure entries: no probe — store as imported, `status=unverified`, snapshot date shown (B0/B4).**
  - STORE: `cameras` + `sources` + `health` + `audit` rows; `status=active` (public-by-design) or `unverified` (exposure); tags; required `attribution` + `official_url` (where known) + `provenance_class` + `snapshot_date`; `added_by`.
- **Remove** = soft-delete `retired` (+ reason, `removed_by`, tombstone) → auto-quarantine after N consecutive fails (default N=10; applies to public-by-design health checks) → `retired` after sustained death → restore on recovery; takedown request = `removed` + tombstone + public contact page (B6); **exposure entries are also removable in bulk by dataset version**.
- **Search** = filter by **provenance (public_by_design / exposure_aggregator)**, country / region / city / bbox, protocol (mjpeg·jpeg·hls·iframe·rtsp), status (live·stale·dead·quarantined·retired·unverified), tag (scene·type), source_id, free text (name·operator); every result returns `status`, `last_checked`, `uptime_14d`, `attribution`, `source_url`, `provenance_class` (C8/C9 shape). Status model: live / stale / dead (C9) + quarantined / retired / unverified (lifecycle).
- Roles (owner / curator / viewer) encoded even for one user (`added_by`/`removed_by`).

**Dead ends / limitations (as per rules):**
- `K3ysTr0K3R/Webanator` — 404 at capture (from seed TABS-LIST); no evidence obtained.
- `x64vbhv/webcamX` — no README (404 via API); analyzed `webcamX.py` directly instead.
- `oz0977776/Insecam_ImageScrapper` — tree 404 on 2026-10-05 (gone/private); no data recoverable.
- ZoomEye pricing/help pages — JS-rendered/blocked to extractor; **free-tier quota numbers unverified**.
- FOFA `en.fofa.info/api` — JS placeholder only; syntax taken from the GoFOFA repo + VIP-page search snapshot (quota figures marked).
- `docs.shinobi.video/monitors` — extractor failures (quota); Shinobi add/remove specifics partly **(verify)**.
- Purdue CAM2 API — obsolete repos (`CAM2API-Obsolete`, `CAM2RetrieveData` "DO NOT USE"); treated as dormant.
- `docs/userguide/console.rst` not found in ZoneMinder repo docs — used `definemonitor/*.rst` instead.
- Web-search backend intermittently rate-limited (Exa/Nimble quotas); empty first returns were retried where load-bearing.

**Number provenance:** A.20 dataset counts = downloaded & counted 2026-10-05 (jrw 17,399 rows; OpenEyes 7,170; virtualpeephole 2,806; rackcams 1,089 lines; giasuddin 210 JSONL; roulette 50; feedtv 12). Insecam scale = Wikipedia + PAM 2018 (2017 window) + as-of-2025 figure from Wikipedia. Repo stars/licenses/push dates = GitHub API at capture time. Shodan/Censys/FOFA figures = vendor pages (extracted/snapshot; FOFA/ZoomEye marked). OpenCCTV counts = the site's own claims (moving numbers).

**OPEN QUESTIONS FOR OWNER**
- Ingest route for the exposed category: datasets only (recommended; A.20) vs. also the live directory crawl (A.19 bycountry/bytype)? And which dataset first — jrw (17.4K, 2019-stale) or OpenEyes (7,170, newer, includes manufacturer field)?
- Confirm the no-probe rule for exposure entries (status `unverified`, snapshot date shown) — or do you want a future opt-in liveness tier with separate risk review (default: off)?
- Display treatment: metadata + click-through only (recommended), blurred thumbnail, or inline preview? And geo-mapped or aggregated-only?
- Distribution: keep the exposed category to the private build (recommended) with the public surface exposing public-by-design only — or plan a public exposure surface (then: noindex + warnings + takedown SLA + legal review)?
- Takedown workflow specifics: public contact point, response SLA, hard-remove + tombstone, credential-redaction rules, and dataset refresh cadence (monthly?).

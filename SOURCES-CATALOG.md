# SOURCES-CATALOG — World Feed DB (living collation)

Status: **SEED (2026-10-05)** — built from the Brave tab corpus + local prior art + the Live-Environment-Streams (L-E-S) index. Wave fold-ins (S1–S5) will refine each section; entries carry `→W<n>` markers where deeper detail is pending.

Reading rules: every count carries a source; "per L-E-S index" = counts from `research/seed-tabs/data/LES-sources.json` (fetched 2026-10-05; their per-stream verification dates vary). Caveat: in that index, `active_count: 0` on an `html_page` source means "page-level source, not ffprobe-checkable" — it does NOT necessarily mean dead. `0` on an `hls` source does mean all its probed streams failed at their last check.

---

## 0 · Already VERIFIED working (from zero-hud WV1 dossier, 2026-10-03 — frames decoded locally)

| Source | Endpoint (as verified) | Result |
|---|---|---|
| Caltrans D10 HLS | `https://wzmedia.dot.ca.gov/D10/SJ_SB5_NO_LathropRd.stream/playlist.m3u8` | 42,603 B frame; JSON `https://cwwp2.dot.ca.gov/data/d10/cctv/cctvStatusD10.json` (154 cams, 8 video in D10) |
| NASA — ISS live | `https://www.youtube.com/@NASA/live` (yt-dlp `bv*[height<=720]+ba/b`) | 33,340 B frame; byte-flow proof 300,000 B |
| explore.org — Brooks Falls | `https://www.youtube.com/@ExploreLiveNatureCams/live` | 97,153 B frame |
| Virtual Railfan | `https://www.youtube.com/@VirtualRailfan/live` | 131,480 B frame |
| Monterey Bay Aquarium | same, + `--extractor-args "youtube:player_client=android_vr"` | 122,090 B frame |
| Sen 4K ISS / USGS Kīlauea / auroras (Lyngen, Reykjavík) / explore.org manatee | YouTube channel `/live` family | frames 14K–54K B |
| Levanto coastal HLS | `https://5e0add8153fcd.streamlock.net:1936/vedetta/levanto.stream/playlist.m3u8` | 41,759 B (provenance caution) |
| Image tier | USGS HVO `volcanoes.usgs.gov/observatories/hvo/cams/<ID>/images/M.jpg` · SDO `sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0193.jpg` (+0131) · Keck `www2.keck.hawaii.edu/realtime/webcam/k2Mast.jpg` / `kcam_1.jpg` · JCMT `eao.hawaii.edu/weather/images/jcmt.jpg` · IFA `hp.ifa.hawaii.edu/cams/dormb-ptz.jpg` · TfL `s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/<id>.jpg` | all 6.8K–349K B, refresh 1–15 min |

Full method detail + exact commands: `C:\Users\user\zero-hud\reference\world\WV1-live-video-sources.md`.
Currently wired into zero-hud's sidecar (`server/world_feed.py`, :8772): 5 channels (caltrans, iss, katmai, railfan, aquarium) with lazy ffmpeg pipelines + honest health.
Dead ends from that pass: NASA TV akamaized m3u8 (empty segments), Purdue MJPEG (decommissioned). → Don't re-try.

---

## 1 · Class G — Government / public-agency sources (worldwide)

| Family | Geo | Scale (per L-E-S index unless noted) | Enumerate via | Stream pattern | License |
|---|---|---|---|---|---|
| Caltrans (districts) | US-CA | D10: 154 cams / 8 HLS (verified 10-03). All 12 districts: →W2 | `cwwp2.dot.ca.gov/data/d<NN>/cctv/cctvStatusD<NN>.json` | HLS `wzmedia.dot.ca.gov/...stream/playlist.m3u8` + stills `.../image/<id>.jpg` | Public agency (courtesy) |
| VDOT / 511Virginia | US-VA | **1,168 (all active)** | 511virginia.org services →W2 | HLS | Public domain |
| MD SHA | US-MD | 404 (all active) | chart.maryland.gov →W2 | HLS | Public domain |
| DelDOT | US-DE | 261 (0 active at last L-E-S check) | deldot.gov →W2 | HLS | Public domain |
| Iowa DOT | US-IA | 50 (50 active) | 511ia.org (Argus scraper exists) | HLS | Fair use |
| NYSDOT | US-NY | 23 (+ NYC DOT scraper in Argus) | 511ny.org | HLS | Public domain |
| Louisiana DOT | US-LA | 6 (6 active) | 511la →W2 | HLS | Fair use |
| LADOT (LA city) | US-CA | ~14+9 probe | ladot.lacity.org | HLS | Public domain |
| Ohio/ODOT (ohgo) | US-OH | wrapper repo found (TomCasavant/ohgo-wrapper) | OHGo API | →W2 | — |
| ~25 more US state DOTs | US | OpenTrafficCamMap ships per-state scrapers: NewEngland511, Nebraska, Pennsylvania, Idaho, Oklahoma, Texas (special API), Minnesota, Florida, Wyoming, Maryland, Mississippi, WV, South Dakota, Kansas, New Jersey, Colorado, Alaska, Arizona, Indiana, … | see `OpenTrafficCamMap/compilation/*` | mixed HLS/IMG/TXDOT-special | mixed |
| Argus scraper set (11 real sources) | multi | Argus pipeline: `scripts/scrapers/` — singapore/lta, canada/bc/drivebc, europe/uk/tfl_london, global/windy, oceania/nz/nzta, opencctv_bridge, txdot_resolver, usa/california/caltrans, usa/iowa/iowa511, usa/new_york/nyc_dot, usa/road511 + `host_prober.py`, `ipcamlive_resolver.py` | GitHub `GoSlowPoke168/Argus` | — | MIT code; sources per-provider |
| TfL JamCams | UK-London | full list via keyless API | `api.tfl.gov.uk` camera list (in GEV notes) | `s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/<id>.jpg` (verified) | TfL Open Data — attribution REQUIRED |
| Autobahn NRW | DE | 252 listed / 1 active at last check (verify variance) | verkehr.nrw →W2 | HLS + pages | Public domain |
| Vegvesen | NO | 22 (html) | vegvesen.no →W2 (camforge has connector) | HTML pages | Public domain |
| NZTA | NZ | Argus scraper | nzta →W2 | →W2 | Public |
| Singapore LTA | SG | Argus scraper | lta →W2 | →W2 | Public |
| Taiwan Freeway Bureau | TW | 18 | freeway.gov.tw →W2 | HTML | Public domain |
| KTICT | KR | 20 | ktict.co.kr | HTML | Public domain |
| Thailand (trafficvision TH / itic / iticfoundation) | TH | 245 / 88 / 7 (all 0 active at last check) | — | HLS | fair_use |
| ATCS Tasikmalaya + other ID feeds | ID | 31+ | — | HLS | fair_use |
| USGS volcano cams | US/multi | all observatories →W2 | `volcanoes.usgs.gov/observatories/<obs>/cams/...` | `images/M.jpg` pattern (verified) | Public domain |
| NOAA / USAP Antarctica | US | page-level | →W2 | JS/pannellum | Public |
| NASA SDO / ISS | US | verified | sdo.gsfc.nasa.gov; YouTube | JPG refresh / yt | Public domain |

Key artifacts: `research/seed-tabs/github-topics/traffic-cameras--stars.json` (31 repos incl. per-city apps), `repos/AidanWelch__OpenTrafficCamMap.README.md`, `repos/GoSlowPoke168__Argus.README.md`.

---

## 2 · Class A — Aggregators (non-government, consumer/nature/tourism)

| Family | Scale (L-E-S) | Access mechanism | Notes |
|---|---|---|---|
| Skyline Webcams | 1,684 (1,284 active) | HTML pages; direct HLS uses **expiring tokens** (token_refresh) | Biggest single consumer network; YouTube arm: 167 (13 active) |
| OpenCCTV.com | 746 (668 active) | mixes HLS + pages + YouTube | "OpenCCTV Public Feed Aggregator" |
| worldviewstream | 82 (79 active) | HLS + YouTube | |
| balticlivecam | 64 (45) | HLS | |
| camguide.net | 53 (26) | HLS+YouTube (ipcamlive entries) | |
| webcamera.pl | 52 (47) | HLS | PL |
| beachcam (Meo) | 31 (31) | HLS | PT |
| resortcams | 12 (8) | HLS | US resorts |
| wetmet-poconos | 11 (10) | html | |
| Windy Webcams | (API; keyed) | `api.windy.com/webcams/api/v3/webcams` — keyless 403 (verified 10-03) | image URLs expire ~10 min |
| webcams.travel, EarthCam, WebcamTaxi, Lookr, worldcams.tv, EarthTV, AfriCam, Roundshot | — | →W1 (deep detail this wave) | |
| explore.org | YouTube backbone (verified family) | channel `@ExploreLiveNatureCams` etc. | philanthropic, made to be watched |
| **TrafficVision.Live** | **155,000+ claimed / 700+ sources / 130+ countries** | site + API recon →W3 | see §4 — closest peer system |

---

## 3 · Class P — Platforms & portable layers

| Layer | Key facts |
|---|---|
| YouTube-live | yt-dlp resolve mechanics VERIFIED (WV1): `bv*[height<=720]+ba/b`; channel `/live` URLs work; some `watch?v=` bot-walled; `android_vr` fallback rescued one; byte-flow proof method. 475 YouTube entries inside L-E-S. Verify-live syntax →W3/W4. |
| iptv-org | giant public IPTV catalog + stream-checking CI →W3 (its verification machinery is a reuse candidate) |
| livetrafficcam.com | US traffic cam directory built on official state DOT feeds; "each camera checked on a rolling schedule with real HTTP requests — 'live' means a verified current image"; public JSON API wrapped by `bzsasson/livetrafficcam-mcp` + HA integration "verified-live signature" →W2/W4 |
| Test fixtures (pipeline testing) | rtsp.stream / octostream / viomic samples listed in rtsp-camera-view#3 →W3 (verify which still work) |

---

## 4 · Reference systems (borrow design — not feed sources)

- **trafficvision.live** — claims: 155k+ cams, 700+ official sources, 130+ countries; live video + refreshing images + YouTube on one map; route builder; AI overlays (vehicle boxes/counts); "each stream tested in real time before the round starts" (CamGuessr) = real-time liveness testing. API endpoints →W3. Capture: `seed-tabs/reddit/trafficvision-live-site.md`.
- **Argus** (GoSlowPoke168) — scrapers → SQLite → layered JSON exports (`cameras.core.json` / `.labels.json` / `.detail/`), MapLibre+Deck.GL, HLS w/ JPEG cache-bust fallback, CORS/ipcamlive local proxy. 229k+ claim; `public/cameras.geojson` = 100 MB.
- **camforge** (SoCloseSociety) — self-hosted map+relay+local AI vision; connectors `caltrans.ts / five11.ts / vegvesen.ts / windy.ts / youtube.ts`; `lib/policy.ts` bright-line module; PostGIS; Next.js 15. MIT.
- **God's Eye View** (local, C:\pinokio\api\gods-eye-view.git) — georeferenced CCTV schema; proxy+cache+serve-stale; attribution system; MIT code w/ per-source data licenses.
- **Live-Environment-Streams** — status/url_type/source_url_requires fields = a ready-made quality model; ffprobe-based production verification.
- **OpenTrafficCamMap** — crowdsourced schema (per-state-per-county rows; encoding/format enums incl. IMAGE_STREAM, M3U8, UNIQUE_TEXASDOT).
- **zero-hud world_feed.py** (local) — lazy-pipeline channel proxy w/ honest health states (live/stale/error/idle).

---

## 5 · Ready-made corpora to ingest (data artifacts)

| Corpus | File | Size | Status |
|---|---|---|---|
| L-E-S | `research/seed-tabs/data/LES-streams.geojson` + `LES-sources.json` | 4.0 MB / 18 KB | **downloaded** (5,997 features: 3,754 hls, 1,768 html, 475 yt; 4,226 active) |
| Argus | `public/cameras.geojson` (+ `.core/.labels/.detail`) | 100 MB | to fetch (build prep) |
| OpenTrafficCamMap | `cameras/<ISO3>.json` (USA 1.5 MB) | ~a few MB | to fetch |
| cctv-camera-database | `data/cameras.json` (+ CSV) + `data/rtsp-patterns.json` | 69 MB + 648 KB | to fetch (specs + per-brand RTSP URL patterns) |
| scan-for-webcams | `sfw/cams.json` | small | downloaded (`repos/scan-for-webcams.cams.json`) |

Query example for L-E-S (from its README): usable = `status=="active" and url_type in ("hls","youtube") and source_url_requires is None` → ~2,929 streams.

## 6 · Class F — Flagged / restricted — **Q1 RESOLVED (2026-10-05): INCLUDE as flagged category**

- **insecam-derived corpora** — OWNER DECISION 10-05: **INCLUDED** (`provenance: exposed` + warning badge + separate filter). Harvest status: dataset IN HAND — `totalynothackedijokeyounot` (1.7 MB CSV, `ip:port / country / city / feed-url`, datestamp 2019-02-21 — historical, low liveness expected; saved under `research/exposed/` + README with stats). Repo inventory: 41 GitHub 'insecam' repos found (top: GeorgePatsias/OpenEyes, apockill/InsecamScraper, matiasraisanen/insecrawl, OEUG99/InsecamPy, L3-X/Insecam-IP-Scraper, 8133/camera-scraper, HadiAssadDiab/Insecam-Scraper, vicalejuri/insecam-feedtv; list in `research/exposed/README.md`). insecam.org direct probe 2026-10-05: HTTP 000 via curl (blocked/failed — browser lane likely needed; mechanics →W5). Handling: prefer these existing datasets over re-scraping; rate-polite; public-release caveat preserved via the flag.
- **Scanner / recon tools** (documented for awareness, not run): `JettChenT/scan-for-webcams` (shodan queries per camera type — webcamXP/MJPG/yawcam/hipcam/rtsp, with capture_url patterns; queries captured in `repos/scan-for-webcams.cams.json`), `spyboy-productions/CamXploit`, `Y0oshi/Project-Eyes-On`, `josh0xA/Pantheon` (IoT camera recon + viewer), `2l7b/public-camera-indexing-insights` (Google-dork corpus), Kamerka (woj-ciech). `K3ysTr0K3R/Webanator` — **gone** (404; account has no public repos, 2026-10-05).
- Grey-edge mixes to treat carefully: `pbkompasz/webcams` (crawl approach, references insecam-adjacent practice), `baywolf88/seeallthethings` (SC set mixes DOT + insecam site-searches + tourism cams).

## 7 · Known gaps / dead ends

- Reddit thread **comments** not captured (Reddit bot wall; automation browser also blocked) — both posts captured as bodies. Low value; noted.
- `cve.org` + `streamlabs.com` tabs: context-only; no project info extracted (deliberately skipped).
- WV1 dead ends (do not retry): NASA TV akamaized HLS, Purdue MJPEG.
- L-E-S `active_count:0` on `html_page` sources = "not probeable", not "dead" (see reading rules).

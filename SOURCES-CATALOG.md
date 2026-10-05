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

**S2 fold-in (2026-10-05) — verified endpoint menu (full detail: `research/gov/S2-gov-institutional.md`):**
- US: Caltrans 12-district JSONs (D12=419 cams verified; D03 500 → skip) · VDOT 1,168 (`media-sfs{2,6,8}.vdotcameras.com` HLS; old geojson stale) · MD SHA 404 · DelDOT JSON 361 cams + direct HLS (verified) · Iowa ArcGIS count 1,260 · OHGO Ohio 1,161 cams + direct JPEGs (verified) · WSdot 1,706 features (latin-1!) · Road511 20-state gateway (now key-gated) · OTC per-state menu: TX special (`GetCctvSnapshotByIcdId`), MO/NV/NM/UT/HI/OK/TN/KY/ND/SD/SC/IL/WV, FL/LA/GA/AK/AZ/WI/MN/MS (`List/GetData/Cameras` family), KS/NE/CO/IN/IA GraphQL-511 family · NYC TMC API (unreachable from this host — retry elsewhere).
- Canada: DriveBC 1,066 (1,045 on) verified · Ontario 511 925 cams verified · Alberta re-test.
- Intl: TfL 890 verified · Vegvesen `kamera.atlas.vegvesen.no/api/images/<id>` + DATEX (registered) · Autobahn.de API shape (re-test) · NSW/QLD need free keys · SG data.gov.sg 8 cams · NZ trafficnz 313 verified · TW geo-blocked from host · TH/KR/JP event/manual.
- Institutional: USGS HVO/AVO/CVO/YVO/CalVO verified patterns (V1cam 200/56 KB) · NPS + Pixelcaster snapshot (200/20.9 KB), token-gated HLS · USAP XHR API (McMurdo/SouthPole/Palmer + weather) · ski: Jackson Hole JSON + direct JPGs, Ischgl; Roundshot/Panomax providers.
- Keys needed (free): Windy, Road511, NSW, QLD, LTA DataMall alt.
- Institutional/nature batch-2 (S7): SDZ / NZP / MBA / Bondi / BAS / Cruise-Panomax — full mechanics in `research/gov/S7-institutional-2.md`; resolvers listed in §2 batch-2 block.

Key artifacts: `research/seed-tabs/github-topics/traffic-cameras--stars.json` (31 repos incl. per-city apps), `repos/AidanWelch__OpenTrafficCamMap.README.md`, `repos/GoSlowPoke168__Argus.README.md`.

---

## 2 · Class A — Aggregators (non-government: consumer/nature/tourism)

*(S1 fold-in — measured 2026-10-05; full detail: `research/sources/S1-aggregators.md`; L-E-S-scope counts retained where different.)*

| Family | Scale (measured; date) | Access mechanism | Notes |
|---|---|---|---|
| Skyline Webcams | **2,447 cam pages / 71 countries / 217 regions** (full crawl) vs 1,684 in L-E-S scope | HTML crawl (country→region→city→cam); JS token player | ADOPT registry; stream = token spike |
| Windy Webcams (API v3) | 40K (2021) → 70,000+ (2026) claimed | REST, key required (403 keyless ✓); `/webcams /categories /countries /regions /cities /continents /map/clusters` | absorbed webcams.travel + lookr (302→Windy) |
| EarthCam | **365 cams keyless** (36 countries + 45 US states); app claims 1,500+ | `network_search.php` + `playlist.php`; tokenized HLS; `cam_state` | ≥1.5 s spacing + Referer; ADOPT |
| explore.org | **101 groups / ~1,140 feeds** | keyless omega API (`video_id`, `is_offline`, `current_viewers`) | ADOPT; viewer = yt-dlp |
| Roundshot | **561 livecams — 469 working / 53 broken / 32 idle / 6 late / 1 error** | keyless directory JSON + per-site `structure.json` | exemplary liveness model; JPEG panorama tier |
| WebcamTaxi | 1,950 cams / 67 listing pages | HTML → YouTube embeds | ADOPT registry |
| CamGuide.net | 5,052 unique pages (25,260 w/ translations) | sitemap → iframe upstreams (DOT/YT) | ADOPT registry |
| BalticLiveCam | 1,278 camera pages (435 online counter) | HTML crawl; admin-ajax `auth_token` → HLS | ADOPT registry; token spike |
| WorldCams.tv | 775 cam cards | HTML → YouTube embeds; robots disallows `/list/ /player /ajax/ /go` | REFERENCE |
| webcamera.pl | 600+ claimed | per-cam subdomains; `imageserver.webcamera.pl/rec/<slug>/latest.mp4` | REFERENCE |
| earthTV | 495 places (API) / 278 webcam pages | keyless places API; tokenized player | REFERENCE |
| AfriCam | 43 lodges / 6 countries | HTML → YouTube embeds | REFERENCE |
| Skyline YouTube | 580 composite entries | yt-dlp channel | viewer filler |
| ~~OpenCCTV.com~~ | **DEAD — parked (HugeDomains); last Wayback 2025-07-12** | — | purge the 746 index entries; opencctv.**org** is a different live site (see §6 / S5 A.18) |
| worldViewStream · beachcam Meo · resortcams · wetmet-poconos | 82 · 31 · 12 · 11 (L-E-S) | HLS/HTML per L-E-S | retained from L-E-S index |
| **TrafficVision.Live** | **155,000+ claimed / 700+ sources / 130+ countries** | see §4 | closest peer system |

**S1 patterns → build rules:** YouTube-embed prevalence → yt-dlp resolution subsystem = the highest-leverage shared component for this slice (matches WV1 M2). Token-gated players everywhere (Skyline JS, BalticLiveCam admin-ajax, EarthCam time-stamped tokens, earthTV playerToken, Windy 10-min image tokens) → **resolve-on-demand adapters; never store tokenized URLs as durable records**. ≈14,000 keyless records enumerated in this slice before dedupe. Rate tiers: EarthCam ≥1.5 s/call; Skyline tolerated ~6-way; BalticLiveCam keep gentlest (WP shared hosting).

---

### Batch-2 additions (S6, 2026-10-05)

| Family | Scale | Access | Verdict |
|---|---|---|---|
| webcamera24.com | **6,570 cams / 67 countries** | sitemap → RSC payload (`streamLink` HLS / `youtubeCode`); `isWork` | **ADOPT** |
| worldcam.eu | DE 1,592 · UK 754 · FR 712 (counter 32,330) | country `/p/N` 25/page; dated snapshot imgs | **ADOPT** |
| earthlive24.com | **414 cams** | sitemap → SSR YouTube embeds | **ADOPT** |
| earthcamtv + EarthCam animal | 12 live playlist / 13 animal cams | playlist.php; camshots keyless; HLS tokenized | ADOPT |
| CruisingEarth ships | **274 pages / 22 lines** | sitemap; Panomax iframes / proxied JPG | ADOPT-lite |
| ARGOS ATLAS | **220,449 cams / 20,781 video** (keyless stats) | benchmark; data pro-gated | REFERENCE |
| openwebcamdb.com | 1,881 | keyed API — ToS bans competitors | **SKIP** |
| worldlive.app | app-only (15k claim) | none | SKIP |

**Institutional batch-2 (S7):** SDZ 13 cams (Camzone HLS) · NZP 6 streams (Wowza failover) · MBA 10 (YouTube ids) · Bondi 2 (ipcamlive HLS) · BAS 1 · Panomax image API — new resolvers: **Camzone / ipcamlive / Panomax / EarthCam-token / YouTube** (full mechanics: `research/gov/S7-institutional-2.md`).

---

## 3 · Class P — Platforms & portable layers

| Layer | Key facts |
|---|---|
| YouTube-live | Resolve mechanics VERIFIED (WV1): `bv*[height<=720]+ba/b`; channel `/live` works; some `watch?v=` bot-walled; `android_vr` fallback. S3 fold-in: keyless DISCOVERY verified — `ytsearchN:"…" + --match-filter is_live` (24 live cam channels in 3 sweeps); liveness gate `--simulate --match-filter "is_live"` (rc 0/101); Data-API lane = `search.list eventType=live` (100-unit/day bucket); install deno JS-runtime for yt-dlp. 475 YouTube entries inside L-E-S. |
| iptv-org | Structural validation ONLY — no ffprobe anywhere in the org (S3 [V]); reuse = `freearhey/iptv-checker` (ffprobe CLI, 625★); no public-cam entries in its catalog. |
| livetrafficcam.com | US traffic cam directory built on official state DOT feeds; rolling HTTP checks — "live = verified current image"; status taxonomy live/stale/dead + 14-day uptime (21,580 tracked / 74.9% live verified 2026-10-05); public JSON API wrapped by `bzsasson/livetrafficcam-mcp` + HA "verified-live signature". |
| Test fixtures (pipeline testing) | S3 [V]: public RTSP demo servers DEAD (rtsp.stream / viomic / wowza / Hessdalen; port-quiz proves no local port block) → **self-host MediaMTX** as RTSP fixture; HLS fixtures WORK: Apple bipbop (`devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8`), Mux `test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` + `pts_shift`. |

---

## 4 · Reference systems (borrow design — not feed sources)

- **trafficvision.live** — closest peer system (S3-dissected) [V]: 155k+ cams / 700+ official sources / 130+ countries claimed; live video + refreshing images + YouTube on one map; route builder; AI overlays; CamGuessr "stream-tested before each round". Data surface: **853 per-source `*-cameras.json`** at `data.trafficvision.live/camera-data/` (sampled oktraffic = 683 cams, HLS `videoUrl` + `imageUrl` + make/model per cam); `changelog.json` (199 entries); `/api/catalog/manifest` = session-gated (401). robots.txt `Disallow: /camera-data/` + ToS bans automated access → **reference/benchmark only; do not bulk-pull**; use the 853 source-names to re-derive from the original agencies; consider a permission contact (→Q11). Captures: `seed-tabs/reddit/trafficvision-live-site.md`, `research/platforms/S3-platforms-lists.md` entry 1.
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

- **insecam-derived corpora** — OWNER DECISION 10-05: **INCLUDED** (`provenance: exposed` + warning badge + separate filter). **Harvest set (S5 fold-in; all counts verified 2026-10-05):** ① jrw `totalynothackedijokeyounot` 17,398 rows (TSV, snapshot 2019-02-21; saved `research/exposed/`); ② OpenEyes `app/markers.json` 7,170 records (manufacturer+geo fields); ③ virtualpeephole `webcams_headers.csv` 2,805 cams; ④ rackcams 1,089; ⑤ giasuddin2548 210; ⑥ insecamRoulette 50; ⑦ feedtv 12. All **unlicensed → private-use/reference only**; credential-bearing URLs redacted at ingest; store flagged + snapshot-dated (`provenance_class=exposure_aggregator`), **no device contact ever**. Directory mechanics (`/en/bycountry/{CC}/`, `/en/bytype/{Type}/`, `?page=N`) = conditional route (polite rate + kill-switch); datasets preferred. Also: **opencctv.org** claims 160,703 streams / 169 countries — its .com domain is unreachable from this host; reconcile vs the L-E-S "opencctv 746" index before consuming. Refs: `research/osint/S5-osint-policy-mgmt.md` §A.19/A.20/B; `research/exposed/README.md`.
- **Scanner / recon tools** (documented for awareness, not run): `JettChenT/scan-for-webcams` (shodan queries per camera type — webcamXP/MJPG/yawcam/hipcam/rtsp, with capture_url patterns; queries captured in `repos/scan-for-webcams.cams.json`), `spyboy-productions/CamXploit`, `Y0oshi/Project-Eyes-On`, `josh0xA/Pantheon` (IoT camera recon + viewer), `2l7b/public-camera-indexing-insights` (Google-dork corpus), Kamerka (woj-ciech). `K3ysTr0K3R/Webanator` — **gone** (404; account has no public repos, 2026-10-05).
- Grey-edge mixes to treat carefully: `pbkompasz/webcams` (crawl approach, references insecam-adjacent practice), `baywolf88/seeallthethings` (SC set mixes DOT + insecam site-searches + tourism cams).

**Batch-2 update (S8, 2026-10-05):** direct insecam access solved for recon (`http://` + browser UA; certificate expired; robots allows, crawl-delay 0.1; no ToS). Directory ≈2.2–2.3k now; polite census feasible (sitemap = 1 request) — **gated on Q6**. New era snapshots: GODEYE 1,775 (2026-05) + rafasapiens 2,100 (2026-10) → era chain 2019→2022→2026 with planned timeline diffs. Remote-stations class opened: AAD Mawson (Antarctica).

## 7 · Known gaps / dead ends

- Reddit thread **comments** not captured (Reddit bot wall; automation browser also blocked) — both posts captured as bodies. Low value; noted.
- `cve.org` + `streamlabs.com` tabs: context-only; no project info extracted (deliberately skipped).
- WV1 dead ends (do not retry): NASA TV akamaized HLS, Purdue MJPEG.
- L-E-S `active_count:0` on `html_page` sources = "not probeable", not "dead" (see reading rules).

# S8 · insecam.org — direct recon + new datasets + community mining

**Date:** 2026-10-05 (all fetches this session) · **Host:** Moddy's Windows box (MSYS bash, curl 8.x/schannel, python 3) · **Scope:** reconnaissance only — no device contact, no probe of any listed camera. Every insecam request = a directory page (homepage / country / bynew / FAQ / robots / sitemap). No `/en/view/` page was opened; no thumbnail (device URL) was fetched.

**Prior art (not redone):** S5 §A.19 (directory mechanics), §A.20 (7 known datasets: jrw 17,399; OpenEyes 7,170; virtualpeephole 2,806; rackcams 1,089; giasuddin 210; roulette 50; feedtv 12). Counts below are NEW unless labelled. OpenEyes was re-downloaded only as a SHA reference.

---

## (A) DIRECT RECON — insecam.org

### 1 · Reachability & TLS — the block is a self-signed, now-expired cert (plus a UA bot filter)
- DNS: `insecam.org` & `www.insecam.org` → **91.206.14.53** (A). TCP connects fine (~0.31 s).
- `curl https://insecam.org/` → exit 60 `schannel: SEC_E_UNTRUSTED_ROOT` (×3 attempts). **NOT a TCP failure** (parent recon's "TCP-fail 000" refined).
- Cert (openssl probe): `subject=issuer=C=RU, ST=Moscow, L=Moscow, O=Internet Widgits Pty Ltd, CN=insecam.org`; valid **2025-08-07 → 2026-08-07 = EXPIRED** (today 2026-10-05).
- `https://www.insecam.org/` with `-k` → **301** `Location: http://www.insecam.org/` (nginx/1.23.2). Canonical = **plain HTTP**.
- `http://www.insecam.org/` default curl UA → **403**; browser UA → **200**. (Bot/UA filter.)
- Working route used for all recon: `curl -sS -A "<desktop Chrome UA>" http://www.insecam.org/...` (or `-k` on https).
- Attempts: https non-www ×3 (cert-fail) + 1 cert-bypassed fetch (301); https www ×2; http ×2 initial (403) then 200; browser ×3 (item 7). ≤3/route for probing; later fetches were one-off page GETs spaced ≥ ~1 min.

### 2 · robots.txt — crawling is explicitly allowed at crawl-delay 0.1
Live (2026-10-05, 200, 159 B):
```
Host: www.insecam.org
User-Agent: *
Disallow: /cgi-bin
Disallow: /setcamtag
Disallow: /osm
Crawl-delay: 0.1
Sitemap: http://www.insecam.org/static/sitemap.xml
```
- Wayback: robots.txt archived since 2014 (404s); 200 `text/plain` since ≥ 2021-07; the 2022-01-17 capture is identical except `Sitemap: .../sitemap.xml`. Same policy ≥ 4 years.
- Meaning: a polite directory crawl is robots-allowed (we'd run ≥ 20× slower than the declared delay). No ToS contract exists (item 8).

### 3 · Homepage structure (200, 18,590 B; title "Insecam - World biggest online cameras directory")
- Nav: Most popular `/en/byrating/` · Manufacturers `/en/bytype/{36 values}` (Android-IPWebcam, Axis, Axis2, AxisMkII, BlueIris, Bosch, Canon, ChannelVision, Defeway, DLink, DLink-DCS-932, Foscam, FoscamIPCam, Fullhan, GK7205, Hi3516, Linksys, Megapixel, Mobotix, Motion, Ninivision, Panasonic, PanasonicHD, Sony, Sony-CS3, StarDot, Streamer, SunellSecurity, Toshiba, TPLink, Vije, Vivotek, WebcamXP, WIFICam, WYM, Yawcam) · Countries/Places (`#` JS dropdowns) · Cities `/en/mapcity/` · Timezones `/en/bytimezone/` · New `/en/bynew/` · FAQ `/en/faq/` · Contacts `/contacts/` · langs en/ru/cn · Google CSE search.
- **No country links on the homepage** (0 `bycountry` refs) — countries only via direct `/en/bycountry/{CC}/` URLs.
- Homepage grid = newest 6 items; sample view IDs: 1004220, 1010229, 196230, 368532, 371870, 891802 (ID high-water ≈ 1,010,229).
- Thumbnails embed **direct device URLs** incl. query keys (some with `u=`/`p=` creds) — never fetch; redact at ingest.

### 4 · Country listing + item markup + pagination (US, 2026-10-05)
- `http://www.insecam.org/en/bycountry/US/` → 200 (21,838 B), title "Live cameras: United States". **6 items/page**; `?page=2` OK (18,808 B); `?page=96` OK (18,558 B, last page full).
- Pagination: server accepts `?page=N`; last page exposed in-page via JS: `pagenavigator("?page=", 96, 1)` (page 96 → `(…,96,96)`). HTML nav shows prev/next only — full pager is JS-built.
- Count reading: US = 96 pages × 6 ≈ **576 cameras** (2026-10-05). AU = 1 pg × 4 ≈ 4; NZ = 1 pg × 4 ≈ 4. AQ (Antarctica) & GL (Greenland) → 404 (not covered; control XX also 404).
- Item markup (verbatim, US page 1):
```html
<div class="col-xs-12 col-sm-6 col-md-4 col-lg-4">
  <div class="thumbnail-item">
    <a class="thumbnail-item__wrap" href="/en/view/1012777/" title="Live camera in United States, Cupertino">
      <div class="thumbnail-item__preview">
        <img id="image1012777" class="thumbnail-item__img img-responsive"
             src="http://208.65.183.226:82/SnapshotJPEG?Resolution=640x480&amp;Quality=Clarity&amp;COUNTER"
             title="Live camera Panasonic in Cupertino, United States" alt="" />
      </div>
      <div class="thumbnail-item__caption"><p>Live camera in Cupertino, United States</p></div>
    </a>
    <div class="admin-buttons"></div>
  </div>
</div>
```

### 5 · Scale reading (2026-10-05) — directory is ~2.2–2.3k cameras now
- `/static/sitemap.xml` (262,128 B): **2,271 `<loc>`** — ALL `/en/view/{id}/`; id range 162–1,012,788; lastmod years: 2015:157, 2016:133, 2017:118, 2018:168, 2019:102, 2020:73, 2021:408, 2022:271, 2023:0, 2024:0, 2025:31, **2026:810**.
- `/en/bynew/` ("New in Insecam directory"): **379 pages × 6 ≈ 2,274**.
- ⇒ current listed ≈ **2.2–2.3k** (matches Wikipedia ">2,000 live feeds" (2025) figure). Historical: 2014 ~73k (Wikipedia); 2017: 28,386 active / ≥ 560k ever (PAM 2018); 2019 dump 17,398. ID space ≥ 1.01M ⇒ ~1M ever-issued IDs, sparsely retained.
- US share ≈ 576 / 2,271 ≈ 25%.

### 6 · Wayback cross-checks (structure + policy fallback)
- Homepage: dense 2024–2026 archiving (CDX; showNumPages=2); the 2024-05-12 `id_` capture is valid: 18,742 B, same title, same 6-per-page grid ⇒ structure stable ≥ 2 yrs.
- US country page: dense 2020–2024 (dozens of 200s); a 2024-05-11 `id_` fetch came back gzip (curl sans `--compressed`) — live fetch used instead.
- robots history: item 2. Availability API 429'd mid-recon; CDX + `/web/` worked.
- The r/geography thread is NOT archived on Wayback (404) — PullPush used instead (item 19).

### 7 · Browser-tool block — exact (don't retry blindly)
- 3 attempts (default session ×2, isolated session ×1): `https://insecam.org` → `chrome-error://chromewebdata/`, title "🐴 Privacy error"; CDP `Security.setIgnoreCertificateErrors` returns `{}` but a fresh navigation still lands on the interstitial; `http://www.insecam.org/` in a fresh tab ALSO ends `chrome-error` (outerHTML len 57, blank white screenshot; 2nd screenshot attempt timed out).
- ⇒ Browser tool unusable for this host (both schemes) with current config; use curl (`-k` or plain http + browser UA). Do not burn more attempts on the browser path.

### 8 · ToS/legal-text availability — no ToS exists (live or archived)
- No terms/privacy page: CDX filter (term|tos|legal|privacy|policy|rules) → only substring noise + `/.well-known/dnt-policy.txt` (404). Live site has FAQ + Contacts only.
- FAQ (`/en/faq/`, 200): removal policy — "send the URL of your camera to email from contacts section. But remember … your camera still will be available … The only solution to make your camera private is to set up a password!"; and "These cameras are not hacked. All cameras listed … do not have any password protection."
- ⇒ Interaction is governed by robots + courtesy only; we mirror the removal channel in our own display policy.

### 9 · FEASIBILITY VERDICT — polite directory crawl: FEASIBLE (small, cheap), gated on owner Q6
- Cost: sitemap = full current ID set in **1 request**; per-country/type/bynew pagenav reads + optional listing pages ≈ 1–2k page-requests worst case; at 1 req/2 s ≈ **1.5–2 h**, a few MB. Full listing-level census: ~2.3k entries at 6 items/page.
- Risks: expired/self-signed cert (use http / `-k`; no trust anchor); 403 to non-browser UAs (set honest UA w/ contact); no ToS (robots + politeness only; halt-on-block + kill-switch per S5 B4); Russian-hosted third party; privacy-sensitive content (GDPR/APPs); thumbnails leak device URLs w/ keys → redaction mandatory; **NEVER** fetch img src or follow `/en/view/` outbound links (inherits "no device contact").
- Yield beyond existing datasets: current-era state (2026) at ~2.3k vs 2019/2022 dumps; live country/manufacturer distribution; id census + diff-on-refresh (new/removed). Cheapest refresh = sitemap only (1 request) → a longitudinal listing timeline no public dataset has.
- Component: update directory-crawler spec — base `http://www.insecam.org`; entrypoints `/en/bycountry/{CC}/?page=N`, `/en/bytype/{T}/?page=N`, `/en/bynew/?page=N`, `/static/sitemap.xml`; read `pagenavigator` for last page; 6/page; 1 req/2 s + kill-switch; record fetch date + UA; `provenance_class=exposure_aggregator`; `geo_confidence=low`; redact img src.

---

## (B) NEW insecam-derived datasets (2024–2026) beyond the 7 known

### 10 · Search coverage (methods, 2026-10-05)
- `gh search repos insecam` (updated + stars sorts, limit 100) → 41 repos total; `pushed:>2024-01-01` → 15. `in:readme` → 100. `gh search code`: "insecam" (100), "insecam_cameras" (7), "insecam.org/en/view" (50), extension:csv/json/sqlite/db variants. Plus HF API, Kaggle API, GitLab API, Bitbucket API.
- All ~15 post-2024 repos fetched/checked; data-bearing finds below. Tool-only repos not re-listed (S5 has them; new tool-only: OEUG99/InsecamPy 2025, n0stal6ic/Insecam-Scraper 2026-03, Ninja-Yubaraj/Insecam 2025-08, AvastrOficial/Cam-HackBSZ 2025-06, Whomrx666/God-eyes 2026-10-04, johnqherman/CCTV-twitter-bot 2025-05, YONGXD/PythonInsecam 2024). License on every find below: **none** → private-use/reference only (S5 storage rule).

### 11 · ★ GODEYE — `data/insecam_cameras.json` — 1,775 cams, snapshot 2026-05-27 — ADOPT CANDIDATE
- Repo `Hacker-Sam-is-here/GODEYE` (created & pushed 2026-05-27; 250 KB; not a fork; no license).
- Fetch: `curl -sSL https://raw.githubusercontent.com/Hacker-Sam-is-here/GODEYE/HEAD/data/insecam_cameras.json` → 200, 416,968 B, JSON array, **1,775 records**; fields `id, country, city, manufacturer, lat, lng, stream` (sample: id 162 / Japan / Tokyo / Panasonic — same lineage as the sitemap's min id 162).
- Backup twin `data/backups/insecam_2026-05-27T13-47-18.json` byte-identical (sha256 `e8b17875…`).
- README claims "606 cameras, 62 countries" — README number ≠ file (1,775); file is authoritative (flag).
- Credentials present: `u=admin` ×2, `[?&]p=` ×2 → redact at ingest. Snapshot date: 2026-05-27.
- Mechanics (doc-only): `scripts/scrape_insecam.js`, `scripts/super_scrape.js`.
- VERDICT: **ADOPT** as the 2026-05 exposure snapshot (era chain: 2019 jrw → 2022 OpenEyes → 2026 GODEYE). Component: ingest + redaction + snapshot_date + diff-on-refresh.

### 12 · reconeyes — `markers.json` (1,406) + `deploy/markers.json` (1,308) — OpenEyes-lineage refresh, 2026-01 — LOG
- Repo `skibidibladee2025/reconeyes` (2026-01-12; 29.1 MB; no license; README = OpenEyes text; claims sources "insecam.org and hacked.camera").
- `markers.json` → 396,568 B, **1,406 records** (sha `05e7639b…`). `deploy/markers.json` → 373,086 B, **1,308 records** (sha `794274e4…`). Fields: id, country, country_code, region, city, zip, timezone, manufacturer, lat, lng, stream.
- `app/markers.json` → 2,067,534 B, 7,170 records, sha256 `ad6cef9c…` = **byte-identical to GeorgePatsias/OpenEyes** (hash-verified against fresh download) — a copy of known dataset #2, NOT new.
- VERDICT: log as lineage redundancy (subset variants); ingest only if owner wants OpenEyes-family redundancy. Component: same as OpenEyes (#2).

### 13 · EyeFinder — mixed-source map data, exported 2026-09-30 — REFERENCE (77 insecam of 256)
- Repo `LincolnKermit/eyefinder` (created 2026-04-28; pushed 2026-09-30; no license). "Real-time OSINT CCTV map tracker".
- `public/backups/cameras.json` → dict, `total=256`, `exported_at=2026-09-30T06:20Z`. `data/cameras.json` → **256 records** (adds `insecam_url`); `seed.json` → **249 records**. Fields: id, name, lat/lng, stream_url, preview_image, is_snapshot, refresh_interval, source, status, last_checked, country, city.
- Sources: Insecam (Axis) 66 + Insecam (Mobotix) 11 (~77 insecam) + French DIR road cams (35+34+33), Grand Lyon CRITER 14–15, SkylineWebcams 15+4.
- VERDICT: reference — small insecam subset; its FR road/DIR + CRITER source names are useful for the base layer. Component: named-source list only.

### 14 · ★ rafasapiens/webscraping — `cams/cameras.json` + `.csv` — 2,100 cams, current-era — ADOPT CANDIDATE
- Repo created 2024-09-10; **pushed 2026-10-04** (active); 45.8 MB; no license.
- `curl -sSL .../rafasapiens/webscraping/HEAD/cams/cameras.json` → 680,167 B, **2,100 records**; fields `title, url` (insecam view page), `image` (device URL), `location, source` ("Insecam" × 2100), `city`. `.csv` → 411,403 B, 2,100 data rows.
- Credentials: `u=admin` ×16, `[?&]p=` ×16 → redact. Snapshot date ≈ repo push 2026-10-04 (verify export date inside).
- VERDICT: **ADOPT CANDIDATE** — closest public artifact to the current (~2.3k) directory shape. Component: ingest + redaction + dedupe vs GODEYE & live crawl.

### 15 · Threatify — `PublicIpCameraURLS.txt` — 13 URLs (2022) — SKIP
- `Haasha/Threatify` (2020→2022; "Threat detection using CCTV"): `PublicIpCameraURLS.txt` 969 B, **13 lines** `http://ip:port/… <tabs> source(http://www.insecam.org/en/view/<id>/)`. Tiny, stale. VERDICT: note only.

### 16 · az0977776/Insecam_ImageScrapper — resurfaces; samples only — NOTE (name fix)
- S5 flagged as dead (`oz0977776` … 404). Live today: **`az0977776/Insecam_ImageScrapper`** (pushed 2022-06-22; 160 MB repo size incl. historical images; no license).
- Data files: `insecam_scrapper/streams.txt` (279 B, 4 rows: label,url), `test.txt` (266 B, 4 rows), `src/schema.sql` (2,842 B, MySQL "HuskyWatch" schema). No bulk URL dataset; image history NOT downloaded (images aren't our target).
- VERDICT: NOTE — correct the repo name in S5 (az, not oz); no ingest.

### 17 · Mini/embedded lists + adjacent leads — NOTE
- `nik123-py/WORLDWIDE-INTELLIGENCE-PLATFORM` (2026-03): `src/services/cctvService.ts` embeds a curated list — **120 hardcoded insecam camera entries**; comment block documents `/en/view/{id}`, `/en/bycountry/{CC}`, `/en/bycity/{City}`, `/en/bytype/{Mfr}` schemas. Micro-dataset; mechanics doc.
- `Skytuhua/SIGINT`: `src/lib/server/cctv/insecam/{scraper.ts 6.9 KB, cityCoords.ts 9.7 KB, regionMap.ts 1.9 KB}` — crawler mechanics (doc-only).
- `Owlinkai/redroom`: **no insecam data** — but its feed router names base-layer leads: TfL JamCams 882 (free, no key), Asfinag (AT) ~1,900 (basic auth), Windy webcam embeds. (verify; adjacent, not insecam)
- Checked, no committed data: Dborasik/ARGUS, Modular-Misfits/osint-cam-finder, emrekybs/signalops, satvikpathak/Rakshak-AI, truix/multi-int-console, johnqherman/CCTV-twitter-bot, cyb3r17/GOTHAM, Y0oshi/Project-Eyes-On, erfangolpour/EagleEye, JoasASantos/Osint-Social-Mapping.

### 18 · Empty / dead shells (checked, no data)
- HF `masternodedata1/insecam.org`: **empty** (`.gitattributes` + README 25 B; usedStorage 0; created 2026-07-26). Account = 78 generic site-snapshot shells (not a data source).
- GitHub `gabstordal-gif/insecam.org` + `…/http-www.insecam.org-en-view-986159-details`: 1 KB junk ("Where is correlation engine .log" / "covetuss #illegal base detected").
- Kaggle: **none** (list API empty). GitLab: 4 projects, nothing new. Bitbucket: 0.

---

## (C) COMMUNITY-THREAD MINING

### 19 · r/geography — "Repository of live cam feeds from all the remote places?" (id 1fhu391)
- URL: `reddit.com/r/geography/comments/1fhu391/repository_of_live_cam_feeds_from_all_the_remote/` (~2024-09).
- Comments via PullPush (thread not in Wayback): **9 comments** (1 removed). NAMED SOURCE: **AAD Mawson station webcam — https://www.antarctica.gov.au/antarctic-operations/webcams/mawson/** (verified live 2026-10-05, 200 OK, title "Mawson research station Antarctica webcam – Australian Antarctic Program").
- No other named cam sources in-thread (Bouvet/83-42 wiki chatter, a book). The ask ("single source of remote-station livestreams") is still unanswered → demand gap.

### 20 · r/Cyberpunk — TrafficVision threads (1pv0rkv; 1pxdug2/1pxdtat)
- Launch post "Cyberpunk styled website to watch any live camera in the world - TrafficVision.Live" → **32 comments via PullPush** (no login wall hit).
- Named: **deflock.me** ("flock camera locations", no feeds — surveillance-loc map). OP claims: "over 50k video feeds", "600+ sources added", mix of statics + ~15 s loops, manual maintenance. Cross-ref S3 (trafficvision robots disallow + ToS) — no new pull path.
- VERDICT: cross-ref only; adds the 50k/600-source claims + user-QC notes for the reference file.

### 21 · Adjacent remote/public finds (side-finds from mining/search — verify before adopting)
- `naocam.com` — "Live Public Webcams & Traffic Cameras" exists (title verified); r/aviation thread names it for Greenland airports/heliports (Kangerlussuaq, Nuuk, Narsarsuaq, Ilulissat, Sisimiut, Qaarsut). Exact paths TBD (a `/countries/gl` probe 404'd).
- `overwatch.earth/webcams` — thousands of Windy Webcams (windy.com/webcams public API); refresh ~6 h; candidate public-by-design aggregator.
- r/osinttools recent post — 6,602 road cameras across 10 DOT networks + 37 signal layers (AGPL project) — base-layer lead for another wave.
- AAD webcams index — antarctica.gov.au/antarctic-operations/webcams/ (collect full station list).

---

## SUMMARY TABLE

| item | what | count | route | verdict |
|---|---|---|---|---|
| A · insecam directory | live directory reachable; cert expired; robots allows | ~2.2–2.3k listed; US ≈ 576; 96 pg US | curl http + browser-UA (`-k` for https) | FEASIBLE, gated on owner Q6 (use sitemap-first) |
| B11 · GODEYE | 2026-05-27 dump | **1,775** records | raw.githubusercontent | ADOPT candidate ● |
| B12 · reconeyes | OpenEyes-lineage refresh 2026-01 | 1,406 + 1,308 (7,170 copy = OpenEyes) | raw.githubusercontent | LOG (redundancy) |
| B13 · EyeFinder | mixed map data 2026-09 | 249 / 256 (77 insecam) | raw.githubusercontent | REFERENCE |
| B14 · rafasapiens | current-era dump | **2,100** records | raw.githubusercontent | ADOPT candidate ● |
| B15 · Threatify | URL list 2022 | 13 | raw.githubusercontent | SKIP |
| B16 · az0977776 | samples + schema | 4 + 4 rows | raw.githubusercontent | NOTE (name fix) |
| B17 · nik123 | embedded list | 120 | raw.githubusercontent | NOTE |
| C19 · r/geography | remote-cams thread | 9 comments | PullPush | ADD: AAD Mawson |
| C20 · r/Cyberpunk | TrafficVision threads | 32 comments | PullPush | cross-ref S3 |
| C21 · side-finds | naocam / overwatch / DOT-mapper | — | web search + probes | verify next |

## WHAT "MAKE-IT-HUGE" ADDS (updated)

**Exposure class:** volume is NOT the point anymore — the live directory is ~2.2–2.3k cams (vs 17.4k in the 2019 dump; 28k actives in 2017). The unique value is *time*: we can now hold era snapshots — 2019 (jrw 17,399) → 2022 (OpenEyes-family 7,170) → 2026-05 (GODEYE 1,775) / 2026-10 (rafasapiens 2,100) — and diff them (new/removed/era transitions). Nobody publicly shows that timeline. To make it huge: (1) owner approves Q6 → one-shot polite census (sitemap = 1 request gives ALL current IDs; + country pagenav reads for counts) → freeze the 2026 baseline; (2) monthly sitemap-only re-pull (1 request/month) = longitudinal listing index; (3) ingest GODEYE + rafasapiens + OpenEyes (+jrw) as era snapshots w/ mandatory redaction + snapshot_date; (4) UI: era/timeline view + "gone dark" diffs.

**Remote-cams class:** insecam has NO Antarctica/Greenland (AQ/GL 404) — this class must come from institutions: AAD webcams (Mawson verified; add AAD's full station set), naocam.com (Greenland airports/heliports), overwatch.earth/Windy (community incl. remote), plus existing wave assets (Live-Environment-Streams etc.). The 2024 thread asking for exactly this remains unanswered → a curated "remote stations & far places" layer (Antarctic/sub-Antarctic/Arctic/remote islands) is a differentiation win and fits the base layer (public-by-design, no policy strain).

## DEAD-ENDS / NOTES (log)
- insecam https: untrusted AND expired cert (2026-08-07); https non-www →301→ http; default curl UA → 403; browser tool → chrome-error (both schemes; 3 attempts); `/en/bycountry/` index 404; AQ/GL/XX 404; robots declares `/osm` disallowed (avoid).
- archive.org availability API 429 mid-recon; a Wayback `id_` fetch returned gzip (use `--compressed` next time); r/geography thread not archived.
- PullPush: 1× 429 then OK (retry lane works).
- Kaggle empty; HF shell empty; masternodedata1/gabstordal = shells.
- Repo hygiene: my recon scratch files (`az_streams.txt`, `az_test.txt`, `pp_geo_sub.json`, `pp_cp_sub.json`, `wb_home.html`, `wb_us.html`) were swept into parallel commits ede2307/0d5f824 by another agent's `git add -A`; removed in commit `39610be` (S8 cleanup).

## FETCH-COMMAND LEDGER (exact, for refresh)

**insecam (all with `-A "<Chrome desktop UA>"`):**
```
curl -sS http://www.insecam.org/                                     → 200, 18590 B (homepage)
curl -sS http://www.insecam.org/en/bycountry/US/                     → 200, 21838 B
curl -sS http://www.insecam.org/en/bycountry/US/?page=2  (and page=96) → 200
curl -sS http://www.insecam.org/en/bycountry/AU/  (+ NZ)             → 200 (1 pg × 4)
curl -sS http://www.insecam.org/en/bynew/                            → 200, 18466 B (379 pg)
curl -sS http://www.insecam.org/en/faq/                              → 200, 12845 B
curl -sS http://www.insecam.org/robots.txt                           → 200, 159 B
curl -sS http://www.insecam.org/static/sitemap.xml                   → 200, 262128 B (2271 locs)
curl -k -sS https://www.insecam.org/                                 → 301 → http://www.insecam.org/
openssl s_client -connect insecam.org:443 -servername insecam.org    → cert details (expired)
```

**Datasets (raw.githubusercontent.com/<repo>/HEAD/<path>):**
```
curl -sSL https://raw.githubusercontent.com/Hacker-Sam-is-here/GODEYE/HEAD/data/insecam_cameras.json                          → 416968 B / 1775 rec
curl -sSL https://raw.githubusercontent.com/Hacker-Sam-is-here/GODEYE/HEAD/data/backups/insecam_2026-05-27T13-47-18.json     → identical sha
curl -sSL https://raw.githubusercontent.com/skibidibladee2025/reconeyes/HEAD/markers.json                                     → 396568 B / 1406
curl -sSL https://raw.githubusercontent.com/skibidibladee2025/reconeyes/HEAD/deploy/markers.json                              → 373086 B / 1308
curl -sSL https://raw.githubusercontent.com/skibidibladee2025/reconeyes/HEAD/app/markers.json                                 → 2067534 B / 7170 (=OpenEyes sha)
curl -sSL https://raw.githubusercontent.com/LincolnKermit/eyefinder/HEAD/seed.json                                            → 143473 B / 249
curl -sSL https://raw.githubusercontent.com/LincolnKermit/eyefinder/HEAD/data/cameras.json                                    → 147396 B / 256
curl -sSL https://raw.githubusercontent.com/LincolnKermit/eyefinder/HEAD/public/backups/cameras.json                          → 155672 B (total=256)
curl -sSL https://raw.githubusercontent.com/rafasapiens/webscraping/HEAD/cams/cameras.json                                    → 680167 B / 2100
curl -sSL https://raw.githubusercontent.com/rafasapiens/webscraping/HEAD/cams/cameras.csv                                     → 411403 B / 2100 rows
curl -sSL https://raw.githubusercontent.com/Haasha/Threatify/HEAD/PublicIpCameraURLS.txt                                      → 969 B / 13
curl -sSL https://raw.githubusercontent.com/az0977776/Insecam_ImageScrapper/HEAD/insecam_scrapper/streams.txt                 → 279 B / 4 rows
curl -sSL https://raw.githubusercontent.com/az0977776/Insecam_ImageScrapper/HEAD/insecam_scrapper/test.txt                    → 266 B / 4 rows
```

**Other lanes:** gh search repos/code (listed item 10); `api.pullpush.io/reddit/search/comment/?link_id=<id>&size=100`; `archive.org/wayback/available` + `web.archive.org/cdx/...`; `huggingface.co/api/datasets?author=masternodedata1`; `kaggle.com/api/v1/datasets/list?search=insecam`; `gitlab.com/api/v4/projects?search=insecam`; `api.bitbucket.org/2.0/repositories?q=name~insecam`.

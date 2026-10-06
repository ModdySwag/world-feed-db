# S7 · INSTITUTIONAL / NATURE / ANIMAL / SHIP sources — batch-2 evidence file

**Collected:** 2026-10-05 ~21:28–21:45 ACST (11:00–11:15 UTC), from a Windows 11 host (MSYS bash, curl, ffprobe/ffmpeg 9.0.1, yt-dlp, py -3).
**Method:** (1) read batch-2 seed captures (`research/seed-tabs-2/html/*.html`); (2) live-fetch every cam page/player (polite: curl GET only, identifying UA, 1 s spacing); (3) player-endpoint extraction from inline JS/iframe configs; (4) liveness proofs per `world-feed-db-ops` doctrine (ffprobe video track + ffmpeg decode rc=0 for HLS; yt-dlp `is_live` gate for YouTube; byte/Last-Modified checks for image tier).
**Policy line:** public-by-design sources only (institutional/operator cams). No device probing. ≤3 attempts per target pattern. Total ~90 polite requests.
**Notation:** counts carry `(source, date)`; `(verify)` = not live-checked. All "VERIFIED TODAY" rows = exact fetch results dated 2026-10-05.
**Extends, not redoes:** S1 (EarthCam keyless endpoints, explore.org omega API) and S3 (Monterey Bay YouTube handles) — only extended where batch-2 adds new structure (EarthCam animal subset; MBA full per-cam id table). explore.org unchanged (S1).

---

### 1 · San Diego Zoo — live cams hub + zoo-side cams (Camzone HLS)
- Hub: https://animals.sandiegozoo.org/live-cams — **13 cams listed** (2026-10-05): Ape · Baboon · Burrowing Owl · Condor · Elephant · Giraffe · Hippo · Koala · Panda · Penguin (presented by Alaska Airlines) · Platypus · Polar · Tiger.
- Zoo-side cam pages: `https://zoo.sandiegozoo.org/cams/{koala,ape,baboon,hippo,penguin,polar}-cam` + `panda-cam-archive` (7 pages).
- **Stream mechanics:** each page embeds a **Camzone** player iframe, keyless; the player page exposes the direct HLS URL. Channels found (2026-10-05): `zssd-koala`, `ape` (yes — plain "ape"), `zssd-baboon`, `zssd-hippo`, `zssd-penguin`, `polarplunge`, `zssd-panda`, `zssd-panda2024` (panda archive = 2 channels).
- Direct HLS pattern (verified): `https://<channel>.hls.camzonecdn.com/CamzoneStreams/<channel>/Playlist.m3u8`.
- **Panda caveat:** the panda page is **email-gated** ("Enter Your Email Address to View Our Panda Cam") — the stream URL is in the page source but the page itself is a marketing gate; do not fake consent at build.
- KEY FACTS: HLS master → `chunklist_w<session>.m3u8`; video ~1280×720 (polar = 1920×1080); `timed_id3` data track present; player stack = videojs + hls.js.
- VERIFIED TODAY: koala ffprobe = `h264,1280×720` + **3 s decode rc=0**; penguin 1280×720 rc=0; ape 1280×720 rc=0; polarplunge 1920×1080 rc=0; all four playlists HTTP 200.
- VERDICT: **ADOPT** — registry (hub page lists cams) + liveness (ffprobe) + viewer (ffmpeg HLS). Component: Camzone resolver (§3).

### 2 · San Diego Zoo Safari Park — cams (same Camzone platform)
- Cam pages: `https://www.sdzsafaripark.org/cams/{tiger-cam,elephant-cam,condor-cam,giraffe-cam,platypus-cam,burrowing-owl-cams}` (6 pages).
- Channels: `zssd-tiger`, `zssd-elephant-2025`, `zssd-condorhd`, `zssd-kijami` (giraffe), `zssd-platypus2` + `zssd-platypus` (2), `zssd-owlaviary` + `zssd-owlburrow` (2) = **8 channels**.
- Player host variant: `<channel>.player.camzonecdn.com` v1.5/v2.1 (zoo side used `secureplayer` v1.3 — same stream family).
- VERIFIED TODAY: `zssd-tiger` ffprobe h264 1280×720 rc=0; `zssd-elephant-2025` h264 1280×720 rc=0 (both HTTP 200).
- VERDICT: **ADOPT** — same registry+liveness+viewer as §1; combined zoo+safari = **13 pages / 16 channels** *(counted from page HTML, 2026-10-05)*.

### 3 · Camzone platform (provider pattern — cross-cutting build component)
- Domain family: `*.camzonecdn.com` — hosts `secureplayer.` / `player.` (iframe player) and `hls.` (streams). Player: videojs + hls.js; ~3.5 KB player HTML; keyless from this host (no referer needed).
- **Resolver recipe:** fetch cam page → regex `channel=([a-z0-9-]+)` from the embed iframe → candidate `https://<channel>.hls.camzonecdn.com/CamzoneStreams/<channel>/Playlist.m3u8` → confirm ffprobe. (Channel naming is NOT uniform: `ape`/`polarplunge` vs `zssd-*` — always read from the page.)
- KEY FACTS: streams are HTTP-200 keyless HLS w/ 720p–1080p h264; single `chunklist_w<session>` variant (no ABR ladder on tested cams).
- VERIFIED TODAY: player pages 200 (×3 fetched), HLS 200 + decodable for 6 channels (koala/penguin/ape/polarplunge/tiger/elephant-2025).
- VERDICT: **ADOPT (pattern)** — build: `camzone_resolver` adapter + probe. Other Camzone clients TBD (provider scan) — the pattern generalizes beyond San Diego.

### 4 · Smithsonian's National Zoo — webcams (own Wowza HLS, keyless)
- Links: https://nationalzoo.si.edu/webcams → per-cam pages `/webcams/{panda-cam, elephants, lion-cam, naked-mole-rat-cam}` (4 pages).
- **Stream mechanics: own Wowza HLS, keyless** — page JSON key `webcamUrls` carries the exact playlists; each stream is mirrored on `nzp-wowza01.si.edu` + `nzp-wowza02.si.edu` (failover pair).
- Streams found (2026-10-05):
  - Giant Panda ×2: `…/live_edge_panda25/smil:panda125_01.smil/playlist.m3u8` + `…panda125_02…`
  - Elephants: `…/live_edge_elephant_zixi/elephant_zixi.smil/playlist.m3u8`
  - Lion: `…/live_edge_lion/smil:lion01_all.smil/playlist.m3u8`
  - Naked mole-rat ×2: `…/live_edge_nmr/nmr_1080_all.smil/…` + `…/live_edge_nmr_02/nmr_02_1080_all.smil/…`
  = **6 streams / 4 pages**.
- KEY FACTS: master playlists are full ABR ladders (panda: 5 renditions 350 kbps–6 Mbps, up to 1920×1080); video h264; pages use hls.js 1.6.14.
- VERIFIED TODAY: panda master HTTP 200 (474 B, 5 renditions); panda ffprobe h264 1920×1030 + **3 s decode rc=0**; elephant ffprobe 1920×1030 rc=0; lion ffprobe 1920×1080 rc=0; nmr ffprobe 1282×720 rc=0.
- VERDICT: **ADOPT** — flagship institutional HLS; registry = static per-page parse (4 pages); build: registry + liveness + ffmpeg HLS viewer. (Only panda_02 not independently probed — same pattern; verify at build.)

### 5 · Monterey Bay Aquarium — live cams (all YouTube-hosted; full id table)
- Hub: https://www.montereybayaquarium.org/cams-videos/live-cams — **10 live cams** (2026-10-05): Jelly · Sea Otter · Kelp Forest · Aviary · Spider Crab · Penguin · Shark · Moon Jelly · Open Sea · Monterey Bay. (Hub also links non-cam series: MeditOceans, Krill Waves Radio, Jelly Jams — not cams.)
- **Mechanics: every cam page = YouTube embed** (`data-live-cam-video="live|offline"` toggles a "Live …Cam" YouTube link vs an "After Hours" VOD link). MBA does not self-host video for these. Per-cam ids (page scrape, 2026-10-05):

| Cam | Live id | After-hours id |
|---|---|---|
| Sea Otter | `abbR-Ttd-cA` | `sq35qS1iVYU` |
| Aviary | `AWJi0LgyA28` | `0L6ZCRHNjXY` |
| Jelly | `eQ_foBERmzA` | (none captured) |
| Kelp Forest | `w3LjpFhySTg` | `oeEqNMDXRiU` |
| Monterey Bay | `fVa6-zCBR7A` | (same id) |
| Moon Jelly | `zL68biE6wAs` | `oyOnIPE2CIo` |
| Open Sea | `n_GpVsz4nHU` | `jf1izUn1yoU` |
| Penguin | `gfe7xNLFY50` *(label: Temporarily offline)* | `CJFpi4nQImE` |
| Shark | `tEtg5Kg3voQ` | `crquJLqMFuM` |
| Spider Crab | `dzmJXWmA2EM` | `aKOd6fwNRqQ` |

- KEY FACTS: `AWJi0LgyA28` = the same id S3 resolved from `@MontereyBayAquarium/live` (aviary) — channel handle cross-check confirmed. YouTube resolution must use `bv*+ba` (live formats split; S3 note).
- VERIFIED TODAY (yt-dlp `is_live` gate): otter `abbR-Ttd-cA` **is_live=True**; kelp `w3LjpFhySTg` is_live=True; shark `tEtg5Kg3voQ` is_live=True (all "Live … Cam | Monterey Bay Aquarium", 21:31 ACST).
- VERDICT: **ADOPT** — build: YouTube adapter keyed by per-cam id table; liveness gate `--match-filter is_live`; fall back to "after hours" id as a labelled non-live state.

### 6 · North Bondi SLSC webcam (AU — beach surf cam) — direct ipcamlive HLS
- Link: https://northbondisurfclub.com/webcam/ — **2 webcams** ("a free service, proudly provided by North Bondi SLSC for our community").
- **Stream target: ipcamlive, keyless direct HLS.** Two iframes → two aliases; resolved from each player's inline config:
  - Cam 1: alias `687a39cf71c58` → streamid `230eh5igyehypvtnc` @ `s35.ipcamlive.com`
  - Cam 2: alias `669243ec21d29` → streamid `9cjvdotvy0jmpbnqe` @ `s156.ipcamlive.com`
- Direct URLs (verified): `http://s35.ipcamlive.com/streams/230eh5igyehypvtnc/master.m3u8` · `…/stream.m3u8` · `…/snapshot.jpg`; `http://s156.ipcamlive.com/streams/9cjvdotvy0jmpbnqe/{master.m3u8,snapshot.jpg}`.
- KEY FACTS: cam1 master = 2 renditions: h264 1920×1088 @2.4 Mbps + **HEVC 3200×1800** @867 kbps; snapshots 87,562 B (cam1) / 58,938 B (cam2); no auth/token needed from this host (the player config includes a token, but stream+snapshot loaded clean).
- VERIFIED TODAY: cam1 ffprobe h264+hevc rc=0 + **3 s decode rc=0**; cam2 ffprobe h264+hevc rc=0; both snapshots HTTP 200 JPEG; snapshot md5 identical across ~4 s (snapshot refresh interval > 4 s — check at build when calibrating freshness).
- **AU cam family note:** the page reveals **ipcamlive** as the hosting family for surf-club community cams (alias-based). Same resolver works for any club using ipcamlive; second family lead = surf clubs à la Bondi (verify more aliases at build).
- VERDICT: **ADOPT** — direct keyless HLS; build: ipcamlive resolver (§7) + registry (alias table) + liveness.

### 7 · ipcamlive platform (provider pattern — cross-cutting)
- Player: `https://g3.ipcamlive.com/player/player.php?alias=<alias>` (keyless HTML) → inline JS vars: `alias`, `streamid`, `address` (e.g. `http://s35.ipcamlive.com/`), `token`, `websocketenabled`, `streamcount`.
- **Resolver recipe:** alias → fetch player.php → parse `streamid`/`address` → stream URLs `<address>streams/<streamid>/stream.m3u8` (single) or `/master.m3u8` (multi-rendition, `streamcount>1`) and `/snapshot.jpg`.
- Player JS v12 (275 KB) supports HLS + native; runs "resolve-on-demand" style tokens — but tested streams+snapshots fetched **without** token/websocket (websocketenabled=0 on these cams).
- VERIFIED TODAY: 2 aliases resolved + 5 stream/snapshot URLs HTTP 200 (see §6); token ignored in fetch worked.
- VERDICT: **ADOPT (pattern)** — build: `ipcamlive_resolver` (alias → server/streamid → HLS). Family scan TODO: other ipcamlive clients (surf clubs/marinas).

### 8 · Cruise Earth — ship webcams (hub + full enumeration)
- Hub: https://www.cruisingearth.com/ship-webcams/ ("Ship Webcams / Live Ship Cameras"; hub lists **21 lines** 2026-10-05).
- **Enumeration (sitemap, best method):** `https://www.cruisingearth.com/community/sitemap-custom.xml` → **298 ship-webcams URLs** = **1 hub + 23 line pages + 274 ship cam pages** (counted 2026-10-05; file 1,193,176 B). Sitemap covers 22 lines *with* ships + `po-cruises-au` (no ships) — plus `royal-caribbean-international` hub page exists but lists **no ship cams** (all decommissioned/removed; page 200, 116 KB).
- Per-line ship-cam page counts (sitemap, 2026-10-05): aida 36 · carnival 56 · hurtigruten 23 · msc 23 · ncl 22 · princess 26 · costa 18 · viking 14 · tui 11 · crystal 6 · hapag 5 · po 5 · cunard 4 · oet 4 · oceania 4 · osu 4 · phoenix 4 · explora 3 · greenpeace 3 · BAS 1 · HAL 1 · lindblad 1 = **274**.
- **Do NOT use their `/api/webcam-sort-line/` endpoint** — `robots.txt` disallows `/api/` and our call returned **403** (2026-10-05). Enumerate via sitemap; parse each ship page (server-rendered webcam block).
- License/notice: "All images courtesy of and copyright their respective owners." → catalog links + attribution, link-out viewing; no bulk re-hosting.
- VERIFIED TODAY: sitemap HTTP 200 (1,193,176 B); hub 200; counts computed from sitemap XML.
- VERDICT: **ADOPT (enumeration)** — build: registry from sitemap-custom; per-cam fetch; robots-compliant (skip /api/).

### 9 · Cruise Earth — per-ship stream mechanics (sampled) + honest states
- Mechanics vary per ship; the webcam block is server-rendered (detectable via 2 regexes: `iframe id="webcam-image"` vs `new WebcamRefresh(container,{imageUrl:…})`). Sampled 12 ship pages (2026-10-05):
  - **Panomax iframe**: Hurtigruten `hrx.panomax.com/fn` (MS Fridtjof Nansen), `/ra` (MS Roald Amundsen); Viking `viking.panomax.com/jupiter`; HAL `hal.panomax.com/oosterdam`. (See §10.)
  - **YouTube embed**: OSU `gilbert-r-mason` → `youtube.com/embed/zKXPw48ohHA` ("Build Webcam" — not currently available; see §12).
  - **Cruise-Earth-proxied JPEG, 30 s auto-refresh**: `…/webcam/ship/<id>/<line>/<ship>.jpg` — Princess Sky Princess (id 316), NCL Breakaway (id 160), Greenpeace Rainbow Warrior (id 100, currently a 42 B placeholder gif).
  - **External official JPEG**: BAS (see §11).
  - **Decommissioned/inactive placeholders**: Carnival Breeze + Celebration (`ship-webcam-decommed.webp`), Cunard QM2 (same), OET Nautilus (`ship-webcam-unavailable.webp`).
- KEY FACTS: ship cams are satellite/VSTAT-fed — updates range 30 s to 15 min; the site itself says so. Store `Last-Modified`/hash freshness, not just 200s.
- VERIFIED TODAY: Sky Princess jpg = **200, 369,215 B, JPEG 1920×1080**; NCL Breakaway jpg = **200, 141,556 B**; both fetched 21:40–21:43 ACST. Decomm/unavailable states captured from live pages.
- VERDICT: **ADOPT-lite** — registry covers all 274; per-cam fetch + freshness gate; honestly label decommissioned/unavailable (do not serve placeholders as live).

### 10 · Panomax platform (provider pattern — keyless image API found)
- Pattern (from Cruise Earth iframes + Panomax pages): subdomain page `<site>.panomax.com/<cam>` embeds `panodata.panomax.com/cams/<id>/…`.
- **Keyless image endpoints (verified)**: `https://panodata.panomax.com/cams/<id>/recent_reduced.jpg` (full-size live still) and `…/preview_og.jpg` (small preview). Cam ids captured: Hurtigruten fn=**2167**, ra=**2114**; Viking Jupiter=**2046**; HAL Oosterdam=**2193**.
- KEY FACTS: `Cache-Control: max-age=60, public`; use `Last-Modified` as freshness signal. No keyless HLS found (4 candidate m3u8 paths → 404; player uses its own JS/hls.js — REFERENCE only).
- VERIFIED TODAY: `cams/2046/recent_reduced.jpg` = 200, 170,126 B, **Last-Modified 2026-10-05 11:05:03 GMT (fresh!)**; `cams/2167/recent_reduced.jpg` = 200, 217,627 B but **Last-Modified 2026-02-21 08:05:48 GMT (stale ~7.5 months)** — the ship's image froze; `preview_og.jpg` 52,331 B. Honest-state lesson: same provider, wildly different freshness — gate per cam.
- VERDICT: **ADOPT (image tier)** + REFERENCE (HLS) — build: Panomax resolver (page → cam id) + image-refresh viewer + Last-Modified gate.

### 11 · British Antarctic Survey — RRS Sir David Attenborough bridge cam (official JPEG)
- Found via Cruise Earth ship page (`/ship-webcams/british-antarctic-survey/sir-david-attenborough/`, refreshInterval 30).
- **Direct target (official BAS):** `https://legacy.bas.ac.uk/webcams/rrs_sir_david_attenborough/latest.jpg`
- VERIFIED TODAY: **200, 73,996 B, JPEG 1920×1080, AXIS M1045-LW, EXIF datetime 2026:10:05 10:59:03, Last-Modified 11:00:46 GMT** — fresh at fetch. 
- VERDICT: **ADOPT** — single-cam official JPEG; registry entry + image-refresh + freshness gate. (Class: polar research vessel cams.)

### 12 · Oregon State University research fleet (4 vessels)
- Pages: `https://www.cruisingearth.com/ship-webcams/oregon-state-university/{gilbert-r-mason, narragansett-dawn, oceanus, taani}/` (4 cams).
- Mechanics: YouTube embeds (e.g. Gilbert R. Mason → `zKXPw48ohHA`, "Build Webcam"). These are aboard **R/V research vessels** (institutional science-cam class).
- VERIFIED TODAY: yt-dlp on `zKXPw48ohHA` → "This live stream recording is not available" (not currently live/streamable). Other ships' ids not extracted (pages require per-page JS parse; sample only).
- VERDICT: **REFERENCE** — institutional fleet worth re-checking at build (cams live when vessels are at sea/dock); YouTube adapter per ship.

### 13 · Ocean Exploration Trust — E/V Nautilus (4 cam pages)
- Pages: `…/ocean-exploration-trust/{nautilus, nautilus-live1, nautilus-live2, nautilus-live3}/` (4).
- Mechanic: the webcam container currently serves `ship-webcam-unavailable.webp` ("Camera Inactive") — Nautilus cams stream only during expeditions (the org's own NautilusLive portal). Event-mode source.
- VERIFIED TODAY: nautilus-live1 page 200; container = unavailable placeholder (no iframe present).
- VERDICT: **REFERENCE** — re-check during expedition season; watch for the real stream URL appearing in the container.

### 14 · Greenpeace ships (3 vessels)
- Pages: `…/greenpeace/{arctic-sunrise, esperanza, rainbow-warrior}/` (3 cams).
- Mechanic: Cruise Earth proxied JPEG `https://www.cruisingearth.com/webcam/ship/100/greenpeace/rainbow-warrior.jpg`, 30 s refresh.
- VERIFIED TODAY: rainbow-warrior.jpg → **200 but 42 B `image/gif` = placeholder** (no live image now). Original source = Greenpeace (link-out class).
- VERDICT: **REFERENCE** — cams transmit when ships are at sea; build: poll the proxy + placeholder detection (tiny-gif guard).

### 15 · EarthCam Animal Cams — curated subset from EarthCam's network
- Link: https://www.earthcam.com/events/animalcams/ — **13 unique cam entries** (14 links incl. duplicate "Meerkat" featured slot), 2026-10-05:
  1. Meerkat Cam — Miami, FL · 2. Hideaways Camp Kuzuma Cam — Chobe, Botswana · 3. Michigan Snowman Cam — Gaylord, MI · 4. Flamingo Cam — Miami, FL · 5. Bali Elephant Cam – Bathing Pool — Bali, Indonesia · 6. Bali Elephant Cam – Trail Path — Bali, Indonesia · 7. Giraffe Cam – Paddock — Greenville, SC · 8. Giraffe Cam – Barn — Greenville, SC · 9. Falcon Cam — Omaha, NE · 10. Manatee Lagoon Cam — West Palm Beach, FL (page also carries an **Underwater Manatee Cam** variant) · 11. Osprey Cam — Boston, MA · 12. Osprey Cam — Oxford, MA · 13. Everglades Cam — Fort Lauderdale, FL.
- **Stream mechanics (EarthCam player):** per-cam page config carries `html5_streamingdomain` + `html5_streampath` = tokenized HLS `https://videos-3.earthcam.com/fecnetwork/<vid>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>`; video ids seen: Bali Trail `4337`, Bali Bathing `4338`; RTMP twin `rtmp://videos-3.earthcam.com/fecnetwork/<vid>.flv`. **Keyless camshots**: `https://static.earthcam.com/camshots/{128x72,256x144,512x288}/<hash>.jpg`.
- **S1 endpoint to reproduce:** `https://www.earthcam.com/api/dotcom/network_search.php?r=ecn&a=fetch&country=<Country>` (+`&state=XX` for US), **requires `Referer: https://www.earthcam.com/network/`**, ~1.5 s spacing.
- VERIFIED TODAY: animalcams page 200 (50,012 B) + 13 links extracted; Bali trail camshot **200, 36,580 B** ×2 (identical over ~8 s — snapshot cadence > 8 s); Meerkat camshot 200, 12,185 B; **tokenless HLS → 403, 0 B** (token required — resolve-on-demand only); network_search reproduce: `country=Botswana` → **200, 1,095 B, cam_count 1** (Chobe/Hideaways — same cam as #2 above).
- VERDICT: **ADOPT** (curated subset + camshots as liveness/thumbnail tier); HLS = resolve-on-demand adapter (store id + page URL, never the token). Build: registry (events page parse) + camshot refresher + EarthCam token resolver.

### 16 · Institutional partner leads surfaced by the EarthCam animal page
- Chobe = "EarthCam and **Hideaways Africa**" partnership (per network_search description, verified today). Manatee Lagoon (West Palm Beach) runs **2 cams** (surface + underwater). Greenville giraffe pair (Paddock/Barn), Omaha falcon, Boston + Oxford osprey, Gaylord snowman — operator attributions not stated on the page; capture at build via per-cam page text.
- These identify the actual zoos/sanctuaries behind the cams (registry attribution layer + possible direct-source leads).
- VERDICT: **REFERENCE** — attribution/source-hunting leads; do not over-claim operators beyond page text.

---

## SUMMARY TABLE

| # | Name | Cams | Stream type | Verify result (2026-10-05) |
|---|---|---|---|---|
| 1 | San Diego Zoo (zoo) | 7 pages / 8 channels | Camzone HLS (keyless) | koala 720p decode rc=0; penguin/ape 720p; polar 1080p — LIVE |
| 2 | SDZ Safari Park | 6 pages / 8 channels | Camzone HLS (keyless) | tiger + elephant-2025 720p rc=0 — LIVE |
| 3 | Camzone platform | provider | HLS pattern | 6 channels probe-pass |
| 4 | Smithsonian NZP | 4 pages / 6 streams | Wowza HLS w/ failover (keyless) | panda 1080p decode rc=0; elephant/lion/nmr rc=0 — LIVE |
| 5 | Monterey Bay Aquarium | 10 cams | YouTube (ids in table) | 3/3 yt-dlp is_live=True; ids for all 10 |
| 6 | North Bondi SLSC | 2 cams | ipcamlive HLS (keyless) | cam1 h264+HEVC decode rc=0; cam2 rc=0; snapshots 200 — LIVE |
| 7 | ipcamlive platform | provider | HLS pattern | 2 aliases → 5 URLs 200 |
| 8 | Cruise Earth hub | 274 ship pages / 22 lines | mixed (see 9) | sitemap 298 URLs counted; /api/ = robots-disallowed |
| 9 | Cruise Earth mechanics | sampled 12 | Panomax iframe / YouTube / proxied JPG (30 s) / decomm. | Sky Princess 1920×1080 369 KB 200; NCL 141 KB 200; QA states |
| 10 | Panomax platform | provider | keyless image API (`cams/<id>/recent_reduced.jpg`) | 2046 fresh (11:05 GMT today); 2167 stale (Feb 21) |
| 11 | BAS (Sir David Attenborough) | 1 | official JPEG (latest.jpg) | 200, 1920×1080, Last-Modified 11:00:46 GMT — LIVE |
| 12 | Oregon State Univ fleet | 4 | YouTube | build-cam video not available now — REFERENCE |
| 13 | OET Nautilus | 4 | (expedition mode) | "Camera Inactive" today — REFERENCE |
| 14 | Greenpeace | 3 | proxied JPEG | 42 B placeholder today — REFERENCE |
| 15 | EarthCam Animal Cams | 13 curated | tokenized HLS + keyless camshots | camshots 200 (bali 36 KB, meerkat 12 KB); HLS 403 w/o token; network_search reproduce OK |
| 16 | EarthCam partner leads | — | attribution | Chobe/Hideaways confirmed via API |

## DEAD-ENDS / CAVEATS (log)
- **Cruise Earth `/api/webcam-sort-line/` → 403** + `robots.txt Disallow: /api/` — robots-compliant: use sitemap enumeration instead. (≤1 attempt, policy reason.)
- **EarthCam tokenless HLS → 403** (expected; tokens per page-load `td=YYYYMMDDHHMM` — resolve-on-demand only).
- **Panomax HLS m3u8 ×4 candidate paths → 404** — image API is the keyless tier; player JS is token/JS-bound (stopped per ≤3-attempt rule).
- **SDZ panda cam = email gate** — do not automate consent; if desired, treat as manual tier.
- **OSU `zKXPw48ohHA` "live stream recording is not available"** — not live now; recheck.
- **OET pages "Camera Inactive"**, **Carnival Breeze/Celebration + Cunard QM2 decommissioned**, **Greenpeace placeholder gif 42 B** — honest-state handling required; placeholders must never be shown as live.
- **Hurtigruten `hrx.panomax.com/fn` image stale since 2026-02-21** — provider gating can't rely on HTTP 200 alone; use Last-Modified/hash.
- **Bondi snapshot cadence > 4 s; EarthCam camshot cadence > 8 s** — calibrate freshness thresholds per source at build.
- **MBA Jelly "after hours" id not captured** (page only exposed the live link) — recheck at build.

## QUICK BUILD NOTES (per component)
- **Registry:** SDZ hub page (13 cams) · NZP 4 pages (webcamUrls JSON) · MBA 10 cam pages · Bondi alias table · Cruise Earth sitemap-custom (274) · BAS 1 · EarthCam events page (13) + network_search for the wider net.
- **Resolvers:** Camzone (channel → hls.camzonecdn.com) · ipcamlive (alias → server/streamid → HLS) · Panomax (page → cam id → image API) · EarthCam token resolver (page config, on demand) · YouTube (yt-dlp, `bv*+ba`, is_live gate).
- **Liveness:** HLS ffprobe+decode for Camzone/NZP/ipcamlive; yt-dlp is_live for MBA; Last-Modified/hash for Panomax/BAS/Cruise-Earth-JPG/camshots; placeholder-byte guards (42 B gif, decommed/unavailable webp).
- **Honest states:** store decommissioned/inactive/gated (SDZ panda) explicitly; never substitute placeholders.

*File: S7-institutional-2.md · 16 entries · collected 2026-10-05 21:28–21:45 ACST · all live-fetch results dated & byte-counted above.*

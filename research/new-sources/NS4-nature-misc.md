# NS4 — Nature / Animal / Vendor-Demo cluster (3 sites)

Researched 2026-10-06 (Cen. Australia). Host: Windows, MSYS bash; `curl` + `py -3.11`.
All curl commands below used `UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"` (shown as "$UA").

---

### Explore.org — https://explore.org/livecams
- **Scale:** 101 cam collections ("camgroups") in the official JSON; **239 unique camera feeds** (deduped feed slugs across all groups; e.g. Birds group id=6 has 70 feeds, brown-bears id=20 has 10). The hydrated DOM of /livecams renders ~235 `/livecams/` anchors. Counted 2026-10-06 by parsing the omega API (below), not by hand.
- **Feed types:** overwhelmingly **YouTube-hosted live streams** — each feed carries a `video_id` in the page JSON (Brooks Falls `J7ZrIDvqlic`, Penguins `GSxpCbXsvtI`, Wagcam `x0CloLdk44g`, Tembe `0P_LBKqVbfs`); cam pages embed `youtube.com/embed/<video_id>`. Stills are jpegs on `media.explore.org` / `files.explore.org`; live-edge snapshots come from `snapshots.explore.org` (timestamped `EXP-<name>-EDGE-<epoch>-scaled.jpg` — see Dead ends re DNS). No HLS/mjpeg found in samples.
- **Enumeration path:**
  1. `GET https://omega.explore.org/api/initial?contenttype=livecams` → JSON `{status, message, data:{ camgroups:[101] {id, slug, title, feed_count, feeds:[{id,title,slug,uuid}], channel_ids}, channels:[11], default_livecam:{...featured cam incl. video_id, stillframe, snapshot_enabled, stream_id, youtube_channel...}, snapshotToken }}`. Cam page URL = `https://explore.org/livecams/<camgroup_slug>/<feed_slug>`.
  2. Per-group liveness/snapshot list: `GET https://omega.explore.org/api/get_cam_group_snapshots.json?id=<camgroup.id>` → `{count, status, data:[ {id, slug, title, snapshot, thumb, stillframe_imageset, current_viewers, is_offline, force_offline, snapshot_enabled, stream_id, cam_group, primary_feed, ...} ]}` — full feed list for that group (birds id=6 → 70 items; brown-bears id=20 → 10).
  3. Per-feed YouTube id: fetch any cam page HTML and regex the embedded feed records `"slug":"<feed_slug>","camgroup_slug":"<group>","video_id":"<id>"` — each cam page carries its whole group's feed list, so one page per group harvests slug→video_id for all its feeds. Verified across 5 pages (brooks, penguin, wagcam, tembe, decorah); every extracted id resolved to a matching live oembed title.
- **Sample verification** (fetched 2026-10-06):
  - `curl -sL -A "$UA" -o omega.json -w "%{http_code} %{size_download} %{content_type}\n" "https://omega.explore.org/api/initial?contenttype=livecams"` → `200 277396 application/json`
  - `curl -sL -A "$UA" -o /dev/null -w "%{http_code} %{size_download} %{content_type}\n" "https://media.explore.org/stillframes/Bear-Cam-Brooks-Falls-028538749__media_1280x720.jpg"` → `200 168435 image/jpeg`
  - `... "https://files.explore.org/files/Bear-Cam-Brooks-Falls-028538749.jpg"` → `200 246492 image/jpeg`
  - `curl -s -A "$UA" "https://www.youtube.com/oembed?url=https%3A//www.youtube.com/watch%3Fv%3DJ7ZrIDvqlic&format=json"` → `200 {"title":"LIVE Brooks Falls - Katmai National Park, Alaska 2026 | explore.org","author_name":"Explore Live Nature Cams", ...}`
  - `https://snapshots.explore.org/EXP-BrooksFalls-EDGE/EXP-BrooksFalls-EDGE-1791218027-scaled.jpg` → DNS failure from this host (both curl and Python) — see Dead ends.
- **Provenance:** public_by_design — Explore.org (Annenberg Foundation) operates/publishes this cam network itself for public viewing; open JSON API, no auth seen.
- **Constraints:** robots.txt = `User-Agent:* / Allow:/` + sitemap. omega API no auth observed. Feeds are mostly YouTube → embedding/recording subject to YouTube ToS; for monitoring prefer the snapshot JSON's `is_offline`/`current_viewers` flags plus oembed/video_id checks. Many feeds are seasonal.
- **Fold-in verdict:** **ADD NOW** — family `explore-omega` (nature network, biggest single win: ~239 feeds). Ingester: poll initial + per-group snapshots JSON; keep slug→video_id map for YouTube-side health checks.

---

### Edinburgh Zoo — https://www.edinburghzoo.org.uk/animals/webcams
- **Scale:** 6 cams: giraffe, koala, lion, penguin, tiger (under `/animals/webcams/<x>-cam`) + rockhopper (`/webcams/rockhopper-cam`). 5 emit a Streamdays player; koala currently renders "There appears to be a problem / Please check back later." (offline at test time).
- **Feed types:** HLS only (Flowplayer + hls.js inside a Streamdays vendor iframe) — no jpeg/mjpeg found. YouTube channel link on the page is promo only.
- **Enumeration path (vendor = Streamdays):**
  1. Each cam page's `.video` div contains `<script src="https://live.streamdays.com/<8-char-code>" type="text/javascript">` — must be fetched with `Referer: <the zoo cam page>` (bare fetch → 403).
  2. That JS `document.write()`s a loader pointing to `https://live.streamdays.com/<code>/iframe?authorization=<signed-token>` (token format `<base64>--<sha1>`).
  3. Fetch the iframe URL (Referer: zoo page) → HTML (Flowplayer config). HLS source inside: `https://takeoff.jetstre.am/?account=streamdays&type=live&service=wowza&protocol=https&token=<tok>&output=playlist.m3u8&file=EdinburghZoo-<Name>-<num>` → 307 redirect → master playlist `https://n2.cdn.jetstre.am/session/<session>/sz/streamdays/wowza4/live/<file>/playlist.m3u8?token=..&time=..` → `chunklist.m3u8` → `media_<seq>.ts`.
  Codes found: penguin `xb1u3eln`, lion `2ej7o9e5`, giraffe `mlhwz7bt`, tiger `y4trtxbp`, rockhopper `67u7il21`.
- **Sample verification** (fetched 2026-10-06):
  - `curl -s -A "$UA" -H 'Referer: https://www.edinburghzoo.org.uk/animals/webcams/penguin-cam' -o sds.js -w "%{http_code} %{size_download} %{content_type}\n" "https://live.streamdays.com/xb1u3eln"` → `200 1694 application/javascript` (contains `/xb1u3eln/iframe?authorization=...`).
  - Same URL without Referer → `403` (empty).
  - `curl -sL -A "$UA" -H 'Referer: https://live.streamdays.com/' "<takeoff.jetstre.am playlist.m3u8 URL from the iframe>"` → `200 235 application/vnd.apple.mpegurl` (master playlist).
  - chunklist fetch → `200 368 application/vnd.apple.mpegurl` (`#EXT-X-MEDIA-SEQUENCE`, `media_*.ts` lines); first media chunk → `200 200000 video/MP2T`, head `4740001a` (TS sync byte).
- **Provenance:** public_by_design — RZSS/Edinburgh Zoo publishes its own animal cams for public viewing via a commercial streaming vendor (Streamdays).
- **Constraints:** Referer required for script+iframe (403 otherwise); authorization tokens are short-lived (a takeoff URL fetched ~19 min after discovery had 307'd to a fresh signed session — re-derive the whole chain per poll); robots.txt disallows only admin/user paths.
- **Fold-in verdict:** **ADD NOW** — family `streamdays` (VENDOR family, not just this zoo). Any site embedding `live.streamdays.com/<code>` or `live.streamdays.com/bespoke-hosting/<project>/<file>.html` enumerates the same way; confirmed other embedders exist (Derby Cathedral peregrines `.../bespoke-hosting/derbyperegrines/left.html`; Len Pick Trust `.../lenpicktrust/camera01.html`) — follow-up sweep recommended.

---

### Camsecure Live Demo Index — https://www.camsecure.co.uk/Camsecure_Live_Demo_Index.html
- **Scale:** index lists 32 demo/location pages (crawled 2026-10-06); **30 pages have a player wrapper and all 30 yield a feed** (28 HLS + 2 YouTube); the other 2 are non-cam pages (Christmas TV channel, Tennis Club page whose wrapper is gone). Index pages cross-link further location pages (Dorset/Devon cams etc.) — expansion possible beyond the index set.
- **Feed types:** HLS (MPEG-TS segments) ×28; YouTube embeds ×2 (Lapland/Levi `LwihxyJ4V20`, Isle of Wight Steam Railway `b7xdKcf6TRE`). Without the correct Referer the wrapper serves a PNG placeholder "This Website Is Not Authorised to Show This Content" (108,341 bytes, 571×411, md5 `1efc2f418c5742bcbfc55a43662a1bbb`) — anti-hotlink guard, not a feed.
- **Enumeration path:**
  1. Parse cam-page links from the index (e.g. `/ballyholme_webcam.html`, `/Camsecure2/Weymouth_Seafront_Webcam.html`, `/Camsecure3/Brixham_Harbour.html` …).
  2. Each cam page contains an iframe `//camsecure.(co|uk)/httpswebcam/camsecure/<code>.html` — include protocol-relative `//` (5 wrappers missed without it).
  3. Fetch the wrapper **with `Referer: <its cam page URL>`** → small HTML with `<source src="/HLS/<name>.m3u8">`; resolve against the wrapper host (camsecure.co or camsecure.uk).
  4. Fetch the playlist → segment URLs `https://<host>/HLS/<name>-<seq>.ts` — use the LAST (live-edge) segment; older ones 404. Wrapper code ≠ stream name (weymouth → `bayvwebcam.m3u8`), so parse, don't construct.
  Code→media map (30 rows, from cs-hls.tsv):
  | Index page | wrapper code | media |
  |---|---|---|
  | /BudeBeach.html | bude | https://camsecure.co/HLS/potandbarrel.m3u8 |
  | /Camsecure2/Weymouth_Seafront_Webcam.html | weymouth | https://camsecure.co/HLS/bayvwebcam.m3u8 |
  | /Camsecure3/Brixham_Harbour.html | brixham1 | https://camsecure.co/HLS/brixham.m3u8 |
  | /Camsecure3/Dundee_Webcam.html | royaltay | https://camsecure.uk/HLS/royaltay.m3u8 |
  | /Camsecure3/ilfra2.html | ilfracombe2 | https://camsecure.co/HLS/ilfracombe1camz.m3u8 |
  | /Christmas/FinlandChristmasWebcam.html | Christmas/levi1 | YouTube: https://www.youtube.com/embed/LwihxyJ4V20 |
  | /CoastwatchRedcarWebcam.html | redcar1 | https://camsecure.co/HLS/redcar1.m3u8 |
  | /FramptonLake.html | frampton1 | https://camsecure.co/HLS/frampton1.m3u8 |
  | /Portmeirion.html | portmeirion1 | https://camsecure.co/HLS/portmeirion1.m3u8 |
  | /Ruin_Beach_Cafe.html | scillyrb | https://camsecure.co/HLS/tresco2.m3u8 |
  | /SouthportPierWebcam.html | silcock | https://camsecure.co/HLS/silcock.m3u8 |
  | /StIves1.html | stives1 | https://camsecure.co/HLS/stives1a.m3u8 |
  | /WinkingMan.html | winkingman | https://camsecure.co/HLS/winkingman.m3u8 |
  | /arnside pier webcam.html | arnside | https://camsecure.co/HLS/arnside.m3u8 |
  | /ballyholme_webcam.html | ballyholme | https://camsecure.uk/HLS/ballyholmecam.m3u8 |
  | /bexhill_on_sea_webcam.html | bexhill | https://camsecure.co/HLS/bexhill2feed.m3u8 |
  | /derwent_water_webcam.html | derwentwater | https://camsecure.co/HLS/lingholmestate.m3u8 |
  | /felixstowe_beach_webcam.html | felixstowe | https://camsecure.co/HLS/felixpl.m3u8 |
  | /island_sailing_club.html | iowsailing | https://camsecure.co/HLS/iowsailing2.m3u8 |
  | /isle_of_man_webcam.html | scarlettsequence | https://camsecure.uk/HLS/scarlettsequence.m3u8 |
  | /isle_of_wight_steam_railway_webcam.html | yt/iowsteam1 | YouTube: https://www.youtube.com/embed/b7xdKcf6TRE |
  | /kingston_upon_thames_webcam.html | minimayc | https://camsecure.uk/HLS/minimayc.m3u8 |
  | /lee_on_the_solent_webcam.html | lossc | https://camsecure.uk/HLS/lossc.m3u8 |
  | /llangrannog_beach_webcam.html | pentre | https://camsecure.co/HLS/pentreplaylistz.m3u8 |
  | /oban bay webcam.html | greystones | https://camsecure.uk/HLS/greystonesoban.m3u8 |
  | /portishead_webcam.html | portishead | https://camsecure.uk/HLS/portishead.m3u8 |
  | /ullswater_lake_webcam.html | ullswater | https://camsecure.co/HLS/netconnex2.m3u8 |
  | /whitby lifeboat webcam.html | whitbylifeboat | https://camsecure.uk/HLS/whitbynci.m3u8 |
  | /whitstable-webcam.html | whitstableyacht | https://camsecure.co/HLS/wyc.m3u8 |
  | /PSGC.html | psgc2 | https://camsecure.co/HLS/psgc2.m3u8 |
- **Sample verification** (fetched 2026-10-06):
  - Wrapper with Referer: `curl -s -A "$UA" -H 'Referer: https://www.camsecure.co.uk/ballyholme_webcam.html' "https://camsecure.uk/httpswebcam/camsecure/ballyholme.html"` → `200 text/html 2282` (video.js player page). Same URL **without Referer** → `200 image/png 108341` (placeholder).
  - `curl -s -A "$UA" "https://camsecure.uk/HLS/ballyholmecam.m3u8"` → `200 191 M3U8/Playlist`; live-edge segment (refetched playlist) → `200 1577320 MPEG2TS/Stream`, head `4740e039` (TS sync).
  - `curl -s -A "$UA" "https://camsecure.co/HLS/brixham.m3u8"` → `200 181 M3U8/Playlist`; segment → `200 2011412 MPEG2TS/Stream`, head `4740e037`.
  - m3u8s are open (no Referer needed): `no-ref m3u8 http:200 type:M3U8/Playlist`.
- **Provenance:** public_by_design (vendor-demo) — Camsecure host these cams for clubs/venues and publish them for public viewing as demos of their hosting service ("Live Demo Index"). Not an aggregator of third-party/exposed cams; single HLS origin. Flag: commercial vendor context — if the registry wants a `vendor_demo` distinction, keep this in one.
- **Constraints:** wrapper requires same-site Referer (else placeholder PNG); no robots.txt (404); pages are ad/analytics heavy; segments rotate fast (live edge only); stream names must be parsed per cam.
- **Fold-in verdict:** **ADD NOW** — family `camsecure-webcams` (30 feeds).

---

## Dead ends
- `snapshots.explore.org` does not resolve from this host (curl `exit 6 "Could not resolve host"`, Python `gaierror 11001`) → Explore live-edge snapshot jpgs unverifiable here; rely on `media.explore.org` stillframes or snapshot-API metadata (`is_offline`, `current_viewers`).
- Edinburgh koala cam offline at test time ("There appears to be a problem") — no streamdays code emitted.
- Headless-browser screenshots of the Edinburgh penguin page timed out twice (`Page.captureScreenshot` 60s) → abandoned in favour of HTTP-level proof (script + m3u8 + chunk fetches).
- Camsecure: an old `.ts` segment fetched ~1 min late returned 404 HTML (segments purge quickly) — always refetch the playlist and use the last segment.
- Camsecure index also lists non-cam pages (ProductSupport, sitemap, CamsecureIPNetworkWebcams, christmas_tv) — excluded from the 30 count; Tennis Club London page now has no wrapper.
- Explore `default_livecam` is a single featured cam, not an all-cams endpoint; `data.gfy` was empty at test time.
- YouTube-embed check for Camsecure's Levi cam (`LwihxyJ4V20`) only inspected as an embed URL; no oembed verified for it.

## Method notes
- Tools: curl (UA-spoofed) + Python urllib for batch passes; headless Chromium via CDP (`performance.getEntriesByType('resource')`) was what exposed `omega.explore.org/api/initial` (the raw `/livecams` HTML is a Next.js shell with no feed links).
- Key techniques: (1) Referer probes to reveal anti-hotlink wrappers; (2) live-edge (last) segment fetches as working-stream proof, with TS sync-byte check; (3) include protocol-relative `//` iframes when crawling (first pass missed 5 wrappers).
- Scratch artifacts (session cache, may be pruned): `$TMPDIR/ns4/explore-feeds.tsv` (239 feed page URLs), `cs-cams.tsv` (index→wrapper map), `cs-hls.tsv` (30-row code→m3u8 map), plus raw HTML snapshots (`brooks.html`, `sds-iframe.out`, …).
- All fetches were GET-only against published feed/player URLs; no admin/PTZ/login endpoints touched anywhere.

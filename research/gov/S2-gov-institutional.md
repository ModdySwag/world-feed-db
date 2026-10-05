# S2 · GOVERNMENT + INSTITUTIONAL public live-camera sources (worldwide) — evidence file

**Collected:** 2026-10-05, ~21:00–22:40 ACST (UTC+10:30), from Moddy's Win11 host (MSYS bash, curl, python3).
**Method:** (1) mined the real scraper code of two repos — `GoSlowPoke168/Argus` (`scripts/scrapers/*`) and `AidanWelch/OpenTrafficCamMap` (`compilation/*`, `compilation/USA/*.mjs`) — both freshly cloned 2026-10-05; (2) live probes with curl (limit 1–2 requests/source, polite UA, no auth where possible); (3) targeted web research via search/extract for international + institutional sources.
**Policy line:** public-by-design sources only. No probing of private/exposed cameras; no credentials used; ~60 polite requests total.
**Notation:** counts carry `(source, date)`; `(verify)` = not live-checked. Every "VERIFIED TODAY" records the exact fetch result (HTTP status / bytes / type). Repo-mined endpoints are marked `[Argus code]` / `[OTC code]` and were NOT separately live-fetched unless a verify line says so.

**Headline counts from repo mining (2026-10-05):**
- Argus README: **229,308 cameras total** in its store (only `windy` needs an API key; every other source keyless).
- OpenTrafficCamMap README: "**7515 traffic cameras**"; its `cameras/USA.json` (clone today) = **7,029 cams across 10 states** (mid-migration; `v1` branch holds previous data).
- Seed inventory (`world-feed-db/research/seed-tabs/data/LES-sources.json`, 2026-10-05): vdot 1168 · mdsha 404 · deldot 261 · autobahn_nrw 252 · iowa_dot 50 · nysdot 23 · vegvesen 22 · taiwan_freeway 18 · ktict 20 · opencctv 746 · trafficvision(TH) 245.

---

### 1 · Caltrans CCTV (California DOT, US) — full 12-district coverage
- Discovery JSON: `https://cwwp2.dot.ca.gov/data/d<N>/cctv/cctvStatusD<NN>.json` for N=1..12 (dir `d<N>`, file zero-padded `D01`…`D12`).
- Stream pattern: `https://wzmedia.dot.ca.gov/D<N>/<cameraID>.stream/playlist.m3u8` (HLS). Stills: `imageData.static.currentImageURL` (~2 min refresh; `currentImageUpdateFrequency` = minutes in JSON).
- KEY FACTS: per-cam fields `index`, `inService`, `location.{latitude,longitude,route,county}`, `imageData.static.currentImageURL`, `imageData.streamingVideoURL`. Only some cams carry `streamingVideoURL` (D10: 8 of 154 on 2026-10-03). License: US public agency / public domain-style.
- VERIFIED TODAY: **D12 JSON = HTTP 200, 1,344,754 B, 419 cams** (sample stream `…/D12/SB5MagnoliaAveSO91.stream/playlist.m3u8`); **D03 JSON = HTTP 500** (persists from WV1 test on 2026-10-03 — D03 broken server-side). D10 frame grab 42,603 B on 2026-10-03 (WV1). D02 loop: `for d in $(seq -w 1 12)`.
- VERDICT: **ADOPT** — flagship keyless HLS + stills; build components: **registry** (crawl 12 district JSONs, skip 500s) + **viewer** (ffmpeg HLS → frames). Extend WV1: use all districts, retry D03 later.

### 2 · Mid-Atlantic HLS trio — VDOT (Virginia) + MD SHA + DelDOT
- VDOT: 1,168 cams; stream pattern `https://media-sfs{2,6,8}.vdotcameras.com/rtplive/<id>/playlist.m3u8` [LES seed]. Enumeration geojson `https://www.511virginia.org/data/geojson/icons.cameras.geojson` — **stale today** (301 → Angular SPA HTML; re-derive list).
- MD SHA (CHART): 404 cams; streams `https://strmr{3,5}.sha.maryland.gov/rtplive/<32-hex>/playlist.m3u8` [LES seed]. Enumeration JSONP `https://chartexp1.sha.maryland.gov/CHARTExportClientService/getCameraMapDataJSON.do?…callback=Ext.data.JsonP.callback6&page=1&start=0&limit=25` → follow `publicVideoURL` page-scrape for `src:` [OTC code].
- DelDOT: enumeration `https://tmc.deldot.gov/json/videocamera.json` — fields `cameraCount`, `videoCameras[].urls.{m3u8,m3u8s,rtmp,f4m}`.
- KEY FACTS: protocol HLS everywhere; all three are state DOTs publishing for traveler info (US public-record).
- VERIFIED TODAY: VDOT master playlist HTTP 200, 126 B (chunklist, 320×240) for `…/rtplive/38iggm3xn7t5tr9grypj6mmtuxjp165p/playlist.m3u8`; MD `…/strmr5.sha.maryland.gov/rtplive/0901227b…d0a/playlist.m3u8` HTTP 200, 126 B; **DelDOT JSON HTTP 200, 184,004 B — `cameraCount: 361`** (LES said 261 → grown); DelDOT HLS `https://video.deldot.gov:443/live/KCAM001.stream/playlist.m3u8` HTTP 200, 125 B (1280×720).
- VERDICT: **ADOPT** all three (registry+liveness; DelDOT best-verified: JSON + direct HLS URLs).

### 3 · Verified US DOT JSON trio — Iowa · Ohio · Washington (metrics + direct imagery)
- **Iowa DOT**: ArcGIS `https://services.arcgis.com/8lRhdTsQyJpO52F1/ArcGIS/rest/services/Traffic_Cameras_View/FeatureServer/0/query?where=1%3D1&outFields=*&f=pjson` (+ `returnCountOnly=true`), fields `ImageURL`, `VideoURL`, `Route`, `latitude/longitude` [Argus code]. HLS `https://iowadotsfs1.us-east-1.skyvdn.com/rtplive/<camId>/playlist.m3u8` (`…/thumbs/<id>.flv.jpg` → id extract) [Argus+OTC code]. Alt 511ia GraphQL `https://www.511ia.org/api/graphql`.
- **Ohio (OHGO)**: `https://api.ohgo.com/roadmarkers/cameras?pointData=%7B%22lowLongitude%22…%7D` → array of sites each with `Cameras[]{Direction,SmallURL,LargeURL}`; images direct JPEGs at `https://itscameras.dot.state.oh.us/images/<region>/<name>.jpg`. Second variant: `https://api.ohgo.com/roadmarkers/TrafficSpeedAndAlertMarkers?pointData=…` [OTC code].
- **Washington WSdot**: `https://data.wsdot.wa.gov/travelcenter/Cameras.json` (GeoJSON; **encoding latin-1/CP1252, not UTF-8**) → `features[].attributes.ImageURL` e.g. `https://images.wsdot.wa.gov/sw/005vc00320.jpg` (region folder `sw`, `or`…; some border cams served from tripcheck.com CDN).
- VERIFIED TODAY: Iowa count `{"count":1260}` (HTTP 200, 14 B; note: one HLS fetch attempt from this host timed out — re-test); Ohio HTTP 200, 444,545 B, **1,161 cams** in bbox −85..−80 / 38..42.5 (+ image 200, 17,058 B, 352×240 "OPTC"); WSdot HTTP 200, 407,631 B, **1,706 features**; VDOT/MD verified in §2 (Iowa HLS = code+LES only).
- VERDICT: **ADOPT** Ohio + WSdot fully (registry+liveness+viewer); **ADOPT-lite** Iowa (JSON solid; re-test skyvdn streaming at build).

### 4 · Road511 multi-state gateway (US, 20 states) — now key-gated
- Endpoint: `https://api.road511.com/api/v1/features?type=cameras&jurisdiction=<ST>&limit=500&offset=<N>` → `{data[],has_more}`; props `image_url`, `video_url` per cam [Argus code].
- States shipped in Argus run: **FL UT WA OR CO SC IN TN AZ KS AR OH KY NE DE MA WY ND SD MT** (image-confirmed in code); excluded (no usable URLs): TX NC WI GA NV PA MI ID LA MS CT ME NH WV VT.
- Broken stream hosts list (drop `video_url`): `trafficwise.org` (IN), `kdot-sfs` (KS), `actis.idrivearkansas.com` (AR), `api.trafficland.com` (MA).
- VERIFIED TODAY: `…jurisdiction=WY&limit=3` → **HTTP 401** `{"error":…}` (anonymous access now denied → key required, 2026-10-05).
- VERDICT: **REFERENCE** — free key now needed; keep as one-request multi-state discovery layer (build: discovery; verify key terms).

### 5 · OpenTrafficCamMap "Iteris-class" 511 group (US + Ontario)
Per-state (all `[OTC code]`, 2026-10-05 clone; iterate states at build):
- **FL**: `https://fl511.com/map/mapIcons/Cameras` → per-cam `https://fl511.com/map/Cctv/<itemId>` (IMAGE_STREAM; server limit: 100 req/min, 20/s).
- **LA**: `https://www.511la.org/map/mapIcons/Cameras` → tooltip scrape `data-videourl` (M3U8; same vendor as FL).
- **GA**: `https://511ga.org/List/GetData/Cameras?query=<json{start,length:100000}>` → `videoUrl` (M3U8) or `https://511ga.org/map/Cctv/<id>`. **VERIFIED TODAY: HTTP 500 twice** (needs browser-like session; re-test).
- **AK**: `https://511.alaska.gov/List/GetData/Cameras` → `https://511.alaska.gov/map/Cctv/<groupedId>`.
- **AZ**: `https://az511.gov/List/GetData/Cameras` → `https://az511.gov/map/Cctv/<groupedId>`.
- **WI**: `https://511wi.gov/List/GetData/Cameras?query=<json>` → `https://511wi.gov/map/Cctv/<id>`.
- **MN**: `https://lb.511mn.org/mnlb/cameras/routeselect.jsf` (JSF scrape → img src).
- **MS**: `https://www.mdottraffic.com/` frame scrape → `https://streamingjxn<server>.mdottraffic.com/rtplive/<cam_id>.stream/playlist.m3u8`.
- **ON (Canada)**: `https://511on.ca/List/GetData/Cameras?query=<json length:100000>` + `Accept: application/json` + `X-Requested-With: XMLHttpRequest` + Referer `https://511on.ca/cctv` → **HTTP 200, 140,229 B, recordsTotal 925**; image `https://511on.ca/map/Cctv/<id>` → **HTTP 200, 157,201 B JPEG (AXIS Q6054, 1280×720)**.
- VERIFIED TODAY: ON full flow (200s above); GA 500; others = code-only.
- VERDICT: **ADOPT for ON** (verified, keyless) — merge into Canada entry; **REFERENCE** for US members (mine individually; the `List/GetData/Cameras` shape is shared with GA/WI/AK/AZ).

### 6 · OpenTrafficCamMap "GraphQL-511" group (KS · NE · CO · IN + IA alt)
- All use the same `mapFeaturesQuery` graph query returning `mapFeatures[].views[]{uri,url,category,sources[]{src}}` [OTC code]:
  - KS `https://kandrive.org/api/graphql`; NE `https://new.511.nebraska.gov/api/graphql`; CO `https://www.cotrip.org/api/graphql`; IN `https://511in.org/api/graphql`; IA `https://www.511ia.org/api/graphql`.
- Query template (abbrev., full text in repo): `query MapFeatures($input:MapFeaturesArgs!){mapFeaturesQuery(input:$input){mapFeatures{bbox tooltip uri … on Camera{views(limit:10000){uri … on CameraView{title category uri url sources{type src}}}}}}}` — CO/IN note: `zoom: 1` avoids clustering; camera ids ≈400–100000; larger requests rejected.
- VERIFIED TODAY: not individually fetched (Iowa covered via ArcGIS §3; the 511ia `views` url → skyvdn HLS build rule `https://iowadotsfs1.us-east-1.skyvdn.com/rtplive/<id>/playlist.m3u8`).
- VERDICT: **REFERENCE** — high-value JSON APIs (CO/IN/K S/NE); build a shared GraphQL query module at prototype stage.

### 7 · OpenTrafficCamMap direct-JSON / XML / KML group (14 agencies)
Per-agency (all `[OTC code]`):
- **TX**: POST `https://its.txdot.gov/ITS_WEB/FrontEnd/svc/DataRequestWebService.svc/GetCctvDataOfArea` body `{"arguments":"<camUrlKey>,100,-200,0,0"}`; image via `GetCctvContent` (CSV; slice from `data` = base64 JPEG). Argus adds snapshot resolver: `GET https://its.txdot.gov/its/DistrictIts/GetCctvSnapshotByIcdId?icdId=<id>&districtCode=<district>` → `{snippet: base64 JPEG}` (no CORS header).
- **MO**: `http://traveler.modot.org/timconfig/feed/desktop/StreamingCams2.json` → `cam.html` (M3U8).
- **NV**: `https://www.nvroads.com/services/MapServiceProxy.asmx/GetFullCameraListXML` → `StreamingURL`.
- **NM**: `https://servicev4.nmroads.com/RealMapWAR//GetCameraInfo?callback=…` (JSONP) → `snapshotFile`.
- **UT**: `https://udottraffic.utah.gov/KmlFile.aspx?kmlFileType=Camera` → KML `ImageUrl` (jpg/gif).
- **HI**: `http://goakamai.org/services/CameraProxy.svc/cameras/tours/H-1%20And%20H-201%20All/xml` → `FullImageURL`.
- **OK**: `https://oktraffic.org/api/CameraPoles` + header `filter: {"include":[…"streamDictionary"…]}` → `streamDictionary.streamSrc` (M3U8).
- **TN**: `https://smartway.tn.gov/Traffic/api/Cameras/0` → `dataItem.httpVideoUrl` (M3U8). **Fetch failed from this host (conn timeout ×2) — verify elsewhere.**
- **KY**: `https://services2.arcgis.com/CcI36Pduqd0OR4W9/arcgis/rest/services/trafficCamerasCur_Prd/FeatureServer/0/query?…f=pjson` → `attributes.snapshot`.
- **ND**: `https://dotfiles.azureedge.net/geojson/cameras/cameras.json` → `FullPath`.
- **SD**: `https://sd.cdn.iteris-atis.com/geojson/icons/metadata/icons.cameras.geojson` → `image`.
- **SC**: `https://files0.iteriscdn.com/WebApps/SC/SafeTravel4/data/geojson/icons/metadata/icons.cctv.geojsonp` → `properties.http_url` (M3U8).
- **IL**: `https://opendata.arcgis.com/datasets/8a885da23dfb46caaa1827ad920fb5b1_0.geojson` → `SnapShot`.
- **WV**: `http://wv511.org/rest/unifiedEntityService/ids` → `entity.iosUrl` (M3U8).
- VERIFIED TODAY: none fetched (TX snapshot = notable; its endpoint shape confirmed in two independent repos).
- VERDICT: **REFERENCE** — a rich per-state menu; Texas (`its.txdot.gov`) is the standout for build (M3U8 via snapshot resolver; watch CORS).

### 8 · OpenTrafficCamMap HTML/misc group (MI · PA · NJ · VA) + NYC DOT TMC
- **MI**: `https://mdotjboss.state.mi.us/MiDrive/camera/AllForMap/` + `/camera/getCameraInformation/<id>` (JSON `link`) [OTC code].
- **PA**: `https://www.511pa.com/wsvc/gmap.asmx/buildCamerasJSONjs` (JSONP); Turnpike snapshots `https://www.paturnpike.com/webmap/1_devices/cam<id>.jpg`; streams `http://pa511wmedia102.ilchost.com/live/<md5>.stream/playlist.m3u8?wmsAuthSign=<token>` — token from `https://www.511pa.com/wowzKey.aspx` (3 alternate IPs 209.71.158.{42,48,54} noted in code).
- **NJ**: `https://511nj.org/api/client/camera/GetCameraDataByTourId?tourid=3`; HLS OTP `https://511nj.org/api/client/camera/getHlsToken?Id=2`; Turnpike `https://njtpk-wink.xcmdata.org/turnpike/hls/<…>` (cross-domain issues noted).
- **NYC DOT TMC**: `https://webcams.nyctmc.org/api/cameras` → `{id,name,area,latitude,longitude,isOnline,imageUrl}` [Argus code]. **NOT-FETCHED: 3 attempts from this host = no response (DNS 207.251.86.235; TCP blocked/timeout). Verify from another vantage.**
- VA enumeration geojson stale — see §2.
- VERDICT: **REFERENCE** — NJ/PA need token/JS work; NYC likely fine (endpoint corroborated by 2 repos) but unverified here.

### 9 · Canada — Ontario 511 + DriveBC (+ AB/QC notes)
- **Ontario 511** (verified, see §5): 925 cams; images `https://511on.ca/map/Cctv/<id>` (JPEG). License: King's Printer for Ontario (OGL-Ontario style).
- **DriveBC** (BC MoTI): `https://www.drivebc.ca/api/webcams/?format=json` (array; `is_on`, `links.imageDisplay`, `location.coordinates[lon,lat]`, `highway`) [Argus code]. Image `https://www.drivebc.ca/images/<id>.jpg?t=<cb>`.
- **Alberta 511**: try `https://511.alberta.ca/List/GetData/Cameras?query=<json>` (same Iteris family) — **HTTP 500 today (×2, unverified)**.
- **Quebec**: quebec511.info — SPA; not mined this pass.
- VERIFIED TODAY: DriveBC HTTP 200, 1,239,143 B — **1,066 webcams, 1,045 `is_on`**; sample image 200, 53,213 B JPEG (800×468). Ontario as above.
- VERDICT: **ADOPT** (BC + ON: keyless JSON + direct imagery; AB re-test; QC TODO).

### 10 · UK — TfL JamCams (London)
- List API (keyless): `https://api.tfl.gov.uk/Place/Type/JamCam` → `additionalProperties: available, imageUrl, videoUrl, view`.
- Frames: `https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/<camId>.jpg`; video: same path `.mp4` (camId format `00002.00865`).
- KEY FACTS: 890 cams live today; refresh minutes-scale; small (≈320-class) JPEGs. License: TfL open data, attribution required ("Powered by TfL Open Data").
- VERIFIED TODAY: API HTTP 200, 1,146,513 B, **890 cams**; sample imageUrl/videoUrl recorded; WV1 had frame 6,878 B (2026-10-03).
- VERDICT: **ADOPT** — registry + liveness (list is the enumeration API; skip `available=false`).

### 11 · Norway — Statens vegvesen (NPRA) webcams
- **New keyless image API** (migration notice found live on the old page 2026-10-05): `https://kamera.atlas.vegvesen.no/api/images/<id>` replaces `https://webkamera.atlas.vegvesen.no/public/kamera?id=<id>`. List endpoint not found (`/api/cameras`, `/api/images` → 404; phone-code IDs like 1201/1203 exist in LES seed).
- **DATEX II (registered)**: `https://datex-server-get-v3-1.atlas.vegvesen.no/datexapi/GetCCTVSiteTable/pullsnapshotdata` (site+images) and `…/GetCCTVStatus/pullsnapshotdata` (statuses) — XML; registration required.
- KEY FACTS: machine-readable datex XML (SOAP/WSDL/WFS variants); images "varierende frekvens". License: NLOD; attribute "Statens vegvesen".
- VERIFIED TODAY: DATEX = **HTTP 401 anonymous** (registration confirmed needed); migration notice text captured (200); image fetch on ids 1201/1203 = **HTTP 400, 0 B** (ID space changed — verify current IDs at build; try DATEX list or portal).
- VERDICT: **REFERENCE→ADOPT-lite** pending ID check — the new `kamera.atlas` image API is a clean registry+liveness target; DATEX for enumeration.

### 12 · Germany — Autobahn GmbH API + NRW webcams
- Official-ish app API (open, no key): base `https://verkehr.autobahn.de/o/autobahn/` → `{roads:[A1…]}`; per road `…/{roadId}/services/webcam`; detail `…/details/webcam/{webcamId}`. Records carry `imageurl` (e.g. `https://www.verkehr.nrw/webcams/<id>.jpg`) and `linkurl` (player/stream).
- NRW: LES seed lists **252 cams** `http://62.113.210.7/strassennrw-rtplive/<id>.stream/playlist.m3u8` (HLS via blitzvideoserver; player `blitzvideoserver.de/player_strassennrw.html?…`).
- KEY FACTS: mixed protocols (JPEG + HLS via provider); operator tags per camera (NRW, etc.). No SLA (community-documented API).
- VERIFIED TODAY: base list HTTP 200, 723 B (roads A1…); `/A1|A3|A61/services/webcam` = HTTP 200 but **empty `{"webcam":[]}`** (data-empty today or moved); NRW image URL `…/webcams/10108109881648294854.jpg` = **HTTP 403** (referrer/WAF from this host). Not build-blocking: re-test from a browser session.
- VERDICT: **REFERENCE** — API shape + NRW stream host are worth a re-test; likely productive with a browser-context fetch.

### 13 · Australia — NSW · QLD · VIC · WA
- **NSW (TfNSW)**: `https://api.transport.nsw.gov.au/v1/live/cameras` (GeoJSON; each feature `properties.href` = JPEG image URL; CC-BY). Free API key via opendata.transport.nsw.gov.au. VERIFIED: **HTTP 401** anonymous ("The calling application is unauthenticated") — key required.
- **QLD (TMR)**: `https://api.qldtraffic.qld.gov.au/v1/webcams` — "All live traffic web camera still images & metadata" (API spec v1.10 PDF); VERIFIED **HTTP 401** anonymous → key required (free registration).
- **VIC (VicRoads)**: `traffic.vicroads.vic.gov.au` (SPA; no keyless API found today; hosts unreachable/403 from here).
- **WA (Main Roads)**: `https://travelmap.mainroads.wa.gov.au/Home/GetMapConfiguration` (**200, 8,729 B** — ArcGIS endpoints) + `https://gisservices.mainroads.wa.gov.au/arcgis/rest/services/Apps/TravelMap/MapServer` (**200, 5,682 B; 17 layers — no Camera layer found**; cameras may load elsewhere).
- VERDICT: **REFERENCE** — NSW + QLD are solid once a free key is registered (both CC-BY-style); VIC/WA need browser work.

### 14 · Asia-Pacific small — Singapore (LTA) + New Zealand (trafficnz)
- **Singapore**: `https://api.data.gov.sg/v1/transport/traffic-images` (keyless) → `items[0].cameras[]{camera_id,image,timestamp,location}`. Image pattern `https://images.data.gov.sg/api/traffic-images/<YYYY>/<MM>/<uuid>.jpg`. License: Singapore Open Data Licence. LTA DataMall alt `Traffic-Imagesv2` (AccountKey).
- **New Zealand**: `https://trafficnz.info/service/traffic/rest/4/cameras/all` → `response.camera[]{id,name,latitude,longitude,region,highway,direction,offline,underMaintenance,imageUrl}`; image `https://trafficnz.info/camera/<id>.jpg` (~70 KB JPEG). Third-party mirror (NZTA `journeys.nzta.govt.nz` webcam API deprecated/404 — per Argus code comment).
- VERIFIED TODAY: SG JSON 200 (2,620 B) — **8 cameras at 18:32 SGT** (dataset historically larger — re-check; maybe a partial incident feed), sample image 200, 119,929 B JPEG 1920×1080. NZ JSON 200, 237,144 B — **313 cams, 252 not-offline** (variance vs Argus note "257 active" — normal drift).
- VERDICT: **ADOPT** both (registry+liveness; NZ = REFERENCE-grade because third-party).

### 15 · Asia misc — Taiwan · Thailand · Korea · Japan (research-only)
- **Taiwan (Freeway Bureau TISV)**: static list `https://tisvcloud.freeway.gov.tw/history/motc20/CCTV.xml` (+ `cctv_info.xml.gz`, `cctv_value.xml.gz`); live MJPEG `https://cctvc.freeway.gov.tw/abs2mjpg/bmjpg?camera=<id>` (south) / `cctvn.freeway.gov.tw` (north); ID format `1-5K-0.01` (route-km) [LES seed + research]. Open data (data.gov.tw). **NOT-FETCHED: all hosts returned 000/400 from this network today (5 tries, 4 hosts) — geo/network-blocked here; retry from another vantage.**
- **Thailand**: LES trafficvision 245 cams `https://streaming.noc.nakhoncity.org/live/<ID>.m3u8`; ITIC 88 `https://camerai1.iticfoundation.org/pass/<ip:port>/<node>.stream/playlist.m3u8` + `camera1.iticfoundation.org/hls/<host>.m3u8` (0 active in seed).
- **Korea (KTICT)**: 20 cams `http://cctvsec.ktict.co.kr/<n>/<token>` (per-cam opaque tokens; html_page).
- **Japan**: no keyless machine catalog found; portals are JS (NEXCO `https://www.drivetraffic.jp/camera`; JARTIC `jartic.or.jp`); JARTIC open data API = traffic volumes, not cameras; aggregator DB exists (livecam.asia).
- VERDICT: **REFERENCE** — TW has the best structure (documented MJPEG IDs) once reachable; others = event-mode/manual at best.

### 16 · USGS Volcano Observatories (Hawaii · Alaska · Cascades · Yellowstone · California)
- **HVO stills**: `https://volcanoes.usgs.gov/observatories/hvo/cams/<ID>/images/M.jpg` (IDs: V1cam, V2cam, V3cam, K2cam, KWcam, M…; ~1–2 min refresh).
- **AVO ashcams**: page `https://avo.alaska.edu/webcam/` lists per-station latest: `https://avo.alaska.edu/ashcam-api/images/<station>/<YYYY>/<DDD>/<station>-<YYYYMMDDTHHMMSSZ>.jpg` (double slash after `images//` as served; stations e.g. `akutan_av06`, `cleveland_clco`, `augustine`).
- **CVO**: Johnston Ridge / Mount St. Helens (page `https://www.usgs.gov/observatories/cvo/multimedia/webcams`); **YVO** Yellowstone Lake; **CalVO** Long Valley — page-level, single cams.
- Licensed US public domain (USGS); thermal/PTZ cams in HVO set.
- VERIFIED TODAY: **HVO V1cam M.jpg = HTTP 200, 56,108 B JPEG (1920×1080)**; AVO page HTTP 200, 279,751 B with live timestamped image URLs (77 refs; sample 2026-10-05T10:05Z). WV1 (2026-10-03) had V2 213,470 B / V3 348,748 B / K2 202,601 B, and USGS Kilauea YouTube live 54,261 B.
- VERDICT: **ADOPT** — enumeration per observatory (parse AVO page or find its JSON; HVO by ID list); build: **registry** + image-refresh viewer (M7 loop).

### 17 · US federal nature/science — NPS park webcams + USAP Antarctica
- **NPS**: hub per park `https://www.nps.gov/<park>/learn/photosmultimedia/webcams.htm` (YOSE has 5 incl. El Capitan/Yosemite Falls; YELL has 10, one live stream "Old Faithful"; usage agreement for some cams). Yellowstone's cams are powered by **Pixelcaster**:
  - snapshot (keyless): `https://cdn.pixelcaster.com/public.pixelcaster.com/snapshots/yellowstone-old-faithful/latest_1920x.jpg`;
  - HLS: `https://cs7.pixelcaster.com/yellowstone/faithful.stream/playlist_dvr.m3u8` + `wmsAuthSign=<token>` (keyless → 403; token obtained from the page).
- **USAP (NSF Antarctica)**: image API `https://www.usap.gov/components/webcams.cfc?method=outputCurrentCamImage&cameraLocation=<McMurdo|SouthPole|Palmer>&camera=<cam>` → e.g. `McM00091.jpg?=99059395.2933,Live,Live`; direct image `https://www.usap.gov/videoclipsandmaps/SouthPoleWebcam/McM00091.jpg?=<cb>`; weather `…webcams.cfc?method=outputWeatherDataByStation&cameraLocation=McMurdo`. Cams: McMurdo (arrivalHeights/obHill/royalSociety/pier), South Pole (x2), Palmer.
- VERIFIED TODAY: Pixelcaster snapshot **HTTP 200, 20,943 B JPEG 1920×1080**; Pixelcaster HLS 403 without token; USAP endpoints captured from live XHR on both McMurdo and South Pole pages (200 pages).
- VERDICT: **ADOPT** both — NPS snapshot tier + USAP image API with weather (build: registry + image-refresh viewer; NPS HLS only with page token).

### 18 · Ski resorts with official cams + direct URLs
- **Jackson Hole (US)**: catalog JSON `https://jacksonhole-prod.zaneray.com/api/web-cams.json` → `webcams[]{caption,url,thumbUrl,isPanoCam,liveStreamUrl,youtubeId}`; direct JPGs `https://cams.jacksonhole.com/webcam/<name>.jpg` (codybowl, teewinot, gondi_bottom, SouthHoback, tetonvillagecommons…); pano cams `https://backend.roundshot.com/cams/<hash>/default`.
- **Ischgl (AT)**: `https://www.ischgl.com/var/webcams/<id>.jpg` (ids like 100178351, 100178336; from the official webcams page media list).
- **Providers to scale**: Roundshot (`backend.roundshot.com/cams/<hash>/default|medium`), Panomax (per-site `*.panomax.com`; `live-image.panomax.com` seen in the wild — no keyless pattern established today), Feratel (untested).
- VERIFIED TODAY: JH JSON 200, 1,825 B (7+ cams listed); JH `codybowl.jpg` **200, 269,663 B JPEG, AXIS Q3615, 1920×1080, timestamp 2026-10-05 04:42**; Ischgl jpg **200, 187,080 B, 1920×1080**.
- VERDICT: **ADOPT** — official resort cams, direct JPEGs (registry + image-refresh; JH JSON is a clean catalog; Ischgl = per-id pattern). Note resort ToS; likely fine for personal viewing, check before redistribution.

### 19 · Ports & airports (official pages; no keyless direct endpoints this pass)
- **Port of Rotterdam**: `https://www.portofrotterdam.com/en/experience-online/webcams` — HTTP 200 verified (map-driven; image links behind JS/map points; "click a point … link to the images").
- **Istanbul iGA Airport**: `https://www.istairport.com/en/airport/maps/airport-live-stream/operation-center` — HTTP 200 verified (official live cameras pagerunway/pier views; player JS — no direct URL extracted).
- Dublin Airport `/live-cam` = 404 (no final URL confirmed).
- Pattern: port/airport cams are usually JS map players or YouTube embeds; treat as manual-curation tier.
- VERDICT: **REFERENCE** — two verified official pages worth a browser-inspection pass; do not expect keyless direct streams.

---

## DEAD-ENDS / FAILED PROBES (log)
- **NYC DOT TMC** `webcams.nyctmc.org/api/cameras`: 3 attempts (https, https -k, http) → no response from this host (DNS ok, TCP blocked). Endpoint corroborated by 2 repo codes — verify elsewhere. **(≤3 attempts respected, stop.)**
- **Taiwan**: `tisvcloud.freeway.gov.tw` (000 ×2), `cctvc.freeway.gov.tw` (400 ×2), `cctvn.freeway.gov.tw` (400), `1968.freeway.gov.tw` (000) — unreachable from this network; likely geo-filtered. Retry from another vantage.
- **Georgia 511** + **Alberta 511**: `List/GetData/Cameras` → HTTP 500 even with full query + XHR headers (Ontario's identical pattern worked; GA/AB may need session cookies).
- **Road511**: anonymous → 401 (key now required).
- **Norway**: DATEX endpoints 401 (registration); new image API 400 on old IDs (ID space moved).
- **Germany**: autobahn webcam service empty for A1/A3/A61 (200/`[]`); NRW jpg 403 w/ referer.
- **UK National Highways**: `trafficengland.com/api/cameras` → 404 (301→404); not pursued further this pass (TfL covers UK).
- **NPS guessed patterns** (`/webcams-yell/*.jpg`) 403/404 — real path is Pixelcaster snapshot (found).
- **Iowa skyvdn HLS**: one fetch timed out from host (000) — re-test; JSON registry solid.
- **VA geojson** `511virginia.org/data/geojson/…` now 301→SPA (stale semantics; streams still fine).
- **Caltrans D03** JSON: HTTP 500 (persistent since 2026-10-03) — skip district until fixed.
- **Panomax** keyless image pattern: not established (only per-site pages/aggregators) — treat as provider TODO.
- **USAP HTML** gives no direct URLs (JS app) — its XHR API was extracted instead (§17).

## QUICK BUILD NOTES (per component)
- **Registry (enumeration):** TfL / Place/Type/JamCam · DriveBC /api/webcams · DelDOT videocamera.json · Iowa ArcGIS count+query · OHGO pointData · WSdot Cameras.json · ON List/GetData · Caltrans 12 JSONs · SG data.gov.sg · NZ trafficnz · JH web-cams.json · USAP webcams.cfc · AVO page · NPS per-park + pixelcaster ids.
- **Liveness:** HEAD/GET first frame per cam; skip `available=false` (TfL), `is_on=false` (DriveBC), `offline/underMaintenance` (NZ), `inService=false` (Caltrans), `isOnline!=true` (NYC).
- **Viewer:** HLS (Caltrans/VDOT/MD/DE/ON-N/A) via ffmpeg; JPEG-refresh for the rest (AVO/USGS/NPS/SG/Ischgl/JH/ski).
- **Known-broken host list to carry:** `trafficwise.org`, `kdot-sfs`, `actis.idrivearkansas.com`, `api.trafficland.com` (Road511, per Argus).
- **Keys needed (free):** Windy, Road511 (now), NSW, QLD, Korea(?), LTA DataMall(alt). Everything else keyless.

*File: S2-gov-institutional.md · 19 family entries · collected 2026-10-05 · all live-fetch results dated & byte-counted above.*

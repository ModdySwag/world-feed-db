# 00 — Tab-ingest: map/globe sources for the WORLD MAP view

_Run 2026-10-06 (subagent). Input: owner's Brave tab cluster (open-source Google-Earth alikes, CesiumJS, GeoLibre, satellite-imagery providers, NASA Earth model). Purpose: actionable design/tech data for a Google-Earth-type 3D globe (rotatable, zoomable, searchable, all ~31–35k camera rows pinned) inside the local World Feed DB viewer (vanilla JS + vendored libs, 127.0.0.1:8773)._

Method notes (honesty): Hermes `web_search` was rate-limited this run (Nimble trial quota 402; Exa free-tier 429) → used the keyless **hound** search/fetch service + direct `curl`. Google `goto?url=` tokens were not decoded — pages resolved by title search (substitutions flagged below). Every HTTP status below was checked live on 2026-10-06 from this machine.

## A. Source status

| Tab # | Source | URL used | Status | What it is |
|---|---|---|---|---|
| 1 | NASA Earth 3D Model | https://solarsystem.nasa.gov/gltf_embed/2393/ | ✅ fetched + HTML inspected | `<model-viewer>` embed of a 12.9 MB Earth GLB. Tech read in D1. |
| 2 | Google search page | — | skipped | (owner said skip) |
| 3 | GitHub `opengeos/GeoLibre` | https://github.com/opengeos/GeoLibre | ✅ fetched | MIT. Web/desktop/mobile GIS: Tauri v2 + React + **MapLibre GL JS** + **deck.gl** + DuckDB-WASM; 1,000+ in-browser WASM geoprocessing tools; 6,745★; repo created 2026-05-27. |
| 5 | "Google Earth Alternatives" (goto token) | ➜ substitute: https://www.linuxlinks.com/virtualglobe/ | ✅ fetched (substitute) | "8 Best Free and Open Source Virtual Globes" (2026-08-29): QGIS, OpenStreetMap, Marble, GeoMapApp, osgEarth, NASA World Wind, TerriaMap, ossimPlanet. |
| 6, 12, 14 | CesiumJS | https://cesium.com/platform/cesiumjs/ + /learn/cesiumjs-learn/cesiumjs-quickstart/ | ✅ fetched | Apache-2.0 3D globe engine; 3D Tiles/terrain/imagery + KML/GeoJSON/CZML + time + Columbus view. See D2. |
| 7, 15, 17 | `google/earthenterprise` | https://github.com/google/earthenterprise (+ GitHub API) | ✅ fetched | **Archived** (`archived: true`, last push 2023-01-04), Apache-2.0, 2,749★. Fusion/Server/Client globe-baking suite. See D4. |
| 8, 9 | TLGeo: OpenDataCube vs GEE | https://tlgeo.xyz/en/blog/what-is-opendatacube/ | ✅ fetched (2026-04-15) | ODC = Apache-2.0 self-hosted data cube (space/time/spectrum), offline, OGC WMS into QGIS. Data side, not a viewer. |
| 10 | "15 Best Alternatives to Google Earth Engine (2026)" | https://flypix.ai/google-earth-engine-alternatives/ | ✅ fetched (title-resolved) | Vendor list: Sentinel Hub, Planet, OpenEO, QGIS, Microsoft Planetary Computer, Mapbox, ArcGIS Online, Luciad/Octave Alto, etc. Modified 2026-09-22. |
| 11 | QGIS | https://qgis.org | ✅ fetched | Desktop GIS, GPLv2+ — companion tool only, not embeddable. |
| 13 | "Free Satellite Imagery: 2026 Data Providers & Sources" | https://eos.com/blog/free-satellite-imagery-sources/ | ✅ fetched (title-resolved; XHR-heavy page, main list captured) | LandViewer, USGS EarthExplorer, Copernicus Data Space, NOAA, Vantor/Maxar Open Data, ASF Vertex. Modified 2026-08-03. |
| 14 | SkyWatch "Top 10 Free Sources of Satellite Data" | original URL 404; live: https://skywatch.com/free-sources-of-satellite-data/ (no Wayback snapshot of old URL) | ✅ fetched (full) | SkyWatch EXPLORE, Google Earth, Sentinel Hub, USGS EE, NOAA, Copernicus, Earth on AWS, Zoom Earth, NASA Worldview, NASA GIBS + honorable mentions. Article dated 2022-04, updated 2025-04 — treat list as still-true-at-time-of-fetch, flag staleness. |
| 16 | Mapillary | https://www.mapillary.com/ + /developer/api-documentation + https://github.com/mapillary/mapillary-js | ✅ fetched | 3B+ street-level images; API v4 (vector tiles + entity endpoints) requires token; imagery **CC-BY-SA 4.0**; viewer lib mapillary-js MIT (504★). See D5. |
| — | OSM tile usage policy | https://operations.osmfoundation.org/policies/tiles/ | ✅ fetched | Attribution + identifiable User-Agent required; no bulk/offline prefetch; best-effort, block-without-notice. |
| — | Google Earth official pages (for GE UX conventions) | earth/about/versions/ + support.google.com/earth/answer/{148115, 148174, 9010337, 148089} | ✅ fetched | Sourced GE navigation shortcuts, tours, measurement, flight simulator. |
| — | MapLibre GL JS (adjacent, not a tab) | https://maplibre.org/maplibre-gl-js/docs/ | ✅ fetched | v6.12.0 (npm, BSD-3-Clause); quickstart ships a **globe** style (demotiles.maplibre.org/globe.json). Candidate engine. See D6. |

Blocked/failed, called out: SkyWatch original URL (404, no Wayback) → live successor found; Google `goto` tokens (undecoded) → title-substituted; Exa/Nimble rate limits → hound keyless substitution; MapLibre API doc URL guessed 404 → used docs index instead.

## B. Feature inventory (feature → what it means for us → source)

**Navigation / 3D conventions**
- **Orbit, tilt, zoom + keyboard/mouse set**: arrows move; Shift+arrows rotate/tilt; Ctrl+drag first-person; +/- zoom; right-drag = zoom + auto-tilt; Space stops; `n` north-up, `u` top-down, `r` center Earth → GE Help 148115 → adopt as the globe's shortcut sheet (mirrors local spec law 5).
- **Overview (minimap) window, Ctrl+M** → GE Help 148115 → a corner minimap/inset is a GE-native convention; local viewer already has a map view to miniaturize.
- **Fly-to camera animation** — `camera.flyTo({destination, orientation:{heading, pitch}})`; the search-to-place motion → Cesium quickstart → "fly to camera" on search hit / random pin.
- **Tours**: record a flight path, per-tour speed, "wait at features" dwell, "fly along lines", camera tilt angle + range, audio narration, save/share → GE Help 148174 → future "tour of live cams" (cheap v1: scripted flyTo chain).
- **Flight-simulator easter egg** (joystick/keyboard, HUD) → GE Help 148089 → optional fun toggle; low priority.
- **3D / 2D / 2.5D ("Columbus") view switching at runtime** → Cesium platform page → scene-mode toggle in the view.

**Imagery / data features**
- **3D Tiles** (buildings, photogrammetry, point clouds) streamed from open spec → Cesium + GeoLibre demo (3D Tiles on MapLibre) → 3D buildings later; not needed for v1.
- **glTF model support** → Cesium; NASA Earth embed (GLB).
- **Terrain + imagery layers with custom tiling schemes** → Cesium → we supply raster tiles (GIBS/Esri/OSM), no token needed if we avoid ion.
- **Vectors KML/GeoJSON/CZML + drawing API** → Cesium → export "current pins" as GeoJSON = free interop.
- **Time-dynamic / 4D visualisation** → Cesium → day/night + date slider uses GIBS daily layers.
- **Historical imagery, "go back in time"** → GE Pro (GE versions page) → Esri Wayback: 196 releases, 2014 → 2026-08 (see C) — a per-camera-area "how it looked then" flip.
- **Daily imagery + date picker** (NASA Worldview pattern, GIBS behind it) → SkyWatch #9/#10 → "yesterday" layer + time-lapse scrub for free.
- **Day/night / night-lights layer** → GIBS `VIIRS_CityLights_2012` (verified 200) → day/night blend in globe.
- **Street-level 360°** → GE versions page ("Street View's 360° perspectives"); Mapillary (3B+ images, token, CC-BY-SA) → defer; start with link-out.
- **Layer mixing in one view** (10-min GOES + daily GIBS + archival Bing/Esri = Zoom Earth pattern) → SkyWatch #8 → our globe's layer stack: base imagery + daily overlay + optional labels.

**Tooling / UX patterns**
- **In-browser geoprocessing + spatial SQL** (1,000+ WASM tools, DuckDB-WASM) → GeoLibre → far beyond scope for a viewer, but "query bbox, filter, cluster" in-page is the same idea at small scale.
- **Data cubes (space/time/spectrum), offline-first, OGC/WMS serving** → TLGeo ODC → conceptual: our registry is effectively a "camera cube" (space + status + time); WMS delivery not needed.
- **STAC / programmatic imagery catalogs** → flypix (Planetary Computer row), eos.com → if the globe ever wants per-camera latest scenes.
- **Viewer interaction polish**: poster → `reveal` → "interaction prompt" after idle threshold → orbit/zoom; AR on mobile → NASA `<model-viewer>` attrs (`camera-controls`, `interaction-prompt-threshold='1000'`, `ar`, `poster`) → copy the prompt/idle pattern for the globe's first-run hint.
- **Marker clustering at scale** → local reality: Leaflet + markercluster vendored, map renders ≤2,500 markers while the registry is ~31k rows (VIEWER-SPEC/README) → the globe must cluster + query by viewport (local API already supports bbox).
- **Attribution UX** → OSM policy (attribution required), Esri `copyrightText` → per-layer credit line in the status bar / layer panel.

## C. Imagery sources (every endpoint curl-checked 2026-10-06)

| Provider | Endpoint pattern | Licence / attribution | Max zoom | CORS | Cost | Notes |
|---|---|---|---|---|---|---|
| **NASA GIBS** (Global Imagery Browse Services) | `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time|–}/{TMS}/{z}/{y}/{x}.{ext}` (WMTS/REST); capabilities: `/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml` (5.8 MB, **1,330 layers**) | NASA — public domain; courtesy credit "NASA GIBS/Worldview" | L8/L9 for most imagery/static layers (z0–8/9) | `Access-Control-Allow-Origin: *` ✅ | Free | Daily layers take a date in the URL (`2026-10-05` verified). Verified 200: `BlueMarble_ShadedRelief_Bathymetry` z2 (18,926 B jpg), `BlueMarble_NextGeneration` z2, `VIIRS_CityLights_2012` z2, `VIIRS_SNPP_CorrectedReflectance_TrueColor` z3 (20,798 B), `MODIS_Terra_CorrectedReflectance_TrueColor` z3 |
| **ESRI World Imagery** | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` (+ `?f=json` metadata) | Esri terms; required credit string: **"Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"** (from service JSON) | **z0–23** (24 LODs, 256 px JPEG) | `Access-Control-Allow-Origin: *` ✅ | Free public service, no key; display-only — not licensed for bulk download/redistribution | The high-zoom workhorse (GIBS stops at z9) |
| **Esri Imagery Wayback** (historical) | `https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{releaseNum}/{z}/{row}/{col}` — releaseNums from `https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json` (105 KB, **196 releases**) | Same Esri terms | z0–23 (z13 verified) | `Access-Control-Allow-Origin: *` ✅ | Free | Newest release `WB_2026_R07` = "World Imagery (Wayback 2026-08-05)" → releaseNum 26334; tile with releaseNum 32337 (2018) returned 200 jpeg. Powers a date-slider "time travel" |
| **OpenStreetMap raster** | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | ODbL data © OpenStreetMap contributors | z0–19 | `Access-Control-Allow-Origin: *` ✅ | Free but policy-bound | Policy: identifiable UA, no bulk/no offline prefetch, no aggressive proxy caching, best-effort; already gated behind `map_tiles` setting in the app — keep that gate |
| Archive platforms (not tile servers): **USGS EarthExplorer** (Landsat/MODIS/ASTER, free, historic to 40+y), **Copernicus Data Space** (Sentinel-1/2/3/5P, free, account), **Earth on AWS** (open buckets, API-only), **Microsoft Planetary Computer** (STAC APIs), **NASA Worldview** (browser view over GIBS), **NOAA/GOES-R** (15-min, geostationary, low-res), **Maxar/Vantor Open Data** (free high-res disaster scenes), **Sentinel Hub** (free tier w/ account+key) | various APIs/browsers | Public domain (US gov) / CC-BY / program terms; check per catalog | n/a | n/a | Free | Source: SkyWatch #4–#10 + honorable mentions; eos.com list; flypix table. Not live tiles → not usable as basemap directly without tile rendering |

**Verification log (exact commands, abbreviated):**
- `curl -sIL 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/2/1/2.jpg'` → `200 image/jpeg`, `Content-Length: 18926`, `Access-Control-Allow-Origin: *`
- `curl ... VIIRS_SNPP_CorrectedReflectance_TrueColor/default/2026-10-05/.../3/2/4.jpg` → `200 image/jpeg` (20,798 B)
- `curl 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/3/2/4'` → `200 image/jpeg`; service JSON: 24 LODs, max 23; `copyrightText` above
- `curl 'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/32337/3/2/4'` → `200 image/jpeg`, `Access-Control-Allow-Origin: *`
- `curl 'https://tile.openstreetmap.org/3/4/2.png'` → `200 image/png`
- GIBS `WMTSCapabilities.xml` → `200`, 5,841,669 bytes, 1,330 `<Layer>` entries.

## D. Assessments

**D1 — NASA `gltf_embed` tech read.** The page is not a map: it loads **Google `<model-viewer>` v1.10.1** (from unpkg, plus webcomponentsjs/intersection/resize/fullscreen polyfills) and points it at a **12,916,400-byte Earth GLB** (`Earth_1_12756.glb`, served via a redirect+token blob URL; `application/octet-stream`). Attributes observed: `camera-controls` (drag-orbit + scroll zoom), `interaction-prompt-threshold='1000'`, `reveal='auto'`, `poster`, `shadow-intensity`, `ar` + `ios-src` (USDZ for Quick Look AR). Vendor sizes: `model-viewer.min.js` 1,044 KB / module-min 464 KB (Apache-2.0, npm 4.3.1). **Verdict: use only as a landing/About easter-egg ("tiny Earth" hero + first-run hint pattern), not as the navigable globe; vendor the file — NASA's embed itself violates our no-runtime-CDN law.** Bonus read: the GLB itself is a good "instant planet" asset if licence is cleared (NASA content is generally public domain).

**D2 — CesiumJS for a local no-build vanilla app.** Licence **Apache-2.0** (site + repo + npm agree), so vendoring is clean. Latest npm **1.146.0**, `unpackedSize` 79.7 MB; the directory you'd actually vendor is `Build/Cesium` (**22.8 MB** total): single-file `Cesium.js` **6.08 MB** (verified header: version 1.146.0, Apache header, AMD `define(` wrapper — works from a plain `<script>` tag exposing global `Cesium`), plus `index.js`/`index.cjs` ESM/CJS variants, `Assets/` 4.38 MB, `Workers/` 1.03 MB, `ThirdParty/` 1.12 MB, `Widgets/` 0.52 MB (incl. `widgets.css`). Minimal runtime subset ≈ **13.1 MB**. Requires `window.CESIUM_BASE_URL` pointing at those four dirs. **Red flag: the default path is ion-token-gated** — quickstart sets `Ion.defaultAccessToken`; world terrain (`Terrain.fromWorldTerrain()`), ion imagery and `createOsmBuildingsAsync()` are ion assets. Keyless plan: ellipsoid terrain + our own imagery providers (GIBS/Esri/OSM) + skip/replace OSM Buildings. Project is active (last push 2026-10-05, 15.8k★). Performance at ~31–35k pins: needs clustering / point primitives / viewport queries — spike required.

**D3 — GeoLibre.** Not a library — a full app (Tauri v2 + React + TypeScript + MapLibre GL JS + deck.gl + DuckDB-WASM Spatial), MIT, 6.7k★, created 2026-05-27. Not directly reusable as a component, but its stack is the best-practice mix if we want 3D Tiles/deck.gl layers later, and its MIT code is consultable for layer-manager UX. **Takeaway: inspiration — the "layer catalog + in-browser query" pattern, and the proof that MapLibre can render 3D Tiles.**

**D4 — earthenterprise.** GitHub API: **`archived: true`**, last push **2023-01-04**, Apache-2.0, 2,749★. Suite = Fusion (bake imagery+vector+terrain into a flyable globe), Server (Apache/Tornado), Client (native EC + Maps JS API v3) on CentOS 6/7–Ubuntu 16.04. **Dead end for new work; inspiration only** — the "pre-bake tiles into a fast globe" concept survives in the modern stack as Cesium 3D Tiles / pre-rendered raster pyramids.

**D5 — Mapillary / street-level relevance.** API v4 (`graph.mapillary.com` + `tiles.mapillary.com`) **requires a client access token** for all requests; vector tiles `mly1_public/2/{z}/{x}/{y}`; entity bbox queries now capped at **0.01° square** (larger use vector tiles). Imagery licence **CC-BY-SA 4.0** (share-alike — attribution + derived-works same licence), faces/plates auto-blurred; viewer lib `mapillary-js` **MIT** (v4.1.2). **Verdict: defer; Phase-1 = "Open in Mapillary" link-out from a camera popup; only build an embedded street viewer if the licensing/token overhead is accepted.**

**D6 — Landscape + adjacent engines (the realistic build paths).**
- The LinuxLinks roundup (Marble, osgEarth, World Wind, TerriaMap, ossimPlanet, GeoMapApp) is desktop/native or other-stack — useful only as feature inspiration (TerriaMap = web geospatial explorer worth a look later; note it's Terria, not in our tab list beyond this article).
- **(a) CesiumJS** — true 3D globe + 3D Tiles + terrain; Apache-2.0; heavy (~13 MB vendored, ion caveats). Best fidelity for "Google-Earth-type".
- **(b) MapLibre GL JS v6** — globe projection (docs quickstart uses a globe style); BSD-3-Clause (npm); dist is **ESM-only** in the 6.x listing (`maplibre-gl.mjs` 583 KB + `maplibre-gl-shared.mjs` 505 KB + worker 19 KB + css 81 KB ≈ 1.2 MB) → usable with `<script type="module">` + import map, no build step needed but no single-file drop-in either. Lighter path; raster+vector sources. **Spike: confirm GIBS/Esri raster tiles render on the globe projection (docs only demo vector globe style — verify before committing).**
- **(c) three.js + three-globe** — both MIT; three.module.js 647 KB + three.core.js 1,424 KB; renders tens of thousands of markers as GPU points/sprites trivially, but **no imagery tiling** (texture-on-sphere only) — a "pins-first globe" with a Blue Marble texture, not a navigable basemap globe.
- **Recommended spike order:** MapLibre v6 globe with GIBS raster → if raster-on-globe is rough, three-globe with GIBS Blue Marble texture + GPU pins → Cesium only if full 3D Tiles/terrain/Columbus fidelity is required. All three licence-clean (BSD/MIT/Apache).
- **Law update required either way:** VIEWER-SPEC law 3 currently allows "tile.openstreetmap.org only when map tiles setting is ON" — a globe adds GIBS/Esri/Wayback as new tile hosts; extend that setting into a *provider list with per-provider attribution*, keep it OFF by default, and keep zero runtime CDN for libraries.

## E. Steal list (top 5, ranked)

1. **Fly-to + tilt/pitch camera** driven by search results and pin clicks (Cesium-style `flyTo` with heading/pitch; GE's `n/u/r` reset keys as the escape hatch).
2. **Free imagery stack, keyless + CORS-open**: GIBS Blue Marble base + GIBS daily VIIRS/MODIS with a date slider (time-lapse) + City Lights night layer + Esri World Imagery for high zoom + optional OSM labels.
3. **Time travel**: Esri Wayback release slider (196 releases, latest 2026-08) and/or GIBS date picker on a pinned camera's neighbourhood.
4. **Marker UX at 31k+ rows**: cluster at low zoom, expand via the existing `bbox` API filter ("search this area" already exists in Map view), cap rendered entities like the Leaflet path does (≤2,500).
5. **First-run polish from the NASA embed**: poster → reveal → idle "interaction prompt" (1000 ms threshold) → orbit; plus keyboard sheet (GE 148115 set) and a Ctrl+M minimap.

Red flags (short): ion token gate (Cesium defaults); earthenterprise archived; Mapillary CC-BY-SA + token; OSM no-prefetch policy; Esri attribution/display-only; GIBS z8/9 ceiling; MapLibre v6 ESM-only dist; runtime-CDN temptation (NASA's unpkg embed, Cesium CDN snippets) vs local vendoring law.

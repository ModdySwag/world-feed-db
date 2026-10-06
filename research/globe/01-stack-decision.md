# 01 — Stack decision: a Google-Earth-class globe view for the World Feed DB viewer

**Status:** survey + decision, evidence-backed (all HTTP/size claims below were exercised by real
fetches from this host on 2026-10-06).
**Scope:** add a lazy-loaded **WORLD MAP** view to `wfd/web/` (vanilla ES modules + vendored libs +
`wfd/viewer.py` stdlib server, no build step, no runtime CDN for code) rendering ~14k geocoded
camera rows as a navigable, rotatable, searchable 3D globe.

**Deliverable files**
- this doc
- `research/globe/proof/globe-test.html` + `cameras.geojson` + vendored `maplibre-gl.js/.css` + one glyph PBF
  — a **working proof harness** (screenshot-verified, see §9).

---

## 1. TL;DR — RECOMMENDATION

| # | Decision | Choice |
|---|----------|--------|
| 1 | **Engine** | **MapLibre GL JS v5 line (5.24.0), vendored** — globe projection + atmosphere + raster satellite + built-in supercluster clustering, 1 file + 1 CSS = **1.10 MB**. |
| 2 | **Imagery** | **Esri World Imagery** (all zooms, deep zoom to z19/23) + **NASA GIBS Blue Marble ShadedRelief_Bathymetry** (public-domain "from orbit" beauty layer, z0–8) + **GIBS Reference_Labels** (public-domain hybrid label overlay). Optional: GIBS VIIRS true-colour (today's Earth) and VIIRS Black Marble (night lights); EOX Sentinel-2 cloudless (CC BY-NC-SA, non-commercial) as a pretty alt. |
| 3 | **Clustering** | One GeoJSON source with `cluster:true` (supercluster **inside MapLibre's worker**), `clusterRadius:55`, `clusterMaxZoom:12`, `clusterMinPoints:2`; WebGL `circle` + `symbol` layers (no DOM markers); click → `getClusterExpansionZoom()` → `flyTo()` = animated cluster expansion. Measured: **14,065 points load in 898 ms** at ~144 FPS on auto-rotate. |
| 4 | **Lazy-load** | New view id `globe` in `VIEW_ORDER`/`VIEWS`; the view module does `await import('./globe.js')` and *that* module loads the library only when the view opens (`<script>` inject for the v5 UMD build, or `await import(...mjs)` if we take v6). `map.remove()` on view exit. Vendor dir: `wfd/web/vendor/maplibre/`. |
| 5 | **Rejected** | CesiumJS (21.74 MB vendored, ion/ArcGIS tokens, overkill for 14k pins) and globe.gl/three.js (no tiling → no street zoom without rebuilding a map engine). |

---

## 2. Constraints (from the repo, verified)

- `docs/VIEWER-SPEC.md` law #3: *"No runtime CDN: vendored libs only … + local API + feed hosts."*
- `wfd/web/index.html` loads vendored Leaflet 1.9.4 + markercluster + hls.js as **classic scripts**;
  `wfd/web/js/app.js` is an ES module with a **hash router** (`#/overview|map|wall|watch|search|personal|help`)
  and a `VIEWS` registry in `views.js` (`views.js:1358`). Views may return `destroy?`.
- `wfd/viewer.py` (`ViewerHandler`): stdlib `ThreadingHTTPServer` serving static files from `wfd/web/`
  with an **explicit MIME map that already includes `.mjs: text/javascript`** (`viewer.py:388-399`) —
  i.e. the server is already ESM-ready. **No CSP headers are sent** → blob-URL workers are fine.
- Existing `map` view (Leaflet, OSM raster, markercluster, `views.js:361-560`) stays as the flat 2D map;
  the globe is an additional view.

### 2.1 Data reality check (this changes the plan)

| Fact | Value |
|---|---|
| `cameras` rows | **35,541** |
| rows with both `lat` and `lon` | **14,075** |
| in valid range (`-90..90 / -180..180`, excluding 10 at `(0,0)`) | **14,065** |
| `geo_confidence` | `''` 12,300 · `low` 1,775 |
| protocols | jpeg 14,308 · mjpeg 7,352 · hls 6,488 · youtube 3,831 · unknown 1,794 · iframe 1,768 |
| statuses | unverified 20,881 · unknown 7,672 · live 3,916 · dead 2,581 · stale 491 |

So the globe pins **≈14.1k** rows, not 35k. Payload measured from the real DB:

| GeoJSON variant | raw | gzip |
|---|---|---|
| full props (id,name,city,country,protocol,status) | **2.68 MB** | 0.39 MB |
| minimal props (id + geometry) | **1.69 MB** | 0.27 MB |

The viewer API caps `MAX_LIMIT = 5000` (`viewer.py:107-108`, `DEFAULT_LIMIT = 2000`), and
`/api/cameras` already accepts `bbox=w,s,e,n` + `geo=only` and returns GeoJSON features. **14k rows
therefore need either 3 paged calls (5000+5000+4065, parallel) or a new minimal endpoint**
(see §8).

---

## 3. Option A — MapLibre GL JS v5 (recommended)

### 3.1 Versions and vendoring sizes (real measurements)

- npm registry (`https://registry.npmjs.org/maplibre-gl/latest`) → **latest is now `6.12.0`** (ESM-only
  dist, `unpackedSize` 21.3 MB for the package). The **v5 line's latest is `5.24.0`** (what
  `cdn.jsdelivr.net/npm/maplibre-gl@5/dist/...` resolves to).
- jsDelivr file listing (`https://data.jsdelivr.com/v1/packages/npm/maplibre-gl@5.24.0`):

| v5.24.0 file | size |
|---|---|
| `dist/maplibre-gl.js` (minified UMD, exposed as `maplibregl`) | **1,032 KB** |
| `dist/maplibre-gl.css` | **68 KB** |
| `dist/maplibre-gl.js.map` (optional, dev only) | 5.8 MB |

- jsDelivr listing for `maplibre-gl@6.12.0`: `maplibre-gl.mjs` 583 KB + `maplibre-gl-shared.mjs` 505 KB
  + `maplibre-gl-worker.mjs` 19 KB + `maplibre-gl.css` 81 KB ≈ **1.19 MB**.

**Worker wiring (decides vendoring complexity):**
- v5 UMD: worker is bundled/inlined (dist contains `createObjectURL` and `new Worker(t.c.WORKER_URL…)`)
  → **one JS file + one CSS file, drop-in, no extra assets.**
- v6 ESM: `maplibre-gl.mjs` imports `./maplibre-gl-shared.mjs`, and spawns
  `new Worker(e, {type:'module'})` with a classic-worker fallback; the default worker URL is derived
  from `import.meta.url` → **3 files, still fine for this server** (`.mjs` MIME already correct, no CSP).
  Slight extra risk on the classic fallback path in old browsers, and it's a younger dist layout.

**Verdict: take v5.24.0 now** (simplest, battle-tested globe), keep v6 as a drop-in upgrade path.

### 3.2 Globe support — confirmed

- Globe landed in **v5**: `map.setProjection({type:'globe'})` after `style.load` (or `"projection": {"type":"globe"}`
  in the style), plus `new maplibregl.GlobeControl()`. MapLibre auto-transitions globe→mercator at high zoom
  (documented), so street zoom stays undistorted.
- **Raster tiles render on the globe** — three independent confirmations:
  1. Official MapLibre docs, custom-layer-on-a-globe example: *"MapLibre uses this approach to draw raster
     tiles on globe"* (stencil/border seam handling for raster tiles).
  2. PR #3783 "Globe — basic infrastructure, **raster layer adaptation for globe**" (the first raster pilot;
     `test/examples/globe.html` "displays a satellite map projected onto a globe").
  3. Official example **"Display a hybrid satellite map with terrain elevation"** — sets
     `projection:{type:'globe'}` + a raster `satelliteSource` (s2cloudless) + `sky {atmosphere-blend}` +
     `GlobeControl` + `TerrainControl` in one style. (Also proves hillshade/terrain on globe if we ever want it.)
- `sky` style spec has `sky-color`, `sky-horizon-blend`, `horizon-color`, `horizon-fog-blend`,
  `fog-color`, `fog-ground-blend`, `atmosphere-blend` → the "blue marble with halo" look is one style block.

### 3.3 Interactions available (all in v5)

`dragPan`, `dragRotate` (bearing), `pitchWithRotate`/`touchPitch` (tilt up to `maxPitch` 85; the hybrid
example even uses `maxPitch: 95` with terrain), `scrollZoom`, `boxZoom`, `doubleClickZoom`,
`touchZoomRotate`, `keyboard`, plus `flyTo({center,zoom,bearing,pitch,speed,curve,essential})`,
`easeTo`, `jumpTo`, `setBearing`, `setPitch`, `rotateTo`, `fitBounds`, `getBounds`, controls:
`NavigationControl({visualizePitch:true})`, `GlobeControl`, `ScaleControl`, `AttributionControl`,
`FullscreenControl`. Markers: `maplibregl.Marker` (DOM) **and** WebGL layers (preferred here).

### 3.4 Clustering — built in (supercluster in the worker)

- `GeoJSONSource` option `cluster:true` — docs state the worker "prepares the data using **geojson-vt or
  supercluster as appropriate**", so clustering never blocks the main thread.
- Config keys (official "Create and style clusters" example): `cluster:true`, `clusterMaxZoom:14`,
  `clusterRadius:50` (default 50), plus `clusterMinPoints` (used in our proof: `2`); `clusterProperties`
  for aggregate props. Cluster features carry `point_count`, `point_count_abbreviated`, `cluster_id`.
- Expansion: `map.getSource(id).getClusterExpansionZoom(cluster_id)` (also `getClusterChildren()`,
  `getClusterLeaves()`, `getBounds()`) → `map.flyTo({center, zoom})` = native expansion animation.
- Cluster counts need **glyphs** (symbol layer with `text-field:'{point_count_abbreviated}'`); raster-only
  and circle-only styles need **no glyphs at all**.

### 3.5 Glyphs (vendored, verified)

`glyphs: 'fonts/{fontstack}/{range}.pbf'` + `text-font:['Noto Sans Regular']`. Verified local vendoring:

| file | bytes |
|---|---|
| `fonts/Noto Sans Regular/0-255.pbf` | **76,580** |
| `fonts/Noto Sans Regular/256-511.pbf` (not even needed for counts) | 127,219 |

Proof harness server log shows the browser requested exactly **one** glyph range (`0-255.pbf → 200`) —
76 KB covers digits/Latin for cluster counts. (Source used for the copy: `https://tiles.openfreemap.org/fonts/...`,
free/no-key; Noto is OFL so vendoring is clean. MapLibre's demo glyph host 404'd on the same paths.)

### 3.6 Feed size / jank

- 14,065-feature GeoJSON (2.68 MB raw, all props) → source loaded in **898 ms** in the proof, then
  smooth. Tiles/whole-world parse happen in the worker; the main-thread cost is `fetch`+parse of the JSON.
- If 2.68 MB feels heavy later: minimal props = **1.69 MB** (raw) and a `?fmt=min` API variant removes
  ~37% of the bytes. A bbox-first load paints fast, full set merges in behind it (`setData`).

---

## 4. Option B — CesiumJS (verdict: viable on licence, **overkill** here)

| Fact | Evidence |
|---|---|
| Licence | **Apache-2.0**, free commercial + non-commercial (npm/README) |
| Vendored size (minimum viable) | **`Build/Cesium` = 21.74 MB**: `Cesium.js` 5.80 MB (minified UMD), `index.js` 4.59 MB, `Assets/` 4.18 MB, `ThirdParty/` 1.06 MB, `Workers/` 0.99 MB, `Widgets/` 0.49 MB. `Build/CesiumUnminified` = 45.2 MB; npm package `unpackedSize` 74.4 MB. |
| No-build vendoring | Possible (UMD `Build/Cesium/Cesium.js` + `Workers/` + `Assets/` + `Widgets/*.css` served by the same stdlib server), but that's a **21.7 MB** add pulled in whole and a second WebGL engine. |
| Keyless? | Partly. The `Viewer` default base imagery is ion-derived (**needs a Cesium ion token**); you can pass `baseLayer: new Cesium.ImageryLayer(new Cesium.OpenStreetMapImageryProvider({url}))` (documented Viewer example) or `baseLayer:false` to run keyless, and `ArcGisMapServerImageryProvider` docs state *"An ArcGIS Access Token is required to authenticate requests to an ArcGIS Image Tile service"* (i.e. its built-in ArcGIS path expects a token). So keyless = bring your own XYZ/WMS/TMS providers. |
| Clustering | Has `EntityCluster` for entities, but 14k entity pins is the wrong shape of problem for Cesium; it's built for 3D Tiles/terrain/ion. |
| Strengths | True 3D terrain, 3D Tiles, industry-standard Earth-fidelity, cinematic camera (`flyTo` with orientation), `EntityCluster`, time-dynamic data, and a mature widget set. |

**Verdict:** *viable but overkill.* 21.7 MB vendored (≈20× MapLibre), token friction on the default
imagery path, heavier API for a 14k-pin picture — and it buys terrain/3D-Tiles this project does not need.
Keep as the fallback if the brief later changes to "true 3D terrain flythroughs + 3D building tiles".

---

## 5. Option C — globe.gl / three.js custom globe (verdict: beauty, not navigation)

- globe.gl = three.js wrapper: Gorgeous GPU globes, arcs, points, glow, easy custom shaders — but
  **no map tiling, no zoom-from-space to street level**: lat/lon zoom is just camera distance. To get
  Google-Earth-like depth you'd have to build tiled imagery streaming + LOD + projection transitions
  yourself — i.e. re-implement MapLibre/Cesium. Vendor cost is modest (~600 KB three.js core + globe.gl)
  but the feature gap is structural.
- **Verdict:** great for a poster/animation or a "second screen" cosmic view; **not** the navigable world
  map. Not recommended as the primary; could be revisited later for a non-interactive hero view.

---

## 6. Imagery & tiles — every source checked with real fetches

All checks: `curl -sI`/`-s -o /dev/null -w` from this Windows host, 2026-10-06.

| Source | Template (verified) | HTTP | CORS | Max zoom (measured) | Licence / terms | Verdict |
|---|---|---|---|---|---|---|
| **Esri World Imagery** | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` | 200, `image/jpeg`, 256×256 | `Access-Control-Allow-Origin: *` | tileInfo **24 LODs (0–23)**; z=18/19/20 all 200 | Service metadata `copyrightText`: **"Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"**; terms link `https://goto.arcgisonline.com/maps/World_Imagery` | ✅ **primary base** (deep zoom, global, no key) |
| **NASA GIBS BlueMarble ShadedRelief+Bathymetry** | `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg` | 200, `image/jpeg` | `*` | **z0–8** (z=8 →200, z=9 →400) | **Public domain (NASA EOSDIS GIBS)** | ✅ low-zoom "from orbit" layer |
| **GIBS BlueMarble_NextGeneration / VIIRS_Black_Marble** | same pattern, `…/BlueMarble_NextGeneration/…/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`, `…/VIIRS_Black_Marble/…Level8/{z}/{y}/{x}.png` | 200 | `*` | z0–8 | Public domain | ✅ alternatives; Black Marble = night lights |
| **GIBS VIIRS SNPP True Colour (today's Earth)** | `…/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg` | 200, `Layer-Time-Actual: 2026-10-06T00:00:00Z` | `*` | **z0–9** (z=9 →200, z=10 →400) | Public domain | ✅ optional "live Earth" epoch layer |
| **GIBS Reference_Labels (hybrid overlay)** | `…/Reference_Labels/default/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png` (also `Reference_Features`) | 200 PNG w/ alpha | `*` | z0–9 clean | Public domain | ✅ label overlay (see caveat) |
| GIBS Reference_Labels_15m | `…/Reference_Labels_15m/default/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png` | 200 at z1–10, z13 (mid tiles); **corner tiles z0/z13 → HTTP 500** | `*` | z1–13 | Public domain | ⚠️ missing tiles surface as **500s**, not 404s → use the Level9 `Reference_Labels` instead |
| **EOX Sentinel-2 cloudless 2024** | `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg` | 200, `image/jpeg` | `*` | z13/14/15/16 all 200 (mixed png/jpeg content-type mid-range) | **CC BY-NC-SA 4.0 → non-commercial**, attribution "EOxCloudless". Also hosts `bluemarble`, `blackmarble`, `coastline`, `graticules`, `hydrography` layers | ⚠️ beautiful but non-commercial-only; nice personal "cloudless" layer |
| **OpenStreetMap raster** | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | 200 **but** header **`x-blocked: Access denied. See https://operations.osmfoundation.org/policies/tiles/`** — **still present with a normal browser UA** | `*` | z0–19 | Tile Usage Policy explicitly forbids bulk/prefetch use, requires identifying UA + ≥7-day cache, no SLA | ❌ not for the globe; the *existing* Leaflet view's OSM layer is already serving `x-blocked` from this host (pre-existing risk, worth a separate fix — e.g. a keyed provider or self-hosted tiles) |
| **MapTiler** | `https://api.maptiler.com/maps/satellite/0/0/0.jpg` | **403 without key** | — | key-dependent | key required (free tier exists) | ❌ for a no-key local app |
| OpenFreeMap vector styles/fonts | `https://tiles.openfreemap.org/styles/{bright,positron,liberty}` → 200; fonts `…/fonts/{fontstack}/{range}.pbf` → 200 `application/x-protobuf` | 200 | `*` | vector z14 | free, no key/signup | ✅ if we later want a full vector hybrid/streets; also the glyph source used in the proof |

### 6.1 Recommended combo + attribution

1. **Base raster (all zooms)** — Esri World Imagery `{z}/{y}/{x}`, `tileSize:256`, `maxzoom:19`.
2. **Low-zoom beauty layer (z0–8)** — GIBS BlueMarble_ShadedRelief_Bathymetry, `maxzoom:8`,
   visible under/over Esri with opacity blend (it gives the "blue marble + atmosphere" look at planet scale).
3. **Label overlay (optional toggle)** — GIBS `Reference_Labels` (Level9), `raster-opacity ~0.85`.
4. **Extras (toggles, all public domain)** — GIBS VIIRS true-colour ("today"), VIIRS_Black_Marble (night side).
5. **Optional pretty layer** — EOX s2cloudless-2024 (personal use only, CC BY-NC-SA — keep off by default
   and mark it in the UI).

Attribution string (rotating/compact attribution control):
`Imagery: Esri, Vantor, Earthstar Geographics, GIS User Community · Blue Marble & labels: NASA EOSDIS GIBS (public domain) · optional: EOXCloudless Sentinel-2 (CC BY-NC-SA)`.

**Politeness / caching:** pre-seed a small disk cache on the server side (a `/api/tile` proxy that stores
by URL) or simply rely on browser HTTP cache; honour the Esri `Cache-Control: max-age=86400` and GIBS's
public-domain terms; never prefetch zoom levels the user hasn't visited.

---

## 7. Clustering & LOD strategy (the "14k pins" problem)

**One source, WebGL layers, worker clustering.**

```js
map.addSource('cams', {
  type:'geojson', data:'…/api/cameras?fmt=geojson&props=min',
  cluster:true, clusterRadius:55, clusterMaxZoom:12, clusterMinPoints:2, maxzoom:15
});
// circles = clusters (size/colour by point_count), symbol = counts (glyph 0-255), circle = singles by status
```

- **Cluster** layers: `circle-color/radius` via `step` on `point_count`; `symbol` layer with
  `text-field:'{point_count_abbreviated}'` (glyphs vendored, 76 KB).
- **Click a cluster** → `getClusterExpansionZoom(id)` → `flyTo({center, zoom, speed:1.7})` → animated
  expansion. (Verified live: the API resolves and the map flies.)
- **Singles** appear at `z >= 13` as small status-coloured circles (live/unverified/unknown/dead/stale)
  → click → existing `openDrawer`/`openPlayerModal` path.
- **Filter linkage:** the sidebar filter bus already exists; on `filters` re-`setData` a filtered
  FeatureCollection (same clustering rules) — counts and pins always match the Wall/Search views.
- **LOD / progressive paint:** (a) first load bbox-scoped `/api/cameras?bbox=…&geo=only` (fast, matches
  the current viewport), (b) in parallel fetch the global minimal set so zooming out is instant, (c) cache
  the parsed FeatureCollection in the view module (survives view switches until filters change).
- **Measured:** 14,065 pts → source ready in **898 ms**; 49 clusters + 5 singles at z1.4; auto-rotate
  **144.3 FPS** (vsync-bound) on this machine; WebGL2.
- **No DOM markers on the globe** — DOM markers can render across the horizon; WebGL layers are
  horizon-correct and cheap. (Popups remain DOM — fine, they're one at a time.)

---

## 8. Lazy-load strategy (fits the existing shell)

1. `index.html`: add nothing (keeps first paint light). Do **not** add a maplibre `<script>` tag —
   the library must load only when the view opens.
2. `views.js`: add view `globe: { title:'World Map', render, destroy }` to `VIEWS` and insert `'globe'`
   into `VIEW_ORDER` (`views.js:1358`, `app.js:30`) — router, menu, hotkeys 1–8 and Ctrl-K commands pick
   it up automatically.
3. New `wfd/web/js/globeview.js` with a `loadLib()` that is the *only* place the lib is fetched:
   - **v5 UMD path (recommended):** inject `<link rel=stylesheet href="vendor/maplibre/maplibre-gl.css">`
     + `<script src="vendor/maplibre/maplibre-gl.js">`, await `onload`, resolve `window.maplibregl`.
   - **v6 ESM path (upgrade):** `const maplibregl = (await import('../vendor/maplibre/maplibre-gl.mjs')).default`
     — the server already serves `.mjs` as `text/javascript` (`viewer.py:388-399`) and sends no CSP.
4. **Prewarm on intent, not on boot:** when the user hovers/focuses the "World Map" menu item,
   `fetch()` the lib into cache (no execute) or `<link rel="preload" as="script">`; skip on metered/idle.
5. **Teardown:** on `destroy()`, `map.remove()` (frees the WebGL context), abort in-flight fetches
   (`AbortController`) and unsubscribe from the bus — mirrors the app's existing performance laws
   (IntersectionObserver / lazy / small DOM).
6. **Vendored payload added:** `wfd/web/vendor/maplibre/` = `maplibre-gl.js` 1,032 KB + `maplibre-gl.css` 68 KB
   + `fonts/Noto Sans Regular/0-255.pbf` 76 KB ≈ **1.15 MB total** (≈19× smaller than Cesium's 21.7 MB).
7. **Data endpoint:** add `props=min`/`fmt=geojson` (or `/api/globe-points`) to `viewer.py` so the globe
   gets 1.69 MB minimal GeoJSON in 1–3 calls instead of paging `MAX_LIMIT=5000` with full props (2.68 MB).

---

## 9. Proof harness (this is why the recommendation is safe)

`research/globe/proof/globe-test.html` — real MapLibre 5.24.0, globe projection, Esri raster + GIBS
labels + 14,065 real camera points clustered, auto-rotate FPS probe, click-to-expand, vendored 76 KB
glyph PBF. Served by `py -3.11 -m http.server 8799` from that directory and driven in a real browser.

Observed (`window.__status`):
`{"projection":"globe","cameras_loaded_ms":898,"clusters_in_view":49,"singles_in_view":5,"fps_autrotate":144.3}`
plus WebGL2 = `WebGL 2.0 (OpenGL ES 3.0 Chromium)`.
Server log proves **everything was local**: `maplibre-gl.js`, `maplibre-gl.css`, `cameras.geojson`,
`fonts/Noto%20Sans%20Regular/0-255.pbf` → all `200` (zero CDN at runtime).
Screenshot: 3D globe with atmosphere rim, satellite imagery, cluster bubbles `8`, `20`, `392`, `3.5k`,
`8.4k` (glyph text rendering), NavigatorControl + GlobeControl, attribution line rendering correctly.
Known cosmetic artifact: the two GIBS `Reference_Labels_15m` z2 corner tiles 500 → fixed by using the
Level9 `Reference_Labels` layer (verified 200 at all corners).

Reproduce:
```bash
cd <repo>/research/globe/proof
py -3.11 -m http.server 8799 --bind 127.0.0.1   # then open http://127.0.0.1:8799/globe-test.html
```

---

## 10. Feature list to one-up the comparable apps

Surveyed: **Google Earth web** (imagery+3D terrain, placemarks, projects, Voyager tours, historical
imagery, measurement, keyboard, share links), **NASA Eyes on the Earth**, **earth.nullschool.net**
(D3, projection switcher incl. stereographic/orthographic, 3-hourly data epochs, click-for-coordinates),
**Ventusky/Windy** (3D globe mode, layer blending, time slider, webcams layer, search), **Cesium
Sandcastle** (3D Tiles/terrain demos), **MapLibre examples** (globe, hybrid satellite+terrain, clusters,
flyTo, camera animation).

**Core 12 (must)** — each with a one-line "how":

1. **Fly-to search** — reuse `/api/cameras` FTS; `map.flyTo({center:[lon,lat], zoom:11, speed:1.4})`; results list beside the globe.
2. **Random live-cam "teleport"** — pick a `status='live'` row server-side (`/api/cameras?status=live&sort=random`), flyTo + auto-open player.
3. **Cluster-expansion click** (the Google-Earth "dive in" feel) — `getClusterExpansionZoom()` → `flyTo`; doubles as the count affordance.
4. **Idle auto-rotate** — rAF `setCenter([lng+0.12, lat])` (~17°/s), pause on `mousedown`/`touchstart`/`wheel`; toggle in the view toolbar (proof shows 144 FPS).
5. **Globe ⇄ Mercator toggle** — `maplibregl.GlobeControl()` (already the MapLibre idiom) + persist in prefs; v5 auto-transitions internally at high zoom.
6. **Status/protocol filter linkage** — data-driven paint `['match',['get','status'],…]`; on the existing `filters` bus re-`setData()`; legend chips show live counts per status.
7. **Hover preview bubble** — reuse `posterEl(cam)` in a lightweight popup (300 ms dwell) → feels like Google Earth's info cards; click → existing drawer.
8. **In-globe playback popup** — `openPlayerModal(cam)` from the globe (hls.js already vendored); single-player discipline stays.
9. **Viewport "What's here?"** — `moveend` → query `/api/cameras?bbox=…` → sidebar list of cameras currently on screen (nothing like this in the comparables' camera context).
10. **Keyboard navigation** — arrows pan / `+`-`-` zoom / `Shift+arrows` rotate-pitch / `r` random / `/` search / `f` favourite; register in the app's existing shortcut + Ctrl-K registry so the help view stays truthful.
11. **Favourites & Stage on the globe** — star layer from prefs, "fly to next favourite" (Space), add-to-stage from popup; reuses `isFav/toggleFavourite/stagedIds`.
12. **Shareable view URLs** — hash router already: `#/globe?lat=-33.86&lng=151.21&z=4.2&b=165&p=35&cam=<id>`; "Copy view link" button; restores on load.

**Stretch 6 (the "one-up" layer)**:

13. **Day/night terminator** — vendored solar-position math (~2 KB) → night-side GeoJSON polygon `fill` at 30% + optional GIBS VIIRS_Black_Marble under it (nullschool does day/night; Google Earth web doesn't).
14. **"Today's Earth" layer** — GIBS VIIRS true-colour with `{date}` swapped from a date picker (public domain, `Layer-Time-Actual` verified) — visible proof the registry isn't showing a stale planet.
15. **Tour / cinematic playlist** — sequential `flyTo` over Favourites or the Stage with dwell + aerial easing (`curve`, `speed`), Esc to stop (Google-Earth-Voyager-flavoured).
16. **Ruler / measurement** — `map.distance()` haversine between clicks, line + labels in a GeoJSON layer; also "distance from selected cam to cursor".
17. **Mini-map locator** — reuse the already-vendored **Leaflet** map as a sync'd 2D inset (globe `moveend` → minimap `setView`, and vice-versa), or a fixed canvas strip; the comparables all lack an out-of-view indicator for pins.
18. **Density heatmap toggle + "no coordinates" honesty chip** — `heatmap` layer on the same source (maxzoom 6) to show coverage gaps at a glance, plus a chip that states "12,743 rows have no coordinates — see Wall view" (matches the viewer's honest-states principle and beats every comparable on data honesty).

Adjacent wins worth noting: saved named views (placemark-style bookmarks in prefs), a "which cams are in
the current frustum *and* live" status HUD, and an offline-tolerant tile cache indicator.

---

## 11. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Only ~14.1k of 35.5k rows geocode** (12,300 blank `geo_confidence`, 10 at `(0,0)`) | Ship the honesty chip (#18); show the ungeocoded count; optionally geocode-on-demand later. Don't promise "35k pins". |
| 2 | **GIBS returns HTTP 500 for missing tiles** (not 404) → MapLibre logs errors | Use `Reference_Labels` (Level9, verified clean); scope `map.on('error')` to ignore that source, or fetch a tilejson-free static list. |
| 3 | **Esri terms for a public deployment** are stricter than for a private local app | Private/local use with the exact attribution string; keep the tile URL configurable (no hard-coding, per OSM policy advice too); revisit before any public release. |
| 4 | **14k-point payload 2.68 MB** with full props; API `MAX_LIMIT=5000` | `props=min` (1.69 MB) or a dedicated `/api/globe-points`; bbox-first progressive load; parse once and cache. |
| 5 | **v5 UMD vs v6 ESM dist churn** (v6 is now latest, ESM + separate worker file) | Take v5.24.0 now; the server already supports `.mjs` + blob workers, so the v6 upgrade is a 3-file swap plus a dynamic-import switch. |
| 6 | **DOM markers vs globe horizon** | Use WebGL circle/symbol layers (proven in the harness); popups DOM, one at a time. |
| 7 | **OSM raster tiles are blocked/unsuitable** (`x-blocked` + policy) — the flat map view already uses them | Flagged separately in the viewer; for the globe use Esri/GIBS only. |
| 8 | **Windows/stdlib server quirks** (MIME, single-file paths) | MIME map already correct (`viewer.py:388-399`); fonts can be served as octet-stream (MapLibre parses ArrayBuffer); keep vendor dir under `wfd/web/`. |
| 9 | **WebGL context loss / low-end GPUs** | `map.remove()` on view exit, `WebGL2` check with a graceful "globe unavailable — use flat map" message (the app's honest-states pattern). |
| 10 | **Feature creep in one view** | Ship Core 12 first behind the lazy view; stretch items as toggles, all prefs-persisted like `map_tiles`. |

---

## 12. Verification log (commands that produced the numbers)

```bash
# versions + dist sizes
curl -s https://registry.npmjs.org/maplibre-gl/latest | head -c 1200                     # → 6.12.0
curl -sIL https://cdn.jsdelivr.net/npm/maplibre-gl@5/dist/maplibre-gl.js | grep -i x-jsd  # → 5.24.0
curl -s https://data.jsdelivr.com/v1/packages/npm/maplibre-gl@5.24.0 | grep -o '"name":"dist[^}]*'  # sizes
curl -s https://data.jsdelivr.com/v1/packages/npm/cesium@1.146.0                          # Build/Cesium=21.74 MB

# imagery (status + CORS + zoom ceilings)
curl -sI 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/0/0/0'
curl -s  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=json'   # 24 lods, copyrightText
curl -sI 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/0/0/0.jpeg'
curl -s  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/GoogleMapsCompatible_Level9/0/0/0.jpg' -o /dev/null -w '%{http_code}\n'
curl -sI 'https://tile.openstreetmap.org/3/4/2.png' | grep -i x-blocked                    # policy block
curl -sI 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/0/0/0.jpg'  # CORS *, CC BY-NC-SA
curl -s -o /dev/null -w '%{http_code}\n' 'https://api.maptiler.com/maps/satellite/0/0/0.jpg'  # 403 (key required)

# data reality + payload
py -3.11 -c "…sqlite…"   # 35,541 rows; 14,075 lat/lon; 14,065 valid; 2.68 MB / 0.39 MB gz geojson

# live globe proof
cd research/globe/proof && py -3.11 -m http.server 8799 --bind 127.0.0.1
# browser → http://127.0.0.1:8799/globe-test.html  → window.__status
```

*Doc: research/globe/01-stack-decision.md · proof: research/globe/proof/ · 2026-10-06*

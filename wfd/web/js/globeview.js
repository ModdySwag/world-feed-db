/* wfd/web/js/globeview.js — the World Map view: a lazy MapLibre GL globe (v0.3).
 *
 * MapLibre GL JS v5.24.0 is vendored at vendor/maplibre/ and fetched on first
 * render — importing this module loads nothing. Pins come from the compact
 * /api/globe-points payload, fetched once per session and cached in this module;
 * they are ONE clustered GeoJSON source rendered by WebGL circle/symbol layers
 * (no DOM markers — they break across the globe horizon). Exposure rows are
 * always metadata-only: unverified-coloured dots, popups without actions.
 *
 * Imagery is raster-only: Esri World Imagery as the base, NASA GIBS Blue Marble
 * ShadedRelief over it for z0–8 as the "from orbit" look, plus persisted globe_*
 * toggles — GIBS Reference_Labels (labels), VIIRS Black Marble (night lights,
 * dimmed), VIIRS true colour ("today's Earth", date-pinned per globe_today_date)
 * and EOX Sentinel-2 cloudless (CC BY-NC-SA, off by default).
 *
 * Stretch features (same law: WebGL layers only, no DOM markers on the globe):
 * a client-side day/night terminator (visual cue — imagery is never swapped), a
 * date picker for the VIIRS layer, cinematic tours over favourites / Watch stage,
 * a great-circle ruler, a synced Leaflet minimap inset (bottom-left) and a
 * density heatmap — plus an honest coverage line in the header ("N geocoded of
 * T rows"). Tours and the ruler are transient; every *setting* persists.
 *
 * Population layer (info density at the default world view):
 * [1] clusters carry live/stale/dead/unk counts (clusterProperties) — the circle
 *     colour is the live SHARE, a soft blurred glow sits under each bubble and
 *     hover tooltips break the mix down;
 * [2] a country-label layer (z<=6) shows two lines — "Country" / "N cams · M live"
 *     — for the top ~28 countries (>=40 geocoded rows); ranks 13+ shrink to the
 *     2-letter code + count. Click to apply the country filter and fly to its
 *     bbox, click again to clear (counts always cover ALL statuses);
 * [3] a city-label tier (z5–9.5) from the server's `t` (city) property —
 *     "City · N", with the count threshold stepping up as you zoom out;
 * [4] progressive camera disclosure: single dots fade/grow in from z3.5 while
 *     the cluster split starts a stop earlier (clusterRadius 50 / maxZoom 11),
 *     and live singles carry a pulsing glow (rAF ~10 fps; paused while the
 *     document is hidden; static under prefers-reduced-motion);
 * [5] a fixed-position hover card (250 ms dwell) details a cluster breakdown or a
 *     pin (lazy /api/poster/<cid> preview; exposure rows stay metadata-only);
 * [6] an always-on 'world pulse' strip counts what the viewport holds
 *     (cams · live · 'hot right now' country — click to filter · top countries ·
 *     families present);
 * [7] a collapsible legend decodes the status dots and the cluster live-share ramp;
 * [8] a World/Region/City viewpoint-preset group — transient easeTo jumps.
 *
 * v0.4.5 — photo pins + the area panel (still WebGL-only on the globe):
 * [9] photo pins: as the user zooms in (z9.5+, setting globe_photo_pins) real
 *     camera posters materialise as pin thumbnails above their dots. A viewport-
 *     debounced pass takes the first ~70 rendered singles (queryRenderedFeatures,
 *     topped up by bbox over the cached collection) through a 5-wide queue,
 *     downscales each poster to a 44×30 thumb and registers it with
 *     map.addImage('pp-<cid>'). A missing/404/blocked poster is skipped — the
 *     dot stays, never a broken marker. The registry is capped (~300, LRU) and
 *     images that drift far out of view are released (map.removeImage);
 * [10] the area panel: clicking a cluster total, a country label or a city label
 *     opens a right-hand menu for that area — status-breakdown chips, the area's
 *     cameras as rows (thumbnail, Watch / Details / ★ / ＋Stage), search-in-area,
 *     sort (name/status) and All/Live/Stale chips, plus contextual actions:
 *     Zoom to fit · Show photos (pane-only poster pins) · Filter (country panes,
 *     the same setFilters the label click uses). Content re-derives from the
 *     cached points + the active filters; the panel state is never persisted.
 *
 * Settings keys (all via saveSettings, all prefs-persisted):
 *   globe_labels · globe_night · globe_today · globe_today_date · globe_eox ·
 *   globe_terminator · globe_heat · globe_minimap · globe_autorotate ·
 *   globe_favonly · globe_legend · globe_photo_pins
 */
import {
  store, bus, apiGet, esc, fmt, toast, saveSettings, openDrawer, openPlayerModal,
  toggleFavourite, isFav, copyText, go, viewLink, statusChipHTML,
  rememberCamera, clamp, stagedIds, setFilters, reduced, addToStage,
} from './app.js';
import { playSound } from './sound.js';

/* ── local icons (same convention as views.js) ───────────────────────── */

const I = {
  layers: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 9 5-9 5-9-5 9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/></svg>',
  rotate: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>',
  dice: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="8.5" cy="15.5" r="1.2" fill="currentColor"/></svg>',
  copy: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  star: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  play: '<svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  info: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
  globe: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/></svg>',
  term: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/></svg>',
  tour: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="m10 8 5 2.5-5 2.5z" fill="currentColor" stroke="none"/><path d="M8 20h8"/></svg>',
  ruler: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21.3 8.7 15.3 2.7a2.4 2.4 0 0 0-3.4 0L2.7 11.9a2.4 2.4 0 0 0 0 3.4l6 6a2.4 2.4 0 0 0 3.4 0l9.2-9.2a2.4 2.4 0 0 0 0-3.4z"/><path d="m7.5 10.5 2 2"/><path d="m10.5 7.5 2 2"/><path d="m13.5 4.5 2 2"/></svg>',
  chev: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  plus: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>',
  frame: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
  filt: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/></svg>',
  cam: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
};

/* ── constants ───────────────────────────────────────────────────────── */

const LIB_CSS = 'vendor/maplibre/maplibre-gl.css';
const LIB_JS = 'vendor/maplibre/maplibre-gl.js';
const GLYPHS = 'vendor/maplibre/fonts/{fontstack}/{range}.pbf';
const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/';
const ATTRIB = 'Imagery: Esri, Vantor, Earthstar Geographics, GIS User Community '
  + '| Blue Marble & labels: NASA EOSDIS GIBS (public domain)';
const WORLD_VIEW = { lat: 20, lng: 0, zoom: 1.6, bearing: 0, pitch: 0 };
const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const PIN_COLOR = ['match', ['get', 's'], 'live', '#3ddc84', 'stale', '#f5a524',
  'dead', '#ef5350', 'unverified', '#b9a8f5', '#8892a0'];
const LAYER_KEYS = {
  labels: 'globe-labels', night: 'globe-night', today: 'globe-today', eox: 'globe-eox',
};
const ESRI_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const RAD = Math.PI / 180;
const TERM_REFRESH_MS = 60000;              // terminator recompute cadence
const TERM_FILL_ID = 'globe-terminator-fill';
const TERM_GLOW_ID = 'globe-terminator-glow';
const COUNTRY_MIN_ROWS = 40;              // country labels need this many geocoded rows
const COUNTRY_CAP = 28;                   // …and only the top-N by count get a label
const PULSE_MS = 300;                     // world-pulse refresh throttle
const HCARD_DWELL_MS = 250;               // hover-card dwell before it appears
/* cluster fill = live share (live / point_count): grey-violet -> amber -> teal/green */
const CLUSTER_FILL = ['interpolate', ['linear'], ['/', ['get', 'live'], ['get', 'point_count']],
  0, '#8892a0', 0.08, '#a09cc0', 0.3, '#f5a524', 0.62, '#22d3ee', 0.85, '#3ddc84'];

/* progressive disclosure + city tier (see the header block) ──────────────── */
const CLUSTER_RADIUS = ['interpolate', ['linear'], ['zoom'],
  0, ['step', ['get', 'point_count'], 15, 100, 20, 750, 28],
  4, ['step', ['get', 'point_count'], 14, 100, 19, 750, 27],
  7, ['step', ['get', 'point_count'], 13, 100, 18, 750, 25],
  10, ['step', ['get', 'point_count'], 12, 100, 17, 750, 23]];
/* glow = the same ramp pre-scaled 1.6x. MapLibre v5 rejects a zoom expression
 * nested inside arithmetic ("may only be used as input to a top-level step or
 * interpolate"), so the factor is folded into the stops, never applied with *. */
const CLUSTER_GLOW_RADIUS = ['interpolate', ['linear'], ['zoom'],
  0, ['step', ['get', 'point_count'], 24, 100, 32, 750, 44.8],
  4, ['step', ['get', 'point_count'], 22.4, 100, 30.4, 750, 43.2],
  7, ['step', ['get', 'point_count'], 20.8, 100, 28.8, 750, 40],
  10, ['step', ['get', 'point_count'], 19.2, 100, 27.2, 750, 36.8]];
const SINGLE_RADIUS = ['interpolate', ['linear'], ['zoom'],
  3.5, 1.6, 6, 2.6, 9, 3.6, 12, 4.6, 14, 6];
const SINGLE_MINZOOM = 3.5;                // below this the singles regress (clusters only)
const PULSE_LAYER = 'globe-live-pulse';    // live-dot glow, rAF-animated
const PULSE_MINZOOM = 4; const PULSE_MAXZOOM = 13;
const CITY_MIN_ROWS = 8;                   // fewest rows a city ever needs to be labelled
const CITY_CAP = 200;                      // …and only the top-N cities are built
const CITY_MAXZOOM = 9.5;                  // the city tier regresses past z9.5
const CITY_BANDS = [[9, 8], [7, 15], [5, 40]];    // zoom >= z -> min cams for a label
const COUNTRY_TOP = 12;                    // ranks 1-12 keep the full name; the rest "CC · N"

/* photo pins + area panel (v0.4.5) ──────────────────────────────────── */
const PHOTO_LAYER = 'globe-photo-pins';    // poster thumbnails above the single dots
const PHOTO_MARK = 'pp-';                  // registered-image id prefix ('pp-<cid>')
const PHOTO_AUTO_MINZOOM = 9.5;            // 'auto': posters appear as you zoom in
const PHOTO_ON_MINZOOM = 6;                // 'on': forced from z6
const PHOTO_BATCH = 70;                    // posters queued per viewport pass
const PHOTO_CONC = 5;                      // concurrent poster fetches
const PHOTO_MAX = 300;                     // registered-image cap (LRU eviction)
const PHOTO_THUMB_W = 44, PHOTO_THUMB_H = 30;   // thumb size (fit-cover crop)
const PHOTO_DEBOUNCE_MS = 350;             // viewport settle before queueing posters
const PHOTO_SIZE = ['interpolate', ['linear'], ['zoom'],
  6, 0.62, 9.5, 0.9, 10, 1, 13, 1.12, 16, 1.2];
const PANE_SOURCE = 'pane-members';        // the area panel's 'Show photos' source
const PANE_LAYER = 'pane-photo-pins';      // …and its symbol layer
const PANE_PHOTO_BATCH = 40;               // posters 'Show photos' registers
const PANE_PAGE = 120;                     // rows rendered per page
const PANE_STATUS_RANK = { live: 0, stale: 1, dead: 2, unknown: 3, unverified: 4, '': 3 };

/* ── module state (survives view switches; reset by cleanup) ─────────── */

let M = null;                 // window.maplibregl, resolved by loadLib()
let libPromise = null;        // memoised lazy-load
let pointsCache = null;       // compact FeatureCollection — one fetch per session
let map = null;
let ui = {};
let unsubs = [];
let ac = null;                // AbortController for the points fetch
let destroyed = false;
let styleReady = false;
let rafId = 0;
let hereTimer = null; let hereSeq = 0; let hereFeats = [];
let hashTimer = null;
let hoverTimer = null; let hoverId = null; let hoverLatLng = null;
let hoverPopup = null; let clickPopup = null;
let lastInput = 0;
let docClose = null;
let termTimer = null;                 // 60 s terminator refresh interval
let termWanted = false;               // last requested terminator state (style may rebuild)
let tourState = null;                 // active tour: {stops, i, count, dwell, skipped, apiOk}
let tourSeq = 0;                      // guards the async playlist build
let measureState = null;              // active measurement: {cam, pts}
let miniMap = null; let miniBox = null; let miniDot = null; let miniHalo = null;
let miniTimer = null;                 // minimap viewport-sync throttle
let escHandler = null;                // document-level Esc (tour/measure only)
let statsTotal;                       // /api/stats rows (undefined = not asked, null = unavailable)
let countryBox = new Map();           // country -> [w,s,e,n] bbox (country-label clicks)
let pulseTimer = null;
let cardTimer = null;                 // hover-card dwell timer
let cardKey = null;                   // feature currently under the cursor
let cardFor = null;                   // feature the visible card is showing
let cardAnchor = null; let cardAnchorPx = null;
let posterSeq = 0;                    // guards the one-poster-at-a-time fetch
const posterCache = new Map();        // cid -> 'ok' | 'none'
let pulseLast = 0;                    // live-pulse paint throttle (~10 fps)
let pulsePhase = 0;                   // oscillation phase (rad)
let pulseStatic = false;              // reduced motion: one static glow, set once
let photoMode = 'auto';               // globe_photo_pins: 'auto' | 'on' | 'off'
let photoTimer = null;                // viewport-debounce for the poster pass
let photoAbort = null;                // aborts the in-flight poster batch
let photoSeq = 0;                     // stale-batch guard
const photoReg = new Map();           // cid -> true (image on the current style; insertion = LRU)
const photoMiss = new Set();          // cid -> poster 404'd this session (never retried)
const photoPinned = new Set();        // cids the area panel's 'Show photos' owns (LRU-exempt)
let camCoords = null;                 // cid -> [lon, lat], built lazily from the cached points
let pane = null;                      // open area panel: {kind, key, all, members, q, sort, filt, …}
let paneHideTimer = null;             // slide-out → hidden

/* ── lazy library load (the only place MapLibre is fetched) ──────────── */

function loadLib() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (libPromise) return libPromise;
  libPromise = new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = LIB_CSS;
    document.head.appendChild(link);
    const s = document.createElement('script');
    s.src = LIB_JS;
    s.onload = () => (window.maplibregl
      ? resolve(window.maplibregl)
      : reject(new Error('maplibre-gl.js loaded but window.maplibregl is missing')));
    s.onerror = () => reject(new Error('failed to load ' + LIB_JS));
    document.head.appendChild(s);
  });
  libPromise.catch(() => { libPromise = null; });   // a failed load can be retried
  return libPromise;
}

function hasWebGL2() {
  try { return !!document.createElement('canvas').getContext('webgl2'); }
  catch (err) { return false; }
}

/* ── style (raster-only: Esri base + GIBS beauty/labels/extras) ──────── */

function buildStyle() {
  const todayD = todayDateVal();                              // globe_today_date, else today (UTC)
  const heatOn = !!store.settings.globe_heat;
  const vis = (key) => (store.settings[key] ? 'visible' : 'none');
  return {
    version: 8,
    glyphs: GLYPHS,
    sky: { 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 3, 0.5, 7, 0] },
    sources: {
      esri: {
        type: 'raster', tileSize: 256, maxzoom: 19,
        tiles: [ESRI_TILES],                                  // same template as the minimap inset
      },
      bluemarble: {
        type: 'raster', tileSize: 256, maxzoom: 8,
        tiles: [GIBS + 'BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'],
      },
      labels: {
        type: 'raster', tileSize: 256, maxzoom: 9,
        tiles: [GIBS + 'Reference_Labels/default/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png'],
      },
      night: {
        type: 'raster', tileSize: 256, maxzoom: 8,
        tiles: [GIBS + 'VIIRS_Black_Marble/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png'],
        attribution: 'Night lights: NASA EOSDIS GIBS — VIIRS Black Marble (public domain)',
      },
      today: {
        type: 'raster', tileSize: 256, maxzoom: 9,
        tiles: todayTiles(todayD),                            // the date IS the WMTS path segment
        attribution: "Today's Earth: NASA EOSDIS GIBS — VIIRS true colour (public domain)",
      },
      eox: {
        type: 'raster', tileSize: 256, maxzoom: 16,
        tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'],
        attribution: 'Sentinel-2 cloudless by EOX (CC BY-NC-SA 4.0)',
      },
      cams: {
        type: 'geojson', data: EMPTY_FC,
        cluster: true, clusterRadius: 50, clusterMaxZoom: 11, clusterMinPoints: 2,
        // cluster intelligence: every cluster carries status counts so colour and
        // tooltips can speak in live-share terms (reduce over the point properties)
        clusterProperties: {
          live: ['+', ['case', ['==', ['get', 's'], 'live'], 1, 0]],
          stale: ['+', ['case', ['==', ['get', 's'], 'stale'], 1, 0]],
          dead: ['+', ['case', ['==', ['get', 's'], 'dead'], 1, 0]],
          unk: ['+', ['case', ['in', ['get', 's'], ['literal', ['unknown', 'unverified', '']]], 1, 0]],
        },
      },
      'cams-heat': { type: 'geojson', data: EMPTY_FC },       // non-clustered copy for the heatmap
      countries: { type: 'geojson', data: EMPTY_FC },         // country labels (built from the cached points)
      cities: { type: 'geojson', data: EMPTY_FC },            // city labels (t property, same cache)
      focus: { type: 'geojson', data: EMPTY_FC },
      'measure-dots': { type: 'geojson', data: EMPTY_FC },
      'measure-line': { type: 'geojson', data: EMPTY_FC },
    },
    layers: [
      { id: 'globe-bg', type: 'background', paint: { 'background-color': '#05070d' } },
      { id: 'globe-esri', type: 'raster', source: 'esri' },
      { id: 'globe-bluemarble', type: 'raster', source: 'bluemarble', maxzoom: 8 },
      { id: 'globe-night', type: 'raster', source: 'night', maxzoom: 8,
        layout: { visibility: vis('globe_night') }, paint: { 'raster-opacity': 0.85 } },
      { id: 'globe-today', type: 'raster', source: 'today', maxzoom: 9,
        layout: { visibility: vis('globe_today') }, paint: { 'raster-opacity': 0.95 } },
      { id: 'globe-eox', type: 'raster', source: 'eox',
        layout: { visibility: vis('globe_eox') } },
      { id: 'globe-labels', type: 'raster', source: 'labels', maxzoom: 9,
        layout: { visibility: vis('globe_labels') }, paint: { 'raster-opacity': 0.85 } },
      // density heatmap — a non-clustered copy of the same points; reads best with the pins dimmed
      { id: 'globe-heat', type: 'heatmap', source: 'cams-heat',
        layout: { visibility: vis('globe_heat') },
        paint: {
          'heatmap-weight': 1,
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 0.6, 6, 1.1, 12, 1.6],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 8, 5, 14, 10, 22, 16, 26],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.85, 9, 0.8, 14, 0.35],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(5, 7, 13, 0)',
            0.15, 'rgba(34, 211, 238, 0.18)',
            0.35, 'rgba(45, 212, 191, 0.42)',
            0.55, 'rgba(250, 204, 21, 0.6)',
            0.75, 'rgba(244, 114, 182, 0.72)',
            1, 'rgba(239, 83, 80, 0.85)'],
        } },
      { id: 'globe-focus', type: 'circle', source: 'focus', paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 10, 9, 22],
        'circle-color': 'rgba(45,212,191,.14)', 'circle-stroke-width': 2.5,
        'circle-stroke-color': '#2dd4bf',
      } },
      // country labels — a two-line "Country / N cams · M live" for the top
      // countries, built from the cached points; present at world zoom, faded
      // out by z>6 (layer maxzoom 7). The label string is computed client-side
      // (label prop) so it can carry both lines and the live split.
      { id: 'globe-country-labels', type: 'symbol', source: 'countries', maxzoom: 7,
        layout: {
          'text-field': ['get', 'label'], 'text-font': ['Noto Sans Regular'],
          'text-size': ['step', ['get', 'cnt'], 11, 100, 13, 400, 15],
          'text-max-width': 20, 'text-padding': 3, 'text-allow-overlap': false,
          'text-line-height': 1.15,
        },
        paint: {
          'text-color': '#eaf2ff',
          'text-halo-color': 'rgba(4, 7, 12, 0.9)', 'text-halo-width': 1.5,
          'text-opacity': ['interpolate', ['linear'], ['zoom'], 3, 1, 5.5, 0.6, 6.6, 0],
        } },
      { id: 'globe-clusters-glow', type: 'circle', source: 'cams', filter: ['has', 'point_count'],
        paint: {
          'circle-color': CLUSTER_FILL,                     // same live-share ramp, blurred halo
          'circle-radius': CLUSTER_GLOW_RADIUS,             // 1.6x, pre-scaled stops
          'circle-opacity': clusterGlowOpacityExpr(heatOn),
          'circle-blur': 1,
        } },
      { id: 'globe-clusters', type: 'circle', source: 'cams', filter: ['has', 'point_count'],
        paint: {
          'circle-color': CLUSTER_FILL,                     // live share, not raw size
          'circle-radius': CLUSTER_RADIUS,
          'circle-opacity': clusterOpacityExpr(heatOn),     // soft regress as they split
          'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff',
        } },
      { id: 'globe-cluster-count', type: 'symbol', source: 'cams', filter: ['has', 'point_count'],
        layout: { 'text-field': '{point_count_abbreviated}', 'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 0, 12.5, 4, 11.5, 8, 11] },
        paint: { 'text-color': '#04121a', 'text-halo-color': 'rgba(255, 255, 255, 0.28)',
          'text-halo-width': 0.6, 'text-opacity': heatOn ? 0.25 : 1 } },
      // city tier — placed ABOVE the cluster layers on purpose: symbol collision
      // ranks by draw order (a later layer wins), and below them the cluster
      // count text hides the city label at every shared anchor (measured).
      // "City · N" at z5–9.5; the count threshold steps up as you zoom out
      // (CITY_BANDS, re-applied by updateCityTier on every moveend).
      { id: 'globe-city-labels', type: 'symbol', source: 'cities',
        minzoom: 5, maxzoom: CITY_MAXZOOM,
        filter: ['>=', ['get', 'cnt'], 40],
        layout: {
          'text-field': ['get', 'label'], 'text-font': ['Noto Sans Regular'],
          'text-size': ['step', ['get', 'cnt'], 10.5, 40, 11.5, 80, 12.5],
          'text-max-width': 14, 'text-padding': 3, 'text-allow-overlap': false,
        },
        paint: {
          'text-color': '#d9e7f5',
          'text-halo-color': 'rgba(4, 7, 12, 0.9)', 'text-halo-width': 1.2,
          'text-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0, 5.5, 1, 9, 1, 9.4, 0],
        } },
      { id: PULSE_LAYER, type: 'circle', source: 'cams',
        minzoom: PULSE_MINZOOM, maxzoom: PULSE_MAXZOOM,
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 's'], 'live']],
        paint: {                                          // startLoop animates radius/opacity ~10 fps
          'circle-color': '#3ddc84', 'circle-blur': 0.7,
          'circle-radius': pulseRadiusExpr(1.4), 'circle-opacity': 0.2,
        } },
      { id: 'globe-points', type: 'circle', source: 'cams', filter: ['!', ['has', 'point_count']],
        minzoom: SINGLE_MINZOOM,                          // progressive: regress below z3.5
        paint: {
          'circle-color': PIN_COLOR,
          'circle-radius': SINGLE_RADIUS,                 // grow with zoom
          'circle-opacity': pointsOpacityExpr(heatOn),    // fade in from z3.5
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 3.5, 0, 6, 0.5, 12, 0.9],
          'circle-stroke-color': '#ffffff',
        } },
      // photo pins (v0.4.5) — poster thumbnails registered at runtime by the
      // viewport pass as map.addImage('pp-<cid>'). A camera without a cached
      // poster simply never renders here (MapLibre skips a missing icon-image),
      // so its dot underneath stays the honest fallback. 'auto' fades in from
      // z9.5; 'on' forces from z6; 'off' hides the layer (setting toggle).
      { id: PHOTO_LAYER, type: 'symbol', source: 'cams',
        minzoom: photoMode === 'on' ? PHOTO_ON_MINZOOM : PHOTO_AUTO_MINZOOM,
        maxzoom: 20,
        // starts empty: only cams with a REGISTERED poster pass (applyPhotoFilters
        // composes the dots' rule with the live image registry — MapLibre then
        // never asks for an image that does not exist)
        filter: ['boolean', false],
        layout: {
          'icon-image': ['concat', PHOTO_MARK, ['get', 'c']],
          'icon-size': PHOTO_SIZE,
          'icon-anchor': 'bottom', 'icon-offset': [0, -5],   // pin-like: the poster sits above the dot
          'icon-allow-overlap': ['step', ['zoom'], false, 12, true],
          'icon-padding': 2,
        },
        paint: { 'icon-opacity': photoOpacityExpr() } },
      { id: 'globe-measure-line', type: 'line', source: 'measure-line',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#2dd4bf', 'line-width': 1.6, 'line-opacity': 0.9,
          'line-dasharray': [2, 1.5] } },
      { id: 'globe-measure-dots', type: 'circle', source: 'measure-dots',
        paint: { 'circle-radius': 3.5, 'circle-color': '#2dd4bf',
          'circle-stroke-width': 1.5, 'circle-stroke-color': '#04121a' } },
    ],
  };
}

/* ── data ────────────────────────────────────────────────────────────── */

function fetchPoints() {
  if (!ac) ac = new AbortController();
  return fetch('/api/globe-points', { signal: ac.signal, headers: { Accept: 'application/json' } })
    .then((res) => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then((fc) => { pointsCache = fc; return fc; });
}

function pushPoints(fc) {
  const src = map && map.getSource('cams');
  if (!src) return;
  src.setData(fc);
  const heat = map.getSource('cams-heat');       // same rows, one non-clustered copy
  if (heat) heat.setData(fc);
  pushCountryLabels(fc);
  pushCityLabels(fc);
  const n = (fc.features || []).length;
  if (window.__globe) window.__globe.points = n;
  if (ui.loading) ui.loading.hidden = true;
  ensureStatsTotal();
  setSubLine(n);
  updateDebugCounts();
  schedulePulse();
}

/* country aggregation for the label layer — count + status split + wrapped mean
 * centroid + bbox. Labels reflect the FULL cached set (all statuses) by design:
 * they are a coverage read of the map, not a filtered result (the tooltip says
 * so when a status filter is active). Countries with >= COUNTRY_MIN_ROWS rows
 * only, top COUNTRY_CAP. Line 1 = full display name for the top COUNTRY_TOP
 * ranks, else "CC · N"; line 2 = "N cams · M live". Latin-1 glyphs only. */

/* ISO alpha-2 -> display name for every code present in the registry; an
 * unknown 2-letter code falls back to itself (honest, never invented). */
const COUNTRY_NAMES = {
  AI: 'Anguilla', AL: 'Albania', AR: 'Argentina', AT: 'Austria', AU: 'Australia',
  AW: 'Aruba', BA: 'Bosnia and Herzegovina', BB: 'Barbados', BE: 'Belgium',
  BG: 'Bulgaria', BL: 'Saint Barthelemy', BM: 'Bermuda', BO: 'Bolivia',
  BQ: 'Caribbean Netherlands', BR: 'Brazil', BY: 'Belarus', BZ: 'Belize',
  CA: 'Canada', CD: 'DR Congo', CH: 'Switzerland', CL: 'Chile', CN: 'China',
  CR: 'Costa Rica', CV: 'Cabo Verde', CW: 'Curacao', CY: 'Cyprus',
  CZ: 'Czechia', DE: 'Germany', DK: 'Denmark', DO: 'Dominican Republic',
  EC: 'Ecuador', EE: 'Estonia', EG: 'Egypt', ES: 'Spain', FI: 'Finland',
  FO: 'Faroe Islands', FR: 'France', GB: 'United Kingdom', GD: 'Grenada',
  GP: 'Guadeloupe', GR: 'Greece', GT: 'Guatemala', GY: 'Guyana', HR: 'Croatia',
  HU: 'Hungary', ID: 'Indonesia', IE: 'Ireland', IL: 'Israel', IN: 'India',
  IQ: 'Iraq', IR: 'Iran', IS: 'Iceland', IT: 'Italy', JM: 'Jamaica',
  JO: 'Jordan', JP: 'Japan', KE: 'Kenya', KG: 'Kyrgyzstan', KR: 'South Korea',
  KY: 'Cayman Islands', KZ: 'Kazakhstan', LA: 'Laos', LK: 'Sri Lanka',
  LT: 'Lithuania', LU: 'Luxembourg', LV: 'Latvia', MA: 'Morocco',
  MK: 'North Macedonia', MQ: 'Martinique', MT: 'Malta', MU: 'Mauritius',
  MV: 'Maldives', MX: 'Mexico', MY: 'Malaysia', NA: 'Namibia',
  NL: 'Netherlands', NO: 'Norway', NZ: 'New Zealand', PA: 'Panama',
  PE: 'Peru', PH: 'Philippines', PL: 'Poland', PR: 'Puerto Rico',
  PT: 'Portugal', PY: 'Paraguay', RO: 'Romania', RS: 'Serbia', RU: 'Russia',
  SA: 'Saudi Arabia', SC: 'Seychelles', SE: 'Sweden', SG: 'Singapore',
  SI: 'Slovenia', SK: 'Slovakia', SM: 'San Marino', SV: 'El Salvador',
  SX: 'Sint Maarten', TC: 'Turks and Caicos', TH: 'Thailand', TR: 'Turkey',
  TT: 'Trinidad and Tobago', TW: 'Taiwan', TZ: 'Tanzania', UA: 'Ukraine',
  US: 'United States', UY: 'Uruguay', VA: 'Vatican City', VE: 'Venezuela',
  VG: 'British Virgin Islands', VI: 'U.S. Virgin Islands', VN: 'Vietnam',
  XK: 'Kosovo', XX: 'Unknown', ZA: 'South Africa', ZM: 'Zambia',
};

/* Latin-1 only: the vendored Noto Sans subset ships range 0-255, so strip
 * anything above it (CJK, arrows, emoji) — a label must never render as tofu. */
function sanitizeLatin(s) {
  return String(s || '').replace(/[^\x20-\xFF]/g, ' ').replace(/\s+/g, ' ').trim();
}

function titleCaseName(s) {
  return s.toLowerCase()
    .replace(/\bof\b/g, 'of').replace(/\band\b/g, 'and').replace(/\bthe\b/g, 'the')
    .replace(/(^|[\s,(])([a-z])/g, (m, p, c) => p + c.toUpperCase());
}

/* display name for a `y` value: 2-letter code -> mapped name; an all-caps
 * stored name -> title case; anything else is already a display name. */
function countryDisplayName(y) {
  const raw = sanitizeLatin(y);
  if (!raw) return '';
  const up = raw.toUpperCase();
  if (/^[A-Z]{2}$/.test(up)) return COUNTRY_NAMES[up] || up;
  return raw === up ? titleCaseName(raw) : raw;
}

function buildCountryLabels(fc) {
  const agg = new Map();
  for (const f of (fc && fc.features) || []) {
    const p = f.properties || {};
    const g = f.geometry && f.geometry.coordinates;
    if (!p.y || !g) continue;
    const lon = Number(g[0]); const lat = Number(g[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    let a = agg.get(p.y);
    if (!a) { a = { n: 0, live: 0, stale: 0, dead: 0, unk: 0, cx: 0, cy: 0, lat: 0, w: 181, e: -181, s: 91, n2: -91 }; agg.set(p.y, a); }
    a.n++; a.lat += lat;
    a.cx += Math.cos(lon * RAD); a.cy += Math.sin(lon * RAD);   // wrapped mean (antimeridian-safe)
    if (lon < a.w) a.w = lon;
    if (lon > a.e) a.e = lon;
    if (lat < a.s) a.s = lat;
    if (lat > a.n2) a.n2 = lat;
    const s = p.s || '';
    if (s === 'live') a.live++;
    else if (s === 'stale') a.stale++;
    else if (s === 'dead') a.dead++;
    else a.unk++;
  }
  const rows = [...agg.entries()].filter(([, a]) => a.n >= COUNTRY_MIN_ROWS)
    .sort((x, y) => y[1].n - x[1].n).slice(0, COUNTRY_CAP);
  countryBox = new Map();
  const features = rows.map(([y, a], i) => {
    countryBox.set(y, [a.w, a.s, a.e, a.n2]);
    const mlon = Math.atan2(a.cy / a.n, a.cx / a.n) / RAD;
    const line1 = i < COUNTRY_TOP
      ? (countryDisplayName(y) || sanitizeLatin(y))
      : `${sanitizeLatin(y)} · ${fmt(a.n)}`;               // small ones: code + count
    const line2 = `${fmt(a.n)} cams · ${fmt(a.live)} live`;
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [mlon, a.lat / a.n] },
      properties: { y, cnt: a.n, live: a.live, stale: a.stale, dead: a.dead, unk: a.unk,
        label: `${line1}\n${line2}` },
    };
  });
  return { type: 'FeatureCollection', features };
}

/* city aggregation for the label tier — name + count + wrapped mean centroid.
 * Same coverage law as the country tier (the FULL cached set, all statuses);
 * only cities with >= CITY_MIN_ROWS rows are built (top CITY_CAP by count) and
 * updateCityTier() re-applies the per-zoom count threshold on every moveend. */
function buildCityLabels(fc) {
  const agg = new Map();
  for (const f of (fc && fc.features) || []) {
    const p = f.properties || {};
    const g = f.geometry && f.geometry.coordinates;
    if (!p.t || !g) continue;
    const name = sanitizeLatin(p.t);
    if (!name || !/[A-Za-z0-9]/.test(name)) continue;    // skip '-', '', punctuation-only
    const lon = Number(g[0]); const lat = Number(g[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const key = name.toLowerCase();
    let a = agg.get(key);
    if (!a) { a = { name: name.slice(0, 26), n: 0, live: 0, cx: 0, cy: 0, lat: 0 }; agg.set(key, a); }
    a.n++; a.lat += lat;
    a.cx += Math.cos(lon * RAD); a.cy += Math.sin(lon * RAD);
    if (p.s === 'live') a.live++;
  }
  const rows = [...agg.values()].filter((a) => a.n >= CITY_MIN_ROWS)
    .sort((x, y) => y.n - x.n).slice(0, CITY_CAP);
  const features = rows.map((a) => {
    const mlon = Math.atan2(a.cy / a.n, a.cx / a.n) / RAD;
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [mlon, a.lat / a.n] },
      properties: { t: a.name, cnt: a.n, live: a.live, label: `${a.name} · ${fmt(a.n)}` },
    };
  });
  return { type: 'FeatureCollection', features };
}

function pushCountryLabels(fc) {
  const src = map && map.getSource('countries');
  const data = buildCountryLabels(fc);
  if (src) src.setData(data);
  if (window.__globe) window.__globe.countryLabels = data.features.length;
}

function pushCityLabels(fc) {
  const src = map && map.getSource('cities');
  const data = buildCityLabels(fc);
  if (src) src.setData(data);
  if (window.__globe) window.__globe.cities = data.features.length;
  updateCityTier();
}

/* the city tier's count threshold steps by zoom band (CITY_BANDS): z5–6 shows
 * cities with >= 40 rows, z7–8 >= 15, z9 >= 8; past z9.5 the layer maxzoom
 * retires it. A moveend re-applies the threshold band. */
function updateCityTier() {
  if (!map || !styleReady) return;
  const z = map.getZoom();
  let min = null;
  for (const [z0, m] of CITY_BANDS) { if (z >= z0) { min = m; break; } }
  try {
    map.setFilter('globe-city-labels', min == null
      ? ['boolean', false] : ['>=', ['get', 'cnt'], min]);
  } catch (err) { /* style mid-swap — the next moveend re-applies */ }
}

/* honest coverage: "N geocoded of T rows" — T from /api/stats, asked once. */
function ensureStatsTotal() {
  if (statsTotal !== undefined) return;
  if (store.stats && store.stats.total != null) { statsTotal = store.stats.total; return; }
  statsTotal = null;                                     // omit T until the one lookup lands
  apiGet('/api/stats').then((s) => {
    if (destroyed || !s || s.total == null) return;
    statsTotal = s.total;
    if (pointsCache && ui.sub) setSubLine((pointsCache.features || []).length);
  }).catch(() => { /* keep it omitted — never guess a total */ });
}

function setSubLine(n) {
  if (!ui.sub) return;
  ui.sub.textContent = statsTotal != null
    ? `${fmt(n)} geocoded of ${fmt(statsTotal)} rows · clustered pins · imagery: Esri + NASA GIBS`
    : `${fmt(n)} geocoded rows · clustered pins · imagery: Esri + NASA GIBS`;
  ui.sub.title = statsTotal != null
    ? `every geocoded row is on the globe — ${fmt(Math.max(0, statsTotal - n))} rows have no coordinates (Wall / Search)`
    : 'geocoded rows on the globe';
}

async function kickPoints() {
  try {
    const fc = pointsCache || await fetchPoints();
    if (destroyed || !map) return;
    if (styleReady) pushPoints(fc);
  } catch (err) {
    if (destroyed) return;
    if (window.__globe) window.__globe.errors.push('points: ' + (err.message || err));
    if (ui.loading) {
      ui.loading.hidden = false;
      ui.loading.textContent = 'camera points failed — ' + (err.message || err);
    }
    toast('Globe data failed — ' + (err.message || err), { type: 'err' });
  }
}

/* ── filters (client-side, instant) ──────────────────────────────────── */

function activeFilterExpr() {
  const f = store.filters;
  const parts = [];
  const dim = (prop, values) => {
    const arr = (values || []).filter((v) => typeof v === 'string' && v);
    if (arr.length) parts.push(['match', ['get', prop], arr, true, false]);
  };
  dim('s', f.status);
  dim('p', f.protocol);
  dim('f', f.family);
  const countries = (f.country || []).filter(Boolean).map((c) => String(c).toUpperCase());
  if (countries.length) {
    parts.push(['in', ['upcase', ['get', 'y']], ['literal', countries]]);
  }
  if (store.settings.globe_favonly) {
    const ids = [...store.favIds];
    parts.push(ids.length ? ['in', ['get', 'c'], ['literal', ids]] : ['boolean', false]);
  }
  if (!parts.length) return null;
  return parts.length === 1 ? parts[0] : ['all', ...parts];
}

function applyFilters() {
  if (!map || !styleReady) return;
  const expr = activeFilterExpr();
  const cluster = expr ? ['all', ['has', 'point_count'], expr] : ['has', 'point_count'];
  const singlesBase = ['!', ['has', 'point_count']];
  const points = expr ? ['all', singlesBase, expr] : singlesBase;
  const live = ['all', singlesBase, ['==', ['get', 's'], 'live']];
  const pulse = expr ? ['all', singlesBase, ['==', ['get', 's'], 'live'], expr] : live;
  try {
    map.setFilter('globe-clusters', cluster);
    map.setFilter('globe-clusters-glow', cluster);
    map.setFilter('globe-cluster-count', cluster);
    map.setFilter('globe-points', points);
    map.setFilter(PULSE_LAYER, pulse);
    map.setFilter('globe-heat', expr);          // the heat copy holds no clusters
    schedulePhotoFilters();                     // photo pins: dots' rule ∩ registered posters
  } catch (err) { /* filters land again on the next change */ }
}

function updateQNote() {
  if (!ui.qnote) return;
  const q = store.filters.q;
  ui.qnote.hidden = !q;
  if (q) ui.qnote.textContent = `text search “${q}” is not applied on the globe`;
}

/* ── popups (one compact click popup + a 300 ms hover tooltip) ───────── */

function isExposure(p) { return !!p && p.v === 'exposure_aggregator'; }

function compactOf(full) {
  return {
    c: full.camera_id, n: full.name, s: full.status, p: full.protocol,
    f: full.source_family, y: full.country, v: full.provenance,
  };
}

function popupHTML(p) {
  const bits = [];
  if (p.y) bits.push(esc(p.y));
  if (p.f) bits.push(esc(p.f));
  if (p.p) bits.push(esc(p.p));
  let h = '<div class="gpop">';
  h += `<div class="gpop-name">${esc(p.n || '(unnamed)')}</div>`;
  if (bits.length) h += `<div class="gpop-sub">${bits.join(' · ')}</div>`;
  h += `<div class="gpop-meta">${statusChipHTML({ status: p.s })}</div>`;
  if (isExposure(p)) {
    // exposure law: metadata only — no Watch / Details / favourite actions
    h += '<div class="gpop-warn">metadata only — listed by a public aggregator; never previewed</div>';
  } else {
    h += `<div class="gpop-actions">
      <button type="button" class="btn small primary" data-g="watch">${I.play} Watch</button>
      <button type="button" class="btn small" data-g="details">${I.info} Details</button>
      <button type="button" class="btn small icon-only${isFav(p.c) ? ' on' : ''}" data-g="fav" title="Favourite">${I.star}</button>
    </div>`;
  }
  return h + '</div>';
}

function openPointPopup(p, lngLat) {
  if (!map || !M) return;
  if (clickPopup) { try { clickPopup.remove(); } catch (err) { /* noop */ } }
  clickPopup = new M.Popup({ offset: 12, maxWidth: '300px', className: 'wfd-gpop' })
    .setLngLat(lngLat)
    .setHTML(popupHTML(p))
    .addTo(map);
  const node = clickPopup.getElement();
  if (!node) return;
  node.querySelectorAll('[data-g]').forEach((b) => {
    b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const act = b.dataset.g;
      if (act === 'watch') openPlayerFor(p.c);
      else if (act === 'details') openDrawer(p.c);
      else if (act === 'fav') toggleFavourite(p.c).then(() => {
        b.classList.toggle('on', isFav(p.c));
      });
    });
  });
}

async function openPlayerFor(cid) {
  if (!cid) return;
  try {
    const cam = rememberCamera(await apiGet('/api/camera/' + encodeURIComponent(cid)));
    if (!destroyed) openPlayerModal(cam);
  } catch (err) {
    toast('Camera lookup failed — ' + err.message, { type: 'err' });
  }
}

function setCursor(v) {
  if (map) map.getCanvas().style.cursor = v;
}

function setFocus(coords) {
  const src = map && map.getSource('focus');
  if (!src) return;
  src.setData({ type: 'FeatureCollection', features: [
    { type: 'Feature', geometry: { type: 'Point', coordinates: coords }, properties: {} },
  ] });
}

function flyTo(coords, zoom) {
  if (!map) return;
  map.flyTo({ center: coords, zoom, speed: 1.4, curve: 1.42, essential: true });
  setFocus(coords);
}

/* ── "what's here" (debounced viewport count) ────────────────────────── */

function scheduleHere() {
  clearTimeout(hereTimer);
  hereTimer = setTimeout(runHere, 500);
}

async function runHere() {
  if (!map || destroyed || !ui.here) return;
  if (map.getZoom() < 3) {
    ui.here.hidden = true;
    if (ui.hereList) ui.hereList.hidden = true;
    return;
  }
  const b = map.getBounds();
  const bbox = [Math.max(-180, b.getWest()), Math.max(-85, b.getSouth()),
    Math.min(180, b.getEast()), Math.min(85, b.getNorth())]
    .map((v) => v.toFixed(5)).join(',');
  const s = ++hereSeq;
  try {
    const fc = await apiGet('/api/cameras', { bbox, limit: 60, geo: 'only' });
    if (s !== hereSeq || destroyed || !ui.here) return;
    hereFeats = (fc.features || []).filter((f) => f.geometry && f.geometry.coordinates);
    ui.here.textContent = `${fmt(hereFeats.length)}${hereFeats.length >= 60 ? '+' : ''} camera${hereFeats.length === 1 ? '' : 's'} in view`;
    ui.here.hidden = false;
  } catch (err) {
    if (ui.here) ui.here.hidden = true;
  }
}

function toggleHereList() {
  if (!ui.hereList) return;
  ui.hereList.hidden = !ui.hereList.hidden;
  if (!ui.hereList.hidden) renderHereList();
}

function renderHereList() {
  if (!ui.hereList) return;
  if (!hereFeats.length) {
    ui.hereList.innerHTML = '<div class="globe-here-empty">no cameras in this view</div>';
    return;
  }
  ui.hereList.innerHTML = hereFeats.slice(0, 60).map((f, i) => {
    const p = f.properties || {};
    return `<button type="button" class="globe-result" data-i="${i}">
      <span class="gr-name">${esc(p.name || '(unnamed)')}</span>
      ${statusChipHTML(p)}
    </button>`;
  }).join('');
  ui.hereList.querySelectorAll('.globe-result').forEach((b) => {
    b.addEventListener('click', () => {
      const f = hereFeats[Number(b.dataset.i)];
      if (!f || !f.geometry) return;
      const c = f.geometry.coordinates;
      flyTo(c, Math.max(13, map.getZoom()));
      rememberCamera(f.properties);
      openPointPopup(compactOf(f.properties), c);
      playSound('click');
    });
  });
}

/* ── search + random teleport ────────────────────────────────────────── */

function wireSearch() {
  const input = ui.searchInput;
  const box = ui.results;
  if (!input || !box) return;
  let timer = null; let seq = 0; let results = [];
  const hide = () => { box.hidden = true; box.innerHTML = ''; results = []; };
  const pick = (i) => {
    const f = results[i];
    if (!f || !f.geometry) return;
    const c = f.geometry.coordinates;
    rememberCamera(f.properties);
    flyTo(c, 13);
    openPointPopup(compactOf(f.properties), c);
    playSound('click');
    hide();
  };
  const run = async () => {
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    const s = ++seq;
    try {
      const fc = await apiGet('/api/cameras', { q, limit: 8 });
      if (s !== seq || destroyed) return;
      results = (fc.features || []).filter((f) => f.geometry && f.geometry.coordinates);
      if (!results.length) {
        box.innerHTML = '<div class="globe-here-empty">no matches</div>';
        box.hidden = false;
        return;
      }
      box.innerHTML = results.map((f, i) => {
        const p = f.properties || {};
        const sub = [p.city, p.country].filter(Boolean).join(', ') || p.source_family || '';
        return `<button type="button" class="globe-result" data-i="${i}">
          <span class="gr-name">${esc(p.name || '(unnamed)')}</span>
          <span class="gr-sub">${esc(sub)}</span></button>`;
      }).join('');
      box.hidden = false;
      box.querySelectorAll('.globe-result').forEach((b) => {
        b.addEventListener('click', () => pick(Number(b.dataset.i)));
      });
    } catch (err) {
      if (s === seq) hide();
    }
  };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(run, 250);
  });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      clearTimeout(timer);
      run().then(() => {
        const first = box.querySelector('.globe-result');
        if (first) pick(Number(first.dataset.i));
      });
    } else if (ev.key === 'Escape') {
      hide();
      input.blur();
    }
    ev.stopPropagation();               // never leak typing into the app shortcuts
  });
}

async function randomLive() {
  if (!map || destroyed) return;
  const liveN = (store.stats && store.stats.by_status && store.stats.by_status.live) || 0;
  const span = Math.max(0, liveN - 50);
  const offset = span ? Math.floor(Math.random() * span) : 0;
  const params = {
    status: 'live', provenance: 'public', geo: 'only',
    sort: 'last_verified', order: 'desc', limit: 50,
  };
  try {
    let fc = await apiGet('/api/cameras', { ...params, offset });
    let feats = (fc.features || []).filter((f) => f.geometry && f.geometry.coordinates);
    if (!feats.length && offset) {
      fc = await apiGet('/api/cameras', { ...params, offset: 0 });
      feats = (fc.features || []).filter((f) => f.geometry && f.geometry.coordinates);
    }
    if (destroyed || !map) return;
    if (!feats.length) { toast('No live camera to jump to', { type: 'info' }); return; }
    const f = feats[Math.floor(Math.random() * feats.length)];
    const c = f.geometry.coordinates;
    rememberCamera(f.properties);
    flyTo(c, 14);
    openPointPopup(compactOf(f.properties), c);
    playSound('navigate');
    toast('Random live cam — ' + (f.properties.name || f.properties.camera_id), {
      type: 'info', timeout: 2200,
    });
  } catch (err) {
    if (!destroyed) toast('Random cam failed — ' + err.message, { type: 'err' });
  }
}

/* ══ stretch features ══════════════════════════════════════════════════
 * [1] terminator · [2] date picker · [3] tours · [4] measure · [5] minimap ·
 * [6] heat. Tours and the ruler are transient; the toggles persist; cleanup()
 * releases every timer / listener / source / Leaflet map. */

/* great-circle distance in metres (haversine). The vendored MapLibre v5 Map
 * exposes no distance() helper (only LngLat.distanceTo when M is loaded), so
 * the maths lives here — same great-circle model either way. */
const EARTH_R = 6371008.8;                                // IUGG mean radius, metres

function gcDist(a, b) {
  const dp = (b.lat - a.lat) * RAD;
  const dl = (b.lng - a.lng) * RAD;
  const h = Math.sin(dp / 2) ** 2
    + Math.cos(a.lat * RAD) * Math.cos(b.lat * RAD) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/* [1] day/night terminator — NOAA-style solar approximation, client-side.
 * The NIGHT hemisphere is one GeoJSON polygon: terminator latitudes sampled
 * every 2° of longitude, closed through the dark pole; the glow line follows
 * the terminator itself. Rebuilt every 60 s while enabled — a visual cue only
 * (no imagery is swapped). */

function subsolarPoint(ms) {
  const n = ms / 86400000 + 2440587.5 - 2451545.0;          // days since J2000
  const L = (280.460 + 0.9856474 * n) % 360;                // mean longitude, deg
  const g = ((357.528 + 0.9856003 * n) % 360) * RAD;        // mean anomaly, rad
  const lam = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * RAD;
  const eps = (23.439 - 0.0000004 * n) * RAD;               // obliquity, rad
  const dec = Math.asin(Math.sin(eps) * Math.sin(lam));     // solar declination, rad
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam));
  const gmst = 280.46061837 + 360.98564736629 * n;          // GMST, deg
  let lng = (ra / RAD - gmst) % 360;
  if (lng > 180) lng -= 360;
  if (lng < -180) lng += 360;
  return { lat: dec / RAD, lng };
}

function terminatorData(ms) {
  const sub = subsolarPoint(ms);
  const dec = sub.lat * RAD;
  const darkPole = sub.lat >= 0 ? -89.5 : 89.5;             // the pole that is in darkness
  const ring = [];
  const line = [];
  for (let lon = -180; lon <= 180; lon += 2) {
    const h = (lon - sub.lng) * RAD;                        // hour angle, rad
    let phi = Math.atan2(-Math.cos(h) * Math.cos(dec), Math.sin(dec)) / RAD;
    if (phi > 90) phi -= 180;                               // fold into (-90, 90]
    if (phi <= -90) phi += 180;
    ring.push([lon, phi]);
    line.push([lon, phi]);
  }
  ring.push([180, darkPole], [-180, darkPole], ring[0]);
  return {
    fill: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } },
    line: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: line } },
  };
}

function addTerminator() {
  if (!map || !styleReady || destroyed) return;
  const data = terminatorData(Date.now());
  if (!map.getSource('terminator')) {
    map.addSource('terminator', { type: 'geojson', data: data.fill });
    map.addSource('terminator-line', { type: 'geojson', data: data.line });
    // above every imagery layer, below the pins ('globe-focus' sits under the circles)
    const before = map.getLayer('globe-focus') ? 'globe-focus' : undefined;
    map.addLayer({ id: TERM_FILL_ID, type: 'fill', source: 'terminator',
      paint: { 'fill-color': '#040a18', 'fill-opacity': 0.45 } }, before);
    map.addLayer({ id: TERM_GLOW_ID, type: 'line', source: 'terminator-line',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#bfeaff', 'line-width': 1.5, 'line-opacity': 0.5,
        'line-blur': 2.2 } }, before);
  } else {
    map.getSource('terminator').setData(data.fill);
    map.getSource('terminator-line').setData(data.line);
  }
  if (window.__globe) window.__globe.terminator = true;
}

function removeTerminator() {
  if (map && styleReady) {
    for (const id of [TERM_GLOW_ID, TERM_FILL_ID]) {
      try { if (map.getLayer(id)) map.removeLayer(id); } catch (err) { /* noop */ }
    }
    for (const src of ['terminator-line', 'terminator']) {
      try { if (map.getSource(src)) map.removeSource(src); } catch (err) { /* noop */ }
    }
  }
  if (window.__globe) window.__globe.terminator = false;
}

function setTerminator(on) {
  termWanted = on;
  clearInterval(termTimer); termTimer = null;
  if (!on) { removeTerminator(); return; }
  addTerminator();                                          // no-op until the style is ready
  termTimer = setInterval(addTerminator, TERM_REFRESH_MS);  // the sun keeps moving
}

function toggleTerminator() {
  const on = !store.settings.globe_terminator;
  saveSettings({ globe_terminator: on });
  setTerminator(on);
  syncToolbar();
  playSound('toggle');
  toast(on ? 'Day/night terminator on — a visual cue; imagery is not swapped'
    : 'Terminator off', { type: 'info', timeout: 2000 });
}

/* [2] "today's Earth" date — the GIBS WMTS date lives IN the tile path. */

function todayISO() { return new Date().toISOString().slice(0, 10); }

/* accepts YYYY-MM-DD, clamps to today; absent/invalid -> today (safe for old prefs) */
function normalizeTodayDate(v) {
  const s = String(v || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return todayISO();
  const t = Date.parse(s + 'T00:00:00Z');
  if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== s) return todayISO();
  const today = todayISO();
  return s > today ? today : s;
}

function todayDateVal() { return normalizeTodayDate(store.settings.globe_today_date); }

function todayTiles(d) {
  return [GIBS + 'VIIRS_SNPP_CorrectedReflectance_TrueColor/default/' + d
    + '/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg'];
}

function retileToday() {
  const d = todayDateVal();
  if (map && styleReady) {
    try { map.getSource('today').setTiles(todayTiles(d)); } catch (err) { /* style mid-swap */ }
  }
  if (window.__globe) window.__globe.today = d;
}

function setTodayDate(raw) {
  const d = normalizeTodayDate(raw);
  saveSettings({ globe_today_date: d });
  if (ui.dateInput) ui.dateInput.value = d;
  retileToday();
  updateTodaySub(d);
}

function onTodayDateInput(ev) {
  setTodayDate(ev.target.value);
  playSound('toggle');
}

function updateTodaySub(d) {
  const em = ui.pop && ui.pop.querySelector('[data-today-sub]');
  if (em) em.textContent = `VIIRS true colour · ${d} · ~1–2 day latency`;
}

/* [3] cinematic tour — favourites (saved order) or the Watch stage. */

function stopTour(quiet) {
  const t = tourState;
  if (!t) return;
  tourState = null;
  clearTimeout(t.dwell);
  if (ui.tourbar) ui.tourbar.hidden = true;
  if (window.__globe) window.__globe.tour = false;
  syncToolbar();
  if (!quiet) {
    const bits = [`Tour stopped — ${t.count} stop${t.count === 1 ? '' : 's'} flown of ${t.stops.length}`];
    if (t.skipped) bits.push(`${t.skipped} without coordinates skipped`);
    if (!t.apiOk) bits.push('resolved from the cached globe points');
    toast(bits.join(' · '), { type: 'info', timeout: 3400 });
    playSound('toggle');
  }
}

async function startTour() {
  if (tourState || destroyed) return;
  if (measureState) finishMeasure(true);
  hideHoverCard();                               // no hover card while touring
  const favIds = (store.prefs.favourites || []).map((f) => f.camera_id);
  const useFavs = favIds.length > 0;
  const ids = useFavs ? favIds : stagedIds();
  if (!ids.length) { toast('No favourites or staged cameras', { type: 'info' }); return; }
  const seq = ++tourSeq;
  let apiOk = false;
  const byId = new Map();
  if (useFavs) {
    try {
      const fc = await apiGet('/api/cameras', { favourites: 1, geo: 'only', limit: 200 });
      for (const f of fc.features || []) if (f.geometry) byId.set(f.properties.camera_id, f);
      apiOk = true;
    } catch (err) { apiOk = false; }        // fall back to the cached globe points below
  }
  if (destroyed || seq !== tourSeq) return;
  const cached = new Map();
  for (const f of (pointsCache && pointsCache.features) || []) {
    if (f.geometry) cached.set(f.properties.c, f);
  }
  const stops = [];
  let skipped = 0;
  for (const id of ids) {
    const f = byId.get(id) || cached.get(id);
    if (!f || !f.geometry || !Array.isArray(f.geometry.coordinates)) { skipped++; continue; }
    const p = f.properties || {};
    stops.push({
      id,
      name: p.name || p.n || id,
      family: p.source_family || p.f || '',
      status: p.status || p.s || 'unknown',
      coords: f.geometry.coordinates,
    });
  }
  if (!stops.length) {
    toast('No tour stops have coordinates on the globe', { type: 'info' });
    return;
  }
  playSound('navigate');
  tourState = { stops, i: -1, count: 0, dwell: null, skipped, apiOk };
  runTourStop();
}

function runTourStop() {
  const t = tourState;
  if (!t || !map || destroyed) return;
  t.i = (t.i + 1) % t.stops.length;                          // loops; the counter keeps counting
  t.count++;
  const s = t.stops[t.i];
  if (ui.tourbar) {
    ui.tourbar.hidden = false;
    ui.tourbar.innerHTML = `<span class="gt-name">${esc(s.name)}</span>
      <span class="gt-sub">${esc([s.family, s.status].filter(Boolean).join(' · '))}</span>
      <span class="gt-count">${t.count}/${t.stops.length}</span>
      <button type="button" class="btn tiny" data-tour="next">Next</button>
      <button type="button" class="btn tiny ghost" data-tour="stop">Stop</button>`;
  }
  map.flyTo({ center: s.coords, zoom: 11.5, pitch: 50, bearing: -15,
    duration: 6500, essential: true });
  clearTimeout(t.dwell);
  t.dwell = setTimeout(() => { if (tourState) runTourStop(); }, 6500 + 5000);   // ~5 s dwell
  if (window.__globe) window.__globe.tour = true;
  syncToolbar();
}

/* [4] ruler — great-circle distances via gcDist (metres). */

function fmtKm(m) {
  if (m >= 1000) return (m / 1000).toFixed(m >= 100000 ? 0 : 2) + ' km';
  return Math.round(m) + ' m';
}

function fmtMi(m) {
  const mi = m / 1609.344;
  return mi >= 0.1 ? mi.toFixed(2) + ' mi' : Math.max(1, Math.round(mi * 5280)) + ' ft';
}

function startMeasure() {
  if (measureState || !map) return;
  if (tourState) stopTour(true);
  hideHoverCard();                               // no hover card while measuring
  measureState = {
    cam: {
      center: map.getCenter(), zoom: map.getZoom(),
      bearing: map.getBearing(), pitch: map.getPitch(),
    },
    pts: [],
  };
  try { map.doubleClickZoom.disable(); } catch (err) { /* noop */ }
  map.easeTo({ pitch: 0, duration: 550 });                  // top-down reads distances cleanly
  setCursor('crosshair');
  if (ui.mpanel) ui.mpanel.hidden = false;
  if (ui.mread) ui.mread.hidden = true;
  if (window.__globe) window.__globe.measure = true;
  syncToolbar();
  playSound('toggle');
  toast('Measure on — click points on the globe; double-click or Done to finish',
    { type: 'info', timeout: 2600 });
}

function finishMeasure(quiet) {
  const m = measureState;
  if (!m) return;
  measureState = null;
  try { map.doubleClickZoom.enable(); } catch (err) { /* noop */ }
  clearMeasureLayers();
  if (ui.mread) ui.mread.hidden = true;
  if (ui.mpanel) ui.mpanel.hidden = true;
  if (map) {
    map.easeTo({ center: m.cam.center, zoom: m.cam.zoom, bearing: m.cam.bearing,
      pitch: m.cam.pitch, duration: 650 });                 // restore the saved camera state
  }
  setCursor('');
  if (window.__globe) window.__globe.measure = false;
  syncToolbar();
  if (!quiet) playSound('toggle');
}

function clearMeasure() {
  if (!measureState) return;
  measureState.pts = [];
  clearMeasureLayers();
  if (ui.mread) ui.mread.hidden = true;
  playSound('click');
}

function clearMeasureLayers() {
  if (!map || !styleReady) return;
  const dot = map.getSource('measure-dots');
  const line = map.getSource('measure-line');
  if (dot) dot.setData(EMPTY_FC);
  if (line) line.setData(EMPTY_FC);
}

function updateMeasureLayers() {
  if (!map || !styleReady || !measureState) return;
  const pts = measureState.pts;
  const dot = map.getSource('measure-dots');
  const line = map.getSource('measure-line');
  if (dot) {
    dot.setData({ type: 'FeatureCollection', features: pts.map((p, i) => ({
      type: 'Feature', properties: { i },
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    })) });
  }
  if (line) {
    line.setData(pts.length < 2 ? EMPTY_FC : { type: 'FeatureCollection', features: [{
      type: 'Feature', properties: {},
      geometry: { type: 'LineString', coordinates: pts.map((p) => [p.lng, p.lat]) },
    }] });
  }
}

function updateMeasureReadout() {
  if (!ui.mread) return;
  const m = measureState;
  if (!m || !m.pts.length) { ui.mread.hidden = true; return; }
  let total = 0; let last = 0;
  for (let i = 1; i < m.pts.length; i++) {
    last = gcDist(m.pts[i - 1], m.pts[i]);
    total += last;
  }
  ui.mread.hidden = false;
  ui.mread.innerHTML = m.pts.length < 2
    ? '<div class="gm-line">point 1 — click to measure</div>'
    : `<div class="gm-line"><b>${fmtKm(total)}</b> · ${fmtMi(total)}</div>`
      + `<div class="gm-seg">last ${fmtKm(last)} · ${fmtMi(last)}</div>`;
  positionMeasureReadout(m.pts[m.pts.length - 1]);
}

function positionMeasureReadout(p) {
  if (!map || !ui.mread || ui.mread.hidden || !p) return;
  const pt = map.project([p.lng, p.lat]);
  ui.mread.style.left = Math.round(pt.x) + 'px';
  ui.mread.style.top = Math.round(pt.y) + 'px';
}

function onMeasureClick(ev) {
  if (!measureState || !map) return;
  measureState.pts.push({ lng: ev.lngLat.lng, lat: ev.lngLat.lat });
  updateMeasureLayers();
  updateMeasureReadout();
  playSound('click');
}

function onMeasureDbl() {
  if (!measureState || !map) return;
  // a double-click fires two 'click' events first — drop the duplicated vertex
  const pts = measureState.pts;
  if (pts.length >= 2 && gcDist(pts[pts.length - 1], pts[pts.length - 2]) < 8) pts.pop();
  updateMeasureLayers();
  updateMeasureReadout();
  finishMeasure();
}

function toggleMeasure() {
  if (measureState) finishMeasure();
  else startMeasure();
}

/* [5] minimap inset — vendored Leaflet, the SAME Esri imagery as the globe.
 * Created lazily the first time the inset is shown; destroyed by cleanup(). */

function ensureMinimap() {
  if (miniMap || !ui.miniHost) return miniMap;
  if (!window.L || !window.L.map) return null;             // Leaflet always ships; stay safe
  miniMap = window.L.map(ui.miniHost, {
    attributionControl: false, zoomControl: false,
    minZoom: 0, maxZoom: 7, zoomSnap: 0, zoomDelta: 0.5,
    worldCopyJump: true, keyboard: false, scrollWheelZoom: false, doubleClickZoom: false,
  });
  window.L.tileLayer(ESRI_TILES, { maxZoom: 16 }).addTo(miniMap);
  miniMap.setView([20, 0], 0);                              // zoom 0: the whole world fits (no z<0 tiles)
  miniBox = window.L.rectangle([[0, 0], [0, 0]], {
    color: '#2dd4bf', weight: 1, opacity: 0.9, fillColor: '#2dd4bf', fillOpacity: 0.07,
    interactive: false,
  });
  miniDot = window.L.circleMarker([0, 0], {
    radius: 3.5, color: '#ffffff', weight: 1.5, fillColor: '#2dd4bf', fillOpacity: 1,
    interactive: false,
  });
  miniHalo = window.L.circle([0, 0], {
    radius: 1000, color: '#2dd4bf', weight: 1, opacity: 0.55, fillColor: '#2dd4bf',
    fillOpacity: 0.15, interactive: false,
  });
  miniMap.on('click', (ev) => {
    if (!map || destroyed) return;
    map.flyTo({ center: [ev.latlng.lng, ev.latlng.lat],
      zoom: Math.max(6, map.getZoom()), duration: 1400, essential: true });
    playSound('click');
  });
  updateMiniViewport();
  return miniMap;
}

/* wide view -> rectangle footprint; z>=7 -> centre dot + a halo sized to the
 * viewport (floored at a few pixels so it stays visible on a world-scale inset) */
function updateMiniViewport() {
  if (!miniMap || !map || destroyed || !ui.mini || ui.mini.hidden) return;
  const z = map.getZoom();
  const c = map.getCenter();
  if (z >= 7) {
    const b = map.getBounds();
    const dE = gcDist(c, { lng: b.getEast(), lat: c.lat });
    const dN = gcDist(c, { lng: c.lng, lat: b.getNorth() });
    const mPerPx = 156543.03392 * Math.cos(c.lat * RAD) / Math.pow(2, miniMap.getZoom());
    const radius = Math.max(Math.min(dE, dN), mPerPx * 4);
    if (!miniMap.hasLayer(miniDot)) miniDot.addTo(miniMap);
    if (!miniMap.hasLayer(miniHalo)) miniHalo.addTo(miniMap);
    if (miniMap.hasLayer(miniBox)) miniMap.removeLayer(miniBox);
    miniDot.setLatLng([c.lat, c.lng]);
    miniHalo.setLatLng([c.lat, c.lng]).setRadius(radius);
    miniMap.setView([c.lat, c.lng], clamp(Math.round(z) - 4, 0, 7));
  } else {
    if (!miniMap.hasLayer(miniBox)) miniBox.addTo(miniMap);
    if (miniMap.hasLayer(miniDot)) miniMap.removeLayer(miniDot);
    if (miniMap.hasLayer(miniHalo)) miniMap.removeLayer(miniHalo);
    // world-static box: nudge the view back to zoom 0 and follow the globe's latitude
    const tLat = clamp(c.lat, -42, 62);
    if (Math.abs(miniMap.getZoom()) > 0.01 || Math.abs(miniMap.getCenter().lat - tLat) > 1.5) {
      miniMap.setView([tLat, 0], 0);
    }
    const b = map.getBounds();
    const w = b.getWest(); const e = b.getEast();
    if (e < w || e - w >= 359) {
      miniBox.setBounds([[-84, -179.9], [84, 179.9]]);      // wraps the antimeridian: whole-world box
    } else {
      miniBox.setBounds([[Math.max(-84, b.getSouth()), Math.max(-180, w)],
        [Math.min(84, b.getNorth()), Math.min(180, e)]]);
    }
  }
}

function scheduleMini() {
  if (miniTimer) return;                                    // ~150 ms throttle
  miniTimer = setTimeout(() => { miniTimer = null; updateMiniViewport(); }, 150);
}

function applyMinimap(on) {
  if (!ui.mini) return;
  ui.mini.hidden = !on;
  if (ui.wrap) ui.wrap.classList.toggle('gmini', !!on);
  if (window.__globe) window.__globe.minimap = !!on;
  if (!on) return;
  ensureMinimap();
  if (miniMap) { try { miniMap.invalidateSize(); } catch (err) { /* noop */ } }
  updateMiniViewport();
}

/* [6] heat dim — the pins step back while the heatmap is on. */

/* shared opacity expressions so buildStyle and setHeatDim speak the same ramp;
 * the heat factor is folded into the interpolate stops (a zoom expression may
 * not be nested inside arithmetic) */
function clusterOpacityExpr(heat) {
  return heat ? 0.25 : ['interpolate', ['linear'], ['zoom'], 9, 1, 11, 0.95];
}
function clusterGlowOpacityExpr(heat) {
  return heat ? 0.06 : ['interpolate', ['linear'], ['zoom'], 0, 0.22, 9, 0.16, 11, 0.12];
}
function pointsOpacityExpr(heat) {
  const f = heat ? 0.26 : 1;
  return ['interpolate', ['linear'], ['zoom'], 3.5, 0, 5, 0.55 * f, 8, 0.95 * f];
}
/* the pulse radius is a fresh top-level zoom interpolate per tick, with the
 * oscillation factor folded into the stops */
function pulseRadiusExpr(k) {
  return ['interpolate', ['linear'], ['zoom'],
    3.5, 1.6 * k, 6, 2.6 * k, 9, 3.6 * k, 12, 4.6 * k, 14, 6 * k];
}

function setHeatDim(on) {
  if (!map || !styleReady) return;
  try {
    map.setPaintProperty('globe-clusters', 'circle-opacity', clusterOpacityExpr(on));
    map.setPaintProperty('globe-clusters-glow', 'circle-opacity', clusterGlowOpacityExpr(on));
    map.setPaintProperty('globe-cluster-count', 'text-opacity', on ? 0.25 : 1);
    map.setPaintProperty('globe-points', 'circle-opacity', pointsOpacityExpr(on));
  } catch (err) { /* style mid-swap — the rebuilt style picks the dim up */ }
}

function applyHeat(on) {
  if (map && styleReady) {
    try { map.setLayoutProperty('globe-heat', 'visibility', on ? 'visible' : 'none'); }
    catch (err) { /* noop */ }
    setHeatDim(on);
  }
  if (window.__globe) window.__globe.heat = on;
}

/* ══ photo pins (v0.4.5) ══════════════════════════════════════════════
 * Posters materialise as pin thumbnails above the single dots as the user
 * zooms in. After each settled move (350 ms) the first ~70 rendered singles
 * (queryRenderedFeatures, topped up by bbox over the cached collection) go
 * through a 5-wide queue: fetch /api/poster/<cid> → downscale to a 44×30
 * fit-cover thumb → map.addImage('pp-<cid>'). 404s are remembered and
 * skipped (the dot stays); the registry is capped (~300, LRU) and images
 * that drift far out of view are released with map.removeImage. */

function photoMinZoom() { return photoMode === 'on' ? PHOTO_ON_MINZOOM : PHOTO_AUTO_MINZOOM; }

function photoOpacityExpr() {
  return photoMode === 'on'
    ? ['interpolate', ['linear'], ['zoom'], PHOTO_ON_MINZOOM, 0, 8, 1]
    : ['interpolate', ['linear'], ['zoom'], PHOTO_AUTO_MINZOOM, 0, 11, 1];
}

/* Both photo layers only ever reference images that EXIST: their filters are
 * recomputed (debounced) from the live image registry, so MapLibre never asks
 * for an unregistered icon-image (which would log a console warning per pin).
 * The viewport layer keeps the dots' filter too; the pane layer draws only
 * pane-pinned cams whose poster has landed. */
let photoFilterTimer = null;

function schedulePhotoFilters() {
  if (photoFilterTimer) return;
  photoFilterTimer = setTimeout(() => { photoFilterTimer = null; applyPhotoFilters(); }, 180);
}

function applyPhotoFilters() {
  if (!map || !styleReady) return;
  try {
    const ids = [...photoReg.keys()];
    if (map.getLayer(PHOTO_LAYER)) {
      const expr = activeFilterExpr();
      const singles = ['!', ['has', 'point_count']];
      const points = expr ? ['all', singles, expr] : singles;
      map.setFilter(PHOTO_LAYER, ids.length
        ? ['all', points, ['in', ['get', 'c'], ['literal', ids]]]
        : ['boolean', false]);
    }
    if (map.getLayer(PANE_LAYER)) {
      const pinned = [...photoPinned].filter((cid) => photoReg.has(cid));
      map.setFilter(PANE_LAYER, pinned.length
        ? ['in', ['get', 'c'], ['literal', pinned]]
        : ['boolean', false]);
    }
  } catch (err) { /* style mid-swap — the next pass retries */ }
}

/* settings → layer state; safe before the style exists (buildStyle reads
 * photoMode, onStyleReady re-applies) */
function applyPhotoPinsSetting() {
  const v = store.settings.globe_photo_pins;
  photoMode = v === 'on' || v === 'off' ? v : 'auto';
  if (window.__globe) { window.__globe.photoPinsMode = photoMode; window.__globe.photoPins = photoReg.size; }
  if (map && styleReady) {
    try {
      map.setLayoutProperty(PHOTO_LAYER, 'visibility', photoMode === 'off' ? 'none' : 'visible');
      map.setLayerZoomRange(PHOTO_LAYER, photoMinZoom(), 20);
      map.setPaintProperty(PHOTO_LAYER, 'icon-opacity', photoOpacityExpr());
    } catch (err) { /* style mid-swap — onStyleReady re-applies */ }
  }
  schedulePhotoPins();
}

function schedulePhotoPins() {
  clearTimeout(photoTimer);
  photoTimer = setTimeout(() => { photoTimer = null; refreshPhotoPins(); }, PHOTO_DEBOUNCE_MS);
}

function ensureCamCoords() {
  if (camCoords && camCoords.size) return camCoords;
  camCoords = new Map();
  for (const f of (pointsCache && pointsCache.features) || []) {
    const p = f.properties || {};
    const g = f.geometry && f.geometry.coordinates;
    if (p.c && g) camCoords.set(p.c, g);
  }
  return camCoords;
}

/* one viewport pass: pick candidates, queue missing posters, release far ones */
function refreshPhotoPins() {
  if (destroyed || !map || !styleReady || photoMode === 'off') return;
  if (map.getZoom() < photoMinZoom()) return;            // below the zoom rule: nothing to fetch
  const seen = new Set();
  const picks = [];
  const want = (p) => !!p && !!p.c && p.v !== 'exposure_aggregator'
    && !seen.has(p.c) && !photoMiss.has(p.c);
  try {                                                  // rendered singles first (probe may under-report)
    for (const f of map.queryRenderedFeatures({ layers: ['globe-points'] })) {
      if (picks.length >= PHOTO_BATCH) break;
      const p = f.properties || {};
      if (!want(p)) continue;
      seen.add(p.c); picks.push(f);
    }
  } catch (err) { /* style mid-swap — the bbox top-up below still works */ }
  if (picks.length < PHOTO_BATCH && pointsCache) {       // …topped up from the cached collection
    const b = map.getBounds();
    const w = b.getWest(), e = b.getEast(), s = b.getSouth(), n = b.getNorth();
    const cross = e < w;
    const world = !cross && (e - w) >= 359.9;
    const pred = pointPredicate();
    for (const f of pointsCache.features || []) {
      if (picks.length >= PHOTO_BATCH) break;
      const g = f.geometry && f.geometry.coordinates;
      const p = f.properties || {};
      if (!g || !want(p)) continue;
      const lon = Number(g[0]), lat = Number(g[1]);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
      if (lat < s || lat > n) continue;
      if (!world && (cross ? !(lon >= w || lon <= e) : !(lon >= w && lon <= e))) continue;
      if (pred && !pred(p)) continue;                    // respect the active filters
      seen.add(p.c); picks.push(f);
    }
  }
  if (!picks.length) return;
  const todo = [];
  for (const f of picks) {
    const cid = f.properties.c;
    if (photoReg.has(cid)) { touchPhoto(cid); continue; }  // recently used — bump LRU order
    todo.push(cid);
  }
  if (todo.length) queuePosters(todo);
  evictFarPhotos();
}

/* 5-wide poster queue; a new batch aborts the pending fetches (stale work dies) */
function queuePosters(cids) {
  const list = (cids || []).filter((cid) => cid && !photoReg.has(cid) && !photoMiss.has(cid));
  if (!list.length) return;
  if (photoAbort) { try { photoAbort.abort(); } catch (err) { /* noop */ } }
  photoAbort = new AbortController();
  const signal = photoAbort.signal;
  const seq = ++photoSeq;
  let i = 0;
  const worker = async () => {
    while (i < list.length) {
      if (destroyed || seq !== photoSeq || signal.aborted) return;
      const cid = list[i++];
      try { await registerPoster(cid, signal); }
      catch (err) { /* 404 / blocked / aborted — the dot stays, never a broken marker */ }
    }
  };
  for (let k = 0; k < Math.min(PHOTO_CONC, list.length); k++) worker();
}

async function registerPoster(cid, signal) {
  if (!cid || photoReg.has(cid) || photoMiss.has(cid)) return false;
  if (!map || destroyed || !styleReady || signal.aborted) return false;
  const res = await fetch('/api/poster/' + encodeURIComponent(cid),
    { signal, headers: { Accept: 'image/*' } });
  if (!res.ok) {
    if (res.status === 404) rememberPosterMiss(cid);     // no poster — never retried
    return false;
  }
  const blob = await res.blob();
  if (signal.aborted || destroyed || !map || !styleReady) return false;
  const src = await createImageBitmap(blob);
  const cv = document.createElement('canvas');           // fit-cover crop into the 44×30 thumb
  cv.width = PHOTO_THUMB_W; cv.height = PHOTO_THUMB_H;
  const ctx = cv.getContext('2d');
  const sw = src.width || 1, sh = src.height || 1;
  const scale = Math.max(PHOTO_THUMB_W / sw, PHOTO_THUMB_H / sh);
  const dw = sw * scale, dh = sh * scale;
  ctx.drawImage(src, (PHOTO_THUMB_W - dw) / 2, (PHOTO_THUMB_H - dh) / 2, dw, dh);
  try { src.close(); } catch (err) { /* not fatal */ }
  const thumb = await createImageBitmap(cv);
  if (signal.aborted || destroyed || !map || !styleReady) {
    try { thumb.close(); } catch (err) { /* noop */ }
    return false;
  }
  try {
    if (!map.hasImage(PHOTO_MARK + cid)) map.addImage(PHOTO_MARK + cid, thumb, { pixelRatio: 1 });
  } catch (err) {
    try { thumb.close(); } catch (err2) { /* noop */ }
    return false;                                        // style mid-swap — retried next pass
  }
  photoReg.set(cid, true);
  if (window.__globe) window.__globe.photoPins = photoReg.size;
  schedulePhotoFilters();
  evictOverCap();
  return true;
}

function rememberPosterMiss(cid) {
  if (!cid) return;
  photoMiss.add(cid);
  if (photoMiss.size > 900) {                            // bounded (oldest out)
    const first = photoMiss.values().next();
    if (!first.done) photoMiss.delete(first.value);
  }
}

function touchPhoto(cid) {
  if (!photoReg.has(cid)) return;
  photoReg.delete(cid); photoReg.set(cid, true);
}

function removePhoto(cid) {
  photoReg.delete(cid);
  try { if (map && map.hasImage(PHOTO_MARK + cid)) map.removeImage(PHOTO_MARK + cid); }
  catch (err) { /* style mid-swap — a fresh style starts clean anyway */ }
  schedulePhotoFilters();
  if (window.__globe) window.__globe.photoPins = photoReg.size;
}

function evictOverCap() {
  while (photoReg.size > PHOTO_MAX) {
    let victim = null;
    for (const cid of photoReg.keys()) { if (!photoPinned.has(cid)) { victim = cid; break; } }
    if (victim == null) break;
    removePhoto(victim);
  }
}

/* release images for cameras that drifted far out of view (keeps panning cheap) */
function evictFarPhotos() {
  if (!map || !photoReg.size) return;
  const cc = ensureCamCoords();
  const b = map.getBounds();
  const c = map.getCenter();
  const hw = Math.min(180, Math.abs(b.getEast() - b.getWest()) / 2) * 1.8 + 0.5;
  const hh = Math.abs(b.getNorth() - b.getSouth()) / 2 * 1.8 + 0.5;
  for (const cid of [...photoReg.keys()]) {
    if (photoPinned.has(cid)) continue;                  // the pane owns these while on
    const g = cc.get(cid);
    if (!g) continue;
    let dl = Math.abs(Number(g[0]) - c.lng);
    if (dl > 180) dl = 360 - dl;
    const dlat = Math.abs(Number(g[1]) - c.lat);
    if (dl > hw || dlat > hh) removePhoto(cid);
  }
}

/* ══ area panel (v0.4.5) ═════════════════════════════════════════════
 * The right-hand menu. Clicking a CLUSTER bubble / COUNTRY label / CITY label
 * opens a contextual pane for that area: status-breakdown chips, the area's
 * cameras as rows with full per-camera controls (thumbnail, Watch / Details /
 * ★ / ＋Stage — exposure rows stay metadata-only), search-in-area, sort and
 * All/Live/Stale chips, plus contextual actions — Zoom to fit, Show photos
 * (pane-only poster pins) and Filter (country panes). The content re-derives
 * from the cached points + the globe's active filters; nothing persists. */

function paneStatusCounts(members) {
  const c = { live: 0, stale: 0, dead: 0, unknown: 0 };
  for (const m of members) {
    const s = (m.p && m.p.s) || '';
    if (s === 'live') c.live++;
    else if (s === 'stale') c.stale++;
    else if (s === 'dead') c.dead++;
    else c.unknown++;
  }
  return c;
}

function paneTitleText() {
  if (!pane) return 'Area';
  if (pane.kind === 'cluster') return `Cluster — ${fmt(pane.count || pane.all.length)} cams`;
  if (pane.kind === 'country') return `${countryDisplayName(pane.key) || pane.key} — ${fmt(pane.members.length)} cams`;
  return `${pane.key} — ${fmt(pane.members.length)} cams`;
}

function openAreaPanel(ctx) {
  if (!ui.area || destroyed) return;
  hideHoverCard();
  if (clickPopup) { try { clickPopup.remove(); } catch (err) { /* noop */ } clickPopup = null; }
  clearPanePhotos();                                     // drop the previous pane's photos first
  const seq = pane ? pane.seq + 1 : 1;
  pane = {
    kind: ctx.kind, key: String(ctx.key == null ? '' : ctx.key),
    clusterId: ctx.clusterId == null ? null : ctx.clusterId,
    count: Number(ctx.count) || 0, note: '',
    q: '', sort: 'name', filt: 'all', limit: PANE_PAGE, photosOn: false,
    all: [], members: [], seq,
  };
  if (ui.areaQ) ui.areaQ.value = '';
  setPaneSeg(ui.areaSort, pane.sort);
  setPaneSeg(ui.areaFilt, pane.filt);
  ui.area.hidden = false;
  void ui.area.offsetWidth;                              // flush style so the slide-in animates
  ui.area.classList.add('open');
  if (window.__globe) window.__globe.areaPanel = true;
  renderPane();
  if (ctx.kind === 'cluster') loadClusterMembers(pane.clusterId, seq);
  else {
    const members = ctx.kind === 'country' ? membersForCountry(pane.key) : membersForCity(pane.key);
    setPaneMembers(members, seq);
  }
}

function setPaneMembers(members, seq) {
  if (destroyed || !pane || pane.seq !== seq) return;
  pane.all = members;
  refreshPaneMembers();
}

/* re-derive the pane's rows from its full member set + the globe's filters */
function refreshPaneMembers() {
  if (!pane) return;
  const pred = pointPredicate();
  pane.members = pred ? pane.all.filter((m) => pred(m.p || {})) : pane.all.slice();
  renderPane();
  if (pane.photosOn) syncPanePhotos();
}

async function loadClusterMembers(clusterId, seq) {
  const src = map && map.getSource('cams');
  if (!src || clusterId == null || !src.getClusterLeaves) {
    if (pane && pane.seq === seq) setPaneMembers([], seq);
    return;
  }
  try {
    const leaves = await src.getClusterLeaves(clusterId, 500, 0);
    if (destroyed || !pane || pane.seq !== seq) return;
    if (leaves && leaves.length >= 500) pane.note = `first 500 of ${fmt(pane.count)}`;
    setPaneMembers((leaves || [])
      .filter((f) => f && f.geometry && Array.isArray(f.geometry.coordinates))
      .map((f) => ({ p: f.properties || {}, geom: f.geometry.coordinates.slice() })), seq);
  } catch (err) {
    if (pane && pane.seq === seq) {
      pane.note = 'members unavailable — ' + (err.message || err);
      setPaneMembers([], seq);
    }
  }
}

function membersForCountry(cc) {
  const out = [], up = String(cc).toUpperCase();
  for (const f of (pointsCache && pointsCache.features) || []) {
    const p = f.properties || {};
    const g = f.geometry && f.geometry.coordinates;
    if (!g || String(p.y || '').toUpperCase() !== up) continue;
    out.push({ p, geom: g });
  }
  return out;
}

function membersForCity(name) {
  const out = [], key = String(name).toLowerCase();
  for (const f of (pointsCache && pointsCache.features) || []) {
    const p = f.properties || {};
    const g = f.geometry && f.geometry.coordinates;
    if (!g || String(p.t || '').toLowerCase() !== key) continue;
    out.push({ p, geom: g });
  }
  return out;
}

function setPaneSeg(seg, val) {
  if (!seg) return;
  seg.querySelectorAll('.seg-btn').forEach((b) => b.classList.toggle('on', b.dataset.val === val));
}

function renderPane() {
  if (!ui.area || !pane) return;
  const counts = paneStatusCounts(pane.members);
  ui.areaTitle.textContent = paneTitleText();
  ui.areaSub.textContent = pane.kind === 'cluster'
    ? 'cluster members · click a bubble again to refresh'
    : pane.kind === 'country'
      ? 'every cached row for this country'
      : 'every cached row for this city';
  if (pane.note) ui.areaSub.textContent += ' · ' + pane.note;
  ui.areaChips.innerHTML = ['live', 'stale', 'dead', 'unknown'].map((k) => (
    `<span class="ga-chip ga-${k}" title="${esc(k)} cameras in this pane"><i></i>${esc(k)} <b>${fmt(counts[k])}</b></span>`
  )).join('');
  const countryOn = pane.kind === 'country'
    && (store.filters.country || []).filter(Boolean).map((c) => String(c).toUpperCase()).includes(pane.key.toUpperCase());
  ui.areaActs.innerHTML =
    `<button type="button" class="btn tiny" data-pa="zoom" title="Frame this pane's cameras on the globe">${I.frame} Zoom to fit</button>`
    + `<button type="button" class="btn tiny${pane.photosOn ? ' on' : ''}" data-pa="photos" title="Register poster pins for this pane's members (up to ${PANE_PHOTO_BATCH}) — works below the photo-pin zoom">${I.cam} ${pane.photosOn ? 'Hide photos' : 'Show photos'}</button>`
    + (pane.kind === 'country'
      ? `<button type="button" class="btn tiny${countryOn ? ' on' : ''}" data-pa="filter" title="Apply the country filter (same as the label click)">${I.filt} Filter</button>`
      : '');
  renderPaneList();
}

function paneRowsView() {
  let rows = pane.members;
  if (pane.filt === 'live') rows = rows.filter((m) => (m.p && m.p.s) === 'live');
  else if (pane.filt === 'stale') rows = rows.filter((m) => (m.p && m.p.s) === 'stale');
  const q = pane.q.trim().toLowerCase();
  if (q) rows = rows.filter((m) => String((m.p && m.p.n) || '').toLowerCase().includes(q));
  const sorted = rows.slice();
  if (pane.sort === 'status') {
    sorted.sort((a, b) => {
      const ra = PANE_STATUS_RANK[(a.p && a.p.s) || ''] ?? 9;
      const rb = PANE_STATUS_RANK[(b.p && b.p.s) || ''] ?? 9;
      if (ra !== rb) return ra - rb;
      return String((a.p && a.p.n) || '').localeCompare(String((b.p && b.p.n) || ''), 'en', { sensitivity: 'base' });
    });
  } else {
    sorted.sort((a, b) => String((a.p && a.p.n) || '').localeCompare(String((b.p && b.p.n) || ''), 'en', { sensitivity: 'base' }));
  }
  return sorted;
}

function paneRowHTML(m) {
  const p = m.p || {};
  const cid = p.c || '';
  const meta = isExposure(p);
  const sub = [p.f, p.p].filter(Boolean).map(esc).join(' \u00b7 ');
  const thumb = meta
    ? '<span class="ga-thumb ga-thumb-none" title="metadata only">meta</span>'
    : `<span class="ga-thumb"><img loading="lazy" decoding="async" alt="" src="/api/poster/${encodeURIComponent(cid)}"></span>`;
  const acts = meta ? '' : `<span class="ga-row-acts">
      <button type="button" class="btn tiny primary icon-only" data-a="watch" data-cid="${esc(cid)}" title="Watch">${I.play}</button>
      <button type="button" class="btn tiny icon-only" data-a="details" data-cid="${esc(cid)}" title="Details">${I.info}</button>
      <button type="button" class="btn tiny icon-only${isFav(cid) ? ' on' : ''}" data-a="fav" data-cid="${esc(cid)}" title="Favourite">${I.star}</button>
      <button type="button" class="btn tiny icon-only" data-a="stage" data-cid="${esc(cid)}" title="Add to Watch stage">${I.plus}</button>
    </span>`;
  return `<div class="ga-row${meta ? ' ga-row-meta' : ''}"${cid ? ` data-cid="${esc(cid)}"` : ''}>
      ${thumb}
      <span class="ga-main">
        <span class="ga-name" title="${esc(p.n || '')}">${esc(p.n || '(unnamed)')}</span>
        ${sub ? `<span class="ga-rowsub">${sub}</span>` : ''}
        <span class="ga-rowmeta">${statusChipHTML({ status: p.s })}${meta ? '<span class="ga-metaonly">metadata only — never previewed</span>' : ''}</span>
      </span>
      ${acts}
    </div>`;
}

function renderPaneList() {
  const list = ui.areaList;
  if (!list || !pane) return;
  const rows = paneRowsView();
  if (!rows.length) {
    list.innerHTML = `<div class="ga-empty">${pane.all.length ? 'no cameras match the current filters' : 'no cameras in this area'}</div>`;
    if (ui.areaCount) ui.areaCount.textContent = pane.all.length ? `0 of ${fmt(pane.all.length)}` : '';
    return;
  }
  const shown = rows.slice(0, pane.limit);
  if (ui.areaCount) {
    ui.areaCount.textContent = shown.length < rows.length
      ? `showing ${fmt(shown.length)} of ${fmt(rows.length)}`
      : `${fmt(rows.length)} camera${rows.length === 1 ? '' : 's'}`;
  }
  list.innerHTML = shown.map(paneRowHTML).join('')
    + (rows.length > shown.length
      ? `<button type="button" class="btn tiny ga-more" data-pa="more">+ ${fmt(rows.length - shown.length)} more</button>`
      : '');
}

function paneZoomFit() {
  if (!pane || !map) return;
  let w = 181, e = -181, s = 91, n = -91;
  for (const m of pane.members) {
    const g = m.geom;
    if (!Array.isArray(g)) continue;
    const lon = Number(g[0]), lat = Number(g[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    if (lon < w) w = lon;
    if (lon > e) e = lon;
    if (lat < s) s = lat;
    if (lat > n) n = lat;
  }
  if (w > e) { toast('Nothing to frame in this pane yet', { type: 'info' }); return; }
  if (e - w < 0.02 && n - s < 0.02) { flyTo([(w + e) / 2, (s + n) / 2], Math.max(13, map.getZoom())); return; }
  try {
    map.fitBounds([[w, Math.max(-85, s)], [e, Math.min(85, n)]],
      { padding: 70, maxZoom: 13, duration: 1400, essential: true });
  } catch (err) { /* keep the current view */ }
  setFocus([(w + e) / 2, (s + n) / 2]);
  playSound('navigate');
}

/* [2c] 'Show photos' — register posters for up to PANE_PHOTO_BATCH members and
 * draw them in a pane-only symbol layer (works at any zoom, independent of the
 * globe_photo_pins zoom rule). Toggling off removes the layer + unpins. */
function panePhotoMembers() {
  if (!pane) return [];
  return pane.members
    .filter((m) => m.p && m.p.c && !isExposure(m.p) && Array.isArray(m.geom))
    .slice(0, PANE_PHOTO_BATCH);
}

function ensurePaneLayers() {
  if (!map || !styleReady || !pane) return;
  const feats = pane.members
    .filter((m) => m.p && m.p.c && !isExposure(m.p) && Array.isArray(m.geom))
    .slice(0, 600)
    .map((m) => ({ type: 'Feature', properties: { c: m.p.c },
      geometry: { type: 'Point', coordinates: [Number(m.geom[0]), Number(m.geom[1])] } }))
    .filter((f) => Number.isFinite(f.geometry.coordinates[0]) && Number.isFinite(f.geometry.coordinates[1]));
  const data = { type: 'FeatureCollection', features: feats };
  try {
    const src = map.getSource(PANE_SOURCE);
    if (src) src.setData(data);
    else map.addSource(PANE_SOURCE, { type: 'geojson', data });
    if (!map.getLayer(PANE_LAYER)) {
      const pinned = [...photoPinned].filter((cid) => photoReg.has(cid));
      const before = map.getLayer('globe-measure-line') ? 'globe-measure-line' : undefined;
      map.addLayer({ id: PANE_LAYER, type: 'symbol', source: PANE_SOURCE, maxzoom: 20,
        filter: pinned.length ? ['in', ['get', 'c'], ['literal', pinned]] : ['boolean', false],
        layout: {
          'icon-image': ['concat', PHOTO_MARK, ['get', 'c']],
          'icon-size': PHOTO_SIZE,
          'icon-anchor': 'bottom', 'icon-offset': [0, -5],
          'icon-allow-overlap': true,
        },
        paint: { 'icon-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0, 4, 1] } }, before);
    }
  } catch (err) { /* style mid-swap — retried next render */ }
}

function clearPanePhotos() {
  if (map && styleReady) {
    try { if (map.getLayer(PANE_LAYER)) map.removeLayer(PANE_LAYER); } catch (err) { /* noop */ }
    try { if (map.getSource(PANE_SOURCE)) map.removeSource(PANE_SOURCE); } catch (err) { /* noop */ }
  }
  for (const cid of [...photoPinned]) photoPinned.delete(cid);
  if (window.__globe) window.__globe.panePhotos = false;
  evictFarPhotos();
  evictOverCap();
}

function setPanePhotos(on) {
  if (!pane) return;
  pane.photosOn = !!on;
  if (window.__globe) window.__globe.panePhotos = pane.photosOn;
  if (!on) clearPanePhotos();
  else {
    const members = panePhotoMembers();
    for (const m of members) photoPinned.add(m.p.c);
    if (members.length) {
      ensurePaneLayers();
      queuePosters(members.map((m) => m.p.c));
      toast(`Photo pins on — registering ${fmt(members.length)} posters for this pane`, { type: 'info', timeout: 2400 });
    } else {
      toast('No pin-able members in this pane (exposures stay metadata-only)', { type: 'info' });
    }
  }
  renderPane();                                          // refresh the action button state
}

function syncPanePhotos() {
  if (!pane || !pane.photosOn) return;
  const members = panePhotoMembers();
  for (const cid of [...photoPinned]) photoPinned.delete(cid);
  for (const m of members) photoPinned.add(m.p.c);
  ensurePaneLayers();
  queuePosters(members.map((m) => m.p.c));
}

function paneCountryFilter() {
  if (!pane || pane.kind !== 'country') return;
  countryToggle(pane.key, true);                         // the same setFilters the label click uses
}

function closeAreaPanel(quiet) {
  if (!pane || !ui.area) return;
  clearPanePhotos();
  pane = null;
  ui.area.classList.remove('open');
  clearTimeout(paneHideTimer);
  paneHideTimer = setTimeout(() => { if (!pane && ui.area) ui.area.hidden = true; }, 190);
  if (window.__globe) { window.__globe.areaPanel = false; window.__globe.panePhotos = false; }
  if (!quiet) playSound('toggle');
}

/* Esc must not fight the app's overlays: only close the pane when nothing else is open */
function anyAppOverlayOpen() {
  const vis = (id) => { const n = document.getElementById(id); return !!n && !n.hidden; };
  if (vis('palette') || vis('modal-player') || vis('modal-warn') || vis('modal-settings') || vis('modal-help')) return true;
  const d = document.getElementById('drawer');
  if (d && d.classList.contains('open')) return true;
  return !!document.querySelector('.menu.open');
}

function wireAreaPanel() {
  if (!ui.area) return;
  ui.area.addEventListener('click', (ev) => {
    const pa = ev.target.closest('[data-pa]');
    if (pa) {
      const a = pa.dataset.pa;
      if (a === 'close') closeAreaPanel();
      else if (a === 'zoom') paneZoomFit();
      else if (a === 'photos') setPanePhotos(!(pane && pane.photosOn));
      else if (a === 'filter') paneCountryFilter();
      else if (a === 'more' && pane) { pane.limit += PANE_PAGE; renderPaneList(); }
      return;
    }
    const b = ev.target.closest('[data-a]');
    if (!b || !pane) return;
    const cid = b.dataset.cid || '';
    const act = b.dataset.a;
    if (act === 'watch') openPlayerFor(cid);
    else if (act === 'details') openDrawer(cid);
    else if (act === 'fav') {
      toggleFavourite(cid).then(() => {
        if (destroyed || !ui.areaList) return;
        ui.areaList.querySelectorAll('[data-a="fav"]').forEach((x) => x.classList.toggle('on', isFav(x.dataset.cid)));
      });
    } else if (act === 'stage') addToStage(cid);
  });
  // thumbnail fallback: a failed poster becomes a quiet text note, never a broken image
  ui.area.addEventListener('error', (ev) => {
    const img = ev.target;
    if (!img || img.tagName !== 'IMG') return;
    const th = img.closest('.ga-thumb');
    if (!th) return;
    th.classList.add('ga-thumb-none');
    th.textContent = 'no poster yet';
  }, true);
  if (ui.areaX) ui.areaX.addEventListener('click', closeAreaPanel);
  if (ui.areaQ) ui.areaQ.addEventListener('input', () => {
    if (!pane) return;
    pane.q = ui.areaQ.value || '';
    renderPaneList();
  });
  if (ui.areaSort) ui.areaSort.addEventListener('click', (ev) => {
    const b = ev.target.closest('.seg-btn');
    if (!b || !pane) return;
    pane.sort = b.dataset.val; setPaneSeg(ui.areaSort, pane.sort); renderPaneList(); playSound('toggle');
  });
  if (ui.areaFilt) ui.areaFilt.addEventListener('click', (ev) => {
    const b = ev.target.closest('.seg-btn');
    if (!b || !pane) return;
    pane.filt = b.dataset.val; setPaneSeg(ui.areaFilt, pane.filt); renderPaneList(); playSound('toggle');
  });
}

/* ── URL state (#/globe?lat=..&lng=..&z=..&b=..&p=..) ────────────────── */

function writeHash() {
  if (!map || destroyed) return;
  let params = new URLSearchParams();
  try {
    const link = viewLink();                       // keeps the current filter params
    const q = link.indexOf('?');
    if (q >= 0) params = new URLSearchParams(link.slice(q + 1));
  } catch (err) { /* filters just aren't in the link */ }
  const c = map.getCenter();
  params.set('lat', c.lat.toFixed(4));
  params.set('lng', c.lng.toFixed(4));
  params.set('z', map.getZoom().toFixed(2));
  params.set('b', map.getBearing().toFixed(1));
  params.set('p', String(Math.round(map.getPitch())));
  try { history.replaceState(null, '', location.pathname + '#/globe?' + params.toString()); }
  catch (err) { /* noop */ }
}

function scheduleHash() {
  if (hashTimer) return;                          // throttle: one write per ~800 ms window
  hashTimer = setTimeout(() => { hashTimer = null; writeHash(); }, 800);
}

function readHashState() {
  const raw = String(location.hash || '');
  const q = raw.indexOf('?');
  if (q < 0) return null;
  const params = new URLSearchParams(raw.slice(q + 1));
  const num = (k) => {
    const v = params.get(k);
    if (v == null || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const lat = num('lat'); const lng = num('lng');
  if (lat === null || lng === null) return null;
  const z = num('z'); const b = num('b'); const p = num('p');
  return {
    lat: clamp(lat, -89, 89), lng,
    zoom: clamp(z === null ? WORLD_VIEW.zoom : z, 0, 20),
    bearing: b === null ? 0 : b,
    pitch: clamp(p === null ? 0 : p, 0, 85),
  };
}

/* ── map build + interaction wiring ──────────────────────────────────── */

function buildMap() {
  const start = readHashState() || { ...WORLD_VIEW, pitch: 15 };   // fresh entry: a subtle 3D tilt
  map = new M.Map({
    container: ui.host,
    style: buildStyle(),
    center: [start.lng, start.lat],
    zoom: start.zoom,
    bearing: start.bearing,
    pitch: start.pitch,
    maxPitch: 85,
    dragRotate: true,
    attributionControl: false,
  });
  map.addControl(new M.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new M.GlobeControl(), 'top-right');
  map.addControl(new M.ScaleControl({ maxWidth: 90 }), 'bottom-left');
  map.addControl(new M.AttributionControl({ compact: false, customAttribution: ATTRIB }),
    'bottom-right');
  if (window.__globe) window.__globe.map = map;   // debug handle (smoke tests introspect)

  map.on('error', onMapError);
  map.on('style.load', onStyleReady);
  map.on('moveend', () => {
    scheduleHash(); scheduleHere(); updateDebugCounts(); schedulePulse();
    scheduleMini();                                 // minimap viewport (~150 ms throttle)
    updateCityTier();                               // city-label count threshold band
    schedulePhotoPins();                            // photo pins: viewport-driven poster pass (~350 ms)
    positionMeasureReadout(measureState && measureState.pts[measureState.pts.length - 1]);
  });
  map.on('move', () => {
    if (measureState) positionMeasureReadout(measureState.pts[measureState.pts.length - 1]);
    scheduleMini();
  });
  map.on('idle', updateDebugCounts);
  map.on('click', onMeasureClick);                  // ruler vertex (guards internally)
  map.on('dblclick', onMeasureDbl);                 // ruler finish: double-click, never zoom
  map.on('click', 'globe-clusters', onClusterClick);
  map.on('click', 'globe-points', onPointClick);
  map.on('dblclick', 'globe-points', onPointDbl);
  map.on('mousemove', 'globe-points', onPointMove);
  map.on('mouseleave', 'globe-points', onPointLeave);
  map.on('mousemove', 'globe-clusters', onClusterMove);
  map.on('mouseleave', 'globe-clusters', onClusterLeave);
  map.on('click', 'globe-country-labels', onCountryClick);
  map.on('mousemove', 'globe-country-labels', onCountryMove);
  map.on('mouseleave', 'globe-country-labels', onCountryLeave);
  map.on('click', 'globe-city-labels', onCityClick);
  map.on('mousemove', 'globe-city-labels', onCityMove);
  map.on('mouseleave', 'globe-city-labels', onCountryLeave);
  map.on('mouseenter', 'globe-points', () => { if (!measureState) setCursor('pointer'); });
  map.on('mouseenter', 'globe-clusters', () => { if (!measureState) setCursor('pointer'); });
  map.on('mouseenter', 'globe-country-labels', () => { if (!measureState) setCursor('pointer'); });
  map.on('mouseenter', 'globe-city-labels', () => { if (!measureState) setCursor('pointer'); });
  map.on('move', onCardMapMove);                  // hide the hover card once the anchor drifts
  map.on('dragstart', hideHoverCard);
  map.on('zoomstart', hideHoverCard);

  // idle rotation pauses on real map input only (toolbar clicks don't count)
  for (const evt of ['mousedown', 'touchstart', 'wheel']) {
    ui.host.addEventListener(evt, bumpInput, { passive: true });
  }
  ui.wrap.addEventListener('keydown', bumpInput, { capture: true });

  kickPoints();
  startLoop();
  // the container can report a zero-size box for a moment; kick it twice (rAF can stall occluded)
  setTimeout(() => { if (map && !destroyed) map.resize(); }, 60);
  setTimeout(() => { if (map && !destroyed) map.resize(); }, 600);
}

function bumpInput() { lastInput = performance.now(); }
function wrapLng(lng) { return ((lng + 540) % 360) - 180; }

/* style readiness is idempotent: the 'style.load' event OR the loop's isStyleLoaded()
 * check can land it first (the event has been observed to miss on slow first paints). */
function onStyleReady() {
  if (styleReady || destroyed || !map) return;
  map.setProjection({ type: 'globe' });
  styleReady = true;
  if (window.__globe) {
    window.__globe.projection = map.getProjection ? map.getProjection().type : 'globe';
    window.__globe.ready = true;
    window.__globe.today = todayDateVal();
  }
  applyFilters();
  photoReg.clear();                                 // a fresh style has no registered images
  applyPhotoPinsSetting();                          // re-apply the photo-pin mode to the new style
  applyPhotoFilters();                              // …and the empty registry filter
  pulseStatic = false;                              // fresh style: re-arm the pulse
  if (pointsCache) pushPoints(pointsCache);
  if (termWanted) addTerminator();                  // persisted ON: re-add on the new style
  updateTodaySub(todayDateVal());
  scheduleMini();
  writeHash();                                  // router's syncHash drops lat/lng — put them back
  updateDebugCounts();
  schedulePulse();
}

function onMapError(ev) {
  const err = ev && ev.error;
  const msg = String((err && err.message) || err || '');
  const url = String((err && (err.url || (err.request && err.request.url))) || '');
  // GIBS answers missing tiles with HTTP 500 (not 404) — known noise, not a bug
  if (url.includes('gibs.earthdata.nasa.gov') || msg.includes('gibs.earthdata.nasa.gov')) return;
  if (window.__globe) window.__globe.errors.push(msg || 'map error');
}

function onClusterClick(ev) {
  if (measureState) return;                      // measuring: clicks add vertices, never expand
  const f = ev.features && ev.features[0];
  if (!f || f.properties.cluster_id == null) return;
  const src = map && map.getSource('cams');
  if (!src) return;
  const p = f.properties || {};
  // v0.4.5: EVERY cluster total opens the area panel — and the dive is kept
  openAreaPanel({ kind: 'cluster', key: 'k' + p.cluster_id, clusterId: p.cluster_id,
    count: p.point_count || 0, coords: f.geometry.coordinates.slice() });
  src.getClusterExpansionZoom(f.properties.cluster_id).then((z) => {
    if (destroyed || !map) return;
    map.flyTo({ center: f.geometry.coordinates, zoom: Math.min(19, z + 0.2),
      speed: 1.7, essential: true });
    playSound('click');
  }).catch((err) => {
    if (window.__globe) window.__globe.errors.push('expand: ' + (err.message || err));
  });
}

function onPointClick(ev) {
  if (measureState) return;                      // measuring: clicks add vertices, never popups
  const f = ev.features && ev.features[0];
  if (!f) return;
  if (hoverPopup) { hoverPopup.remove(); hoverPopup = null; }
  openPointPopup(f.properties, f.geometry.coordinates);
}

function onPointDbl(ev) {
  if (measureState) return;                      // dblclick finishes the ruler instead
  const f = ev.features && ev.features[0];
  if (!f) return;
  if (isExposure(f.properties)) {
    toast('Metadata only — exposure rows are never previewed', { type: 'info' });
    return;
  }
  openPlayerFor(f.properties.c);
}

/* shared 300 ms hover tooltip (points · clusters · country labels) */
function showTipPopup(html) {
  if (destroyed || !map || !M) return;
  if (hoverPopup) hoverPopup.remove();
  hoverPopup = new M.Popup({ closeButton: false, closeOnClick: false, offset: 10,
    className: 'wfd-gtip' })
    .setLngLat(hoverLatLng)
    .setHTML(html)
    .addTo(map);
}

function scheduleTip(id, html, coords) {
  hoverLatLng = coords || hoverLatLng;
  if (id === hoverId) {
    if (hoverPopup) hoverPopup.setLngLat(hoverLatLng);
    return;
  }
  hoverId = id;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => showTipPopup(html), 300);   // 300 ms dwell
}

function onPointMove(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  const p = f.properties || {};
  let html = `<span class="gtip-name">${esc(p.n || p.c || '')}</span>`;
  if (p.s) html += `<div class="gtip-sub">${esc(p.s)}${p.y ? ' · ' + esc(p.y) : ''}</div>`;
  scheduleTip('p' + (p.c || ''), html, f.geometry ? f.geometry.coordinates : ev.lngLat);
  hoverCardMove('point', f, ev.point);
}

/* [1] cluster hover: "12,345 cams · 3,210 live · 1,102 stale" from clusterProperties */
function clusterTipHTML(p) {
  const bits = [`${fmt(p.point_count || 0)} cams`, `${fmt(p.live || 0)} live`, `${fmt(p.stale || 0)} stale`];
  if (p.dead) bits.push(`${fmt(p.dead)} dead`);
  if (p.unk) bits.push(`${fmt(p.unk)} unknown`);
  return `<span class="gtip-name">${bits.join(' · ')}</span>`;
}

function onClusterMove(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  const p = f.properties || {};
  scheduleTip('k' + p.cluster_id, clusterTipHTML(p), f.geometry ? f.geometry.coordinates : ev.lngLat);
  hoverCardMove('cluster', f, ev.point);
}

/* [2] country-label hover: "United States · 6,640 cams · 2,100 live" plus the
 * full status split, and the honesty sub-caption when a status filter is on */
function onCountryMove(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  const p = f.properties || {};
  const name = countryDisplayName(p.y) || p.y;
  let html = `<span class="gtip-name">${esc(name)} · ${fmt(p.cnt)} cams · ${fmt(p.live || 0)} live</span>`;
  html += `<div class="gtip-sub">${fmt(p.stale || 0)} stale · ${fmt(p.dead || 0)} dead · ${fmt(p.unk || 0)} unknown/unverified</div>`;
  html += '<div class="gtip-sub">click to filter · click again to clear</div>';
  if ((store.filters.status || []).length) {
    html += '<div class="gtip-sub">counts cover all statuses — the status filter is not applied here</div>';
  }
  scheduleTip('y' + p.y, html, f.geometry ? f.geometry.coordinates : ev.lngLat);
}

function onPointLeave() {
  hoverId = null;
  clearTimeout(hoverTimer);
  hoverTimer = null;
  if (hoverPopup) { hoverPopup.remove(); hoverPopup = null; }
  hoverCardLeave();
  setCursor(measureState ? 'crosshair' : '');
}

function onClusterLeave() { onPointLeave(); }
function onCountryLeave() { onPointLeave(); }

/* ── [3] hover info card — rich browsing without clicking ──────────────
 * A fixed-position overlay (allowed: not a DOM marker on the map) that follows
 * a debounced hover (~250 ms dwell) over a cluster or a pin. Single points load
 * /api/poster/<cid> lazily into a 140 px frame — one poster fetch at a time,
 * a failure becomes a "no poster yet" note, never a broken image. Exposure rows
 * stay metadata-only. Hidden while measuring / touring, on mouseleave and when
 * map input moves the anchor beyond ~48 px. */

function hoverKeyOf(kind, f) {
  const p = f.properties || {};
  return kind === 'cluster' ? 'k' + p.cluster_id : 'p' + (p.c || '');
}

function hcardClusterHTML(p) {
  const total = p.point_count || 0;
  const share = total ? Math.round((100 * (p.live || 0)) / total) : 0;
  const rows = [
    ['live', p.live || 0, 'var(--live)'],
    ['stale', p.stale || 0, 'var(--stale)'],
    ['dead', p.dead || 0, 'var(--dead)'],
    ['unknown + unverified', p.unk || 0, 'var(--unverified)'],
  ];
  return `<div class="ghc-title">${fmt(total)} cameras<span class="ghc-share">${share}% live</span></div>`
    + '<div class="ghc-rows">' + rows.map(([lab, n, col]) => '<div class="ghc-row">'
      + `<span class="ghc-dot" style="background:${col}"></span>`
      + `<span class="ghc-lab">${esc(lab)}</span><b>${fmt(n)}</b></div>`).join('') + '</div>'
    + '<div class="ghc-hint">click to dive in</div>';
}

function hcardPointHTML(p) {
  const bits = [p.y, p.f].filter(Boolean).map(esc);
  let h = `<div class="ghc-title">${esc(p.n || '(unnamed)')}</div>`;
  if (bits.length) h += `<div class="ghc-sub">${bits.join(' · ')}</div>`;
  h += `<div class="ghc-meta">${statusChipHTML({ status: p.s })}`
    + `${p.p ? `<span class="ghc-proto">${esc(p.p)}</span>` : ''}</div>`;
  if (isExposure(p)) {
    h += '<div class="ghc-note">metadata only — listed by an aggregator; never previewed</div>';
  } else {
    h += '<div class="ghc-poster"><span class="ghc-post-ph">loading poster…</span></div>';
  }
  return h;
}

function loadPoster(cid) {
  const host = ui.hcard && ui.hcard.querySelector('.ghc-poster');
  if (!host || !cid) return;
  if (posterCache.get(cid) === 'none') {
    host.innerHTML = '<span class="ghc-post-none">no poster yet</span>';
    return;
  }
  const seq = ++posterSeq;                    // one live poster request at a time
  const img = document.createElement('img');
  img.alt = '';
  img.addEventListener('load', () => { if (seq === posterSeq) posterCache.set(cid, 'ok'); });
  img.addEventListener('error', () => {
    if (seq !== posterSeq) return;
    posterCache.set(cid, 'none');
    host.innerHTML = '<span class="ghc-post-none">no poster yet</span>';
  });
  host.innerHTML = '';
  host.appendChild(img);
  img.src = '/api/poster/' + encodeURIComponent(cid);
}

function positionHoverCard(point) {
  const card = ui.hcard;
  if (!card || !point || !ui.wrap) return;
  const w = card.offsetWidth || 230; const hgt = card.offsetHeight || 180;
  const pad = 8; const off = 16;
  let x = point.x + off; let y = point.y + off;
  if (x + w + pad > ui.wrap.clientWidth) x = point.x - off - w;              // flip at the right edge
  if (y + hgt + pad > ui.wrap.clientHeight) y = point.y - off - hgt;         // …and at the bottom
  card.style.left = Math.round(clamp(x, pad, Math.max(pad, ui.wrap.clientWidth - w - pad))) + 'px';
  card.style.top = Math.round(clamp(y, pad, Math.max(pad, ui.wrap.clientHeight - hgt - pad))) + 'px';
}

function showHoverCard(kind, f, point) {
  const card = ui.hcard;
  if (!card || destroyed || measureState || tourState) return;
  const p = f.properties || {};
  card.innerHTML = kind === 'cluster' ? hcardClusterHTML(p) : hcardPointHTML(p);
  card.hidden = false;
  cardFor = hoverKeyOf(kind, f);
  cardAnchor = f.geometry ? f.geometry.coordinates.slice() : null;
  if (cardAnchor) cardAnchorPx = map.project(cardAnchor);
  positionHoverCard(point);
  if (kind === 'point' && !isExposure(p)) loadPoster(p.c);
}

function hoverCardMove(kind, f, point) {
  if (destroyed || !ui.hcard || measureState || tourState || !point) return;
  const key = hoverKeyOf(kind, f);
  if (key !== cardKey) {
    cardKey = key;
    if (cardFor && cardFor !== key) {          // a new feature: drop the old card now
      ui.hcard.hidden = true; ui.hcard.innerHTML = ''; cardFor = null;
    }
    clearTimeout(cardTimer);
    cardTimer = setTimeout(() => {
      cardTimer = null;
      if (cardKey === key) showHoverCard(kind, f, point);
    }, HCARD_DWELL_MS);
  } else if (cardFor === key && !ui.hcard.hidden) {
    positionHoverCard(point);                  // already shown: follow the cursor
  }
}

function hoverCardLeave() {
  cardKey = null;
  clearTimeout(cardTimer);
  cardTimer = null;
  hideHoverCard();
}

function hideHoverCard() {
  clearTimeout(cardTimer);
  cardTimer = null;
  cardFor = null; cardAnchor = null; cardAnchorPx = null;
  if (ui.hcard) { ui.hcard.hidden = true; ui.hcard.innerHTML = ''; }
}

function onCardMapMove() {
  if (!ui.hcard || ui.hcard.hidden || !cardAnchor || !cardAnchorPx || !map) return;
  const p = map.project(cardAnchor);
  if (Math.hypot(p.x - cardAnchorPx.x, p.y - cardAnchorPx.y) > 48) hideHoverCard();
}

/* [2] click a country label: apply that country through the SAME setFilters the
 * sidebar uses (a second click clears it, chip-style) and fly to the country bbox. */
function countryToggle(cc, fly) {
  const cur = (store.filters.country || []).filter(Boolean);
  const had = cur.includes(cc);
  setFilters({ country: had ? cur.filter((v) => v !== cc) : [...cur, cc] });
  playSound('toggle');
  if (!had && fly && map && countryBox.has(cc)) {
    const [w, s, e, n] = countryBox.get(cc);
    const e2 = w > e ? e + 360 : e;            // bbox crosses the antimeridian
    try {
      map.fitBounds([[w, Math.max(-85, s)], [e2, Math.min(85, n)]],
        { padding: 60, maxZoom: 6, duration: 1400, essential: true });
    } catch (err) { /* the filter alone still applies */ }
  }
  toast(had ? `Country filter cleared — ${cc}`
    : `Country filter — ${cc} · click the label or the chip again to clear`,
  { type: 'info', timeout: had ? 1800 : 2600 });
}

function onCountryClick(ev) {
  if (measureState) return;                    // measuring: clicks add vertices
  const f = ev.features && ev.features[0];
  if (!f || !f.properties || !f.properties.y) return;
  hideHoverCard();
  const cc = String(f.properties.y);
  const had = (store.filters.country || []).filter(Boolean).includes(cc);
  countryToggle(cc, true);                     // filter + fly, exactly as before
  // v0.4.5: the panel — a second click on the same country clears and closes
  if (had) {
    if (pane && pane.kind === 'country' && pane.key === cc) closeAreaPanel(true);
  } else {
    openAreaPanel({ kind: 'country', key: cc, count: f.properties.cnt || 0 });
  }
}

/* [3] city-label tier — click flies to the city centroid (cities have no
 * dedicated filter dimension in the app; the tooltip says what a click does).
 * v0.4.5: it also opens the area panel for that city (same click toggles shut). */
function onCityClick(ev) {
  if (measureState) return;                    // measuring: clicks add vertices
  const f = ev.features && ev.features[0];
  if (!f || !f.geometry) return;
  hideHoverCard();
  playSound('click');
  flyTo(f.geometry.coordinates.slice(), 10);   // centroid, city scale
  const t = String((f.properties && f.properties.t) || '');
  if (!t) return;
  if (pane && pane.kind === 'city' && pane.key === t) { closeAreaPanel(true); return; }
  openAreaPanel({ kind: 'city', key: t, count: (f.properties && f.properties.cnt) || 0 });
}

function onCityMove(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  const p = f.properties || {};
  let html = `<span class="gtip-name">${esc(p.t)} · ${fmt(p.cnt)} cams</span>`;
  if (p.live) html += `<div class="gtip-sub">${fmt(p.live)} live</div>`;
  html += '<div class="gtip-sub">click to fly to this city</div>';
  scheduleTip('t' + (p.t || ''), html, f.geometry ? f.geometry.coordinates : ev.lngLat);
}

/* ── [4] world pulse — always-on strip: what the current viewport holds ──
 * Counted client-side from the cached points (same bounds maths as the minimap)
 * and throttled ~300 ms; country tokens apply the country filter like labels. */

function schedulePulse() {
  if (pulseTimer) return;
  pulseTimer = setTimeout(() => { pulseTimer = null; updatePulse(); }, PULSE_MS);
}

function pointPredicate() {
  const f = store.filters;
  const st = f.status || []; const pr = f.protocol || []; const fam = f.family || [];
  const cc = (f.country || []).filter(Boolean).map((c) => String(c).toUpperCase());
  const favOnly = !!store.settings.globe_favonly;
  if (!st.length && !pr.length && !fam.length && !cc.length && !favOnly) return null;
  const ids = store.favIds;
  return (p) => (!st.length || st.includes(p.s))
    && (!pr.length || pr.includes(p.p))
    && (!fam.length || fam.includes(p.f))
    && (!cc.length || cc.includes(String(p.y || '').toUpperCase()))
    && (!favOnly || ids.has(p.c));
}

function inViewStats() {
  if (!map || !pointsCache) return null;
  const b = map.getBounds();
  const w = b.getWest(); const e = b.getEast();
  const s = b.getSouth(); const n = b.getNorth();
  const cross = e < w;
  const world = !cross && (e - w) >= 359.9;
  const pred = pointPredicate();
  const out = { n: 0, live: 0, byCountry: new Map(), byLive: new Map(), fams: new Set() };
  for (const f of pointsCache.features || []) {
    const g = f.geometry && f.geometry.coordinates;
    if (!g) continue;
    const lon = Number(g[0]); const lat = Number(g[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    if (lat < s || lat > n) continue;
    if (!world && (cross ? !(lon >= w || lon <= e) : !(lon >= w && lon <= e))) continue;
    const p = f.properties || {};
    if (pred && !pred(p)) continue;
    out.n++;
    if (p.s === 'live') {
      out.live++;
      if (p.y) out.byLive.set(p.y, (out.byLive.get(p.y) || 0) + 1);
    }
    if (p.y) out.byCountry.set(p.y, (out.byCountry.get(p.y) || 0) + 1);
    if (p.f) out.fams.add(p.f);
  }
  return out;
}

function updatePulse() {
  if (!ui.pulse || destroyed) return;
  const st = inViewStats();
  if (!st) { ui.pulse.hidden = true; return; }
  if (!st.n) {
    ui.pulse.hidden = false;
    ui.pulse.innerHTML = '<span class="gp-hint">no geocoded cameras in view — pan back</span>';
    if (window.__globe) window.__globe.worldPulse = { cams: 0, live: 0, countries: [], hotspots: [],
      families: 0, hot: null, text: ui.pulse.textContent };
    return;
  }
  const top = [...st.byCountry.entries()].sort((a, b2) => b2[1] - a[1]).slice(0, 3);
  const hot = [...st.byLive.entries()].sort((a, b2) => b2[1] - a[1])[0] || null;
  ui.pulse.innerHTML = `<span class="gp-main">in view: <b>${fmt(st.n)}</b> cams · live <b>${fmt(st.live)}</b></span>`
    + (hot ? `<button type="button" class="gp-hot" data-c="${esc(hot[0])}" title="hottest country right now — most live cams in view; click to filter, click again to clear">hot: ${esc(hot[0])} · ${fmt(hot[1])} live</button>` : '')
    + top.map(([c, k]) => `<button type="button" class="gp-cc" data-c="${esc(c)}" title="filter by country ${esc(c)} — click again to clear">${esc(c)} ${fmt(k)}</button>`).join('')
    + `<span class="gp-fam">${fmt(st.fams.size)} famil${st.fams.size === 1 ? 'y' : 'ies'} present</span>`;
  ui.pulse.hidden = false;
  if (window.__globe) {
    window.__globe.worldPulse = { cams: st.n, live: st.live, families: st.fams.size,
      countries: top.map(([c, k]) => ({ y: c, n: k })),
      hot: hot ? { y: hot[0], live: hot[1] } : null, text: ui.pulse.textContent };
  }
}

/* ── [5] legend — status dots + the cluster live-share ramp ────────────
 * Collapsible: the header folds the body; the expanded/collapsed state persists
 * as globe_legend (default true = expanded). */

function setLegendExpanded(on) {
  if (!ui.legend) return;
  ui.legend.classList.toggle('collapsed', !on);
  if (ui.legendBtn) ui.legendBtn.setAttribute('aria-expanded', String(!!on));
  if (ui.wrap) ui.wrap.classList.toggle('glegend', !!on);
  if (window.__globe) window.__globe.legend = !!on;
}

function toggleLegend() {
  if (!ui.legend) return;
  const next = ui.legend.classList.contains('collapsed');   // expand when collapsed
  setLegendExpanded(next);
  saveSettings({ globe_legend: next });
  playSound('toggle');
}

function updateDebugCounts() {
  if (!map || !styleReady || !window.__globe) return;
  try {
    const feats = map.queryRenderedFeatures({ layers: ['globe-clusters'] });
    window.__globe.clusters = feats.length;
    window.__globe.liveClusters = feats.some((f) => ((((f || {}).properties || {}).live) || 0) >= 1);
    window.__globe.singlesVisible = !!map.getLayer('globe-points')
      && map.getZoom() >= SINGLE_MINZOOM;          // progressive disclosure state
    window.__globe.pulse = !!map.getLayer(PULSE_LAYER);
  } catch (err) { /* style may be mid-swap */ }
}

/* auto-rotate + fps probe (single rAF loop) */
function startLoop() {
  let last = 0; let frames = 0; let t0 = 0;
  const step = (ts) => {
    if (destroyed || !map) return;
    rafId = requestAnimationFrame(step);
    if (!styleReady && typeof map.isStyleLoaded === 'function' && map.isStyleLoaded()) {
      onStyleReady();
    }
    frames++;
    if (!t0) t0 = ts;
    if (ts - t0 >= 1000) {
      if (window.__globe) window.__globe.fps = Math.round((frames * 1000) / (ts - t0));
      frames = 0; t0 = ts;
    }
    // live-dot pulse: ~10 fps paint updates on ONE layer (cheap); paused while
    // the document is hidden; a single static glow under prefers-reduced-motion
    if (styleReady && !document.hidden && ts - pulseLast >= 100) {
      pulseLast = ts;
      try {
        if (map.getLayer(PULSE_LAYER)) {
          if (reduced()) {
            if (!pulseStatic) {
              pulseStatic = true;
              map.setPaintProperty(PULSE_LAYER, 'circle-radius', pulseRadiusExpr(1.4));
              map.setPaintProperty(PULSE_LAYER, 'circle-opacity', 0.2);
            }
          } else {
            pulseStatic = false;
            pulsePhase += 0.55;                            // ~1.1 s period
            const sine = Math.sin(pulsePhase);
            map.setPaintProperty(PULSE_LAYER, 'circle-radius',
              pulseRadiusExpr(1.4 + 0.4 * sine));          // 1.0x .. 1.8x
            map.setPaintProperty(PULSE_LAYER, 'circle-opacity', 0.235 - 0.115 * sine);
          }
          if (window.__globe) window.__globe.pulse = true;
        }
      } catch (err) { /* style mid-swap — the next tick retries */ }
    }
    // ~0.12°/s idle drift; pauses on any input, resumes after 20 s idle.
    // Tours and the ruler hold it still for their duration, then it resumes.
    if (store.settings.globe_autorotate && !document.hidden && !tourState && !measureState
      && (ts - lastInput) > 20000 && !map.isMoving()) {
      const dt = last ? Math.min(0.25, (ts - last) / 1000) : 0;
      if (dt > 0) {
        const c = map.getCenter();
        map.setCenter([wrapLng(c.lng + 0.12 * dt), c.lat]);
      }
    }
    last = ts;
  };
  rafId = requestAnimationFrame(step);
}

/* ── overlays ────────────────────────────────────────────────────────── */

/* viewpoint presets — transient easeTo jumps (World / Region / City); nothing
 * persists. Region keeps the current centre at z5; City keeps the centre and
 * drops into a close, pitched view. */
function applyViewpoint(kind) {
  if (!map || destroyed || measureState) return;
  const c = map.getCenter();
  const cam = kind === 'world'
    ? { center: [8, 20], zoom: 1.6, bearing: 0, pitch: 15, duration: 1700 }
    : kind === 'region'
      ? { center: [c.lng, c.lat], zoom: 5, duration: 1300 }
      : { center: [c.lng, c.lat], zoom: 11.5, bearing: -15, pitch: 50, duration: 1500 };
  hideHoverCard();
  map.easeTo({ ...cam, essential: true });
  if (window.__globe) window.__globe.viewpoint = kind;
  playSound('navigate');
}

function syncToolbar() {
  if (!ui.root) return;
  const r = ui.rotateBtn;
  if (r) {
    const on = !!store.settings.globe_autorotate;
    r.classList.toggle('on', on);
    r.title = on ? 'Idle auto-rotate ON — pauses on input, resumes after 20s idle'
      : 'Idle auto-rotate (off)';
  }
  const f = ui.favBtn;
  if (f) {
    const on = !!store.settings.globe_favonly;
    f.classList.toggle('on', on);
    f.title = on ? 'Showing favourites only — click for all pins' : 'Show favourites only';
  }
  const t = ui.termBtn;
  if (t) {
    const on = !!store.settings.globe_terminator;
    t.classList.toggle('on', on);
    t.title = (on ? 'Day/night terminator ON' : 'Day/night terminator (off)')
      + ' — a visual cue; imagery is not swapped';
  }
  const tb = ui.tourBtn;
  if (tb) {
    tb.classList.toggle('on', !!tourState);
    tb.title = tourState ? 'Stop the tour'
      : 'Cinematic tour — favourites (saved order), else the Watch stage';
  }
  const mb = ui.measureBtn;
  if (mb) {
    mb.classList.toggle('on', !!measureState);
    mb.title = measureState ? 'Finish measuring (Done / double-click / Esc)'
      : 'Measure great-circle distances — click points; pitch eases top-down';
  }
  if (ui.dateWrap) ui.dateWrap.hidden = !store.settings.globe_today;
  if (ui.dateInput) {
    ui.dateInput.max = todayISO();
    const d = todayDateVal();
    if (ui.dateInput.value !== d) ui.dateInput.value = d;
  }
  if (ui.pop) {
    ui.pop.querySelectorAll('[data-layer]').forEach((cb) => {
      cb.checked = !!store.settings['globe_' + cb.dataset.layer];
    });
  }
  if (ui.photoSeg) {
    const pm = store.settings.globe_photo_pins === 'on' || store.settings.globe_photo_pins === 'off'
      ? store.settings.globe_photo_pins : 'auto';
    setPaneSeg(ui.photoSeg, pm);
    if (ui.photoNote) {
      ui.photoNote.textContent = pm === 'on' ? 'on — from z6 · poster thumbs over the dots'
        : pm === 'off' ? 'off — posters hidden, dots only'
          : 'auto — from z9.5 · poster thumbs over the dots';
    }
  }
}

function toggleRotate() {
  const on = !store.settings.globe_autorotate;
  saveSettings({ globe_autorotate: on });
  syncToolbar();
  playSound('toggle');
  toast(on ? 'Auto-rotate on — pauses on input, resumes after 20s idle' : 'Auto-rotate off',
    { type: 'info', timeout: 1800 });
}

function toggleFavOnly() {
  const next = !store.settings.globe_favonly;
  saveSettings({ globe_favonly: next });
  applyFilters();
  syncToolbar();
  playSound('toggle');
  if (next && !store.favIds.size) toast('No favourites yet — heart a camera first', { type: 'info' });
}

function wireOverlays() {
  wireSearch();
  wireAreaPanel();
  // filters changed anywhere (sidebar, chips, country labels, pulse tokens)
  // restyle the pins client-side, re-derive the world-pulse counts and refresh
  // an open area panel (its rows respect the same filters)
  unsubs.push(bus.on('filters', () => { applyFilters(); schedulePulse(); if (pane) refreshPaneMembers(); }));
  unsubs.push(bus.on('prefs', () => { applyFilters(); schedulePulse(); applyPhotoPinsSetting(); }));
  unsubs.push(bus.on('settings', (patch) => {
    if (patch && Object.prototype.hasOwnProperty.call(patch, 'globe_photo_pins')) {
      applyPhotoPinsSetting(); syncToolbar();
    }
  }));
  // 'r' = random live cam while the globe container has focus (never leaks to the app)
  ui.wrap.addEventListener('keydown', (ev) => {
    if (ev.key !== 'r' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const t = ev.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    ev.stopPropagation();
    randomLive();
  });
  // layers popover
  const btn = ui.layersBtn;
  if (btn && ui.pop) {
    docClose = (ev) => {
      if (!ui.pop || ui.pop.hidden) return;
      if (!ui.pop.contains(ev.target) && !btn.contains(ev.target)) ui.pop.hidden = true;
    };
    document.addEventListener('click', docClose);
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      ui.pop.hidden = !ui.pop.hidden;
    });
    ui.pop.querySelectorAll('[data-layer]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const key = cb.dataset.layer;
        saveSettings({ ['globe_' + key]: cb.checked });
        if (key === 'heat') applyHeat(cb.checked);
        else if (key === 'minimap') applyMinimap(cb.checked);
        else {
          const layerId = LAYER_KEYS[key];
          if (map && styleReady && layerId) {
            try { map.setLayoutProperty(layerId, 'visibility', cb.checked ? 'visible' : 'none'); }
            catch (err) { /* style not ready — the rebuilt style picks it up */ }
          }
        }
        if (key === 'today' && ui.dateWrap) ui.dateWrap.hidden = !cb.checked;
        playSound('toggle');
      });
    });
  }
  if (ui.photoSeg) {
    ui.photoSeg.addEventListener('click', (ev) => {
      const b = ev.target.closest('.seg-btn');
      if (!b) return;
      saveSettings({ globe_photo_pins: b.dataset.val });
      applyPhotoPinsSetting();
      syncToolbar();
      playSound('toggle');
      toast(b.dataset.val === 'off' ? 'Photo pins off — dots only'
        : b.dataset.val === 'on' ? 'Photo pins on — posters register from z6'
          : 'Photo pins auto — posters register from z9.5', { type: 'info', timeout: 1900 });
    });
  }
  if (ui.rotateBtn) ui.rotateBtn.addEventListener('click', toggleRotate);
  if (ui.vpWorld) ui.vpWorld.addEventListener('click', () => applyViewpoint('world'));
  if (ui.vpRegion) ui.vpRegion.addEventListener('click', () => applyViewpoint('region'));
  if (ui.vpCity) ui.vpCity.addEventListener('click', () => applyViewpoint('city'));
  if (ui.randomBtn) ui.randomBtn.addEventListener('click', () => randomLive());
  if (ui.copyBtn) {
    ui.copyBtn.addEventListener('click', () => {
      writeHash();
      copyText(location.href).then(() => toast('View link copied', { type: 'ok' }));
    });
  }
  if (ui.favBtn) ui.favBtn.addEventListener('click', toggleFavOnly);
  if (ui.here) ui.here.addEventListener('click', toggleHereList);
  if (ui.termBtn) ui.termBtn.addEventListener('click', toggleTerminator);
  if (ui.tourBtn) {
    ui.tourBtn.addEventListener('click', () => { if (tourState) stopTour(); else startTour(); });
  }
  if (ui.measureBtn) ui.measureBtn.addEventListener('click', toggleMeasure);
  if (ui.tourbar) {
    ui.tourbar.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-tour]');
      if (!b || !tourState) return;
      if (b.dataset.tour === 'next') { clearTimeout(tourState.dwell); runTourStop(); }
      else stopTour();
    });
  }
  if (ui.mpanel) {
    ui.mpanel.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-measure]');
      if (!b) return;
      if (b.dataset.measure === 'clear') clearMeasure();
      else finishMeasure();
    });
  }
  if (ui.dateInput) ui.dateInput.addEventListener('change', onTodayDateInput);
  if (ui.dateReset) {
    ui.dateReset.addEventListener('click', () => { setTodayDate(todayISO()); playSound('toggle'); });
  }
  if (ui.miniX) {
    ui.miniX.addEventListener('click', () => {
      saveSettings({ globe_minimap: false });
      applyMinimap(false);
      syncToolbar();
      playSound('toggle');
      toast('Minimap hidden — re-enable it from the layers list', { type: 'info', timeout: 2200 });
    });
  }
  if (ui.legendBtn) ui.legendBtn.addEventListener('click', toggleLegend);
  if (ui.pulse) {
    ui.pulse.addEventListener('click', (ev) => {
      const b = ev.target.closest('.gp-cc, .gp-hot');   // country tokens + hot token
      if (b) countryToggle(b.dataset.c, true);
    });
  }
  // Esc stops a running tour / finishes the ruler — and closes the area panel
  // when nothing else is open — otherwise it is NOT swallowed
  escHandler = (ev) => {
    if (ev.key !== 'Escape') return;
    const t = ev.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (tourState) { ev.stopPropagation(); stopTour(); return; }
    if (measureState) { ev.stopPropagation(); finishMeasure(); return; }
    if (pane && ui.area && !ui.area.hidden && !anyAppOverlayOpen()) {
      ev.stopPropagation();
      closeAreaPanel();
    }
  };
  document.addEventListener('keydown', escHandler, true);
  syncToolbar();
  updateQNote();
}

function renderFallback(msg) {
  if (!ui.host) return;
  if (ui.loading) ui.loading.hidden = true;
  ui.host.innerHTML = `<div class="globe-fallback"><div class="overlay-card">
    <div class="overlay-title">3D globe unavailable</div>
    <p class="warn-text">${esc(msg)}</p>
    <div class="overlay-actions">
      <button type="button" class="btn" id="globe-to-map">Open the flat Map view</button>
    </div>
  </div></div>`;
  const b = ui.host.querySelector('#globe-to-map');
  if (b) b.addEventListener('click', () => go('map'));
}

/* ── lifecycle ───────────────────────────────────────────────────────── */

function cleanup() {
  unsubs.forEach((u) => u()); unsubs = [];
  clearTimeout(hereTimer); hereTimer = null;
  clearTimeout(hashTimer); hashTimer = null;
  clearTimeout(hoverTimer); hoverTimer = null;
  clearTimeout(pulseTimer); pulseTimer = null;
  clearTimeout(cardTimer); cardTimer = null;
  clearTimeout(photoTimer); photoTimer = null;
  clearTimeout(photoFilterTimer); photoFilterTimer = null;
  clearTimeout(paneHideTimer); paneHideTimer = null;
  if (photoAbort) { try { photoAbort.abort(); } catch (err) { /* noop */ } photoAbort = null; }
  photoSeq++;
  photoReg.clear(); photoMiss.clear(); photoPinned.clear(); camCoords = null;
  pane = null;
  cardKey = null; cardFor = null; cardAnchor = null; cardAnchorPx = null;
  clearInterval(termTimer); termTimer = null; termWanted = false;
  clearTimeout(miniTimer); miniTimer = null;
  if (tourState) { clearTimeout(tourState.dwell); tourState = null; }
  measureState = null;                                   // sources die with the map
  if (escHandler) { document.removeEventListener('keydown', escHandler, true); escHandler = null; }
  if (miniMap) { try { miniMap.remove(); } catch (err) { /* noop */ } }
  miniMap = null; miniBox = null; miniDot = null; miniHalo = null;
  if (window.__globe) {
    window.__globe.tour = false; window.__globe.measure = false;
    window.__globe.terminator = false; window.__globe.minimap = false;
    window.__globe.worldPulse = null;
    window.__globe.singlesVisible = false; window.__globe.cities = 0; window.__globe.pulse = false;
    window.__globe.photoPins = 0; window.__globe.areaPanel = false; window.__globe.panePhotos = false;
  }
  if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
  if (ac) { try { ac.abort(); } catch (err) { /* noop */ } ac = null; }
  if (hoverPopup) { try { hoverPopup.remove(); } catch (err) { /* noop */ } hoverPopup = null; }
  if (clickPopup) { try { clickPopup.remove(); } catch (err) { /* noop */ } clickPopup = null; }
  if (docClose) { document.removeEventListener('click', docClose); docClose = null; }
  if (map) { const m = map; map = null; try { m.remove(); } catch (err) { /* noop */ } }
  styleReady = false;
  hoverId = null; hoverLatLng = null;
  hereFeats = []; hereSeq = 0;
  ui = {};
}

export const globeView = {
  title: 'World Map',
  icon: I.globe,
  render(root) {
    cleanup();
    destroyed = false;
    if (!window.__globe) {
      window.__globe = { ready: false, points: 0, clusters: 0, fps: 0, projection: '', errors: [],
        liveClusters: false, countryLabels: 0, legend: true, pulse: false,
        singlesVisible: false, cities: 0, worldPulse: null };
    }
    window.__globe.ready = false;
    window.__globe.projection = '';
    Object.assign(window.__globe, {
      tour: false, measure: false,
      terminator: !!store.settings.globe_terminator,
      heat: !!store.settings.globe_heat,
      minimap: !!store.settings.globe_minimap,
      today: todayDateVal(),
      liveClusters: false, countryLabels: 0,
      legend: store.settings.globe_legend !== false, pulse: false,
      singlesVisible: false, cities: 0, worldPulse: null,
      photoPins: 0, photoPinsMode: 'auto', areaPanel: false, panePhotos: false,
    });
    const todayD = todayDateVal();
    root.innerHTML = `<div class="vwrap view-enter">
      <div class="vhead"><div><h2 class="vtitle">World Map</h2>
        <div class="vsub" id="globe-sub">3D globe · clustered pins · imagery: Esri + NASA GIBS</div></div></div>
      <div class="globe-wrap" id="globe-wrap" tabindex="0">
        <div class="globe-host" id="globe-host"></div>
        <div class="globe-panel globe-search">
          <input id="globe-q" type="search" placeholder="Fly to a camera — name, city, country…" autocomplete="off" spellcheck="false" aria-label="Fly to a camera">
          <div class="globe-results" id="globe-results" hidden></div>
        </div>
        <div class="globe-qnote" id="globe-qnote" hidden></div>
        <div class="globe-tools" id="globe-tools">
          <span class="globe-vp" role="group" aria-label="Viewpoint presets">
            <button type="button" class="btn small" id="globe-vp-world" title="World view — the whole globe (centre 8°,20°, z1.6, tilted)">World</button>
            <button type="button" class="btn small" id="globe-vp-region" title="Region view — z5 around the current centre">Region</button>
            <button type="button" class="btn small" id="globe-vp-city" title="City view — z11.5, pitched 50° around the current centre">City</button>
          </span>
          <button type="button" class="btn small icon-only" id="globe-layers-btn" title="Imagery layers">${I.layers}</button>
          <button type="button" class="btn small icon-only" id="globe-terminator-btn" title="Day/night terminator — a visual cue; imagery is not swapped">${I.term}</button>
          <button type="button" class="btn small icon-only" id="globe-tour-btn" title="Cinematic tour — favourites (saved order), else the Watch stage">${I.tour}</button>
          <button type="button" class="btn small icon-only" id="globe-measure-btn" title="Measure great-circle distances — click points; Done / double-click finishes">${I.ruler}</button>
          <button type="button" class="btn small icon-only" id="globe-rotate-btn" title="Idle auto-rotate (off)">${I.rotate}</button>
          <button type="button" class="btn small icon-only" id="globe-random-btn" title="Random live cam (r while the globe has focus)">${I.dice}</button>
          <button type="button" class="btn small icon-only" id="globe-copy-btn" title="Copy a link to this exact view">${I.copy}</button>
          <button type="button" class="btn small icon-only" id="globe-fav-btn" title="Show favourites only">${I.star}</button>
          <div class="globe-pop" id="globe-pop" hidden>
            <label title="NASA EOSDIS GIBS — Reference Labels (public domain)">
              <input type="checkbox" data-layer="labels"><span>Labels<em>GIBS Reference_Labels</em></span></label>
            <label title="NASA EOSDIS GIBS — VIIRS Black Marble (public domain)">
              <input type="checkbox" data-layer="night"><span>Night lights<em>VIIRS Black Marble · dimmed</em></span></label>
            <label title="NASA EOSDIS GIBS — VIIRS true colour (public domain); pick any day back from today">
              <input type="checkbox" data-layer="today"><span>Today's Earth<em data-today-sub>VIIRS true colour · ${todayD} · ~1–2 day latency</em></span></label>
            <div class="globe-date" id="globe-today-date" hidden>
              <input type="date" id="globe-date-input" max="${todayD}" value="${todayD}" aria-label="Date for the Today's Earth imagery">
              <button type="button" id="globe-date-reset" title="Reset to today (UTC)">Today</button>
            </div>
            <label title="Sentinel-2 cloudless by EOX — CC BY-NC-SA 4.0: non-commercial use only">
              <input type="checkbox" data-layer="eox"><span>Sentinel-2 cloudless<em>EOX · CC BY-NC-SA (non-commercial)</em></span></label>
            <label title="Every geocoded row as a density heatmap — the pins step back while it is on">
              <input type="checkbox" data-layer="heat"><span>Density heatmap<em>every geocoded row · pins dimmed</em></span></label>
            <label title="Small synced map inset, bottom-left — same Esri imagery; click it to fly there">
              <input type="checkbox" data-layer="minimap"><span>Minimap inset<em>Esri imagery · viewport marker</em></span></label>
            <div class="globe-photo-row" id="globe-photo-row" title="Photo pins — real camera posters register as pin thumbnails above their dots: auto fades in from z9.5, on forces from z6, off hides them. A camera without a cached poster keeps its plain dot (lazy queue, ~300-image LRU).">
              <span class="gpr-name">Photo pins<em id="globe-photo-note">auto — from z9.5 · poster thumbs over the dots</em></span>
              <span class="seg seg-s" id="globe-photo-seg" role="group" aria-label="Photo pins mode">
                <button type="button" class="seg-btn" data-val="auto">Auto</button>
                <button type="button" class="seg-btn" data-val="on">On</button>
                <button type="button" class="seg-btn" data-val="off">Off</button>
              </span>
            </div>
            <div class="gpop-note">Attribution for every visible layer sits at the bottom-right:
              Esri imagery · NASA EOSDIS GIBS (public domain) · EOX Sentinel-2 (CC BY-NC-SA).</div>
          </div>
        </div>
        <button type="button" class="globe-here" id="globe-here" hidden title="Cameras in the current viewport"></button>
        <div class="globe-panel globe-here-list" id="globe-here-list" hidden></div>
        <div class="globe-tourbar" id="globe-tourbar" hidden></div>
        <div class="globe-mpanel" id="globe-mpanel" hidden>
          <button type="button" class="btn tiny" data-measure="clear">Clear</button>
          <button type="button" class="btn tiny ghost" data-measure="done">Done</button>
          <span class="gm-note">great-circle distances</span>
        </div>
        <div class="globe-mread" id="globe-mread" hidden></div>
        <div class="globe-mini" id="globe-mini" hidden>
          <div class="globe-mini-host" id="globe-mini-host"></div>
          <button type="button" class="globe-mini-x" id="globe-mini-x" title="Hide the minimap (re-enable it in the layers list)">&times;</button>
        </div>
        <div class="globe-legend collapsed" id="globe-legend" hidden>
          <button type="button" class="gl-hed" id="globe-legend-btn" title="Collapse / expand the legend (persisted as globe_legend)">
            <span>Legend</span><span class="gl-chev">${I.chev}</span>
          </button>
          <div class="gl-body" id="globe-legend-body">
            <div class="gl-row"><span class="gl-dot" style="background:var(--live)"></span>live</div>
            <div class="gl-row"><span class="gl-dot" style="background:var(--stale)"></span>stale</div>
            <div class="gl-row"><span class="gl-dot" style="background:var(--dead)"></span>dead</div>
            <div class="gl-row"><span class="gl-dot" style="background:var(--unknown)"></span>unknown</div>
            <div class="gl-row"><span class="gl-dot" style="background:var(--unverified)"></span>unverified (aggregator-listed)</div>
            <div class="gl-sep"></div>
            <div class="gl-share"><span class="gl-grad"><i class="gl-sw sw0"></i><i class="gl-sw sw1"></i><i class="gl-sw sw2"></i></span><span class="gl-note">cluster colour = live share</span></div>
          </div>
        </div>
        <div class="globe-pulse" id="globe-pulse" hidden></div>
        <div class="globe-hcard" id="globe-hcard" hidden></div>
        <div class="globe-area" id="globe-area" hidden aria-label="Area cameras panel">
          <div class="ga-head">
            <span class="ga-head-main">
              <span class="ga-title" id="globe-area-title">Area</span>
              <span class="ga-sub" id="globe-area-sub"></span>
            </span>
            <button type="button" class="xbtn ga-x" id="globe-area-x" title="Close (Esc)" data-pa="close">&times;</button>
          </div>
          <div class="ga-chips" id="globe-area-chips"></div>
          <div class="ga-acts" id="globe-area-acts"></div>
          <div class="ga-tools">
            <input type="search" id="globe-area-q" placeholder="filter by name in this area…" autocomplete="off" spellcheck="false" aria-label="Filter cameras in this area by name">
            <div class="ga-tools-row">
              <span class="seg seg-s" id="globe-area-sort" role="group" aria-label="Sort pane rows">
                <button type="button" class="seg-btn" data-val="name">Name</button>
                <button type="button" class="seg-btn" data-val="status">Status</button>
              </span>
              <span class="seg seg-s" id="globe-area-filter" role="group" aria-label="Filter pane rows by status">
                <button type="button" class="seg-btn" data-val="all">All</button>
                <button type="button" class="seg-btn" data-val="live">Live</button>
                <button type="button" class="seg-btn" data-val="stale">Stale</button>
              </span>
              <span class="ga-count" id="globe-area-count"></span>
            </div>
          </div>
          <div class="ga-list" id="globe-area-list"></div>
        </div>
        <div class="globe-loading" id="globe-loading">loading globe…</div>
      </div>
    </div>`;

    ui = {
      root,
      wrap: root.querySelector('#globe-wrap'),
      host: root.querySelector('#globe-host'),
      sub: root.querySelector('#globe-sub'),
      loading: root.querySelector('#globe-loading'),
      searchInput: root.querySelector('#globe-q'),
      results: root.querySelector('#globe-results'),
      qnote: root.querySelector('#globe-qnote'),
      layersBtn: root.querySelector('#globe-layers-btn'),
      rotateBtn: root.querySelector('#globe-rotate-btn'),
      randomBtn: root.querySelector('#globe-random-btn'),
      copyBtn: root.querySelector('#globe-copy-btn'),
      favBtn: root.querySelector('#globe-fav-btn'),
      vpWorld: root.querySelector('#globe-vp-world'),
      vpRegion: root.querySelector('#globe-vp-region'),
      vpCity: root.querySelector('#globe-vp-city'),
      pop: root.querySelector('#globe-pop'),
      here: root.querySelector('#globe-here'),
      hereList: root.querySelector('#globe-here-list'),
      termBtn: root.querySelector('#globe-terminator-btn'),
      tourBtn: root.querySelector('#globe-tour-btn'),
      measureBtn: root.querySelector('#globe-measure-btn'),
      dateWrap: root.querySelector('#globe-today-date'),
      dateInput: root.querySelector('#globe-date-input'),
      dateReset: root.querySelector('#globe-date-reset'),
      tourbar: root.querySelector('#globe-tourbar'),
      mpanel: root.querySelector('#globe-mpanel'),
      mread: root.querySelector('#globe-mread'),
      mini: root.querySelector('#globe-mini'),
      miniHost: root.querySelector('#globe-mini-host'),
      miniX: root.querySelector('#globe-mini-x'),
      legend: root.querySelector('#globe-legend'),
      legendBtn: root.querySelector('#globe-legend-btn'),
      legendBody: root.querySelector('#globe-legend-body'),
      pulse: root.querySelector('#globe-pulse'),
      hcard: root.querySelector('#globe-hcard'),
      area: root.querySelector('#globe-area'),
      areaTitle: root.querySelector('#globe-area-title'),
      areaSub: root.querySelector('#globe-area-sub'),
      areaChips: root.querySelector('#globe-area-chips'),
      areaActs: root.querySelector('#globe-area-acts'),
      areaQ: root.querySelector('#globe-area-q'),
      areaSort: root.querySelector('#globe-area-sort'),
      areaFilt: root.querySelector('#globe-area-filter'),
      areaCount: root.querySelector('#globe-area-count'),
      areaList: root.querySelector('#globe-area-list'),
      areaX: root.querySelector('#globe-area-x'),
      photoSeg: root.querySelector('#globe-photo-seg'),
      photoNote: root.querySelector('#globe-photo-note'),
    };

    // geometry lessons from the Leaflet view: the container must have a real box
    ui.host.style.setProperty('position', 'absolute', 'important');
    ui.host.style.setProperty('inset', '0', 'important');

    if (!hasWebGL2()) {
      renderFallback('3D globe requires WebGL2 — falling back to the flat Map view');
      return;
    }

    applyMinimap(!!store.settings.globe_minimap);          // persisted, default ON; lazily created
    if (store.settings.globe_terminator) setTerminator(true);   // re-arm the 60 s refresh
    ui.legend.hidden = false;                              // the legend box is part of the view
    setLegendExpanded(store.settings.globe_legend !== false);
    applyPhotoPinsSetting();                               // photo-pin mode before the style is built

    loadLib().then((ml) => {
      if (destroyed) return;
      M = ml;
      buildMap();
      wireOverlays();
    }).catch((err) => {
      if (destroyed) return;
      if (window.__globe) window.__globe.errors.push('lib: ' + (err.message || err));
      renderFallback('map library failed to load — ' + (err.message || err));
    });
  },
  refresh() {
    applyFilters();
    scheduleHere();
    schedulePulse();
    updateQNote();
    syncToolbar();
    if (map && !destroyed) { try { map.resize(); } catch (err) { /* noop */ } }
    if (miniMap) { try { miniMap.invalidateSize(); } catch (err) { /* noop */ } }
    scheduleMini();
  },
  destroy() {
    destroyed = true;
    cleanup();
  },
};

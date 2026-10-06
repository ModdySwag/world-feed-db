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
 * dimmed), VIIRS true colour ("today's Earth", date-pinned to the current UTC
 * day) and EOX Sentinel-2 cloudless (CC BY-NC-SA, off by default).
 *
 * Settings keys (all via saveSettings, all prefs-persisted):
 *   globe_labels · globe_night · globe_today · globe_eox · globe_autorotate · globe_favonly
 */
import {
  store, bus, apiGet, esc, fmt, toast, saveSettings, openDrawer, openPlayerModal,
  toggleFavourite, isFav, copyText, go, viewLink, statusChipHTML,
  rememberCamera, clamp,
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
  const today = new Date().toISOString().slice(0, 10);        // UTC day for GIBS
  const vis = (key) => (store.settings[key] ? 'visible' : 'none');
  return {
    version: 8,
    glyphs: GLYPHS,
    sky: { 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 3, 0.5, 7, 0] },
    sources: {
      esri: {
        type: 'raster', tileSize: 256, maxzoom: 19,
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
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
        tiles: [GIBS + 'VIIRS_SNPP_CorrectedReflectance_TrueColor/default/' + today
          + '/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg'],
        attribution: 'Today: NASA EOSDIS GIBS — VIIRS true colour ' + today + ' (public domain)',
      },
      eox: {
        type: 'raster', tileSize: 256, maxzoom: 16,
        tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'],
        attribution: 'Sentinel-2 cloudless by EOX (CC BY-NC-SA 4.0)',
      },
      cams: {
        type: 'geojson', data: EMPTY_FC,
        cluster: true, clusterRadius: 55, clusterMaxZoom: 12, clusterMinPoints: 2,
      },
      focus: { type: 'geojson', data: EMPTY_FC },
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
      { id: 'globe-focus', type: 'circle', source: 'focus', paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 10, 9, 22],
        'circle-color': 'rgba(45,212,191,.14)', 'circle-stroke-width': 2.5,
        'circle-stroke-color': '#2dd4bf',
      } },
      { id: 'globe-clusters', type: 'circle', source: 'cams', filter: ['has', 'point_count'],
        paint: {
          'circle-color': ['step', ['get', 'point_count'], '#22d3ee', 100, '#facc15', 750, '#f472b6'],
          'circle-radius': ['step', ['get', 'point_count'], 12, 100, 17, 750, 23],
          'circle-opacity': 0.85, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff',
        } },
      { id: 'globe-cluster-count', type: 'symbol', source: 'cams', filter: ['has', 'point_count'],
        layout: { 'text-field': '{point_count_abbreviated}', 'text-font': ['Noto Sans Regular'],
          'text-size': 11 },
        paint: { 'text-color': '#04121a' } },
      { id: 'globe-points', type: 'circle', source: 'cams', filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': PIN_COLOR, 'circle-radius': 4,
          'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff',
        } },
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
  const n = (fc.features || []).length;
  if (window.__globe) window.__globe.points = n;
  if (ui.loading) ui.loading.hidden = true;
  if (ui.sub) ui.sub.textContent = `${fmt(n)} geocoded rows · clustered pins · imagery: Esri + NASA GIBS`;
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
  const points = expr ? ['all', ['!', ['has', 'point_count']], expr]
    : ['!', ['has', 'point_count']];
  try {
    map.setFilter('globe-clusters', cluster);
    map.setFilter('globe-cluster-count', cluster);
    map.setFilter('globe-points', points);
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
  const start = readHashState() || WORLD_VIEW;
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
  map.on('moveend', () => { scheduleHash(); scheduleHere(); updateDebugCounts(); });
  map.on('idle', updateDebugCounts);
  map.on('click', 'globe-clusters', onClusterClick);
  map.on('click', 'globe-points', onPointClick);
  map.on('dblclick', 'globe-points', onPointDbl);
  map.on('mousemove', 'globe-points', onPointMove);
  map.on('mouseleave', 'globe-points', onPointLeave);
  map.on('mouseenter', 'globe-points', () => setCursor('pointer'));
  map.on('mouseenter', 'globe-clusters', () => setCursor('pointer'));
  map.on('mouseleave', 'globe-clusters', () => setCursor(''));

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
  }
  applyFilters();
  if (pointsCache) pushPoints(pointsCache);
  writeHash();                                  // router's syncHash drops lat/lng — put them back
  updateDebugCounts();
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
  const f = ev.features && ev.features[0];
  if (!f || f.properties.cluster_id == null) return;
  const src = map && map.getSource('cams');
  if (!src) return;
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
  const f = ev.features && ev.features[0];
  if (!f) return;
  if (hoverPopup) { hoverPopup.remove(); hoverPopup = null; }
  openPointPopup(f.properties, f.geometry.coordinates);
}

function onPointDbl(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  if (isExposure(f.properties)) {
    toast('Metadata only — exposure rows are never previewed', { type: 'info' });
    return;
  }
  openPlayerFor(f.properties.c);
}

function onPointMove(ev) {
  const f = ev.features && ev.features[0];
  if (!f) return;
  hoverLatLng = f.geometry ? f.geometry.coordinates : ev.lngLat;
  const id = f.properties.c;
  if (id === hoverId) {
    if (hoverPopup) hoverPopup.setLngLat(hoverLatLng);
    return;
  }
  hoverId = id;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => {
    if (destroyed || !map || !M) return;
    if (hoverPopup) hoverPopup.remove();
    hoverPopup = new M.Popup({ closeButton: false, closeOnClick: false, offset: 10,
      className: 'wfd-gtip' })
      .setLngLat(hoverLatLng)
      .setHTML(`<span class="gtip-name">${esc(f.properties.n || hoverId || '')}</span>`)
      .addTo(map);
  }, 300);                                       // 300 ms dwell before the name tooltip shows
}

function onPointLeave() {
  hoverId = null;
  clearTimeout(hoverTimer);
  hoverTimer = null;
  if (hoverPopup) { hoverPopup.remove(); hoverPopup = null; }
  setCursor('');
}

function updateDebugCounts() {
  if (!map || !styleReady || !window.__globe) return;
  try {
    window.__globe.clusters = map.queryRenderedFeatures({ layers: ['globe-clusters'] }).length;
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
    // ~0.12°/s idle drift; pauses on any input, resumes after 20 s idle
    if (store.settings.globe_autorotate && !document.hidden
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
  if (ui.pop) {
    ui.pop.querySelectorAll('[data-layer]').forEach((cb) => {
      cb.checked = !!store.settings['globe_' + cb.dataset.layer];
    });
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
        const layerId = LAYER_KEYS[key];
        if (map && styleReady && layerId) {
          try { map.setLayoutProperty(layerId, 'visibility', cb.checked ? 'visible' : 'none'); }
          catch (err) { /* style not ready — the rebuilt style picks it up */ }
        }
        playSound('toggle');
      });
    });
  }
  if (ui.rotateBtn) ui.rotateBtn.addEventListener('click', toggleRotate);
  if (ui.randomBtn) ui.randomBtn.addEventListener('click', () => randomLive());
  if (ui.copyBtn) {
    ui.copyBtn.addEventListener('click', () => {
      writeHash();
      copyText(location.href).then(() => toast('View link copied', { type: 'ok' }));
    });
  }
  if (ui.favBtn) ui.favBtn.addEventListener('click', toggleFavOnly);
  if (ui.here) ui.here.addEventListener('click', toggleHereList);
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
      window.__globe = { ready: false, points: 0, clusters: 0, fps: 0, projection: '', errors: [] };
    }
    window.__globe.ready = false;
    window.__globe.projection = '';
    const today = new Date().toISOString().slice(0, 10);
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
          <button type="button" class="btn small icon-only" id="globe-layers-btn" title="Imagery layers">${I.layers}</button>
          <button type="button" class="btn small icon-only" id="globe-rotate-btn" title="Idle auto-rotate (off)">${I.rotate}</button>
          <button type="button" class="btn small icon-only" id="globe-random-btn" title="Random live cam (r while the globe has focus)">${I.dice}</button>
          <button type="button" class="btn small icon-only" id="globe-copy-btn" title="Copy a link to this exact view">${I.copy}</button>
          <button type="button" class="btn small icon-only" id="globe-fav-btn" title="Show favourites only">${I.star}</button>
          <div class="globe-pop" id="globe-pop" hidden>
            <label title="NASA EOSDIS GIBS — Reference Labels (public domain)">
              <input type="checkbox" data-layer="labels"><span>Labels<em>GIBS Reference_Labels</em></span></label>
            <label title="NASA EOSDIS GIBS — VIIRS Black Marble (public domain)">
              <input type="checkbox" data-layer="night"><span>Night lights<em>VIIRS Black Marble · dimmed</em></span></label>
            <label title="NASA EOSDIS GIBS — VIIRS true colour for ${today} UTC (public domain)">
              <input type="checkbox" data-layer="today"><span>Today's Earth<em>VIIRS true colour · ${today}</em></span></label>
            <label title="Sentinel-2 cloudless by EOX — CC BY-NC-SA 4.0: non-commercial use only">
              <input type="checkbox" data-layer="eox"><span>Sentinel-2 cloudless<em>EOX · CC BY-NC-SA (non-commercial)</em></span></label>
            <div class="gpop-note">Attribution for every visible layer sits at the bottom-right:
              Esri imagery · NASA EOSDIS GIBS (public domain) · EOX Sentinel-2 (CC BY-NC-SA).</div>
          </div>
        </div>
        <button type="button" class="globe-here" id="globe-here" hidden title="Cameras in the current viewport"></button>
        <div class="globe-panel globe-here-list" id="globe-here-list" hidden></div>
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
      pop: root.querySelector('#globe-pop'),
      here: root.querySelector('#globe-here'),
      hereList: root.querySelector('#globe-here-list'),
    };

    // geometry lessons from the Leaflet view: the container must have a real box
    ui.host.style.setProperty('position', 'absolute', 'important');
    ui.host.style.setProperty('inset', '0', 'important');

    if (!hasWebGL2()) {
      renderFallback('3D globe requires WebGL2 — falling back to the flat Map view');
      return;
    }

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
    updateQNote();
    syncToolbar();
    if (map && !destroyed) { try { map.resize(); } catch (err) { /* noop */ } }
  },
  destroy() {
    destroyed = true;
    cleanup();
  },
};

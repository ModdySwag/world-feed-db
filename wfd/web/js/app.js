/* wfd/web/js/app.js — world-feed-db viewer core (v0.3).
 *
 * Holds: the state store, hash router, API client (GET + hardened POST),
 * menu bar, command palette, settings, toasts, keyboard, drawer, player modal,
 * sidebar/facets, status bar. Views live in views.js; players in player.js.
 *
 * The app talks ONLY to the local API (/api/*) + vendored assets; the only
 * external requests are feed hosts, YouTube thumbnails/embeds and (when the
 * map-tiles setting is ON) OSM tiles.
 */
import { VIEWS, HELP_SECTIONS } from './views.js';
import { createPlayer, LiveBudget } from './player.js';
import {
  playSound, soundGestureHook, setSoundEnabled, setSoundVolume, setSoundReducedMotion,
} from './sound.js';

/* ══ constants ══════════════════════════════════════════════════════════ */

export const VERSION = 'v0.3';

const STATUS_ORDER = ['live', 'stale', 'dead', 'unknown', 'unverified'];
const STATUS_HINT = {
  live: 'registry health check last found this feed live',
  stale: 'registry health check found the feed not updating',
  dead: 'registry health check found this feed dead',
  unknown: 'enumerated, not yet health-checked',
  unverified: 'listed in an aggregator snapshot — never verified',
};

export const VIEW_ORDER = ['overview', 'map', 'globe', 'wall', 'watch', 'search', 'personal', 'help'];

const PROV_LABEL = { public: 'Public', directory: 'Directory', exposure: 'Exposure', all: 'All' };

export const DEFAULT_SETTINGS = {
  sound_on: true,
  sound_volume: 0.35,
  reduced_motion: 'auto',          // auto | on | off
  default_view: 'last',            // last | <view id>
  tile_size: 'md',                 // sm | md | lg
  still_refresh_s: 30,
  live_previews: false,
  max_live_tiles: 4,
  map_tiles: true,
  globe_labels: false,             // World Map: GIBS Reference_Labels overlay
  globe_night: false,              // World Map: VIIRS Black Marble (night lights)
  globe_today: false,              // World Map: VIIRS true colour (today, UTC)
  globe_today_date: '',            // World Map: date for the VIIRS layer ('' -> today, UTC)
  globe_eox: false,                // World Map: EOX Sentinel-2 cloudless (CC BY-NC-SA)
  globe_terminator: true,          // World Map: day/night terminator (visual cue only; default ON)
  globe_heat: false,               // World Map: density heatmap of the geocoded rows
  globe_minimap: true,             // World Map: minimap inset (bottom-left)
  globe_autorotate: true,          // World Map: idle auto-rotate (default ON — livelier world view)
  globe_favonly: false,            // World Map: pins limited to favourites
  globe_legend: true,              // World Map: legend expanded (status dots + cluster live-share ramp)
  results_per_page: 60,
  accent: 'teal',                  // teal | violet | amber
  sidebar_open: true,
  watch_stage: [],
  watch_layout: '2x2',             // 1x1 | 2x2 | 3x3
  last_view: 'overview',
};

const DEFAULT_FILTERS = {
  provenance: 'public',
  status: [], family: [], country: [], protocol: [], tag: [],
  q: '', bbox: null,               // bbox: "west,south,east,north" (pinned by "Search this area")
  sort: 'name', order: 'asc',
};

/* ══ icons (inline SVG only) ═══════════════════════════════════════════ */

export const ICONS = {
  heart: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
  play: '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  stage: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  info: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
  open: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>',
  copy: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  x: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  warn: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  sound: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="currentColor" stroke="none"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>',
  soundOff: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="currentColor" stroke="none"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>',
  command: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3"/></svg>',
  link: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  download: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  star: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  shield: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>',
  chevron: '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  camera: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
};

/* ══ store + bus ═══════════════════════════════════════════════════════ */

export const store = {
  stats: null,
  overview: null,
  facets: null,
  prefs: { favourites: [], favourite_ids: [], settings: {}, updated_at: '' },
  favIds: new Set(),
  settings: { ...DEFAULT_SETTINGS },
  exposureEnabled: false,
  filters: { ...DEFAULT_FILTERS, status: [], family: [], country: [], protocol: [], tag: [] },
  route: { view: null },
  selectedId: null,
  camerasById: new Map(),     // last-seen camera rows (features + details)
  ui: { busy: false },
};

export const bus = {
  _m: new Map(),
  on(evt, fn) {
    if (!this._m.has(evt)) this._m.set(evt, new Set());
    this._m.get(evt).add(fn);
    return () => this.off(evt, fn);
  },
  off(evt, fn) { const s = this._m.get(evt); if (s) s.delete(fn); },
  emit(evt, data) {
    const s = this._m.get(evt);
    if (!s) return;
    for (const fn of [...s]) { try { fn(data); } catch (err) { console.error(err); } }
  },
};

/* ══ tiny helpers ══════════════════════════════════════════════════════ */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
export function el(tag, cls, html) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html != null) node.innerHTML = html;
  return node;
}
export const fmt = (n) => Number(n || 0).toLocaleString('en-US');
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
export function timeHM(d = new Date()) {
  const p = (x) => (x < 10 ? '0' : '') + x;
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function downloadFile(name, text, mime) {
  const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 400);
}

export function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(() => legacyCopy(text));
  }
  legacyCopy(text);
  return Promise.resolve();
}
function legacyCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (err) { /* noop */ }
  ta.remove();
}

export function reduced() {
  const s = store.settings.reduced_motion;
  if (s === 'on') return true;
  if (s === 'off') return false;
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* ══ API client ════════════════════════════════════════════════════════ */

let apiOk = null;          // null=connecting, true, false
let lastApiError = '';

function setApiState(ok, message) {
  apiOk = ok;
  if (message) lastApiError = message;
  const dot = $('#sb-health');
  if (!dot) return;
  dot.className = 'sb-dot ' + (ok === null ? 'busy' : ok ? 'ok' : 'err');
  dot.title = ok === null ? 'connecting to the local API…'
    : ok ? `local API healthy — last call OK (${timeHM()})`
      : `local API unreachable — ${lastApiError}`;
}

export async function apiGet(path, params) {
  const u = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params || {})) {
    if (v == null || v === '') continue;
    u.searchParams.set(k, String(v));
  }
  let res;
  try {
    res = await fetch(u, { headers: { Accept: 'application/json' } });
  } catch (err) {
    setApiState(false, err.message || 'network error');
    throw new Error('API unreachable — is the viewer server running?');
  }
  if (!res.ok) {
    let msg = 'HTTP ' + res.status;
    try { const j = await res.json(); if (j && j.error) msg = j.error; } catch (err) { /* noop */ }
    setApiState(false, msg);
    const e = new Error(msg);
    e.status = res.status;
    throw e;
  }
  setApiState(true);
  return res.json();
}

export async function apiPost(path, body) {
  setPrefsState('saving');
  let res;
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-WFD-Viewer': '1' },
      body: JSON.stringify(body || {}),
    });
  } catch (err) {
    setPrefsState('error', err.message);
    throw new Error('API unreachable — is the viewer server running?');
  }
  let data = null;
  try { data = await res.json(); } catch (err) { /* noop */ }
  if (!res.ok) {
    const msg = (data && data.error) || ('HTTP ' + res.status);
    setPrefsState('error', msg);
    throw new Error(msg);
  }
  setApiState(true);
  setPrefsState('saved');
  return data;
}

/* ══ prefs (favourites + settings) ═════════════════════════════════════ */

let prefsState = 'idle';
function setPrefsState(state, message) {
  prefsState = state;
  const elx = $('#sb-prefs');
  if (!elx) return;
  const cls = state === 'error' ? 'err' : state === 'saving' ? 'busy' : state === 'saved' ? 'ok' : '';
  elx.className = 'sb-item sb-prefs ' + cls;
  elx.textContent = state === 'saving' ? 'prefs · saving…'
    : state === 'saved' ? 'prefs · saved ' + timeHM()
      : state === 'error' ? 'prefs · save failed'
        : 'prefs';
  elx.title = state === 'error' ? 'preference save failed: ' + (message || 'unknown error')
    : 'favourites + settings persist in data/viewer-prefs.json';
}

export function applyPrefs() {
  const s = { ...DEFAULT_SETTINGS, ...(store.prefs.settings || {}) };
  store.settings = s;
  store.favIds = new Set(store.prefs.favourite_ids || []);
  applySettingsAttrs();
  LiveBudget.setCap(clamp(Number(s.max_live_tiles) || 4, 1, 9));
  updateFavCount();
  bus.emit('prefs');
}

export function applySettingsAttrs() {
  const s = store.settings;
  const html = document.documentElement;
  html.dataset.accent = ['teal', 'violet', 'amber'].includes(s.accent) ? s.accent : 'teal';
  html.dataset.tile = ['sm', 'md', 'lg'].includes(s.tile_size) ? s.tile_size : 'md';
  const red = reduced();
  html.dataset.motion = red ? 'reduced' : 'full';
  setSoundEnabled(!!s.sound_on);
  setSoundVolume(Number(s.sound_volume) || 0.35);
  setSoundReducedMotion(red);
  document.body.classList.toggle('sidebar-closed', !s.sidebar_open);
  updateSoundButton();
}

export function saveSettings(patch) {
  Object.assign(store.settings, patch);
  applySettingsAttrs();
  queueSettingsSave(patch);
  bus.emit('settings', patch);
}

let settingsQueue = {};
let settingsTimer = null;
function queueSettingsSave(patch) {
  settingsQueue = { ...settingsQueue, ...patch };
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(flushSettings, 250);
}
async function flushSettings() {
  const patch = settingsQueue;
  settingsQueue = {};
  if (!Object.keys(patch).length) return;
  try {
    const res = await apiPost('/api/prefs/settings', { settings: patch });
    store.prefs = res;
    // keep derived sets in sync (favIds unchanged by settings, but harmless)
    store.favIds = new Set(res.favourite_ids || []);
  } catch (err) {
    settingsQueue = { ...patch, ...settingsQueue };   // retry on next change
    toast('Could not save settings — ' + err.message, { type: 'err' });
    playSound('error');
  }
}

export function isFav(cid) { return store.favIds.has(cid); }

export async function toggleFavourite(cid) {
  if (!cid) return;
  const had = store.favIds.has(cid);
  // optimistic
  if (had) store.favIds.delete(cid); else store.favIds.add(cid);
  updateFavCount();
  bus.emit('prefs');
  playSound(had ? 'fav_remove' : 'fav_add');
  try {
    const res = await apiPost('/api/prefs/favourite', { camera_id: cid, action: had ? 'remove' : 'add' });
    store.prefs = res;
    store.favIds = new Set(res.favourite_ids || []);
    updateFavCount();
    bus.emit('prefs');
    toast(had ? 'Removed from favourites' : 'Added to favourites', {
      type: had ? 'info' : 'ok',
      actions: had ? [] : [{ label: 'Personal', run: () => go('personal') }],
    });
  } catch (err) {
    if (had) store.favIds.add(cid); else store.favIds.delete(cid);
    updateFavCount();
    bus.emit('prefs');
    toast('Favourite update failed — ' + err.message, { type: 'err' });
  }
}

export async function labelFavourite(cid, label) {
  const res = await apiPost('/api/prefs/favourite', { camera_id: cid, action: 'label', label: String(label || '') });
  store.prefs = res;
  bus.emit('prefs');
  return res;
}

export async function reorderFavourites(order) {
  const res = await apiPost('/api/prefs/reorder', { order });
  store.prefs = res;
  bus.emit('prefs');
  return res;
}

export async function loadPrefs() {
  try {
    store.prefs = await apiGet('/api/prefs');
    applyPrefs();
    setPrefsState('idle');
  } catch (err) {
    setPrefsState('error', err.message);
    toast('Could not load preferences — ' + err.message, { type: 'err' });
  }
}

function updateFavCount() {
  const n = store.favIds.size;
  const elx = $('#fav-count');
  if (elx) elx.textContent = String(n);
  const btn = $('#btn-favs');
  if (btn) btn.classList.toggle('has', n > 0);
}

/* ══ stage helpers ═════════════════════════════════════════════════════ */

export function stagedIds() {
  const v = store.settings.watch_stage;
  return Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x) : [];
}

export function addToStage(cid) {
  if (!cid) return false;
  const cur = stagedIds().slice();
  if (cur.includes(cid)) { toast('Already on the Watch stage', { type: 'info' }); return false; }
  if (cur.length >= 9) { toast('Watch stage is full (9 slots) — remove one first', { type: 'err' }); playSound('error'); return false; }
  cur.push(cid);
  saveSettings({ watch_stage: cur });
  const cam = store.camerasById.get(cid);
  toast('Staged' + (cam && cam.name ? ` “${cam.name}”` : '') + ` — Watch has ${cur.length} slot${cur.length === 1 ? '' : 's'}`, {
    type: 'ok',
    actions: [{ label: 'Open Watch', run: () => go('watch') }],
  });
  playSound('fav_add');
  bus.emit('stage');
  return true;
}

export function removeFromStage(cid) {
  saveSettings({ watch_stage: stagedIds().filter((x) => x !== cid) });
  bus.emit('stage');
}

export function addManyToStage(ids) {
  const cur = stagedIds().slice();
  let added = 0; let skipped = 0;
  for (const id of ids || []) {
    if (!id || cur.includes(id)) { skipped++; continue; }
    if (cur.length >= 9) { skipped++; continue; }
    cur.push(id); added++;
  }
  if (added) {
    saveSettings({ watch_stage: cur });
    bus.emit('stage');
    playSound('success');
    toast(`Added ${added} to the Watch stage${skipped ? ` (${skipped} skipped — already staged or stage full)` : ''}`, {
      type: 'ok',
      actions: [{ action: true, label: 'Open Watch', run: () => go('watch') }],
    });
  } else {
    toast('Nothing added — already staged or stage full', { type: 'info' });
  }
  return { added, skipped };
}

/* ══ filters ═══════════════════════════════════════════════════════════ */

export function anyFiltersActive() {
  const f = store.filters;
  return f.provenance !== 'public' || f.status.length || f.family.length || f.country.length
    || f.protocol.length || f.tag.length || !!f.q || !!f.bbox;
}

export function filterParams(opts = {}) {
  const excl = opts.exclude || [];
  const f = store.filters;
  const has = (d) => !excl.includes(d);
  const p = { geo: 'any' };
  if (has('provenance')) p.provenance = f.provenance || 'public';
  if (has('status') && f.status.length) p.status = f.status.join(',');
  if (has('family') && f.family.length) p.family = f.family.join(',');
  if (has('country') && f.country.length) p.country = f.country.join(',');
  if (has('protocol') && f.protocol.length) p.protocol = f.protocol.join(',');
  if (has('tag') && f.tag.length) p.tag = f.tag.join(',');
  if (has('q') && f.q) p.q = f.q;
  if (has('bbox') && f.bbox) p.bbox = f.bbox;
  return p;
}

export function setFilters(patch) {
  Object.assign(store.filters, patch);
  bus.emit('filters');
  syncHash();
  renderChips();
  updateStatusbar();
  fetchFacets();
}

export function resetFilters() {
  store.filters = { ...DEFAULT_FILTERS, status: [], family: [], country: [], protocol: [], tag: [] };
  bus.emit('filters');
  syncHash();
  renderChips();
  updateStatusbar();
  fetchFacets();
  toast('Filters cleared', { type: 'info' });
  playSound('toggle');
}

export function toggleFacet(dim, value) {
  const arr = (store.filters[dim] || []).slice();
  const i = arr.indexOf(value);
  if (i >= 0) arr.splice(i, 1); else arr.push(value);
  setFilters({ [dim]: arr });
  playSound('toggle');
}

export function setProvenance(v) {
  if (v === 'exposure' && !store.exposureEnabled) return;
  setFilters({ provenance: v });
  playSound('toggle');
}

/* ── facets (sidebar counts + result totals) ─────────────────────────── */

const FACET_DIMS = ['status', 'family', 'country', 'protocol', 'tag'];
let facetSeq = 0;

export async function fetchFacets() {
  const seq = ++facetSeq;
  const base = filterParams();
  try {
    const main = await apiGet('/api/facets', base);
    if (seq !== facetSeq) return;
    const extra = {};
    const active = FACET_DIMS.filter((d) => store.filters[d].length);
    await Promise.all(active.map(async (d) => {
      try {
        const res = await apiGet('/api/facets', filterParams({ exclude: [d] }));
        extra[d] = res;
      } catch (err) { /* keep main counts for that dim */ }
    }));
    if (seq !== facetSeq) return;
    store.facets = main;
    store.facetsSelf = extra;
    renderSidebar();
    bus.emit('facets');
    updateStatusbar();
  } catch (err) {
    if (seq !== facetSeq) return;
    const box = $('#sidebar-sections');
    if (box && !store.facets) {
      box.innerHTML = `<div class="side-err">facets unavailable — ${esc(err.message)}</div>`;
    }
  }
}

/* ══ stats ═════════════════════════════════════════════════════════════ */

export async function fetchStats() {
  try {
    const s = await apiGet('/api/stats');
    store.stats = s;
    store.exposureEnabled = !!s.exposure_enabled;
    updateTopbar();
    updateStatusbar();
    bus.emit('stats');
  } catch (err) {
    updateTopbar();
    updateStatusbar();
  }
}

function updateTopbar() {
  const elx = $('#topbar-total');
  if (!elx) return;
  const s = store.stats;
  elx.textContent = s ? fmt(s.total) + ' rows' : '—';
  elx.title = s ? `registry rows (as of ${s.generated_at})` : 'stats unavailable';
}

/* ══ status bar ════════════════════════════════════════════════════════ */

export function updateStatusbar() {
  const s = store.stats;
  const f = store.filters;

  const tot = $('#sb-total');
  if (tot) {
    if (s) {
      const shown = store.facets ? store.facets.total : null;
      tot.textContent = `${fmt(s.total)} rows${shown != null && shown !== s.total ? ` · ${fmt(shown)} in filter` : ''}`;
      tot.title = `registry total ${fmt(s.total)} · as of ${s.generated_at}`;
    } else {
      tot.textContent = '— rows';
      tot.title = 'stats unavailable';
    }
  }

  const gate = $('#sb-gate');
  if (gate && s) {
    const expDefault = (s.by_provenance || {}).exposure_aggregator || 0;
    if (s.exposure_enabled) {
      gate.textContent = `exposure surface ON · ${fmt(expDefault)} metadata-only`;
      gate.className = 'sb-item sb-gate on';
      gate.title = 'the private exposure surface is ON: exposure_aggregator rows are served as metadata only — never previewed';
    } else {
      gate.textContent = 'exposure surface OFF — clean';
      gate.className = 'sb-item sb-gate off';
      gate.title = 'the private exposure surface is OFF: exposure rows are excluded from every response';
    }
  }

  const fs = $('#sb-filters');
  if (fs) {
    const parts = [];
    parts.push(PROV_LABEL[f.provenance] || f.provenance);
    if (f.status.length) parts.push('status: ' + f.status.join(', '));
    if (f.family.length) parts.push('family: ' + f.family.join(', '));
    if (f.country.length) parts.push('country: ' + f.country.join(', '));
    if (f.protocol.length) parts.push('protocol: ' + f.protocol.join(', '));
    if (f.tag.length) parts.push('tag: ' + f.tag.join(', '));
    if (f.q) parts.push(`q “${f.q}”`);
    if (f.bbox) parts.push('area (map)');
    fs.textContent = parts.join(' · ');
    fs.title = fs.textContent;
  }
}

/* ══ sidebar (chips + facet sections) ══════════════════════════════════ */

let familyMore = false;
let countryMore = false;
let tagMore = false;
let countryQuery = '';

export function renderChips() {
  const box = $('#sidebar-chips');
  if (!box) return;
  const f = store.filters;
  const chips = [];
  const chip = (dim, val, label) => `<button type="button" class="chipx" data-dim="${esc(dim)}" data-val="${esc(val)}" title="remove filter">${esc(label)}<span class="x">×</span></button>`;
  if (f.provenance !== 'public') {
    chips.push(`<button type="button" class="chipx" data-dim="provenance" data-val="public" title="reset to Public (default)">provenance: ${esc(PROV_LABEL[f.provenance] || f.provenance)}<span class="x">×</span></button>`);
  }
  for (const d of ['status', 'family', 'country', 'protocol', 'tag']) {
    for (const v of f[d]) chips.push(chip(d, v, `${d === 'family' ? 'family' : d}: ${v}`));
  }
  if (f.q) chips.push(`<button type="button" class="chipx" data-dim="q" data-val="" title="clear search">q: “${esc(f.q)}”<span class="x">×</span></button>`);
  if (f.bbox) chips.push(`<button type="button" class="chipx" data-dim="bbox" data-val="" title="clear area filter">area: map pin<span class="x">×</span></button>`);
  if (!chips.length) {
    box.innerHTML = '<span class="side-note">no filters — showing Public rows</span>';
    return;
  }
  box.innerHTML = chips.join('') + `<button type="button" class="chipx clear" data-dim="__all" title="clear every filter">clear all</button>`;
}

function facetRows(entries, dim, selected, { pinned = 0 } = {}) {
  const on = new Set(selected);
  return entries.map(([val, n]) => {
    const isOn = on.has(val);
    return `<button type="button" class="facet${isOn ? ' on' : ''}" data-dim="${esc(dim)}" data-val="${esc(val)}" title="${esc(val)} — ${fmt(n)} row${n === 1 ? '' : 's'}">
      <span class="fc-name">${esc(val)}</span><span class="fc-count">${fmt(n)}</span></button>`;
  }).join('');
}

export function renderSidebar() {
  renderChips();
  const box = $('#sidebar-sections');
  if (!box) return;
  const fac = store.facets;
  const self = store.facetsSelf || {};
  const f = store.filters;

  if (!fac) {
    box.innerHTML = '<div class="side-skel"><div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div></div>';
    return;
  }

  const sect = [];

  /* Status */
  {
    const counts = f.status.length && self.status ? self.status.by_status : fac.by_status || {};
    const keys = [...STATUS_ORDER];
    for (const k of Object.keys(counts)) if (!keys.includes(k)) keys.push(k);
    const rows = keys.map((k) => {
      const n = counts[k] || 0;
      const isOn = f.status.includes(k);
      if (!n && !isOn) return '';
      return `<button type="button" class="facet st-row${isOn ? ' on' : ''}" data-dim="status" data-val="${esc(k)}" title="${esc(STATUS_HINT[k] || k)}">
        <span class="dot" style="background:var(--${k === 'unverified' ? 'unverified' : k})"></span><span class="fc-name">${esc(k)}</span><span class="fc-count">${fmt(n)}</span></button>`;
    }).join('');
    sect.push(sideSection('Status', rows));
  }

  /* Provenance (radio semantics) */
  {
    const pv = (k) => {
      const raw = fac.by_provenance || {};
      if (k === 'public') return (raw.public_by_design || 0) + (raw.aggregator_directory || 0);
      if (k === 'directory') return raw.aggregator_directory || 0;
      if (k === 'exposure') return raw.exposure_aggregator || 0;
      return fac.total || 0;
    };
    let rows = '';
    for (const k of ['public', 'directory', 'exposure', 'all']) {
      if (k === 'exposure' && !store.exposureEnabled) continue;
      const on = f.provenance === k;
      const count = k === 'all' ? fac.total : pv(k);
      rows += `<button type="button" class="facet${on ? ' on' : ''}" data-dim="provenance" data-val="${k}" title="${esc(PROV_LABEL[k])}">
        <span class="fc-name">${esc(PROV_LABEL[k])}</span><span class="fc-count">${fmt(count)}</span></button>`;
    }
    sect.push(sideSection('Provenance', rows));
  }

  /* Family */
  {
    const counts = f.family.length && self.family ? self.family.by_family : fac.by_family || {};
    const entries = Object.entries(counts).map(([k, v]) => [k, v])
      .sort((a, b) => b[1] - a[1]);
    const selected = f.family;
    const limit = familyMore ? entries.length : 15;
    let rows = facetRows(entries.slice(0, limit), 'family', selected);
    // selected values not in the visible slice stay visible (pinned at top not needed here — they appear if in entries)
    const missing = selected.filter((v) => !entries.slice(0, limit).some(([k]) => k === v));
    rows = missing.map((v) => facetRows([[v, counts[v] || 0]], 'family', selected)).join('') + rows;
    if (entries.length > 15) {
      rows += `<button type="button" class="facet-more" data-more="family">${familyMore ? '− less' : `+ ${entries.length - 15} more`}</button>`;
    }
    sect.push(sideSection('Family', rows));
  }

  /* Country */
  {
    const counts = f.country.length && self.country ? self.country.by_country : fac.by_country || {};
    let entries = Object.entries(counts).filter(([k]) => !countryQuery || k.toLowerCase().includes(countryQuery));
    entries.sort((a, b) => b[1] - a[1]);
    const selected = f.country;
    const limit = countryMore ? entries.length : 20;
    const visible = entries.slice(0, limit);
    const missing = selected.filter((v) => !visible.some(([k]) => k === v));
    let rows = `<input type="search" class="side-search" id="country-q" placeholder="filter countries…" value="${esc(countryQuery)}">`;
    rows += missing.map((v) => facetRows([[v, counts[v] || 0]], 'country', selected)).join('');
    rows += facetRows(visible, 'country', selected);
    if (entries.length > 20 && !countryQuery) {
      rows += `<button type="button" class="facet-more" data-more="country">${countryMore ? '− less' : `+ ${entries.length - 20} more`}</button>`;
    }
    sect.push(sideSection('Country', rows));
  }

  /* Protocol */
  {
    const counts = f.protocol.length && self.protocol ? self.protocol.by_protocol : fac.by_protocol || {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    sect.push(sideSection('Protocol', facetRows(entries, 'protocol', f.protocol)));
  }

  /* Tags */
  {
    const counts = f.tag.length && self.tag ? self.tag.by_tag : fac.by_tag || {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const limit = tagMore ? entries.length : 20;
    const rows = facetRows(entries.slice(0, limit), 'tag', f.tag)
      + (entries.length > 20 ? `<button type="button" class="facet-more" data-more="tag">${tagMore ? '− less' : `+ ${entries.length - 20} more`}</button>` : '');
    sect.push(sideSection('Tags', rows));
  }

  box.innerHTML = sect.join('');
}

function sideSection(title, rows) {
  return `<section class="side-sec"><h3>${esc(title)}</h3><div class="side-rows">${rows}</div></section>`;
}

/* sidebar interactions (delegated, wired once) */
function wireSidebar() {
  const box = $('#sidebar-sections');
  box.addEventListener('click', (ev) => {
    const more = ev.target.closest('[data-more]');
    if (more) {
      const which = more.dataset.more;
      if (which === 'family') familyMore = !familyMore;
      if (which === 'country') countryMore = !countryMore;
      if (which === 'tag') tagMore = !tagMore;
      renderSidebar();
      return;
    }
    const b = ev.target.closest('.facet');
    if (!b) return;
    const dim = b.dataset.dim;
    const val = b.dataset.val;
    if (dim === 'provenance') setProvenance(val);
    else toggleFacet(dim, val);
  });
  box.addEventListener('input', (ev) => {
    if (ev.target.id === 'country-q') {
      countryQuery = ev.target.value.trim().toLowerCase();
      const start = ev.target.selectionStart;
      renderSidebar();
      const again = $('#country-q');
      if (again) { again.focus(); try { again.setSelectionRange(start, start); } catch (err) { /* noop */ } }
    }
  });
  $('#sidebar-chips').addEventListener('click', (ev) => {
    const c = ev.target.closest('.chipx');
    if (!c) return;
    const dim = c.dataset.dim;
    if (dim === '__all') resetFilters();
    else if (dim === 'q') setFilters({ q: '' });
    else if (dim === 'bbox') setFilters({ bbox: null });
    else if (dim === 'provenance') setProvenance('public');
    else toggleFacet(dim, c.dataset.val);
  });
  $('#sidebar-handle').addEventListener('click', toggleSidebar);
}

export function toggleSidebar() {
  saveSettings({ sidebar_open: !store.settings.sidebar_open });
  playSound('toggle');
}

/* ══ toasts ════════════════════════════════════════════════════════════ */

export function toast(message, opts = {}) {
  const box = $('#toasts');
  if (!box) return;
  const type = opts.type || 'info';
  const icons = { info: ICONS.info, ok: ICONS.check, warn: ICONS.warn, err: ICONS.x };
  const node = el('div', `toast toast-${type}`);
  node.innerHTML = `<span class="toast-ico">${icons[type] || ICONS.info}</span><span class="toast-msg">${esc(message)}</span>`;
  if (opts.actions && opts.actions.length) {
    const actions = el('div', 'toast-actions');
    for (const a of opts.actions) {
      const btn = el('button', 'btn tiny', esc(a.label));
      btn.addEventListener('click', () => { dismiss(); a.run(); });
      actions.appendChild(btn);
    }
    node.appendChild(actions);
  }
  box.appendChild(node);
  const timeout = opts.timeout == null ? 3500 : opts.timeout;
  let expiresAt = Date.now() + timeout;
  let timer = timeout > 0 ? setTimeout(dismiss, timeout) : null;

  node.addEventListener('pointerenter', () => {
    if (!timer) return;
    clearTimeout(timer);
    timer = null;
    expiresAt = Math.max(Date.now() + 400, expiresAt);
  });
  node.addEventListener('pointerleave', () => {
    if (timer) return;
    const remain = Math.max(400, expiresAt - Date.now());
    timer = setTimeout(dismiss, remain);
  });

  function dismiss() {
    clearTimeout(timer);
    node.classList.add('toast-out');
    setTimeout(() => node.remove(), 200);
  }
  // cap stack
  while (box.children.length > 5) box.firstChild.remove();
  requestAnimationFrame(() => node.classList.add('toast-in'));
  return dismiss;
}

/* ══ hash router ═══════════════════════════════════════════════════════ */

let currentView = null;

function defaultViewId() {
  const s = store.settings;
  if (s.default_view && s.default_view !== 'last' && VIEWS[s.default_view]) return s.default_view;
  if (s.last_view && VIEWS[s.last_view]) return s.last_view;
  return 'overview';
}

function parseHash() {
  const raw = String(location.hash || '').replace(/^#\/?/, '');
  const [view, query] = raw.split('?');
  const params = new URLSearchParams(query || '');
  return { view: view || null, params };
}

function applyHashFilters(params) {
  if (![...params.keys()].length) return;
  const f = { ...DEFAULT_FILTERS, status: [], family: [], country: [], protocol: [], tag: [] };
  const csv = (k) => (params.get(k) || '').split(',').map((x) => x.trim()).filter(Boolean);
  if (params.get('provenance')) f.provenance = params.get('provenance');
  f.status = csv('status'); f.family = csv('family'); f.country = csv('country');
  f.protocol = csv('protocol'); f.tag = csv('tag');
  if (params.get('q')) f.q = params.get('q');
  if (params.get('bbox')) f.bbox = params.get('bbox');
  if (params.get('sort')) f.sort = params.get('sort');
  if (params.get('order')) f.order = params.get('order');
  store.filters = f;
}

export function viewLink() {
  const f = store.filters;
  const p = new URLSearchParams();
  if (f.provenance && f.provenance !== 'public') p.set('provenance', f.provenance);
  if (f.status.length) p.set('status', f.status.join(','));
  if (f.family.length) p.set('family', f.family.join(','));
  if (f.country.length) p.set('country', f.country.join(','));
  if (f.protocol.length) p.set('protocol', f.protocol.join(','));
  if (f.tag.length) p.set('tag', f.tag.join(','));
  if (f.q) p.set('q', f.q);
  if (f.bbox) p.set('bbox', f.bbox);
  if (f.sort !== 'name') p.set('sort', f.sort);
  if (f.order !== 'asc') p.set('order', f.order);
  const qs = p.toString();
  const view = currentView || defaultViewId();
  return `${location.origin}${location.pathname}#/${view}${qs ? '?' + qs : ''}`;
}

export function syncHash() {
  if (!currentView) return;
  try { history.replaceState(null, '', viewLink()); } catch (err) { /* noop */ }
}

export function go(viewId) {
  if (!VIEWS[viewId]) return;
  if (currentView === viewId) {
    const v = VIEWS[viewId];
    if (v.refresh) v.refresh();
    return;
  }
  location.hash = '#/' + viewId;
}

function route() {
  const { view } = parseHash();
  const target = view && VIEWS[view] ? view : defaultViewId();
  if (target === currentView) return;
  navigateTo(target);
}

function navigateTo(id) {
  const prev = currentView ? VIEWS[currentView] : null;
  if (prev && prev.destroy) { try { prev.destroy(); } catch (err) { console.error(err); } }
  currentView = id;
  store.route.view = id;
  const root = $('#view');
  root.innerHTML = '';
  const v = VIEWS[id];
  document.title = `${v.title} — World Feed DB`;
  try {
    v.render(root);
  } catch (err) {
    console.error(err);
    // libs occasionally throw strings (e.g. vendored markercluster) — never show a blank message
    const msg = (err && err.message) || String(err || 'unknown error');
    root.innerHTML = `<div class="view-enter"><div class="empty err">view failed to render — ${esc(msg)}</div></div>`;
  }
  playSound('navigate');
  store.settings.last_view = id;
  queueSettingsSave({ last_view: id });
  syncHash();
}

/* ══ menus ═════════════════════════════════════════════════════════════ */

const MENUS = [
  { id: 'view', label: 'View', build: buildViewMenu },
  { id: 'filters', label: 'Filters', build: buildFiltersMenu },
  { id: 'tools', label: 'Tools', build: buildToolsMenu },
  { id: 'help', label: 'Help', build: buildHelpMenu },
];

function menuItem(desc) {
  if (desc.sep) return { sep: true };
  return desc;
}

function buildViewMenu() {
  const items = [];
  const cur = currentView || defaultViewId();
  VIEW_ORDER.forEach((v, i) => {
    items.push({ label: VIEWS[v].title, kbd: String(i + 1), checked: cur === v, run: () => go(v) });
  });
  items.push({ sep: true });
  items.push({
    label: 'Sidebar', kbd: '\\', checked: store.settings.sidebar_open, run: toggleSidebar,
  });
  items.push({ sep: true });
  items.push({ hdr: 'Tile size' });
  for (const [v, label] of [['sm', 'Small'], ['md', 'Medium'], ['lg', 'Large']]) {
    items.push({ label, checked: store.settings.tile_size === v, run: () => saveSettings({ tile_size: v }) });
  }
  items.push({ hdr: 'Accent' });
  for (const [v, label] of [['teal', 'Teal (default)'], ['violet', 'Violet'], ['amber', 'Amber']]) {
    items.push({ label, checked: store.settings.accent === v, run: () => { saveSettings({ accent: v }); playSound('toggle'); } });
  }
  items.push({ sep: true });
  items.push({ label: 'Fullscreen', run: toggleFullscreen });
  return items;
}

function buildFiltersMenu() {
  const items = [];
  items.push({ hdr: 'Provenance' });
  const provs = [['public', 'Public (default)'], ['directory', 'Directory'], ['exposure', 'Exposure (metadata only)'], ['all', 'All']];
  for (const [v, label] of provs) {
    if (v === 'exposure' && !store.exposureEnabled) continue;
    items.push({ label, checked: store.filters.provenance === v, run: () => setProvenance(v) });
  }
  const fac = store.facets || {};
  const dimMenu = (title, dim, counts, top) => {
    items.push({ sep: true });
    items.push({ hdr: title });
    const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]).slice(0, top);
    const sel = store.filters[dim] || [];
    for (const [val, n] of entries) {
      items.push({ label: `${val} (${fmt(n)})`, checked: sel.includes(val), run: () => toggleFacet(dim, val) });
    }
    items.push({ label: 'Manage in sidebar →', run: () => { if (!store.settings.sidebar_open) toggleSidebar(); } });
  };
  dimMenu('Status', 'status', ((store.filters.status.length && store.facetsSelf && store.facetsSelf.status) ? store.facetsSelf.status.by_status : fac.by_status), 8);
  dimMenu('Family', 'family', ((store.filters.family.length && store.facetsSelf && store.facetsSelf.family) ? store.facetsSelf.family.by_family : fac.by_family), 8);
  dimMenu('Country', 'country', ((store.filters.country.length && store.facetsSelf && store.facetsSelf.country) ? store.facetsSelf.country.by_country : fac.by_country), 8);
  dimMenu('Protocol', 'protocol', ((store.filters.protocol.length && store.facetsSelf && store.facetsSelf.protocol) ? store.facetsSelf.protocol.by_protocol : fac.by_protocol), 8);
  dimMenu('Tag', 'tag', ((store.filters.tag.length && store.facetsSelf && store.facetsSelf.tag) ? store.facetsSelf.tag.by_tag : fac.by_tag), 8);
  items.push({ sep: true });
  items.push({ label: 'Reset all filters', run: resetFilters, disabled: !anyFiltersActive() });
  return items;
}

function buildToolsMenu() {
  const items = [];
  items.push({ label: 'Command palette…', kbd: 'Ctrl K', icon: ICONS.command, run: openPalette });
  items.push({ label: 'Refresh data', icon: ICONS.refresh, run: refreshAll });
  items.push({ sep: true });
  items.push({ label: 'Sound', kbd: 'm', checked: !!store.settings.sound_on, run: toggleSound });
  items.push({ range: { label: 'Volume', min: 0, max: 100, step: 5, value: Math.round((store.settings.sound_volume || 0.35) * 100), oninput: (v) => saveSettings({ sound_volume: v / 100 }) } });
  items.push({ label: 'Settings…', icon: ICONS.star, run: openSettings });
  items.push({ sep: true });
  items.push({ label: 'Copy view link', icon: ICONS.link, run: () => copyText(viewLink()).then(() => toast('View link copied', { type: 'ok' })) });
  items.push({ label: 'Export CSV (current results)', icon: ICONS.download, run: () => exportResults('csv') });
  items.push({ label: 'Export JSON (current results)', icon: ICONS.download, run: () => exportResults('json') });
  return items;
}

function buildHelpMenu() {
  return [
    { label: 'Help & guide…', run: () => openHelpModal() },
    { label: 'Keyboard shortcuts', kbd: '?', run: () => openHelpModal('shortcuts') },
    { label: 'About', run: () => openHelpModal('about') },
  ];
}

function wireMenus() {
  const nav = $('#menubar');
  nav.innerHTML = '';
  for (const m of MENUS) {
    const wrap = el('div', 'menu');
    const btn = el('button', 'menu-btn', esc(m.label));
    btn.type = 'button';
    btn.setAttribute('aria-haspopup', 'true');
    btn.setAttribute('aria-expanded', 'false');
    const pop = el('div', 'menu-pop');
    pop.hidden = true;
    wrap.append(btn, pop);
    nav.appendChild(wrap);

    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (wrap.classList.contains('open')) closeMenus();
      else openMenu(wrap);
    });
    wrap.addEventListener('pointerenter', () => {
      if ($$('.menu.open').length) openMenu(wrap);
    });
    pop.addEventListener('click', (ev) => ev.stopPropagation());
    pop.addEventListener('keydown', (ev) => menuKeyNav(ev, wrap));
  }
  document.addEventListener('click', () => closeMenus());
  nav.addEventListener('keydown', (ev) => {
    const btn = ev.target.closest('.menu-btn');
    if (!btn) return;
    if (ev.key === 'ArrowDown') { ev.preventDefault(); openMenu(btn.parentElement); focusMenuItem(btn.parentElement, 0); }
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      ev.preventDefault();
      const all = $$('.menu', nav);
      const i = all.indexOf(btn.parentElement);
      const next = all[(i + (ev.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
      openMenu(next); next.querySelector('.menu-btn').focus();
    }
  });
}

function openMenu(wrap) {
  closeMenus();
  const m = MENUS.find((x) => x.label === wrap.querySelector('.menu-btn').textContent);
  const pop = wrap.querySelector('.menu-pop');
  const items = m.build();
  pop.innerHTML = '';
  for (const it of items) {
    if (it.sep) { pop.appendChild(el('div', 'menu-sep')); continue; }
    if (it.hdr) { pop.appendChild(el('div', 'menu-hdr', esc(it.hdr))); continue; }
    if (it.range) {
      const row = el('div', 'menu-range');
      row.innerHTML = `<label>${esc(it.range.label)}<span class="menu-range-val">${it.range.value}%</span></label>`;
      const input = document.createElement('input');
      input.type = 'range';
      input.min = it.range.min; input.max = it.range.max; input.step = it.range.step; input.value = it.range.value;
      input.addEventListener('click', (ev) => ev.stopPropagation());
      input.addEventListener('input', () => {
        row.querySelector('.menu-range-val').textContent = input.value + '%';
        it.range.oninput(Number(input.value));
      });
      row.appendChild(input);
      pop.appendChild(row);
      continue;
    }
    const b = el('button', 'menu-item');
    b.type = 'button';
    b.innerHTML = `<span class="mi-check">${it.checked ? ICONS.check : ''}</span>`
      + `<span class="mi-icon">${it.icon || ''}</span>`
      + `<span class="mi-label">${esc(it.label)}</span>`
      + (it.kbd ? `<span class="mi-kbd">${esc(it.kbd)}</span>` : '');
    if (it.disabled) b.disabled = true;
    b.dataset.menuItem = '1';
    b.addEventListener('click', () => {
      closeMenus();
      playSound('click');
      try { it.run(); } catch (err) { toast('Action failed — ' + err.message, { type: 'err' }); }
    });
    pop.appendChild(b);
  }
  wrap.classList.add('open');
  pop.hidden = false;
  wrap.querySelector('.menu-btn').setAttribute('aria-expanded', 'true');
}

function closeMenus() {
  $$('.menu.open').forEach((w) => {
    w.classList.remove('open');
    w.querySelector('.menu-pop').hidden = true;
    w.querySelector('.menu-btn').setAttribute('aria-expanded', 'false');
  });
}

function menuKeyNav(ev, wrap) {
  const buttons = $$('.menu-item:not(:disabled)', wrap);
  const idx = buttons.indexOf(document.activeElement);
  if (ev.key === 'ArrowDown') { ev.preventDefault(); focusMenuItem(wrap, Math.min(buttons.length - 1, idx + 1)); }
  else if (ev.key === 'ArrowUp') { ev.preventDefault(); focusMenuItem(wrap, Math.max(0, idx - 1)); }
  else if (ev.key === 'Escape') { ev.preventDefault(); closeMenus(); wrap.querySelector('.menu-btn').focus(); }
}

function focusMenuItem(wrap, i) {
  const buttons = $$('.menu-item:not(:disabled)', wrap);
  if (buttons[i]) buttons[i].focus();
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
}

/* ══ command palette ═══════════════════════════════════════════════════ */

let paletteSel = 0;
let paletteItems = [];

function commands() {
  const cmds = [];
  VIEW_ORDER.forEach((v, i) => cmds.push({ id: 'go-' + v, label: `Go to ${VIEWS[v].title}`, kbd: String(i + 1), run: () => go(v) }));
  cmds.push({ id: 'sb', label: 'Toggle sidebar', kbd: '\\', run: toggleSidebar });
  cmds.push({ id: 'refresh', label: 'Refresh data', run: refreshAll });
  cmds.push({ id: 'settings', label: 'Open settings', run: openSettings });
  cmds.push({ id: 'sound', label: (store.settings.sound_on ? 'Mute' : 'Unmute') + ' sound', kbd: 'm', run: toggleSound });
  cmds.push({ id: 'tile-sm', label: 'Tile size: small', kbd: '[', run: () => saveSettings({ tile_size: 'sm' }) });
  cmds.push({ id: 'tile-md', label: 'Tile size: medium', run: () => saveSettings({ tile_size: 'md' }) });
  cmds.push({ id: 'tile-lg', label: 'Tile size: large', kbd: ']', run: () => saveSettings({ tile_size: 'lg' }) });
  for (const [v, label] of [['teal', 'Teal'], ['violet', 'Violet'], ['amber', 'Amber']]) {
    cmds.push({ id: 'accent-' + v, label: `Accent: ${label}`, checked: store.settings.accent === v, run: () => { saveSettings({ accent: v }); playSound('toggle'); } });
  }
  for (const [v, label] of [['public', 'Public (default)'], ['directory', 'Directory'], ['exposure', 'Exposure (metadata only)'], ['all', 'All']]) {
    if (v === 'exposure' && !store.exposureEnabled) continue;
    cmds.push({ id: 'prov-' + v, label: `Provenance: ${label}`, checked: store.filters.provenance === v, run: () => setProvenance(v) });
  }
  for (const st of STATUS_ORDER) {
    cmds.push({ id: 'st-' + st, label: `Toggle status: ${st}`, checked: store.filters.status.includes(st), run: () => toggleFacet('status', st) });
  }
  cmds.push({ id: 'reset', label: 'Reset all filters', run: resetFilters });
  cmds.push({ id: 'link', label: 'Copy view link', run: () => copyText(viewLink()).then(() => toast('View link copied', { type: 'ok' })) });
  cmds.push({ id: 'csv', label: 'Export CSV (current results)', run: () => exportResults('csv') });
  cmds.push({ id: 'json', label: 'Export JSON (current results)', run: () => exportResults('json') });
  cmds.push({ id: 'watch', label: 'Open Watch stage', run: () => go('watch') });
  cmds.push({ id: 'stage-clear', label: 'Clear Watch stage', run: () => { saveSettings({ watch_stage: [] }); bus.emit('stage'); toast('Watch stage cleared', { type: 'info' }); } });
  cmds.push({ id: 'map-tiles', label: 'Toggle map tiles', checked: !!store.settings.map_tiles, run: () => saveSettings({ map_tiles: !store.settings.map_tiles }) });
  cmds.push({ id: 'help', label: 'Help & guide', run: () => openHelpModal() });
  cmds.push({ id: 'shortcuts', label: 'Keyboard shortcuts', kbd: '?', run: () => openHelpModal('shortcuts') });
  cmds.push({ id: 'about', label: 'About World Feed DB viewer', run: () => openHelpModal('about') });
  return cmds;
}

function subseq(needle, hay) {
  let i = 0;
  const n = needle.toLowerCase(); const h = hay.toLowerCase();
  for (const ch of h) { if (ch === n[i]) i++; if (i === n.length) return true; }
  return n.length === 0;
}

/* rank palette matches: substring-first beats loose subsequence ("export" should
   surface "Export CSV…" above "Provenance: Exposure…") */
function paletteScore(label, q) {
  const l = label.toLowerCase(); const ql = q.toLowerCase();
  const idx = l.indexOf(ql);
  if (idx === 0) return 0;
  if (idx > 0) return 1;
  if (subseq(ql, l)) return 2;
  return -1;
}

export function openPalette() {
  const overlay = $('#palette');
  overlay.hidden = false;
  const input = $('#palette-input');
  input.value = '';
  renderPaletteList('');
  input.focus();
  playSound('palette_open');
}

export function closePalette() {
  const overlay = $('#palette');
  if (overlay.hidden) return;
  overlay.hidden = true;
  playSound('palette_close');
}

function renderPaletteList(query) {
  const list = $('#palette-list');
  const all = commands();
  let items;
  if (query) {
    const scored = all
      .map((c) => ({ c, s: paletteScore(c.label, query) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => a.s - b.s)
      .map((x) => x.c);
    const searchItem = {
      id: 'search-q',
      label: `Search cameras for “${query}”`,
      hint: 'open Search with this query',
      run: () => { setFilters({ q: query }); go('search'); },
    };
    // Command matches come first so Enter runs the expected command;
    // the "search cameras" escape hatch sits last (or alone when nothing matches).
    items = scored.length ? [...scored, searchItem] : [searchItem];
  } else {
    items = all;
  }
  items = items.slice(0, 14);
  paletteItems = items;
  paletteSel = 0;
  list.innerHTML = items.map((c, i) => (
    `<button type="button" class="palette-item${i === 0 ? ' sel' : ''}" data-i="${i}">
      <span class="pi-label">${esc(c.label)}</span>
      ${c.hint ? `<span class="pi-hint">${esc(c.hint)}</span>` : ''}
      ${c.kbd ? `<span class="pi-kbd">${esc(c.kbd)}</span>` : ''}
      ${c.checked ? `<span class="pi-check">${ICONS.check}</span>` : ''}
    </button>`
  )).join('') || '<div class="palette-empty">no matching commands</div>';
  list.querySelectorAll('.palette-item').forEach((b) => {
    b.addEventListener('click', () => { runPaletteItem(Number(b.dataset.i)); });
    b.addEventListener('pointerenter', () => { paletteSel = Number(b.dataset.i); paintPaletteSel(); });
  });
}

function paintPaletteSel() {
  $$('#palette-list .palette-item').forEach((b) => b.classList.toggle('sel', Number(b.dataset.i) === paletteSel));
}

function runPaletteItem(i) {
  const item = paletteItems[i];
  if (!item) return;
  closePalette();
  try { item.run(); } catch (err) { toast('Command failed — ' + err.message, { type: 'err' }); }
}

function wirePalette() {
  const input = $('#palette-input');
  input.addEventListener('input', () => renderPaletteList(input.value.trim()));
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); paletteSel = Math.min(paletteItems.length - 1, paletteSel + 1); paintPaletteSel(); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); paletteSel = Math.max(0, paletteSel - 1); paintPaletteSel(); }
    else if (ev.key === 'Enter') { ev.preventDefault(); runPaletteItem(paletteSel); }
  });
  $('#palette').addEventListener('click', (ev) => { if (ev.target.id === 'palette') closePalette(); });
}

function togglePalette() {
  if ($('#palette').hidden) openPalette(); else closePalette();
}

/* ══ overlays / drawer / player modal ══════════════════════════════════ */

const ackExposure = new Set();
let pendingWarn = null;
let drawerSeq = 0;

export function selectCamera(cid) {
  store.selectedId = cid || null;
  $$('.card.sel, .row-item.sel').forEach((n) => n.classList.remove('sel'));
  if (!cid) return;
  let found = null;
  try { found = document.querySelector(`[data-cid="${CSS.escape(cid)}"]`); } catch (err) { found = null; }
  const card = found && found.closest('.card, .row-item');
  if (card) card.classList.add('sel');
}

export function rememberCamera(cam) {
  if (cam && cam.camera_id) store.camerasById.set(cam.camera_id, cam);
  return cam;
}

export function openDrawer(cid) {
  if (!cid) return;
  selectCamera(cid);
  const d = $('#drawer');
  d.classList.add('open');
  d.setAttribute('aria-hidden', 'false');
  $('#drawer-title').textContent = 'Camera';
  $('#drawer-sub').textContent = cid;
  $('#drawer-body').innerHTML = '<div class="drawer-loading"><div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div></div>';
  const seq = ++drawerSeq;
  apiGet('/api/camera/' + encodeURIComponent(cid)).then((row) => {
    if (seq !== drawerSeq) return;
    rememberCamera(row);
    if (row.display_policy === 'metadata_only' || row.provenance === 'exposure_aggregator') {
      if (ackExposure.has(cid)) { renderDrawer(row); return; }
      showWarn(row, () => { ackExposure.add(cid); renderDrawer(row); }, () => closeDrawer());
    } else {
      renderDrawer(row);
    }
  }).catch((err) => {
    if (seq !== drawerSeq) return;
    $('#drawer-body').innerHTML = `<div class="empty err">detail fetch failed — ${esc(err.message)}</div>`;
  });
}

export function closeDrawer() {
  const d = $('#drawer');
  d.classList.remove('open');
  d.setAttribute('aria-hidden', 'true');
}

/* the drawer's X button in index.html is not part of the .overlay [data-close] set */
function wireDrawer() {
  const btn = $('#drawer-close');
  if (btn) btn.addEventListener('click', () => closeDrawer());
}

function isMetaOnly(row) {
  return !!row && (row.display_policy === 'metadata_only' || row.provenance === 'exposure_aggregator');
}

function renderDrawer(row) {
  const meta = isMetaOnly(row);
  $('#drawer-title').textContent = row.name || '(unnamed)';
  const sub = [[row.city, row.country].filter(Boolean).join(', '), row.source_family].filter(Boolean).join(' · ');
  $('#drawer-sub').textContent = sub || row.camera_id;

  let h = '';
  if (meta) {
    h += `<div class="warnstrip">${ICONS.warn}<div>
      <div class="warn-text">${esc(row.warning || 'Unsecured camera listed by a public aggregator.')}</div>
      <div class="warn-meta">${esc(row.source_family || 'aggregator dataset')}${row.snapshot_date ? ' · snapshot ' + esc(row.snapshot_date) : ''} · metadata only — never previewed, never probed</div>
    </div></div>`;
  }
  const fields = [];
  fields.push(['status', statusChipHTML(row)]);
  fields.push(['provenance', provChipHTML(row.provenance)]);
  for (const [k, v] of [
    ['family', row.source_family], ['protocol', row.protocol], ['city', row.city], ['country', row.country],
    ['last verified', row.last_verified], ['snapshot date', row.snapshot_date], ['fetch date', row.fetch_date],
    ['geo confidence', row.geo_confidence], ['attribution', row.attribution],
  ]) {
    if (v) fields.push([k, esc(v)]);
  }
  if (row.was_redacted) fields.push(['redacted', 'yes — credential-bearing URL stripped at ingest']);
  if (row.credential_present) fields.push(['credentials in url', 'yes (redacted at ingest)']);
  fields.push(['camera id', `<code class="mono">${esc(row.camera_id || '')}</code>`]);
  h += `<div class="fields">${fields.map(([k, v]) => `<div class="fld"><div class="fld-l">${esc(k)}</div><div class="fld-v">${v}</div></div>`).join('')}</div>`;

  if (Array.isArray(row.tags) && row.tags.length) {
    h += `<div class="tags">${row.tags.map((t) => `<span class="tg">${esc(t)}</span>`).join('')}</div>`;
  }
  if (!meta && row.url) {
    h += `<div class="urlblock"><div class="fld-l">stream url</div><code class="url">${esc(row.url)}</code></div>`;
  }
  if (!meta && (row.resolvable || row.live_url)) {
    h += '<div class="linkline">live relay: this source is resolved server-side and played through the local proxy</div>';
  }
  if (row.meta && typeof row.meta === 'object') {
    const keys = Object.keys(row.meta);
    if (keys.length) {
      h += `<details class="metabox"><summary>meta · ${keys.length} key${keys.length === 1 ? '' : 's'}</summary>${
        keys.map((k) => `<div class="fld"><div class="fld-l">${esc(k)}</div><div class="fld-v mono2">${esc(v2s(row.meta[k]))}</div></div>`).join('')}</details>`;
    }
  }
  if (!meta && row.official_url) {
    h += `<div class="linkline">official page: <a href="${esc(row.official_url)}" target="_blank" rel="noopener noreferrer">open ↗</a></div>`;
  }
  h += '<div class="drawer-actions"></div>';
  $('#drawer-body').innerHTML = h;

  const actions = $('#drawer-body .drawer-actions');
  const proto = String(row.protocol || '').toLowerCase();
  const playable = !meta && !!row.url && (['youtube', 'hls', 'mjpeg', 'jpeg'].includes(proto)
    || (proto === 'iframe' && (row.resolvable || row.live_url)));
  if (playable) {
    const b = el('button', 'btn primary', ICONS.play + ' Play');
    b.addEventListener('click', () => openPlayerModal(row));
    actions.appendChild(b);
  }
  const stageBtn = el('button', 'btn', ICONS.stage + ' Stage');
  stageBtn.addEventListener('click', () => addToStage(row.camera_id));
  actions.appendChild(stageBtn);
  const favBtn = el('button', 'btn' + (isFav(row.camera_id) ? ' fav-on' : ''), ICONS.heart + (isFav(row.camera_id) ? ' Favourited' : ' Favourite'));
  favBtn.addEventListener('click', async () => {
    await toggleFavourite(row.camera_id);
    favBtn.innerHTML = ICONS.heart + (isFav(row.camera_id) ? ' Favourited' : ' Favourite');
    favBtn.classList.toggle('fav-on', isFav(row.camera_id));
  });
  actions.appendChild(favBtn);
  if (!meta && row.url) {
    const copyBtn = el('button', 'btn', ICONS.copy + ' Copy URL');
    copyBtn.addEventListener('click', () => copyText(row.url).then(() => toast('URL copied', { type: 'ok' })));
    actions.appendChild(copyBtn);
    const openBtn = el('button', 'btn', ICONS.open + ' Open original');
    openBtn.addEventListener('click', () => window.open(row.url, '_blank', 'noopener'));
    actions.appendChild(openBtn);
  }
}

function v2s(v) {
  if (v == null) return '—';
  if (typeof v === 'object') { try { return JSON.stringify(v); } catch (err) { return String(v); } }
  return String(v);
}

/* warn modal (exposure interstitial) */

function showWarn(row, onOk, onCancel) {
  pendingWarn = { onOk, onCancel };
  $('#warn-text').textContent = row.warning || 'Unsecured camera listed by a public aggregator — may capture private scenes; location approximate; unverified.';
  const bits = [row.source_family || 'public aggregator dataset'];
  if (row.snapshot_date) bits.push('snapshot ' + row.snapshot_date);
  $('#warn-src').textContent = bits.join(' · ');
  $('#modal-warn').hidden = false;
  $('#warn-continue').focus();
}

function hideWarn() {
  $('#modal-warn').hidden = true;
  pendingWarn = null;
}

function wireWarn() {
  $('#warn-continue').addEventListener('click', () => {
    const p = pendingWarn;
    hideWarn();
    if (p && p.onOk) p.onOk();
  });
  $('#warn-cancel').addEventListener('click', () => {
    const p = pendingWarn;
    hideWarn();
    if (p && p.onCancel) p.onCancel();
  });
  $('#modal-warn').addEventListener('click', (ev) => {
    if (ev.target.id === 'modal-warn') { const p = pendingWarn; hideWarn(); if (p && p.onCancel) p.onCancel(); }
  });
}

/* player modal */

let modalPlayer = null;

export function playerHandlers() {
  return {
    isFav: (cid) => isFav(cid),
    onHeart: (cam) => toggleFavourite(cam.camera_id),
    onStage: (cam) => addToStage(cam.camera_id),
    onInfo: (cam) => openDrawer(cam.camera_id),
    onOpen: (cam) => { if (cam.url) window.open(cam.url, '_blank', 'noopener'); },
    onCopy: (cam) => { if (cam.url) copyText(cam.url).then(() => toast('URL copied', { type: 'ok' })); },
  };
}

export function openPlayerModal(camera) {
  if (!camera || !camera.camera_id) return;
  rememberCamera(camera);
  $('#player-title').textContent = camera.name || '(unnamed)';
  $('#player-chip').innerHTML = statusChipHTML(camera);
  const host = $('#player-host');
  host.innerHTML = '';
  if (modalPlayer) { try { modalPlayer.api.destroy(); } catch (err) { /* noop */ } modalPlayer = null; }
  const p = createPlayer(camera, { context: 'modal', autoplay: true, handlers: playerHandlers() });
  modalPlayer = p;
  host.appendChild(p.el);
  $('#modal-player').hidden = false;
  const closeBtn = $('#modal-player [data-close="modal-player"]');
  if (closeBtn) closeBtn.focus();
}

export function closePlayerModal() {
  if (modalPlayer) { try { modalPlayer.api.destroy(); } catch (err) { /* noop */ } modalPlayer = null; }
  $('#player-host').innerHTML = '';
  $('#modal-player').hidden = true;
}

function wireOverlayClose() {
  $$('.overlay [data-close]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.dataset.close;
      if (id === 'modal-player') closePlayerModal();
      else $('#' + id).hidden = true;
    });
  });
  for (const id of ['modal-settings', 'modal-help', 'modal-player']) {
    $('#' + id).addEventListener('click', (ev) => {
      if (ev.target.id === id) {
        if (id === 'modal-player') closePlayerModal();
        else $('#' + id).hidden = true;
      }
    });
  }
}

/* ══ settings modal ════════════════════════════════════════════════════ */

export function openSettings() {
  buildSettingsModal();
  $('#modal-settings').hidden = false;
}

function buildSettingsModal() {
  const s = store.settings;
  const body = $('#settings-body');
  const rows = [];
  const row = (label, desc, control) => `<div class="set-row"><div class="set-info"><div class="set-label">${esc(label)}</div><div class="set-desc">${esc(desc)}</div></div><div class="set-control">${control}</div></div>`;

  rows.push('<h4 class="set-h">Appearance</h4>');
  rows.push(row('Accent', 'teal is the house colour; violet and amber are alternates.',
    `<div class="seg" data-set="accent">${['teal', 'violet', 'amber'].map((a) => `<button type="button" class="seg-btn${s.accent === a ? ' on' : ''}" data-val="${a}">${a}</button>`).join('')}</div>`));
  rows.push(row('Reduced motion', 'auto follows your OS setting; on disables stagger, pulse, count-up and the nav whoosh.',
    `<select data-set="reduced_motion">${['auto', 'on', 'off'].map((v) => `<option value="${v}"${s.reduced_motion === v ? ' selected' : ''}>${v}</option>`).join('')}</select>`));
  rows.push(row('Tile size', 'wall / search card density.', `<div class="seg" data-set="tile_size">${[['sm', 'S'], ['md', 'M'], ['lg', 'L']].map(([v, l]) => `<button type="button" class="seg-btn${s.tile_size === v ? ' on' : ''}" data-val="${v}">${l}</button>`).join('')}</div>`));

  rows.push('<h4 class="set-h">Sound</h4>');
  rows.push(row('Sound', 'synthesized UI sounds — no audio files.',
    `<label class="switch"><input type="checkbox" data-set="sound_on"${s.sound_on ? ' checked' : ''}><span></span></label>`));
  rows.push(row('Volume', 'master volume for all sounds.', `<input type="range" min="0" max="100" step="5" value="${Math.round((s.sound_volume || 0.35) * 100)}" data-set="sound_volume"><span class="set-val" id="vol-val">${Math.round((s.sound_volume || 0.35) * 100)}%</span>`));

  rows.push('<h4 class="set-h">Playback</h4>');
  rows.push(row('Live previews (hover)', 'wall cards of video formats start a muted inline preview on hover (capped, off by default).',
    `<label class="switch"><input type="checkbox" data-set="live_previews"${s.live_previews ? ' checked' : ''}><span></span></label>`));
  rows.push(row('Max live tiles', 'concurrent live players (watch stage + previews + modal). Older ones pause when exceeded.',
    `<select data-set="max_live_tiles">${Array.from({ length: 9 }, (_, i) => i + 1).map((n) => `<option value="${n}"${Number(s.max_live_tiles) === n ? ' selected' : ''}>${n}</option>`).join('')}</select>`));
  rows.push(row('Still refresh (s)', 'JPEG stills refresh on this interval while visible (5–300s).',
    `<input type="number" min="5" max="300" step="5" value="${Number(s.still_refresh_s) || 30}" data-set="still_refresh_s">`));

  rows.push('<h4 class="set-h">Data & map</h4>');
  rows.push(row('Map tiles', 'OpenStreetMap tiles on the map view — off = dark canvas + markers only, no tile requests.',
    `<label class="switch"><input type="checkbox" data-set="map_tiles"${s.map_tiles ? ' checked' : ''}><span></span></label>`));
  rows.push(row('Results per page', 'wall + search pagination size (12–240).',
    `<input type="number" min="12" max="240" step="12" value="${Number(s.results_per_page) || 60}" data-set="results_per_page">`));

  rows.push('<h4 class="set-h">Behaviour</h4>');
  rows.push(row('Default view', '"last" reopens the view you left; or pin one.',
    `<select data-set="default_view"><option value="last"${s.default_view === 'last' ? ' selected' : ''}>Last used</option>${VIEW_ORDER.map((v) => `<option value="${v}"${s.default_view === v ? ' selected' : ''}>${VIEWS[v].title}</option>`).join('')}</select>`));
  rows.push(row('Watch layout', 'grid for the Watch stage.',
    `<div class="seg" data-set="watch_layout">${['1x1', '2x2', '3x3'].map((v) => `<button type="button" class="seg-btn${s.watch_layout === v ? ' on' : ''}" data-val="${v}">${v}</button>`).join('')}</div>`));
  rows.push(row('Sidebar open', 'show the filter sidebar on load.',
    `<label class="switch"><input type="checkbox" data-set="sidebar_open"${s.sidebar_open ? ' checked' : ''}><span></span></label>`));

  body.innerHTML = `<div class="settings-list">${rows.join('')}</div>
    <div class="settings-foot">
      <button type="button" class="btn ghost" id="settings-reset">Restore defaults</button>
      <span class="settings-note">Favourites are not affected. Everything persists server-side in data/viewer-prefs.json.</span>
    </div>`;

  body.addEventListener('click', (ev) => {
    const seg = ev.target.closest('.seg-btn');
    if (seg) {
      const key = seg.parentElement.dataset.set;
      applySetting(key, seg.dataset.val);
      seg.parentElement.querySelectorAll('.seg-btn').forEach((b) => b.classList.toggle('on', b === seg));
      playSound('toggle');
    }
  });
  body.addEventListener('change', (ev) => {
    const t = ev.target.closest('[data-set]');
    if (!t || t.classList.contains('seg-btn')) return;
    const key = t.dataset.set;
    let val;
    if (t.type === 'checkbox') val = t.checked;
    else if (t.type === 'range' || t.type === 'number') val = Number(t.value);
    else val = t.value;
    applySetting(key, val);
  });
  body.addEventListener('input', (ev) => {
    const t = ev.target.closest('[data-set]');
    if (!t || t.type !== 'range') return;
    if (t.dataset.set === 'sound_volume') {
      const v = Number(t.value) / 100;
      setSoundVolume(v);
      const valEl = $('#vol-val');
      if (valEl) valEl.textContent = t.value + '%';
      saveSettings({ sound_volume: v });
    }
  });
  const reset = $('#settings-reset');
  if (reset) reset.addEventListener('click', () => {
    const stage = stagedIds();
    saveSettings({ ...DEFAULT_SETTINGS, watch_stage: stage, last_view: store.settings.last_view });
    buildSettingsModal();
    toast('Settings restored to defaults (favourites + stage kept)', { type: 'info' });
  });
}

function applySetting(key, val) {
  if (key === 'still_refresh_s') val = clamp(Number(val) || 30, 5, 300);
  if (key === 'results_per_page') val = clamp(Number(val) || 60, 12, 240);
  if (key === 'max_live_tiles') val = clamp(Number(val) || 4, 1, 9);
  saveSettings({ [key]: val });
}

/* ══ help modal ════════════════════════════════════════════════════════ */

export function openHelpModal(sectionId) {
  const nav = $('#help-nav');
  const body = $('#help-body');
  nav.innerHTML = HELP_SECTIONS.map((s) => `<button type="button" class="help-nav-item" data-sec="${s.id}">${esc(s.title)}</button>`).join('');
  body.innerHTML = HELP_SECTIONS.map((s) => `<section class="help-sec" id="help-sec-${s.id}"><h3>${esc(s.title)}</h3>${s.html}</section>`).join('');
  $('#modal-help').hidden = false;
  nav.querySelectorAll('.help-nav-item').forEach((b) => {
    b.addEventListener('click', () => {
      const sec = $('#help-sec-' + b.dataset.sec);
      if (sec) sec.scrollIntoView({ block: 'start', behavior: reduced() ? 'auto' : 'smooth' });
      nav.querySelectorAll('.help-nav-item').forEach((x) => x.classList.toggle('on', x === b));
    });
  });
  if (sectionId) {
    const sec = $('#help-sec-' + sectionId);
    if (sec) setTimeout(() => sec.scrollIntoView({ block: 'start', behavior: 'auto' }), 30);
    const navBtn = nav.querySelector(`[data-sec="${sectionId}"]`);
    if (navBtn) navBtn.classList.add('on');
  }
}

/* ══ data actions ══════════════════════════════════════════════════════ */

export async function refreshAll() {
  await Promise.all([fetchStats(), fetchFacets(), loadPrefs()]);
  bus.emit('refresh');
  toast('Data refreshed', { type: 'ok' });
}

export async function exportResults(format) {
  try {
    const params = { ...filterParams(), limit: 5000, sort: store.filters.sort, order: store.filters.order };
    const fc = await apiGet('/api/cameras', params);
    const feats = (fc.features || []).map((f) => f.properties);
    if (!feats.length) { toast('Nothing to export — no rows match', { type: 'info' }); return; }
    if (format === 'json') {
      downloadFile(`world-feed-db-export-${Date.now()}.json`, JSON.stringify({
        exported_at: new Date().toISOString(), filters: store.filters, count: feats.length, cameras: feats,
      }, null, 2), 'application/json');
    } else {
      const cols = ['camera_id', 'name', 'city', 'country', 'source_family', 'provenance', 'display_policy', 'status', 'protocol', 'last_verified', 'snapshot_date', 'tags', 'url'];
      const escCsv = (v) => {
        if (v == null) return '';
        let s = Array.isArray(v) ? v.join('|') : String(v);
        if (/[",\n\r]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
        return s;
      };
      const lines = [cols.join(',')];
      for (const p of feats) lines.push(cols.map((c) => escCsv(p[c])).join(','));
      downloadFile(`world-feed-db-export-${Date.now()}.csv`, '\ufeff' + lines.join('\r\n'), 'text/csv;charset=utf-8');
    }
    playSound('success');
    toast(`Exported ${fmt(feats.length)} rows (${format.toUpperCase()})${feats.length >= 5000 ? ' — capped at 5000' : ''}`, { type: 'ok' });
  } catch (err) {
    toast('Export failed — ' + err.message, { type: 'err' });
    playSound('error');
  }
}

export function toggleSound() {
  const next = !store.settings.sound_on;
  saveSettings({ sound_on: next });
  updateSoundButton();
  if (next) playSound('toggle');
}

function updateSoundButton() {
  const b = $('#btn-sound');
  if (!b) return;
  b.innerHTML = store.settings.sound_on ? ICONS.sound : ICONS.soundOff;
  b.classList.toggle('off', !store.settings.sound_on);
  b.title = store.settings.sound_on ? `Sound on (${Math.round((store.settings.sound_volume || 0.35) * 100)}%) — m to mute` : 'Sound muted — m to unmute';
}

const TILE_SIZES = ['sm', 'md', 'lg'];
export function changeTileSize(dir) {
  const i = TILE_SIZES.indexOf(store.settings.tile_size);
  const next = TILE_SIZES[clamp(i + dir, 0, TILE_SIZES.length - 1)];
  saveSettings({ tile_size: next });
  playSound('toggle');
  toast(`Tile size: ${next === 'sm' ? 'small' : next === 'md' ? 'medium' : 'large'}`, { type: 'info', timeout: 1200 });
}

export function focusSearch() {
  if (currentView === 'search') {
    const inp = $('#search-q');
    if (inp) { inp.focus(); inp.select(); return; }
  }
  const g = $('#global-q');
  if (g) { g.focus(); g.select(); }
}

function favouriteSelected() {
  if (!store.selectedId) { toast('Select a camera first — click any card, then press f', { type: 'info' }); return; }
  toggleFavourite(store.selectedId);
}

/* ══ keyboard ══════════════════════════════════════════════════════════ */

function isTypingTarget(t) {
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
}

function closeTopOverlay() {
  if (!$('#palette').hidden) { closePalette(); return true; }
  if (!$('#modal-player').hidden) { closePlayerModal(); return true; }
  if (!$('#modal-warn').hidden) { const p = pendingWarn; hideWarn(); if (p && p.onCancel) p.onCancel(); return true; }
  if (!$('#modal-settings').hidden) { $('#modal-settings').hidden = true; return true; }
  if (!$('#modal-help').hidden) { $('#modal-help').hidden = true; return true; }
  if ($('#drawer').classList.contains('open')) { closeDrawer(); return true; }
  if ($$('.menu.open').length) { closeMenus(); return true; }
  return false;
}

function wireKeyboard() {
  document.addEventListener('keydown', (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (mod && (ev.key === 'k' || ev.key === 'K')) { ev.preventDefault(); togglePalette(); return; }
    if (ev.key === 'Escape') {
      if (closeTopOverlay()) { if (isTypingTarget(ev.target)) ev.target.blur(); return; }
      if (isTypingTarget(ev.target)) ev.target.blur();
      return;
    }
    if (isTypingTarget(ev.target)) return;
    if (mod || ev.altKey) return;
    if (!$('#palette').hidden) return;                 // palette owns keys while open
    if (ev.key === '/') { ev.preventDefault(); focusSearch(); return; }
    if (ev.key === '?') { ev.preventDefault(); openHelpModal('shortcuts'); return; }
    if (ev.key === 'm') { toggleSound(); return; }
    if (ev.key === 'f') { favouriteSelected(); return; }
    if (ev.key === '[') { changeTileSize(-1); return; }
    if (ev.key === ']') { changeTileSize(1); return; }
    if (/^[1-8]$/.test(ev.key)) { go(VIEW_ORDER[Number(ev.key) - 1]); return; }
  });
}

/* ══ topbar wiring ═════════════════════════════════════════════════════ */

function wireTopbar() {
  $('#btn-favs').addEventListener('click', () => go('personal'));
  $('#btn-sound').addEventListener('click', toggleSound);
  $('#btn-settings').addEventListener('click', () => openSettings());
  const input = $('#global-q');
  const kick = debounce(() => {
    const q = input.value.trim();
    if (q === store.filters.q) return;
    setFilters({ q });
    if (currentView !== 'search') go('search');
  }, 250);
  input.addEventListener('input', kick);
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); const q = input.value.trim(); setFilters({ q }); go('search'); }
  });
  bus.on('filters', () => {
    if (document.activeElement !== input && input.value !== store.filters.q) input.value = store.filters.q;
  });
}

/* ══ chips helpers (shared with views) ═════════════════════════════════ */

export function statusMeta(status) {
  const s = String(status || 'unknown').toLowerCase();
  return { label: s, cls: s.replace(/[^a-z0-9_-]/g, ''), hint: STATUS_HINT[s] || 'status as recorded in the registry' };
}

export function statusChipHTML(cam) {
  const m = statusMeta(cam && cam.status);
  return `<span class="st st-${m.cls}" title="${esc(m.hint)}">${esc(m.label)}</span>`;
}

export function provChipHTML(prov) {
  const map = { public_by_design: 'public', aggregator_directory: 'directory', exposure_aggregator: 'exposure' };
  const cls = map[prov] || 'unknown';
  return `<span class="pv pv-${cls}" title="provenance: ${esc(prov || 'unknown')}">${esc(prov || 'unknown')}</span>`;
}

/* ══ boot ══════════════════════════════════════════════════════════════ */

async function boot() {
  wireTopbar();
  wireMenus();
  wirePalette();
  wireSidebar();
  wireWarn();
  wireOverlayClose();
  wireDrawer();
  wireKeyboard();
  soundGestureHook();
  setApiState(null);
  setPrefsState('idle');
  updateStatusbar();
  renderChips();

  // hydrate the hash BEFORE the first route so ?q=… deep links land filtered
  const { params } = parseHash();
  applyHashFilters(params);

  await loadPrefs();                 // prefs first so default_view / accent apply before paint

  // initial route: hash view wins; otherwise the default view
  const { view } = parseHash();
  const first = view && VIEWS[view] ? view : defaultViewId();
  navigateTo(first);
  try { history.replaceState(null, '', viewLink()); } catch (err) { /* noop */ }

  fetchStats();
  fetchFacets();

  window.addEventListener('hashchange', route);
  setInterval(() => { if (!document.hidden) fetchStats(); }, 180000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { fetchStats(); if (!settingsTimer && !Object.keys(settingsQueue).length) loadPrefsQuiet(); }
  });
  // re-render sidebar + chips on prefs changes from any surface
  bus.on('prefs', () => { updateFavCount(); });
  bus.on('stage', () => { /* views listen for their own refresh */ });
}

let prefsQuietBusy = false;
async function loadPrefsQuiet() {
  if (prefsQuietBusy) return;
  prefsQuietBusy = true;
  try {
    const res = await apiGet('/api/prefs');
    store.prefs = res;
    applyPrefs();
  } catch (err) { /* keep current */ } finally { prefsQuietBusy = false; }
}

boot();

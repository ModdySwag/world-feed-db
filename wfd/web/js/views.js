/* wfd/web/js/views.js — view renderers for the world-feed-db viewer (v0.3).
 *
 * Views (hash router #/…): overview, map, globe, wall, watch, search, personal, help.
 * Each view: { title, render(root), refresh?, destroy? } — live updates are wired
 * through the app bus ('filters', 'prefs', 'stage', 'facets', 'refresh', 'settings').
 *
 * Principles: render whatever the API returns (no hardcoded families), honest
 * states only, posters by default / players on demand, small per-card DOM.
 */
import {
  store, bus, apiGet, esc, el, fmt, $, $$, toast, go, setFilters, filterParams,
  isFav, toggleFavourite, addToStage, removeFromStage, addManyToStage, openDrawer,
  openPlayerModal, statusChipHTML, reduced, selectCamera, rememberCamera,
  saveSettings, labelFavourite, reorderFavourites, downloadFile, stagedIds, resetFilters,
  playerHandlers, diag, dispName,
} from './app.js';
import { posterEl, createPlayer, startLivePreview, isMetadataOnly } from './player.js';
import { globeView } from './globeview.js';

/* ── local icons ─────────────────────────────────────────────────────── */

const I = {
  play: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  heart: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
  stage: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  info: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
  open: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>',
  expand: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>',
  x: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  drag: '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>',
  cards: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/></svg>',
  rows: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>',
  search: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
  map: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
  star: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  help: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>',
};

/* ── shared helpers ──────────────────────────────────────────────────── */

function stagger(node, i) {
  node.style.setProperty('--i', String(Math.min(i || 0, 23)));
}

function skeletonCards(n) {
  let h = '';
  for (let i = 0; i < n; i++) h += '<div class="skel skel-card"></div>';
  return h;
}

/* Cancel pending poster/image loads before a grid is rebuilt: detach each img
 * first (the poster error handler no-ops on disconnected nodes), then drop its
 * src so the in-flight image fetch aborts — an old image can never land in a
 * card of a later result set, and stale loads stop occupying the server's
 * snapshot gate / browser connections. */
function releasePosters(scope) {
  if (!scope || !scope.querySelectorAll) return 0;
  let n = 0;
  for (const img of scope.querySelectorAll('img[src]')) {
    img.remove();
    img.removeAttribute('src');
    n++;
  }
  if (n) diag.posterReleased += n;
  return n;
}

function countUp(node, target, dur = 600) {
  if (!node) return;
  if (reduced()) { node.textContent = fmt(target); return; }
  const t0 = performance.now();
  function step(t) {
    const k = Math.min(1, (t - t0) / dur);
    node.textContent = fmt(Math.round(target * (k * (2 - k))));
    if (k < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function updateHearts(root, cid) {
  const nodes = cid
    ? $$(`[data-cid="${CSS.escape(cid)}"] [data-act="heart"]`, root)
    : $$('[data-cid] [data-act="heart"]', root);
  for (const b of nodes) {
    const c = b.closest('[data-cid]');
    if (c) {
      const on = isFav(c.dataset.cid);
      b.classList.toggle('on', on);
      b.title = on ? 'Remove from favourites' : 'Favourite';
    }
  }
}

function playableCam(cam) {
  return !!cam && !!cam.url && !isMetadataOnly(cam)
    && (['youtube', 'hls', 'mjpeg', 'jpeg'].includes(String(cam.protocol || '').toLowerCase())
      || (String(cam.protocol || '').toLowerCase() === 'iframe' && (cam.resolvable || cam.live_url)));
}

/* ── card builders (wall + search) ───────────────────────────────────── */

function buildCard(cam, opts = {}) {
  const card = el('div', 'card');
  card.dataset.cid = cam.camera_id;
  card.tabIndex = 0;
  const meta = isMetadataOnly(cam);
  card.classList.toggle('meta-only', meta);

  const media = el('div', 'card-media');
  media.appendChild(posterEl(cam));
  media.appendChild(el('span', 'fmt-badge fmt-' + String(cam.protocol || 'unknown').toLowerCase(),
    esc(cam.protocol === 'youtube' ? 'YT' : String(cam.protocol || '?').toUpperCase())));
  media.appendChild(el('span', 'card-st', statusChipHTML(cam)));

  const hover = el('div', 'card-hover');
  if (playableCam(cam)) {
    const play = el('button', 'card-play', I.play);
    play.type = 'button';
    play.title = 'Open player';
    play.addEventListener('click', (ev) => { ev.stopPropagation(); openPlayerModal(cam); });
    hover.appendChild(play);
  }
  const quick = el('div', 'card-quick');
  const mkQuick = (act, icon, title, fn) => {
    const b = el('button', 'icon-btn', icon);
    b.type = 'button';
    b.title = title;
    b.dataset.act = act;
    b.addEventListener('click', (ev) => { ev.stopPropagation(); fn(); });
    quick.appendChild(b);
    return b;
  };
  mkQuick('stage', I.stage, 'Stage in Watch', () => addToStage(cam.camera_id));
  mkQuick('heart', I.heart, isFav(cam.camera_id) ? 'Remove from favourites' : 'Favourite',
    () => toggleFavourite(cam.camera_id));
  mkQuick('info', I.info, 'Details', () => openDrawer(cam.camera_id));
  if (!meta && cam.url) mkQuick('open', I.open, 'Open original', () => window.open(cam.url, '_blank', 'noopener'));
  hover.appendChild(quick);
  media.appendChild(hover);

  if (opts.selectable) {
    const pick = el('label', 'pick');
    pick.title = 'Select for “Send to Watch”';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = opts.isSelected ? opts.isSelected(cam.camera_id) : false;
    cb.addEventListener('click', (ev) => ev.stopPropagation());
    cb.addEventListener('change', () => opts.onPick && opts.onPick(cam.camera_id, cb.checked));
    pick.appendChild(cb);
    media.appendChild(pick);
  }

  const body = el('div', 'card-body');
  const name = el('div', 'c-name', esc(dispName(cam)));
  name.title = cam.name || '';
  const sub = el('div', 'c-sub');
  const bits = [];
  if (cam.source_family) bits.push(cam.source_family);
  if (cam.country) bits.push(cam.country);
  sub.textContent = bits.join(' · ') || cam.camera_id;
  body.append(name, sub, el('div', 'c-meta', statusChipHTML(cam)));

  card.append(media, body);
  wireCardActivation(card, cam);
  hoverLive(card, media, cam);
  return card;
}

function buildRow(cam, opts = {}) {
  const row = el('div', 'row-item');
  row.dataset.cid = cam.camera_id;
  row.tabIndex = 0;
  const meta = isMetadataOnly(cam);
  row.classList.toggle('meta-only', meta);

  if (opts.selectable) {
    const pick = el('label', 'pick');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = opts.isSelected ? opts.isSelected(cam.camera_id) : false;
    cb.addEventListener('click', (ev) => ev.stopPropagation());
    cb.addEventListener('change', () => opts.onPick && opts.onPick(cam.camera_id, cb.checked));
    pick.appendChild(cb);
    row.appendChild(pick);
  }
  const thumb = el('div', 'ri-thumb');
  thumb.appendChild(posterEl(cam));
  row.appendChild(thumb);

  const main = el('div', 'ri-main');
  main.appendChild(el('div', 'ri-name', esc(dispName(cam))));
  const bits = [];
  if (cam.source_family) bits.push(cam.source_family);
  if (cam.city || cam.country) bits.push([cam.city, cam.country].filter(Boolean).join(', '));
  main.appendChild(el('div', 'ri-sub', esc(bits.join(' · ') || cam.camera_id)));
  row.appendChild(main);

  row.appendChild(el('span', 'ri-status', statusChipHTML(cam)));

  const acts = el('div', 'ri-actions');
  if (playableCam(cam)) {
    const p = el('button', 'icon-btn', I.play);
    p.type = 'button';
    p.title = 'Open player';
    p.addEventListener('click', (ev) => { ev.stopPropagation(); openPlayerModal(cam); });
    acts.appendChild(p);
  }
  const h = el('button', 'icon-btn' + (isFav(cam.camera_id) ? ' on' : ''), I.heart);
  h.type = 'button';
  h.title = 'Favourite';
  h.dataset.act = 'heart';
  h.addEventListener('click', (ev) => { ev.stopPropagation(); toggleFavourite(cam.camera_id); });
  acts.appendChild(h);
  const inf = el('button', 'icon-btn', I.info);
  inf.type = 'button';
  inf.title = 'Details';
  inf.addEventListener('click', (ev) => { ev.stopPropagation(); openDrawer(cam.camera_id); });
  acts.appendChild(inf);
  row.appendChild(acts);

  wireCardActivation(row, cam);
  return row;
}

function wireCardActivation(node, cam) {
  let clickTimer = null;
  node.addEventListener('click', (ev) => {
    if (ev.target.closest('button, input, a, label')) return;
    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => { selectCamera(cam.camera_id); openDrawer(cam.camera_id); }, 220);
  });
  node.addEventListener('dblclick', (ev) => {
    if (ev.target.closest('button, input, a, label')) return;
    clearTimeout(clickTimer);
    if (playableCam(cam)) openPlayerModal(cam);
  });
  node.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); selectCamera(cam.camera_id); openDrawer(cam.camera_id); }
  });
}

function hoverLive(card, media, cam) {
  if (!store.settings.live_previews) return;
  if (isMetadataOnly(cam)) return;
  const proto = String(cam.protocol || '').toLowerCase();
  if (proto !== 'hls' && proto !== 'mjpeg' && !(proto === 'iframe' && (cam.resolvable || cam.live_url))) return;
  let timer = null;
  let preview = null;
  card.addEventListener('mouseenter', () => {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      preview = startLivePreview(cam, media);
    }, 350);
  });
  card.addEventListener('mouseleave', () => {
    clearTimeout(timer); timer = null;
    if (preview) { preview.stop(); preview = null; }
  });
}

/* ══ 1. Overview ═══════════════════════════════════════════════════════ */

const overviewView = (() => {
  let unsubs = [];
  function cleanup() { unsubs.forEach((u) => u()); unsubs = []; }

  function paint(root) {
    const ov = store.overview;
    const body = $('#ov-body', root);
    if (!body) return;
    if (!ov) {
      body.innerHTML = '<div class="empty err">overview data unavailable — is the viewer server running?</div>';
      return;
    }
    const statuses = ov.by_status || {};
    const maxFam = Math.max(1, ...(ov.top_families || []).map((f) => f.total || 0));
    const favCount = store.favIds.size;

    let h = '';
    h += `<div class="ov-hero">
      <div class="ov-total"><div class="ov-num" id="ov-total-num">0</div><div class="ov-lbl">rows in the served registry set</div></div>
      <div class="ov-status" id="ov-status"></div>
      <div class="ov-fav">${I.star}<div class="ov-fav-txt"><b>${fmt(favCount)}</b> favourite${favCount === 1 ? '' : 's'}
        <div class="ov-fav-hint">${favCount ? 'open Personal to manage' : 'heart a camera to collect it'}</div></div>
        <button type="button" class="btn small" id="ov-fav-btn">Personal</button></div>
    </div>`;
    if (ov.exposure_enabled) {
      const n = (ov.by_provenance || {}).exposure_aggregator || 0;
      h += `<div class="ov-note">${I.info}<span>Exposure surface ON — ${fmt(n)} aggregator-listed rows are included as metadata only; they are never previewed (see Help → Honest states).</span></div>`;
    }
    const order = ['live', 'stale', 'dead', 'unknown', 'unverified'];
    for (const k of Object.keys(statuses)) if (!order.includes(k)) order.push(k);
    const present = order.filter((k) => statuses[k] != null);

    h += `<div class="ov-grid">
      <section class="ov-panel">
        <h3>Top families <span class="ov-sub">rows · live share</span></h3>
        <div class="ov-fams">${(ov.top_families || []).map((f) => {
    const tot = f.total || 0;
    const live = f.live || 0;
    const wpct = Math.max(1, Math.round((tot / maxFam) * 100));
    const lpct = Math.round((live / maxFam) * 100);
    return `<button type="button" class="ov-fam" data-fam="${esc(f.family)}" title="filter by family ${esc(f.family)}">
            <span class="of-name">${esc(f.family)}</span>
            <span class="of-bar"><i class="of-total" style="width:${wpct}%"></i><i class="of-live" style="width:${lpct}%"></i></span>
            <span class="of-count">${fmt(tot)}<span class="of-livec"> · ${fmt(live)} live</span></span></button>`;
  }).join('')}</div>
      </section>
      <section class="ov-panel">
        <h3>Top countries</h3>
        <div class="ov-countries">${Object.entries(ov.top_countries || {}).map(([c, n]) => (
    `<button type="button" class="ov-country" data-country="${esc(c)}" title="filter by country ${esc(c)}"><span>${esc(c)}</span><b>${fmt(n)}</b></button>`
  )).join('')}</div>
      </section>
      <section class="ov-panel ov-quick-panel">
        <h3>Quick start</h3>
        <div class="ov-cards">
          <button type="button" class="ov-card" data-go="search">${I.search}<b>Search</b><span>text, facets, sorting, multi-select</span></button>
          <button type="button" class="ov-card" data-go="map">${I.map}<b>Map</b><span>browse by area with clustered pins</span></button>
          <button type="button" class="ov-card" data-go="watch">${I.stage}<b>Watch</b><span>the multi-watch stage, 1×1 → 3×3</span></button>
          <button type="button" class="ov-card" data-go="help">${I.help}<b>Help</b><span>guide, formats, shortcuts, policy</span></button>
        </div>
      </section>
    </div>`;
    body.innerHTML = h;

    countUp($('#ov-total-num', root), ov.total || 0);
    const st = $('#ov-status', root);
    st.innerHTML = present.map((k) => (
      `<span class="ov-chip st-${k}" title="${esc(k)}"><i class="dot"></i><b>0</b>&nbsp;${esc(k)}</span>`
    )).join('');
    const chips = $$('.ov-chip', st);
    chips.forEach((c, i) => countUp($('b', c), statuses[present[i]] || 0));

    $('#ov-fav-btn', root).addEventListener('click', () => go('personal'));
    $$('.ov-fam', body).forEach((b) => b.addEventListener('click', () => {
      setFilters({ family: [b.dataset.fam] });
      go('wall');
    }));
    $$('.ov-country', body).forEach((b) => b.addEventListener('click', () => {
      setFilters({ country: [b.dataset.country] });
      go('wall');
    }));
    $$('.ov-card', body).forEach((b) => b.addEventListener('click', () => go(b.dataset.go)));
  }

  return {
    title: 'Overview',
    icon: I.star,
    render(root) {
      cleanup();
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead"><div><h2 class="vtitle">Overview</h2><div class="vsub" id="ov-sub">registry snapshot</div></div></div>
        <div class="vbody" id="ov-body"><div class="skel skel-panel"></div><div class="skel skel-panel"></div></div>
      </div>`;
      const load = async () => {
        try {
          store.overview = await apiGet('/api/overview');
          const sub = $('#ov-sub', root);
          if (sub) sub.textContent = `as of ${store.overview.generated_at || ''}`;
        } catch (err) {
          store.overview = null;
        }
        paint(root);
      };
      load();
      unsubs.push(bus.on('refresh', load));
      unsubs.push(bus.on('prefs', () => paint(root)));
    },
    refresh() { const r = $('#view'); if (r) overviewView.render(r); },
    destroy() { cleanup(); },
  };
})();

/* ══ 2. Map ════════════════════════════════════════════════════════════ */

const mapView = (() => {
  let mapEl = null; let map = null; let cluster = null; let tiles = null;
  let seq = 0; let moveTimer = null; let unsubs = [];
  let statusEl = null; let noteEl = null;
  const popupCams = new Map();

  function ensureMap() {
    if (map) return true;
    if (!window.L || !window.L.map) return false;
    mapEl = el('div', 'map-canvas');
    // Geometry is set inline (with !important): the cascaded stylesheet for this
    // container has proven unreliable in some browser sessions, and a Leaflet
    // container MUST have a real box for getBounds()/tiles to work.
    mapEl.style.setProperty('position', 'absolute', 'important');
    mapEl.style.setProperty('inset', '0', 'important');
    // NOTE: maxZoom is required — the vendored markercluster throws
    // "Map has no maxZoom specified" when the map's getMaxZoom() is not finite.
    map = window.L.map(mapEl, { minZoom: 2, maxZoom: 19, worldCopyJump: true }).setView([22, 12], 2);
    if (window.L.markerClusterGroup) {
      cluster = window.L.markerClusterGroup({ maxClusterRadius: 55, chunkedLoading: true, showCoverageOnHover: false, disableClusteringAtZoom: 15 });
    } else {
      cluster = window.L.layerGroup();
    }
    cluster.addTo(map);
    map.on('moveend', () => { clearTimeout(moveTimer); moveTimer = setTimeout(fetchMarkers, 250); });
    map.on('resize', () => { clearTimeout(moveTimer); moveTimer = setTimeout(fetchMarkers, 250); });
    map.on('popupopen', (e) => wirePopup(e.popup));
    applyTiles();
    return true;
  }

  function applyTiles() {
    if (!map) return;
    const on = !!store.settings.map_tiles;
    if (on && !tiles) {
      tiles = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      });
      tiles.addTo(map);
    } else if (!on && tiles) {
      map.removeLayer(tiles);
      tiles = null;
    }
  }

  function boundsString() {
    const b = map.getBounds();
    const w = Math.max(-180, b.getWest()); const e = Math.min(180, b.getEast());
    const s = Math.max(-85, b.getSouth()); const n = Math.min(85, b.getNorth());
    return [w, s, e, n].map((v) => v.toFixed(5)).join(',');
  }

  function degenerateBounds(s) {
    const p = String(s || '').split(',');
    if (p.length !== 4) return true;
    const [w, s2, e, n] = p.map(Number);
    return !(isFinite(w) && isFinite(s2) && isFinite(e) && isFinite(n)) || (e - w) < 0.01 || (n - s2) < 0.01;
  }

  let boundsRetry = 0;

  function setStatus(text, isErr) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.classList.toggle('err', !!isErr);
  }

  function markerClass(p) {
    if (p.provenance === 'exposure_aggregator' || p.display_policy === 'metadata_only') return 'exposure';
    const known = ['live', 'stale', 'dead', 'unknown', 'unverified'];
    return known.includes(String(p.status)) ? String(p.status) : 'unknown';
  }

  function makeIcon(kind) {
    const warn = kind === 'exposure';
    return window.L.divIcon({
      className: 'wfd-icon',
      html: `<span class="wfd-pin wfd-${kind}${warn ? ' warn' : ''}">${warn ? '<i>!</i>' : ''}</span>`,
      iconSize: [13, 13], iconAnchor: [6.5, 6.5], popupAnchor: [0, -9],
    });
  }

  function popupHtml(p) {
    const meta = p.display_policy === 'metadata_only' || p.provenance === 'exposure_aggregator';
    const bits = [];
    if (p.city || p.country) bits.push([p.city, p.country].filter(Boolean).join(', '));
    let h = `<div class="pp"><div class="pp-name">${esc(dispName(p))}</div>`;
    if (bits.length) h += `<div class="pp-sub">${esc(bits.join(''))}</div>`;
    h += `<div class="pp-meta">${statusChipHTML(p)}${p.source_family ? `<span class="pp-fam">${esc(p.source_family)}</span>` : ''}${meta ? '<span class="pv pv-exposure">metadata only</span>' : ''}</div>`;
    if (meta) h += '<div class="pp-warn">No preview — metadata only (exposure policy).</div>';
    h += `<div class="pp-actions">
      <button type="button" class="btn small" data-pp="open">Open</button>
      <button type="button" class="btn small" data-pp="stage">Stage</button>
      <button type="button" class="btn small icon-only${isFav(p.camera_id) ? ' on' : ''}" data-pp="heart" title="Favourite">${I.heart}</button>
    </div></div>`;
    return h;
  }

  function wirePopup(popup) {
    const node = popup.getElement();
    if (!node) return;
    const b0 = node.querySelector('[data-cid]');
    const cidVal = b0 ? b0.dataset.cid : null;
    if (!cidVal) return;
    node.querySelectorAll('[data-pp]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const act = b.dataset.pp;
        if (act === 'open') openDrawer(cidVal);
        else if (act === 'stage') addToStage(cidVal);
        else if (act === 'heart') toggleFavourite(cidVal).then(() => b.classList.toggle('on', isFav(cidVal)));
      });
    });
  }

  function renderMarkers(feats) {
    if (!map || !cluster) return;
    cluster.clearLayers();
    popupCams.clear();
    const markers = [];
    for (const f of feats) {
      const p = f.properties || {};
      const g = (f.geometry || {}).coordinates || [];
      if (g.length < 2) continue;
      const lon = +g[0]; const lat = +g[1];
      if (!isFinite(lon) || !isFinite(lat)) continue;
      popupCams.set(p.camera_id, p);
      rememberCamera(p);
      const m = window.L.marker([lat, lon], { icon: makeIcon(markerClass(p)), title: p.name || '' });
      m.bindPopup(`<div data-cid="${esc(p.camera_id)}">${popupHtml(p)}</div>`, { maxWidth: 300, minWidth: 210 });
      markers.push(m);
    }
    if (typeof cluster.addLayers === 'function' && markers.length > 40) cluster.addLayers(markers);
    else markers.forEach((m) => cluster.addLayer(m));
  }

  async function fetchMarkers() {
    if (!map) return;
    let bbox = store.filters.bbox || boundsString();
    // a fresh map can report a degenerate (zero-size) viewport for a moment —
    // wait for real bounds instead of querying a nonsense area
    if (!store.filters.bbox && degenerateBounds(bbox)) {
      if (boundsRetry < 10) {
        boundsRetry++;
        setStatus('sizing map…');
        setTimeout(fetchMarkers, 350);
        return;
      }
      bbox = '-180,-85,180,85';   // last resort: honest world view, never a nonsense area
    }
    boundsRetry = 0;
    const s = ++seq;
    const params = { ...filterParams(), limit: 2500 };
    params.bbox = bbox;
    setStatus('loading…');
    try {
      const fc = await apiGet('/api/cameras', params);
      if (s !== seq) { diag.mapStale++; return; }
      const feats = fc.features || [];
      renderMarkers(feats);
      const pinned = !!store.filters.bbox;
      if (!feats.length) setStatus('no rows match in this area');
      else setStatus(`${fmt(feats.length)} row${feats.length === 1 ? '' : 's'} in view${pinned ? ' · area pinned' : ''}${feats.length >= 2500 ? ' · capped' : ''}`);
      if (noteEl) {
        noteEl.hidden = feats.length < 2500;
        noteEl.textContent = 'Showing the first 2,500 rows — refine filters or zoom in for the rest.';
      }
    } catch (err) {
      if (s !== seq) { diag.mapStale++; return; }
      cluster.clearLayers();
      setStatus('cameras load failed — ' + err.message + ' (nothing shown)', true);
    }
  }

  return {
    title: 'Map',
    icon: I.map,
    render(root) {
      unsubs.forEach((u) => u()); unsubs = [];
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead"><div><h2 class="vtitle">Map</h2><div class="vsub">status-coloured pins · clusters · “Search this area” pins the viewport</div></div>
          <div class="vtools"><button type="button" class="btn" id="map-area-btn" title="Pin the current viewport as an area filter">${I.search} Search this area</button></div>
        </div>
        <div class="map-wrap">
          <div class="map-host" id="map-host"></div>
          <div class="map-status" id="map-status">initialising…</div>
          <div class="map-note" id="map-note" hidden></div>
        </div>
      </div>`;
      statusEl = $('#map-status', root);
      noteEl = $('#map-note', root);
      const hostEl = $('#map-host', root);

      if (!ensureMap()) {
        hostEl.innerHTML = '<div class="empty err">map library failed to load (vendored leaflet missing?) — Wall, Search and Personal still work.</div>';
        return;
      }
      hostEl.appendChild(mapEl);
      // size the map first, then fetch — getBounds() is degenerate until invalidateSize lands.
      // setTimeout rather than rAF: rAF can stall when the browser window is occluded.
      const kick = () => {
        try { map.invalidateSize(); } catch (err) { /* noop */ }
        fetchMarkers();
      };
      setTimeout(kick, 40);
      setTimeout(kick, 700);

      $('#map-area-btn', root).addEventListener('click', () => {
        setFilters({ bbox: boundsString() });
        toast('Area pinned — the filter applies everywhere; clear it from the sidebar chips', { type: 'info' });
      });

      unsubs.push(bus.on('filters', () => fetchMarkers()));
      unsubs.push(bus.on('settings', (patch) => { if ('map_tiles' in patch) applyTiles(); }));
    },
    refresh() { fetchMarkers(); },
    destroy() { unsubs.forEach((u) => u()); unsubs = []; clearTimeout(moveTimer); },
  };
})();

/* ══ 3. Wall ═══════════════════════════════════════════════════════════ */

const wallView = (() => {
  let unsubs = [];
  let seq = 0; let offset = 0; let loadingMore = false; let lastPageFull = false;
  let ctrl = null;                 // in-flight /api/cameras request (aborted when superseded)
  let busy = false;

  function currentTotal() {
    return store.facets ? store.facets.total : null;
  }

  function updateCount(root) {
    const c = $('#wall-count', root);
    if (!c) return;
    const tot = currentTotal();
    c.textContent = tot == null ? `${fmt(offset)} shown` : `${fmt(Math.min(offset, tot))} of ${fmt(tot)} shown`;
  }

  function updateFoot(root) {
    const btn = $('#wall-more', root);
    if (!btn) return;
    if (!lastPageFull) { btn.hidden = true; return; }
    btn.hidden = false;
    btn.disabled = loadingMore;
  }

  function paintHideDeadChip(root) {
    const b = $('#wall-hidedead', root);
    if (!b) return;
    const on = store.settings.hide_dead !== false;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.textContent = on ? 'Hide dead ✓' : 'Dead included';
    b.title = on
      ? 'dead feeds are hidden from wall / search lists — click to include them'
      : 'dead feeds are included — click to hide them';
  }

  async function load(root, { reset }) {
    const grid = $('#wall-grid', root);
    if (!grid) return;
    const s = ++seq;
    if (busy && ctrl) { diag.wallAborted++; try { ctrl.abort(); } catch (err) { /* noop */ } }
    const myCtrl = (ctrl = new AbortController());
    busy = true;
    if (reset) {
      offset = 0;
      grid.className = 'card-grid';
      releasePosters(grid);        // cancel the previous result set's image loads before dropping it
      grid.innerHTML = skeletonCards(12);
    }
    const rpp = Math.max(12, Math.min(240, Number(store.settings.results_per_page) || 60));
    const params = { ...filterParams(), sort: store.filters.sort, order: store.filters.order, limit: rpp, offset };
    try {
      const fc = await apiGet('/api/cameras', params, { signal: myCtrl.signal });
      if (s !== seq) { diag.wallStale++; return; }
      const feats = fc.features || [];
      if (reset) grid.innerHTML = '';
      if (reset && !feats.length) {
        grid.innerHTML = `<div class="empty">no rows match — adjust filters or clear them
          <div class="empty-actions"><button type="button" class="btn small" id="wall-clear">Clear filters</button></div></div>`;
        const cl = $('#wall-clear', grid);
        if (cl) cl.addEventListener('click', resetFilters);
        lastPageFull = false;
      } else {
        feats.forEach((f, i) => {
          const cam = rememberCamera(f.properties);
          const card = buildCard(cam);
          stagger(card, i + (offset % 24));
          grid.appendChild(card);
        });
        offset += feats.length;
        lastPageFull = feats.length >= rpp;
      }
      updateCount(root);
      updateFoot(root);
    } catch (err) {
      if (err && err.name === 'AbortError') return;      // superseded — counted at the abort site
      if (s !== seq) { diag.wallStale++; return; }
      if (reset) grid.innerHTML = `<div class="empty err">wall load failed — ${esc(err.message)}<br><span>nothing shown (no fake data)</span></div>`;
      updateFoot(root);
    } finally {
      if (ctrl === myCtrl) busy = false;
    }
  }

  return {
    title: 'Wall',
    icon: I.cards,
    render(root) {
      unsubs.forEach((u) => u()); unsubs = [];
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead"><div><h2 class="vtitle">Wall</h2><div class="vsub" id="wall-count">loading…</div></div>
          <div class="vtools">
            <button type="button" class="hd-chip" id="wall-hidedead" aria-pressed="true" title="hide dead feeds"></button>
            <div class="seg seg-s" id="wall-tilesize" title="Tile size">
              ${['sm', 'md', 'lg'].map((v) => `<button type="button" class="seg-btn${store.settings.tile_size === v ? ' on' : ''}" data-size="${v}">${v === 'sm' ? 'S' : v === 'md' ? 'M' : 'L'}</button>`).join('')}
            </div>
            <button type="button" class="btn" id="wall-refresh" title="Reload">${I.refresh}</button>
          </div>
        </div>
        <div class="vbody grid-body"><div class="card-grid" id="wall-grid">${skeletonCards(12)}</div></div>
        <div class="vfoot"><button type="button" class="btn more" id="wall-more" hidden>Load more</button></div>
      </div>`;

      paintHideDeadChip(root);
      $('#wall-hidedead', root).addEventListener('click', () => {
        saveSettings({ hide_dead: store.settings.hide_dead === false });
      });
      $('#wall-tilesize', root).addEventListener('click', (ev) => {
        const b = ev.target.closest('[data-size]');
        if (!b) return;
        saveSettings({ tile_size: b.dataset.size });
        $$('#wall-tilesize .seg-btn', root).forEach((x) => x.classList.toggle('on', x === b));
      });
      $('#wall-refresh', root).addEventListener('click', () => load(root, { reset: true }));
      $('#wall-more', root).addEventListener('click', async () => {
        loadingMore = true;
        updateFoot(root);
        await load(root, { reset: false });
        loadingMore = false;
        updateFoot(root);
      });

      load(root, { reset: true });
      unsubs.push(bus.on('filters', () => load(root, { reset: true })));
      unsubs.push(bus.on('facets', () => { updateCount(root); updateFoot(root); }));
      unsubs.push(bus.on('refresh', () => load(root, { reset: true })));
      unsubs.push(bus.on('prefs', () => updateHearts(root)));
      unsubs.push(bus.on('settings', (patch) => { if (patch && 'hide_dead' in patch) paintHideDeadChip(root); }));
    },
    refresh() { const r = $('#view'); if (r) load(r, { reset: true }); },
    destroy() {
      unsubs.forEach((u) => u()); unsubs = [];
      seq++;
      if (busy && ctrl) { try { ctrl.abort(); } catch (err) { /* noop */ } }
      releasePosters($('#view'));
    },
  };
})();

/* ══ 4. Watch (multi-watch stage) ══════════════════════════════════════ */

const watchView = (() => {
  let unsubs = [];
  let players = [];
  let mounted = false;

  async function resolveCameras(ids) {
    return Promise.all(ids.map(async (id) => {
      let cam = store.camerasById.get(id);
      if (!cam) {
        try { cam = rememberCamera(await apiGet('/api/camera/' + encodeURIComponent(id))); }
        catch (err) { cam = { camera_id: id, name: '', protocol: 'unknown', status: 'unknown', _missing: true }; }
      }
      return cam;
    }));
  }

  function layoutCapacity() {
    const l = store.settings.watch_layout;
    return l === '1x1' ? 1 : l === '3x3' ? 9 : 4;
  }

  function destroyPlayers() {
    for (const p of players) { try { p.api.destroy(); } catch (err) { /* noop */ } }
    players = [];
  }

  async function paint(root) {
    const ids = stagedIds();
    const cap = layoutCapacity();
    const stage = $('#stage', root);
    if (!stage) return;
    destroyPlayers();
    stage.className = 'stage stage-' + (store.settings.watch_layout || '2x2');

    const head = $('#watch-count', root);
    if (head) {
      const extra = Math.max(0, ids.length - cap);
      head.textContent = ids.length
        ? `${ids.length} staged · showing ${Math.min(ids.length, cap)} (${store.settings.watch_layout})${extra ? ` · ${extra} more — switch layout` : ''}`
        : 'nothing staged yet';
    }
    const capEl = $('#watch-cap', root);
    if (capEl) capEl.textContent = 'live cap: ' + Math.max(1, Math.min(9, Number(store.settings.max_live_tiles) || 4));

    if (!ids.length) {
      stage.innerHTML = `<div class="stage-empty">
        <h3>${I.stage} Nothing staged yet</h3>
        <p>Three ways to fill the stage:</p>
        <ol>
          <li>Hover any card and press the <b>Stage</b> button (the grid icon).</li>
          <li>Open <b>Personal</b> and use <b>Send all to Watch</b>.</li>
          <li>In <b>Search</b>, tick several results and press <b>Send N to Watch</b>.</li>
        </ol>
        <div class="empty-actions">
          <button type="button" class="btn small" id="stage-go-search">Find cameras</button>
          <button type="button" class="btn small ghost" id="stage-go-personal">Personal</button>
        </div>
      </div>`;
      $('#stage-go-search', stage).addEventListener('click', () => go('search'));
      $('#stage-go-personal', stage).addEventListener('click', () => go('personal'));
      return;
    }

    const cams = await resolveCameras(ids.slice(0, cap));
    if (!stage.isConnected) return;
    stage.innerHTML = '';
    cams.forEach((cam, i) => {
      const slot = el('div', 'slot');
      slot.dataset.cid = cam.camera_id;
      const chrome = el('div', 'slot-chrome',
        `<span class="slot-num">${i + 1}</span>
         <div class="slot-btns">
           <button type="button" class="icon-btn" data-slot="expand" title="Open in player modal">${I.expand}</button>
           <button type="button" class="icon-btn danger" data-slot="remove" title="Remove from stage">${I.x}</button>
         </div>`);
      slot.appendChild(chrome);

      if (cam._missing) {
        slot.classList.add('slot-missing');
        slot.appendChild(el('div', 'slot-missing-body',
          '<p>This camera is not available right now — removed from the registry, or hidden by the exposure gate.</p>'));
      } else {
        const p = createPlayer(cam, { context: 'stage', autoplay: false, handlers: playerHandlers() });
        slot.appendChild(p.el);
        players.push({ cid: cam.camera_id, api: p.api, el: p.el });
      }

      chrome.querySelector('[data-slot="expand"]').addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (!cam._missing) openPlayerModal(cam);
      });
      chrome.querySelector('[data-slot="remove"]').addEventListener('click', (ev) => {
        ev.stopPropagation();
        removeFromStage(cam.camera_id);
        toast('Removed from the stage', { type: 'info', timeout: 1600 });
      });
      stage.appendChild(slot);
    });
    for (let i = cams.length; i < cap; i++) {
      stage.appendChild(el('div', 'slot slot-empty',
        '<div class="slot-empty-in"><span class="se-ico">+</span><p>Empty slot</p><p class="se-hint">Stage from any card, Personal, or Search.</p></div>'));
    }

    // The stage is the user's explicit watch request: start what can start (muted).
    // The live cap pauses the oldest automatically. setTimeout (not rAF): rAF can
    // stall while the window is occluded.
    setTimeout(() => {
      if (!mounted) return;
      for (const p of players) { try { p.api.play(); } catch (err) { /* noop */ } }
    }, 30);
  }

  return {
    title: 'Watch',
    icon: I.stage,
    render(root) {
      unsubs.forEach((u) => u()); unsubs = [];
      mounted = true;
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead"><div><h2 class="vtitle">Watch</h2><div class="vsub" id="watch-count">loading…</div></div>
          <div class="vtools">
            <div class="seg" id="watch-layout" title="Layout">
              ${['1x1', '2x2', '3x3'].map((v) => `<button type="button" class="seg-btn${store.settings.watch_layout === v ? ' on' : ''}" data-layout="${v}">${v}</button>`).join('')}
            </div>
            <button type="button" class="btn small" id="watch-play" title="Play every slot (muted)">${I.play} Play all</button>
            <button type="button" class="btn small ghost" id="watch-pause" title="Pause every slot">Pause all</button>
            <button type="button" class="btn small ghost" id="watch-clear" title="Clear the stage">Clear</button>
            <span class="watch-cap" id="watch-cap" title="Concurrent live players are capped; the oldest pauses automatically">live cap: 4</span>
          </div>
        </div>
        <div class="vbody stage-body"><div class="stage" id="stage"></div></div>
        <div class="vfoot watch-foot">Slots persist across reloads. Video plays muted — expand a slot for a bigger view.</div>
      </div>`;

      $('#watch-layout', root).addEventListener('click', (ev) => {
        const b = ev.target.closest('[data-layout]');
        if (!b) return;
        saveSettings({ watch_layout: b.dataset.layout });
        $$('#watch-layout .seg-btn', root).forEach((x) => x.classList.toggle('on', x === b));
        paint(root);
      });
      $('#watch-play', root).addEventListener('click', () => {
        for (const p of players) { try { p.api.play(); } catch (err) { /* noop */ } }
      });
      $('#watch-pause', root).addEventListener('click', () => {
        for (const p of players) { try { p.api.pause(); } catch (err) { /* noop */ } }
      });
      $('#watch-clear', root).addEventListener('click', () => {
        saveSettings({ watch_stage: [] });
        bus.emit('stage');
        toast('Watch stage cleared', { type: 'info' });
      });

      paint(root);
      unsubs.push(bus.on('stage', () => paint(root)));
      unsubs.push(bus.on('settings', (patch) => { if ('watch_layout' in patch) paint(root); }));
    },
    refresh() { const r = $('#view'); if (r) paint(r); },
    destroy() {
      mounted = false;
      unsubs.forEach((u) => u()); unsubs = [];
      destroyPlayers();
    },
  };
})();

/* ══ 5. Search ═════════════════════════════════════════════════════════ */

const searchView = (() => {
  let unsubs = [];
  let seq = 0; let offset = 0; let loadingMore = false; let lastPageFull = false;
  let ctrl = null;                 // in-flight /api/cameras request (aborted when superseded)
  let busy = false;
  let mode = 'cards';                       // cards | rows (kept for the session)
  let items = [];
  const selection = new Set();              // ids chosen for “Send to Watch”

  function updateSelbar(root) {
    const bar = $('#search-selbar', root);
    if (!bar) return;
    bar.hidden = selection.size === 0;
    const n = $('#sel-n', root);
    if (n) n.textContent = String(selection.size);
  }

  function renderItems(root) {
    const box = $('#search-results', root);
    if (!box) return;
    box.className = mode === 'cards' ? 'card-grid' : 'rows';
    releasePosters(box);
    box.innerHTML = '';
    items.forEach((cam, i) => {
      const opts = {
        selectable: true,
        isSelected: (cid) => selection.has(cid),
        onPick: (cid, on) => { if (on) selection.add(cid); else selection.delete(cid); updateSelbar(root); },
      };
      const node = mode === 'cards' ? buildCard(cam, opts) : buildRow(cam, opts);
      stagger(node, i);
      box.appendChild(node);
    });
  }

  function updateCount(root) {
    const c = $('#search-count', root);
    if (!c) return;
    const tot = store.facets ? store.facets.total : null;
    const parts = [];
    parts.push(tot == null ? `${fmt(items.length)} shown` : `${fmt(Math.min(items.length, tot))} of ${fmt(tot)} matches`);
    if (tot != null && tot >= 5000 && store.filters.q) parts.push('search capped at 5,000');
    c.textContent = parts.join(' · ');
  }

  function updateFoot(root) {
    const btn = $('#search-more', root);
    if (!btn) return;
    btn.hidden = !lastPageFull;
    btn.disabled = loadingMore;
  }

  function exampleChips() {
    return ['falcon', 'beach', 'traffic', 'harbour']
      .map((q) => `<button type="button" class="example-chip" data-q="${q}">${q}</button>`).join('');
  }

  function bindExampleChips(scope, root) {
    $$('.example-chip', scope).forEach((b) => b.addEventListener('click', () => {
      const q = b.dataset.q;
      const input = $('#search-q', root);
      if (input) input.value = q;
      setFilters({ q });
    }));
  }

  async function load(root, { reset }) {
    const box = $('#search-results', root);
    if (!box) return;
    const s = ++seq;
    if (busy && ctrl) { diag.searchAborted++; try { ctrl.abort(); } catch (err) { /* noop */ } }
    const myCtrl = (ctrl = new AbortController());
    busy = true;
    if (reset) {
      offset = 0;
      items = [];
      box.className = mode === 'cards' ? 'card-grid' : 'rows';
      releasePosters(box);
      box.innerHTML = mode === 'cards'
        ? skeletonCards(12)
        : '<div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div>';
    }
    const rpp = Math.max(12, Math.min(240, Number(store.settings.results_per_page) || 60));
    const params = { ...filterParams(), sort: store.filters.sort, order: store.filters.order, limit: rpp, offset };
    try {
      const fc = await apiGet('/api/cameras', params, { signal: myCtrl.signal });
      if (s !== seq) { diag.searchStale++; return; }
      const feats = fc.features || [];
      if (reset) { items = []; box.innerHTML = ''; }
      items.push(...feats.map((f) => rememberCamera(f.properties)));
      offset += feats.length;
      lastPageFull = feats.length >= rpp;
      if (!items.length) {
        box.innerHTML = `<div class="empty">no cameras match — loosen a filter or try:
          <div class="empty-actions">${exampleChips()}</div>
          <div class="empty-actions"><button type="button" class="btn small ghost" id="search-reset">Clear filters</button></div></div>`;
        bindExampleChips(box, root);
        const r = $('#search-reset', box);
        if (r) r.addEventListener('click', resetFilters);
      } else {
        renderItems(root);
      }
      updateCount(root);
      updateFoot(root);
    } catch (err) {
      if (err && err.name === 'AbortError') return;      // superseded — counted at the abort site
      if (s !== seq) { diag.searchStale++; return; }
      if (reset) box.innerHTML = `<div class="empty err">search failed — ${esc(err.message)}</div>`;
    } finally {
      if (ctrl === myCtrl) busy = false;
    }
  }

  return {
    title: 'Search',
    icon: I.search,
    render(root) {
      unsubs.forEach((u) => u()); unsubs = [];
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead search-head">
          <div class="search-hero">
            <span class="sh-ico" aria-hidden="true"></span>
            <input id="search-q" type="search" placeholder="Search names, cities, countries…  ( / )" value="${esc(store.filters.q)}" autocomplete="off" spellcheck="false" aria-label="Search cameras">
            <button type="button" class="btn small ghost" id="search-clear" title="Clear the query">clear</button>
          </div>
          <div class="search-tips">try <span id="search-examples">${exampleChips()}</span> — or combine with the sidebar facets</div>
        </div>
        <div class="search-toolbar">
          <span id="search-count" class="st-count">loading…</span>
          <label class="tb-field">sort
            <select id="search-sort">
              <option value="name">name</option>
              <option value="country">country</option>
              <option value="source_family">family</option>
              <option value="status">status</option>
              <option value="last_verified">last verified</option>
              <option value="fetch_date">added (fetch date)</option>
            </select>
          </label>
          <button type="button" class="btn small" id="search-order" title="Toggle sort direction">${store.filters.order === 'asc' ? 'asc ↑' : 'desc ↓'}</button>
          <div class="seg seg-s" id="search-mode" title="Result layout">
            <button type="button" class="seg-btn${mode === 'cards' ? ' on' : ''}" data-mode="cards">${I.cards}</button>
            <button type="button" class="seg-btn${mode === 'rows' ? ' on' : ''}" data-mode="rows">${I.rows}</button>
          </div>
          <span class="tb-spacer"></span>
          <div class="selbar" id="search-selbar" hidden>
            <b id="sel-n">0</b> selected
            <button type="button" class="btn small primary" id="sel-send">Send to Watch</button>
            <button type="button" class="btn small ghost" id="sel-clear">Clear</button>
          </div>
        </div>
        <div class="vbody grid-body"><div class="card-grid" id="search-results">${skeletonCards(12)}</div></div>
        <div class="vfoot"><button type="button" class="btn more" id="search-more" hidden>Load more</button></div>
      </div>`;
      const ico = $('.sh-ico', root);
      if (ico) ico.innerHTML = I.search;

      const input = $('#search-q', root);
      let t = null;
      input.addEventListener('input', () => {
        clearTimeout(t);
        t = setTimeout(() => setFilters({ q: input.value.trim() }), 250);
      });
      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') { clearTimeout(t); setFilters({ q: input.value.trim() }); }
      });
      $('#search-clear', root).addEventListener('click', () => { input.value = ''; setFilters({ q: '' }); input.focus(); });
      bindExampleChips($('#search-examples', root), root);

      const sel = $('#search-sort', root);
      sel.value = ['name', 'country', 'source_family', 'status', 'last_verified', 'fetch_date'].includes(store.filters.sort)
        ? store.filters.sort : 'name';
      sel.addEventListener('change', () => setFilters({ sort: sel.value }));
      const ord = $('#search-order', root);
      ord.addEventListener('click', () => {
        const next = store.filters.order === 'asc' ? 'desc' : 'asc';
        setFilters({ order: next });
        ord.textContent = next === 'asc' ? 'asc ↑' : 'desc ↓';
      });
      $('#search-mode', root).addEventListener('click', (ev) => {
        const b = ev.target.closest('[data-mode]');
        if (!b) return;
        mode = b.dataset.mode;
        $$('#search-mode .seg-btn', root).forEach((x) => x.classList.toggle('on', x === b));
        renderItems(root);
      });
      $('#sel-send', root).addEventListener('click', () => {
        addManyToStage([...selection]);
        selection.clear();
        updateSelbar(root);
        renderItems(root);
      });
      $('#sel-clear', root).addEventListener('click', () => { selection.clear(); updateSelbar(root); renderItems(root); });
      $('#search-more', root).addEventListener('click', async () => {
        loadingMore = true;
        updateFoot(root);
        await load(root, { reset: false });
        loadingMore = false;
        updateFoot(root);
      });

      updateSelbar(root);
      load(root, { reset: true });
      unsubs.push(bus.on('filters', () => {
        if (document.activeElement !== input && input.value !== store.filters.q) input.value = store.filters.q;
        load(root, { reset: true });
      }));
      unsubs.push(bus.on('facets', () => updateCount(root)));
      unsubs.push(bus.on('refresh', () => load(root, { reset: true })));
      unsubs.push(bus.on('prefs', () => updateHearts(root)));
    },
    refresh() { const r = $('#view'); if (r) load(r, { reset: true }); },
    destroy() {
      unsubs.forEach((u) => u()); unsubs = [];
      seq++;
      if (busy && ctrl) { try { ctrl.abort(); } catch (err) { /* noop */ } }
      releasePosters($('#view'));
    },
  };
})();

/* ══ 6. Personal (favourites manager) ══════════════════════════════════ */

const personalView = (() => {
  let unsubs = [];
  let rowsCams = new Map();
  let dragCid = null;
  let painting = false;

  async function loadRows() {
    const favs = store.prefs.favourites || [];
    if (!favs.length) { rowsCams = new Map(); return; }
    try {
      const fc = await apiGet('/api/cameras', { favourites: 1, geo: 'any', limit: 2000 });
      const map = new Map();
      for (const f of fc.features || []) map.set(f.properties.camera_id, rememberCamera(f.properties));
      rowsCams = map;
    } catch (err) {
      /* keep the previous map; rows render as unavailable rather than lying */
    }
  }

  function persistOrder(ids) {
    reorderFavourites(ids)
      .then(() => repaint())
      .catch((err) => { toast('Reorder failed — ' + err.message, { type: 'err' }); repaint(); });
  }

  function moveRow(cid, dir) {
    const ids = (store.prefs.favourites || []).map((f) => f.camera_id);
    const i = ids.indexOf(cid);
    if (i < 0) return;
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    ids.splice(j, 0, ids.splice(i, 1)[0]);
    persistOrder(ids);
  }

  function startLabelEdit(btn) {
    const row = btn.closest('.pers-row');
    const cid = row.dataset.cid;
    const fav = (store.prefs.favourites.find((f) => f.camera_id === cid) || {});
    const input = el('input', 'pr-label-input');
    input.type = 'text';
    input.maxLength = 80;
    input.value = fav.label || '';
    input.placeholder = 'label — Enter to save, Esc to cancel';
    btn.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const save = async () => {
      if (done) return;
      done = true;
      const val = input.value.trim();
      try { await labelFavourite(cid, val); } catch (err) { toast('Label save failed — ' + err.message, { type: 'err' }); }
      repaint();
    };
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); save(); }
      else if (ev.key === 'Escape') { done = true; repaint(); }
    });
    input.addEventListener('blur', save);
  }

  function paint(root) {
    const list = $('#pers-list', root);
    if (!list) return;
    const favs = store.prefs.favourites || [];
    const count = $('#pers-count', root);
    if (count) {
      count.textContent = favs.length
        ? `${favs.length} favourite${favs.length === 1 ? '' : 's'} · drag to reorder, click a label to rename`
        : 'none yet';
    }
    if (!favs.length) {
      list.innerHTML = `<div class="stage-empty pers-empty">
        <h3>${I.heart} No favourites yet</h3>
        <p>Tap the heart on any camera card — or press <kbd>f</kbd> while a camera is selected — to collect it here.
           Favourites persist locally in <code>data/viewer-prefs.json</code>.</p>
        <div class="empty-actions"><button type="button" class="btn small" id="pers-go-search">Find cameras</button></div>
      </div>`;
      $('#pers-go-search', list).addEventListener('click', () => go('search'));
      return;
    }

    list.innerHTML = favs.map((f) => {
      const cam = rowsCams.get(f.camera_id);
      const unavailable = !cam;
      const bits = [];
      if (cam) {
        if (cam.source_family) bits.push(cam.source_family);
        if (cam.city || cam.country) bits.push([cam.city, cam.country].filter(Boolean).join(', '));
        if (cam.protocol) bits.push(cam.protocol);
      }
      const added = f.added_at ? String(f.added_at).slice(0, 10) : '';
      return `<div class="pers-row" data-cid="${esc(f.camera_id)}" draggable="true" tabindex="0">
        <span class="pr-drag" title="Drag to reorder (or focus the row and press Alt+↑/↓)">${I.drag}</span>
        <div class="pr-thumb"></div>
        <div class="pr-main">
          <div class="pr-name">${esc((cam && cam.name) || f.camera_id)}</div>
          <div class="pr-sub">${esc(bits.join(' · ') || (unavailable ? 'not available now — removed from the registry, or hidden by the exposure gate' : ''))}</div>
          <div class="pr-label"><button type="button" class="pr-label-btn" title="Edit label">${f.label ? esc(f.label) : '<span class="pr-label-empty">+ label</span>'}</button></div>
        </div>
        <div class="pr-meta">
          <span class="pr-status">${unavailable ? '' : statusChipHTML(cam)}</span>
          ${added ? `<span class="pr-added">added ${esc(added)}</span>` : ''}
        </div>
        <div class="pr-actions">
          <button type="button" class="btn small" data-pr="open"${unavailable ? ' disabled' : ''}>Open</button>
          <button type="button" class="btn small" data-pr="stage"${unavailable ? ' disabled' : ''}>Stage</button>
          <button type="button" class="btn small ghost" data-pr="remove" title="Remove from favourites">${I.x} remove</button>
        </div>
      </div>`;
    }).join('');

    // real posters attached via DOM so images stay lazy
    $$('.pers-row', list).forEach((row) => {
      const cam = rowsCams.get(row.dataset.cid);
      const thumb = $('.pr-thumb', row);
      if (!cam) { thumb.innerHTML = '<span class="pr-missing">?</span>'; return; }
      const p = posterEl(cam);
      p.classList.add('pr-poster');
      thumb.appendChild(p);
    });

    wireList(list);
  }

  function wireList(list) {
    if (list.dataset.wired === '1') return;
    list.dataset.wired = '1';

    list.addEventListener('click', (ev) => {
      const row = ev.target.closest('.pers-row');
      if (!row) return;
      if (ev.target.closest('.pr-label-btn')) { startLabelEdit(ev.target.closest('.pr-label-btn')); return; }
      const cid = row.dataset.cid;
      const b = ev.target.closest('[data-pr]');
      if (!b) { selectCamera(cid); openDrawer(cid); return; }
      const act = b.dataset.pr;
      if (act === 'open') { selectCamera(cid); openDrawer(cid); }
      else if (act === 'stage') addToStage(cid);
      else if (act === 'remove') toggleFavourite(cid);
    });

    list.addEventListener('keydown', (ev) => {
      const row = ev.target.closest('.pers-row');
      if (!row) return;
      if (ev.altKey && (ev.key === 'ArrowUp' || ev.key === 'ArrowDown')) {
        ev.preventDefault();
        moveRow(row.dataset.cid, ev.key === 'ArrowUp' ? -1 : 1);
      } else if (ev.key === 'Enter' && !ev.target.closest('button')) {
        selectCamera(row.dataset.cid);
        openDrawer(row.dataset.cid);
      }
    });

    list.addEventListener('dragstart', (ev) => {
      const row = ev.target.closest('.pers-row');
      if (!row) return;
      dragCid = row.dataset.cid;
      row.classList.add('dragging');
      ev.dataTransfer.effectAllowed = 'move';
      try { ev.dataTransfer.setData('text/plain', dragCid); } catch (err) { /* noop */ }
    });
    list.addEventListener('dragend', () => {
      dragCid = null;
      $$('.pers-row', list).forEach((r) => r.classList.remove('dragging', 'drop-before', 'drop-after'));
    });
    list.addEventListener('dragover', (ev) => {
      if (!dragCid) return;
      ev.preventDefault();
      const row = ev.target.closest('.pers-row');
      $$('.pers-row', list).forEach((r) => r.classList.remove('drop-before', 'drop-after'));
      if (!row || row.dataset.cid === dragCid) return;
      const rect = row.getBoundingClientRect();
      row.classList.add(ev.clientY < rect.top + rect.height / 2 ? 'drop-before' : 'drop-after');
    });
    list.addEventListener('drop', (ev) => {
      if (!dragCid) return;
      ev.preventDefault();
      const row = ev.target.closest('.pers-row');
      const ids = (store.prefs.favourites || []).map((f) => f.camera_id);
      const from = ids.indexOf(dragCid);
      if (from < 0) { dragCid = null; return; }
      ids.splice(from, 1);
      let to = ids.length;
      if (row && row.dataset.cid !== dragCid) {
        to = ids.indexOf(row.dataset.cid);
        const rect = row.getBoundingClientRect();
        if (ev.clientY >= rect.top + rect.height / 2) to += 1;
      }
      if (to < 0) to = ids.length;
      ids.splice(to, 0, dragCid);
      dragCid = null;
      persistOrder(ids);
    });
  }

  async function repaint() {
    if (painting) return;
    painting = true;
    try {
      await loadRows();
      paint($('#view'));
    } finally { painting = false; }
  }

  return {
    title: 'Personal',
    icon: I.heart,
    render(root) {
      unsubs.forEach((u) => u()); unsubs = [];
      root.innerHTML = `<div class="vwrap view-enter">
        <div class="vhead"><div><h2 class="vtitle">Personal</h2><div class="vsub" id="pers-count">loading…</div></div>
          <div class="vtools">
            <button type="button" class="btn small" id="pers-all-stage" title="Send every favourite to the Watch stage">${I.stage} Send all to Watch</button>
            <button type="button" class="btn small ghost" id="pers-export" title="Export favourites as JSON">Export JSON</button>
          </div>
        </div>
        <div class="vbody"><div class="pers-list" id="pers-list"><div class="skel skel-row"></div><div class="skel skel-row"></div></div></div>
      </div>`;

      $('#pers-all-stage', root).addEventListener('click', () => {
        const ids = (store.prefs.favourites || []).map((f) => f.camera_id);
        if (!ids.length) { toast('No favourites to stage', { type: 'info' }); return; }
        addManyToStage(ids);
      });
      $('#pers-export', root).addEventListener('click', () => {
        const favs = store.prefs.favourites || [];
        const out = favs.map((f) => {
          const cam = rowsCams.get(f.camera_id) || {};
          return {
            camera_id: f.camera_id, label: f.label || '', added_at: f.added_at || '',
            name: cam.name || '', city: cam.city || '', country: cam.country || '',
            source_family: cam.source_family || '', status: cam.status || '',
            protocol: cam.protocol || '', provenance: cam.provenance || '',
          };
        });
        downloadFile(`world-feed-db-favourites-${Date.now()}.json`, JSON.stringify(out, null, 2), 'application/json');
        toast(`Exported ${out.length} favourites`, { type: 'ok' });
      });

      repaint();
      unsubs.push(bus.on('prefs', () => repaint()));
      unsubs.push(bus.on('refresh', () => repaint()));
    },
    refresh() { repaint(); },
    destroy() { unsubs.forEach((u) => u()); unsubs = []; },
  };
})();

/* ══ 7. Help ═══════════════════════════════════════════════════════════ */

const helpView = {
  title: 'Help',
  icon: I.help,
  render(root) {
    root.innerHTML = `<div class="vwrap view-enter">
      <div class="vhead"><div><h2 class="vtitle">Help &amp; guide</h2><div class="vsub">everything this viewer can do — kept in sync with the actual UI</div></div></div>
      <div class="help-doc">
        <nav class="help-doc-nav">${HELP_SECTIONS.map((s) => `<a href="#/help" data-sec="${s.id}">${esc(s.title)}</a>`).join('')}</nav>
        <div class="help-doc-body">${HELP_SECTIONS.map((s) => `<section class="help-sec" id="help-sec-${s.id}"><h3>${esc(s.title)}</h3>${s.html}</section>`).join('')}</div>
      </div>
    </div>`;
    $$('.help-doc-nav a', root).forEach((a) => a.addEventListener('click', (ev) => {
      ev.preventDefault();
      const sec = $('#help-sec-' + a.dataset.sec, root);
      if (sec) sec.scrollIntoView({ block: 'start', behavior: reduced() ? 'auto' : 'smooth' });
    }));
    fillHelpFacts(root);
  },
};

function fillHelpFacts(root) {
  const total = store.stats ? fmt(store.stats.total) : '—';
  const fams = store.stats ? Object.keys(store.stats.by_family || {}).length : '—';
  const gate = store.stats ? (store.stats.exposure_enabled ? 'ON' : 'OFF (clean)') : '—';
  $$('[data-live]', root || document).forEach((n) => {
    const k = n.dataset.live;
    if (k === 'total') n.textContent = total;
    else if (k === 'families') n.textContent = String(fams);
    else if (k === 'gate') n.textContent = gate;
  });
}

/* ══ view registry ═════════════════════════════════════════════════════ */

export const VIEWS = {
  overview: overviewView,
  map: mapView,
  globe: globeView,
  wall: wallView,
  watch: watchView,
  search: searchView,
  personal: personalView,
  help: helpView,
};

/* ══ help content (must match the actual UI) ═══════════════════════════ */

export const HELP_SECTIONS = [
  {
    id: 'getting-started',
    title: 'Getting started',
    html: `
      <p>World Feed DB is a <b>local</b> registry of public live video feeds with a viewer that runs entirely on this machine
      (<code>http://127.0.0.1:8773</code>). The registry itself is read-only; the only thing the viewer writes is your own
      preferences file (<code>data/viewer-prefs.json</code>) — favourites and settings.</p>
      <ul>
        <li>No runtime CDN: maps and HLS playback use vendored libraries in <code>wfd/web/vendor/</code>.</li>
        <li>Previews are <b>on demand</b>: posters first, players only when you ask (or when a stage slot starts).</li>
        <li>Stop the server with Ctrl+C in the console that launched <code>wfd viewer</code>.</li>
      </ul>
      <p>Current registry size: <b><span data-live="total">—</span> rows</b> across <b><span data-live="families">—</span> families</b>.</p>`,
  },
  {
    id: 'views',
    title: 'Views & navigation',
    html: `
      <p>Eight views, reachable from the menu bar, the command palette (Ctrl+K) or the number keys:</p>
      <table class="help-table">
        <thead><tr><th>#</th><th>View</th><th>What it is for</th></tr></thead>
        <tbody>
          <tr><td>1</td><td>Overview</td><td>hero totals, top families and countries, quick-start cards</td></tr>
          <tr><td>2</td><td>Map</td><td>geographic browsing with clustered status-coloured pins</td></tr>
          <tr><td>3</td><td>World Map</td><td>lazy 3D globe — clustered pins, fly-to search, imagery layers</td></tr>
          <tr><td>4</td><td>Wall</td><td>poster-first card grid of the current filter set</td></tr>
          <tr><td>5</td><td>Watch</td><td>the multi-watch stage (1×1 / 2×2 / 3×3)</td></tr>
          <tr><td>6</td><td>Search</td><td>full-text search with facets, sorting and multi-select</td></tr>
          <tr><td>7</td><td>Personal</td><td>favourites: labels, reorder, export, send-to-watch</td></tr>
          <tr><td>8</td><td>Help</td><td>this guide</td></tr>
        </tbody>
      </table>
      <p>The URL hash tracks the view (<code>#/wall</code>); filter state is captured by <b>Tools → Copy view link</b>.</p>`,
  },
  {
    id: 'world-map',
    title: 'World Map',
    html: `
      <p>The <b>World Map</b> view is a 3D globe (vendored MapLibre GL — still no CDN) over every
      geocoded row: <b>~14k clustered pins</b>. Rows without coordinates are not on it — they live in Wall/Search.
      The map library loads only when you open this view, and the view releases the WebGL context when you leave.</p>
      <ul>
        <li><b>Navigate</b>: drag to spin·rotate; <b>ctrl+drag</b> (or right-drag) tilts; wheel or <kbd>+</kbd>/<kbd>-</kbd> zooms;
        <kbd>Shift</kbd>+arrows rotate/tilt and plain arrows pan once the map has focus (click it first).</li>
        <li><b>Dive in</b>: click a cluster bubble — the globe flies in and expands it. At high zoom the projection
        becomes a normal flat map automatically.</li>
        <li><b>Pins</b>: click one for name, status and actions — <b>Watch</b> (player), <b>Details</b> (drawer), <b>★</b> (favourite);
        double-click opens the player. Exposure rows are metadata-only: unverified-coloured dots with no actions.</li>
        <li><b>Search</b> (top-left) is a text fly-to: pick a result and the globe flies there and highlights it.
        <b>Random live cam</b> (toolbar, or press <kbd>r</kbd> while the globe has focus) teleports to a random live row.</li>
        <li><b>Filters</b> apply to the pins instantly: status / protocol / family / country from the sidebar, plus the
        ★-only toggle in the toolbar. Text search (<code>q</code>) is <em>not</em> applied on the globe — a chip says so.</li>
        <li><b>What's here</b>: after the map settles, a chip shows how many cameras are in view; click it for a compact
        list, click an item to fly to it. It hides when zoomed out past world level.</li>
        <li><b>Copy link</b> (toolbar) stores centre / zoom / bearing / pitch in the URL as
        <code>#/globe?lat=..&lng=..&z=..&b=..&p=..</code> — reopening the link restores exactly that view.</li>
        <li><b>Imagery</b> (layers button, top-right): Esri World Imagery is the base; NASA GIBS Blue Marble adds the
        low-zoom “from orbit” look (z0–8). Optional toggles: GIBS labels, night lights (Black Marble, dimmed),
        today's Earth (VIIRS true colour — with a <b>date picker</b>, max today; the day is pinned in the tile path
        and the imagery lags ~1–2 days) and EOX Sentinel-2 cloudless
        (<b>CC BY-NC-SA — non-commercial</b>). The exact attribution for every visible source sits at the bottom-right
        (forced visible); Blue Marble/labels/night/today are public-domain NASA EOSDIS GIBS.</li>
        <li><b>Day/night terminator</b> (toolbar toggle, <b>on by default</b>): shades the night hemisphere and draws a soft glow along the
        terminator, computed client-side from the current UTC time and refreshed every minute. It is a
        <b>visual cue only</b> — no imagery is swapped.</li>
        <li><b>Tour</b> (toolbar): a cinematic loop over your favourites in saved order (or the Watch stage when there
        are none). Each stop shows a bottom bar with name · family · status · <b>k/n</b> and <b>Next</b>/<b>Stop</b>
        buttons; stops loop with the counter still counting up. <kbd>Esc</kbd> stops a running tour. Auto-rotate is
        held for the duration.</li>
        <li><b>Measure</b> (toolbar): eases the camera top-down and turns clicks into vertices; a floating readout shows
        the running total and last segment — <b>great-circle distances</b>, km + miles. <b>Clear</b> wipes the points,
        double-click or <b>Done</b> finishes and restores your camera, <kbd>Esc</kbd> exits too. While measuring,
        clicks never open pins/clusters.</li>
        <li><b>Minimap</b> (bottom-left, on by default): a small Leaflet inset on the same Esri imagery. Its marker
        tracks the globe — a rectangle for wide views, a centre dot + halo when zoomed in (z≥7). Click it to fly the
        globe there; the × hides it and the layers list re-enables it.</li>
        <li><b>Heatmap</b> (layers list): every geocoded row as a density heatmap; the clustered pins dim while it is
        on. The header line states coverage exactly — “N geocoded of T rows”.</li>
        <li><b>Auto-rotate</b> (toolbar): idle spin — <b>on by default</b>; pauses on any input and resumes after 20 s idle.
        It is a persisted setting, like every layer toggle.</li>
        <li><b>Country labels</b>: at world and continental zooms (z ≤ 6) the top ~28 countries (≥ 40 geocoded rows) carry a
        two-line label — full name on top, “N cams · M live” below; the smallest shrink to “CC · count”. Counts cover
        <em>every</em> status. <b>Click a label</b> to set the country filter (the same chips the sidebar uses) and fly to that
        country's bounding box; click it again to clear.</li>
        <li><b>City labels</b>: between z5 and z9.5 the biggest cities (registry city field) get a “City · N” label — the count
        threshold rises as you zoom out (40 → 15 → 8 rows). <b>Click one</b> to fly to that city; cities carry no filter
        dimension, and the tooltip says so.</li>
        <li><b>Progressive detail</b>: single camera dots fade in from z3.5 and grow with zoom, cluster bubbles split a step
        earlier (regional singles appear sooner) and carry a soft glow. <b>Live</b> single dots pulse with a green halo — the
        pulse pauses while the tab is in the background and stays static with reduced motion on.
        <b>World / Region / City</b> (toolbar, top-right) ease the camera between the three scales; City tilts to 50°.</li>
        <li><b>Hot right now</b>: the world-pulse strip adds the country with the most live cameras in view — click the
        <b>hot</b> token to filter by it, click again to clear.</li>
        <li><b>Hover cards</b>: dwell on a cluster bubble or a pin for ~250 ms — a card breaks a cluster down by status
        (live · stale · dead · unknown+unverified) or previews a camera with its cached <code>/api/poster</code> frame
        (“no poster yet” when there is none; exposure rows stay metadata-only).</li>
        <li><b>World pulse</b>: the bottom-centre strip counts what the current viewport holds — “in view: N cams · live M”,
        the top countries (click one to filter, click again to clear) and how many families are present.</li>
        <li><b>Legend</b> (bottom, next to the minimap): status dot colours plus a cluster colour ramp —
        <b>cluster colour = live share</b> (grey-violet = none/few live, amber = some, teal/green = mostly live).
        The header folds the box away; the state persists.</li>
        <li><b>Photo pins</b>: zoom to z9.5+ and real camera posters fade in as pin thumbnails above their dots —
        the layers list carries an <b>Auto / On / Off</b> row (On starts at z6, Off hides them). Posters queue a few
        at a time; a camera with no cached poster simply keeps its dot, and the image registry is capped so panning stays cheap.</li>
        <li><b>Area panel</b>: click a cluster bubble, a country label or a city label total — a right-hand menu opens
        for that area with a status breakdown (live / stale / dead / unknown), its cameras as rows (thumbnail, name,
        status, family · protocol) and quick controls: search-in-area, sort by name/status, and All / Live / Stale chips
        (up to 120 rows at a time, with “show more”).</li>
        <li><b>Every row carries the full per-camera actions</b> — ▶ Watch, ⓘ Details, ★ Favourite and ＋ Stage —
        the same behaviour as the map popups; exposure rows stay metadata-only (no thumbnail, no actions).</li>
        <li><b>Contextual actions</b>: <b>Zoom to fit</b> frames the pane's cameras, <b>Show photos</b> registers poster
        pins for up to 40 members (works below the photo-pin zoom; toggle off restores), and on a country pane
        <b>Filter</b> applies the same country filter as the label. The pane follows the globe's active filters;
        <kbd>Esc</kbd> closes it when nothing else is open, and its state is never persisted.</li>
      </ul>`,
  },
  {
    id: 'finding',
    title: 'Finding cameras',
    html: `
      <ul>
        <li><b>Search</b>: the top-bar box or the big input on the Search view (debounced ~250&nbsp;ms, full-text on names, cities, countries). Press <kbd>/</kbd> to jump there.</li>
        <li><b>Facets</b>: the sidebar sections (Status, Provenance, Family, Country, Protocol, Tags) show live counts under the current filters — click any value to toggle it.</li>
        <li><b>Active filters</b> appear as chips at the top of the sidebar; remove one with its ×, or press <b>clear all</b>.</li>
        <li><b>Provenance</b> picks the serving class: Public (displayable set, default), Directory, Exposure (only while the surface is ON), All.</li>
        <li><b>Map → “Search this area”</b> pins the viewport as an area filter — it applies everywhere until you clear the chip.</li>
        <li><b>Sort</b> offers name, country, family, status, last verified and added (fetch date), ascending or descending.</li>
      </ul>`,
  },
  {
    id: 'formats',
    title: 'Watching formats',
    html: `
      <table class="help-table">
        <thead><tr><th>Format</th><th>Play</th><th>If it fails</th></tr></thead>
        <tbody>
          <tr><td>YouTube</td><td>hqdefault poster from i.ytimg.com → youtube-nocookie embed (muted)</td><td>fallback panel with <b>Open original</b> — never a fake player</td></tr>
          <tr><td>HLS</td><td>hls.js (vendored) or native HLS video; muted</td><td>honest fallback: feed offline or blocked (CORS) — <b>Retry</b>, or open the source</td></tr>
          <tr><td>MJPEG</td><td>native <code>&lt;img&gt;</code> (it is an animated image)</td><td>fallback panel with retry / open original</td></tr>
          <tr><td>JPEG still</td><td>refreshed on a timer while visible (Settings → still refresh, default 30&nbsp;s); manual ⟳ refresh action</td><td>keeps the last good frame and says so; a first-load failure is shown plainly</td></tr>
          <tr><td>iframe / other</td><td>resolved sources play via the local HLS relay; others are not embedded — <b>Open original</b> only</td><td>—</td></tr>
        </tbody>
      </table>
      <p>Everything plays <b>muted</b>; open a card in the player modal or expand a stage slot. The viewer never invents a preview:
      if a feed cannot start you get an explanation and the source link. Some iframe sources (e.g. skylinewebcams) are
      resolved server-side and relayed as HLS through the local proxy, so they play like any other HLS feed.</p>`,
  },
  {
    id: 'favourites',
    title: 'Favourites & Personal',
    html: `
      <ul>
        <li>Heart any camera — card hover action, player actions, detail drawer, or press <kbd>f</kbd> with a camera selected.</li>
        <li><b>Personal</b> lists your favourites in your order; every row has <b>Open</b>, <b>Stage</b> and <b>remove</b>.</li>
        <li>Click a row's label button to give it a custom name (up to 80 chars). Labels persist server-side.</li>
        <li>Reorder with the drag handle — or focus a row and press <kbd>Alt</kbd>+<kbd>↑</kbd>/<kbd>↓</kbd>. The order saves immediately.</li>
        <li><b>Send all to Watch</b> stages every favourite (up to 9 slots); <b>Export JSON</b> downloads your list.</li>
      </ul>`,
  },
  {
    id: 'watch',
    title: 'Watch stage',
    html: `
      <ul>
        <li>Layouts <b>1×1 / 2×2 / 3×3</b>; the stage, layout and slot order persist across reloads.</li>
        <li>Mixed formats sit side by side: YouTube, HLS, MJPEG and JPEG stills all work in one grid.</li>
        <li>Slots start muted and play automatically; the live cap (Settings → max live tiles, default 4) pauses the <b>oldest</b> player when exceeded — resuming any paused slot preempts the oldest in turn.</li>
        <li>Every slot has: heart, details, refresh-still (JPEG), expand to the player modal, and remove (×).</li>
        <li>Offscreen slots pause themselves and resume when you scroll back.</li>
      </ul>`,
  },
  {
    id: 'settings',
    title: 'Settings & sound',
    html: `
      <p>Open with the gear, the Tools menu, or the palette. Everything persists server-side and applies immediately:</p>
      <ul>
        <li><b>Appearance</b>: accent (teal / violet / amber), reduced motion (auto follows your OS), tile size (S / M / L).</li>
        <li><b>Sound</b>: master toggle + volume. Sounds are synthesized in the browser (no audio files) and only ever start after your first click/keypress. Default: on at 35%.</li>
        <li><b>Playback</b>: hover live previews (off by default), max live tiles (1–9), still refresh seconds.</li>
        <li><b>Data &amp; map</b>: OSM map tiles on/off, results per page.</li>
        <li><b>Behaviour</b>: default view (last used or pinned), watch layout, sidebar state.</li>
      </ul>`,
  },
  {
    id: 'shortcuts',
    title: 'Keyboard shortcuts',
    html: `
      <table class="help-table">
        <thead><tr><th>Key</th><th>Action</th></tr></thead>
        <tbody>
          <tr><td><kbd>Ctrl</kbd>+<kbd>K</kbd></td><td>command palette (commands + “search cameras for …”)</td></tr>
          <tr><td><kbd>/</kbd></td><td>focus search</td></tr>
          <tr><td><kbd>1</kbd>…<kbd>8</kbd></td><td>jump to view</td></tr>
          <tr><td><kbd>Esc</kbd></td><td>close palette / modal / drawer / menu, or leave the input</td></tr>
          <tr><td><kbd>f</kbd></td><td>favourite the selected camera</td></tr>
          <tr><td><kbd>m</kbd></td><td>mute / unmute sounds</td></tr>
          <tr><td><kbd>[</kbd> <kbd>]</kbd></td><td>tile size smaller / larger</td></tr>
          <tr><td><kbd>?</kbd></td><td>this guide</td></tr>
          <tr><td><kbd>↑</kbd> <kbd>↓</kbd></td><td>navigate the palette and menus; <kbd>Alt</kbd>+<kbd>↑</kbd>/<kbd>↓</kbd> reorders Personal rows</td></tr>
        </tbody>
      </table>`,
  },
  {
    id: 'honest',
    title: 'Honest states',
    html: `
      <p>Every row carries the registry's own health status — the viewer shows it as-is and never implies more than the data says:</p>
      <ul>
        <li><span class="st st-live">live</span> the last health check found the feed live (date in tooltips and the drawer)</li>
        <li><span class="st st-stale">stale</span> last check found it not updating</li>
        <li><span class="st st-dead">dead</span> last check found it dead</li>
        <li><span class="st st-unknown">unknown</span> enumerated, not yet health-checked</li>
        <li><span class="st st-unverified">unverified</span> listed in an aggregator snapshot, never verified</li>
      </ul>
      <p>Current exposure gate: <b><span data-live="gate">—</span></b>. When the private exposure surface is OFF, exposure rows are absent from every
      endpoint. When it is ON they are <b>metadata-only</b>: no url, no preview, no autoplay — the drawer shows a warning interstitial instead.</p>
      <p>Fallbacks are truthful: a stream that cannot start says why (offline / CORS / no embed) and offers the source link. No fake frames, no pretend liveness.</p>`,
  },
  {
    id: 'about',
    title: 'About & policy',
    html: `
      <p><b>World Feed DB viewer v0.3</b> — a local, single-user surface over the registry on this machine only. The registry is opened
      read-only per request; this UI never contacts cameras directly.</p>
      <ul>
        <li><b>No runtime CDN.</b> Vendored: Leaflet 1.9.4 + markercluster, hls.js. External requests happen only to feed hosts you requested
        (streams, YouTube thumbnails/embeds) and to <code>tile.openstreetmap.org</code> when map tiles are enabled.</li>
        <li><b>Exposure policy.</b> Aggregator-listed unsecured cameras are surfaced only while the private surface is ON, as metadata with a warning —
        the viewer never previews, probes or links them.</li>
        <li><b>YouTube note.</b> Thumbnails come from i.ytimg.com; playback uses youtube-nocookie.com embeds. Nothing loads until you press play
        (or a staged slot starts, muted).</li>
        <li><b>POST hardening.</b> Preference writes require the <code>X-WFD-Viewer: 1</code> header and a localhost origin, so other websites cannot
        script your viewer's state.</li>
      </ul>`,
  },
];

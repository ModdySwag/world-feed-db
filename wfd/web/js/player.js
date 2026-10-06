/* wfd/web/js/player.js — universal player component + per-format logic.
 *
 * Formats (per VIEWER-SPEC):
 *   youtube : poster i.ytimg.com hqdefault -> iframe youtube-nocookie embed (autoplay, muted)
 *   hls     : placeholder poster -> hls.js (or native HLS) video; fatal -> honest fallback panel
 *   mjpeg   : placeholder poster -> native <img src> (it is an animated image); error -> fallback
 *   jpeg    : <img> still + refresh timer (settings.still_refresh_s, default 30s), "updated HH:MM:SS"
 *   iframe  : placeholder + [Open original] only — no embed guessing; server-resolved rows relay as HLS
 *   unknown : placeholder + [Open original] when a url exists, else a no-url note
 *
 * Laws enforced here:
 *   - exposure / metadata_only rows are NEVER given a url, preview or autoplay: a blocked
 *     panel explains the policy instead.
 *   - players are created only on demand; offscreen players are paused/destroyed via
 *     IntersectionObserver + document visibility.
 *   - LiveBudget caps concurrent live tiles (settings.max_live_tiles); when the cap is
 *     exceeded the oldest non-modal player is paused ("pause oldest").
 *
 * Exports: extractYouTubeId, formatLabel, posterEl, relayUrl, createPlayer, startLivePreview, LiveBudget.
 */
import { playSound } from './sound.js';
import { store } from './app.js';

/* ── small local helpers (no deps, safe inline) ───────────────────────── */

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function clockNow() {
  const d = new Date();
  const p = (x) => (x < 10 ? '0' : '') + x;
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function bust(url) {
  try {
    const u = new URL(url, location.href);
    u.searchParams.set('_wfd', String(Date.now()));
    return u.href;
  } catch (err) {
    return url + (url.indexOf('?') >= 0 ? '&' : '?') + '_wfd=' + Date.now();
  }
}

function fmtClockShort(iso) {
  // ISO timestamp -> "HH:MM:SS" local time (best effort; falls back to the raw suffix)
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  const p = (x) => (x < 10 ? '0' : '') + x;
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const PLAY_ICON = '<svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>';
const REFRESH_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>';
const SHIELD_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 9v4"/><path d="M12 16.5h.01"/></svg>';
const EXT_ICON = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>';
const WARN_ICON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

/* ── format helpers ────────────────────────────────────────────────────── */

const PROTO_LABELS = {
  youtube: 'YT', hls: 'HLS', mjpeg: 'MJPEG', jpeg: 'JPEG', iframe: 'IFRAME', unknown: '?',
};

export function formatLabel(proto) {
  const key = String(proto || 'unknown').toLowerCase();
  return PROTO_LABELS[key] || key.toUpperCase().slice(0, 8);
}

export function extractYouTubeId(url) {
  const m = String(url || '').match(/(?:v=|youtu\.be\/|embed\/|shorts\/|live\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

export function isMetadataOnly(camera) {
  return !!camera && (camera.display_policy === 'metadata_only'
    || camera.provenance === 'exposure_aggregator');
}

/** Ready-to-play relay URL for rows the local server can resolve to a live stream. */
export function relayUrl(cam) {
  if (!cam) return null;
  return cam.live_url || (String(cam.protocol || '').toLowerCase() === 'iframe' && cam.resolvable
    ? '/api/live/' + cam.camera_id + '/index.m3u8'
    : null);
}

/** The source a player should load: the server relay when resolved, else the row url. */
function streamUrlFor(cam) {
  return relayUrl(cam) || (cam && cam.url);
}

/** Poster descriptor for cards + player idle state. */
export function posterInfo(camera) {
  if (!camera) return { kind: 'ph' };
  if (camera.protocol === 'youtube') {
    const id = extractYouTubeId(camera.url);
    if (id) return { kind: 'yt', url: `https://i.ytimg.com/vi/${id}/hqdefault.jpg`, ytId: id };
    // channel-live rows have no id in the url until the server resolves one
    if (camera.poster_url) return { kind: 'still', url: camera.poster_url };
    return { kind: 'ph' };
  }
  if (camera.protocol === 'jpeg' && camera.url) return { kind: 'still', url: camera.url };
  // server-cached poster (og:image of a resolvable source), filled in progressively
  if (camera.poster_url) return { kind: 'still', url: camera.poster_url };
  const proto = String(camera.protocol || '').toLowerCase();
  if ((proto === 'iframe' || proto === 'unknown') && camera.url && !isMetadataOnly(camera)) {
    // '/api/poster/<id>' is lazily resolved and cached server-side; a 404 falls
    // back to the placeholder via the poster image error handler
    return { kind: 'still', url: '/api/poster/' + camera.camera_id };
  }
  return { kind: 'ph' };
}

/** Build the poster / placeholder element used by cards and by the player's idle state. */
export function posterEl(camera) {
  const d = document.createElement('div');
  d.className = 'pl-poster';
  if (isMetadataOnly(camera)) {
    d.classList.add('ph', 'ph-meta');
    d.innerHTML = `<span class="ph-stack">${SHIELD_ICON}<span class="ph-label">metadata only</span></span>`;
    return d;
  }
  const info = posterInfo(camera);
  if (info.kind === 'yt' || info.kind === 'still') {
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    img.alt = camera.name ? `preview: ${camera.name}` : 'feed preview';
    let fellBack = false;
    img.addEventListener('error', () => {
      if (fellBack || !img.isConnected) return;
      fellBack = true;
      d.classList.add('ph');
      d.innerHTML = phHTML(camera, 'preview failed');
    });
    img.src = info.url;
    d.appendChild(img);
    return d;
  }
  d.classList.add('ph');
  d.innerHTML = phHTML(camera, null);
  return d;
}

function phHTML(camera, note) {
  const proto = formatLabel(camera && camera.protocol);
  return `<span class="ph-stack">`
    + `<span class="ph-proto">${esc(proto)}</span>`
    + (note ? `<span class="ph-label">${esc(note)}</span>` : '<span class="ph-label">no poster</span>')
    + '</span>';
}

/* ── live budget: cap concurrent live tiles, pause oldest ──────────────── */

export const LiveBudget = (() => {
  let seq = 0;
  const state = { cap: 4, holders: [] };

  function enforce() {
    const active = state.holders.filter((h) => h.active);
    const nonModal = active.filter((h) => h.kind !== 'modal');
    const modalCount = active.length - nonModal.length;
    let over = active.length - state.cap;
    if (over <= 0) return;
    // previews give way first, then oldest-first; modal players are never auto-evicted
    nonModal.sort((a, b) => {
      const pa = a.kind === 'preview' ? 0 : 1;
      const pb = b.kind === 'preview' ? 0 : 1;
      return pa - pb || a.started - b.started;
    });
    while (over > 0 && nonModal.length) {
      const victim = nonModal.shift();
      if (victim.active) {
        victim.active = false;
        try { victim.onEvict('cap'); } catch (err) { /* player gone */ }
      }
      over--;
    }
    // if everything left is modal, allow the overflow (focus wins)
    void modalCount;
  }

  return {
    setCap(n) { state.cap = Math.max(1, Number(n) || 4); enforce(); },
    get cap() { return state.cap; },
    register(id, kind, onEvict) {
      state.holders = state.holders.filter((h) => h.id !== id);
      state.holders.push({ id, kind, started: ++seq, active: true, onEvict });
      enforce();
    },
    activate(id) {
      const h = state.holders.find((x) => x.id === id);
      if (h) { h.active = true; h.started = ++seq; }
      enforce();
    },
    deactivate(id) {
      const h = state.holders.find((x) => x.id === id);
      if (h) h.active = false;
    },
    unregister(id) {
      state.holders = state.holders.filter((h) => h.id !== id);
    },
  };
})();

/* ── the universal player component ────────────────────────────────────── */

let uid = 0;

/**
 * createPlayer(camera, opts) -> { el, play, pause, toggle, destroy, refreshStill,
 *                                isPlaying, setCamera, state }
 * opts.context: 'stage' | 'modal' (styling + budget kind)
 * opts.autoplay: start immediately (muted) — used by the Watch stage / modal
 * opts.handlers: { onHeart, onStage, onInfo, onOpen, onCopy } — heart/stage/… actions
 */
export function createPlayer(camera, opts = {}) {
  const context = opts.context === 'modal' ? 'modal' : 'stage';
  const myId = 'pl-' + (++uid);

  const el = document.createElement('div');
  el.className = `pl pl-${context}`;
  el.dataset.plid = myId;
  el.innerHTML = `
    <div class="pl-media">
      <div class="pl-poster-host"></div>
      <div class="pl-live"></div>
      <button type="button" class="pl-play" title="Play / resume" aria-label="Play">${PLAY_ICON}</button>
      <div class="pl-top"><span class="fmt-badge"></span><span class="pl-status st"></span></div>
      <div class="pl-caption"></div>
      <div class="pl-panels"></div>
    </div>
    <div class="pl-foot">
      <div class="pl-name"></div>
      <div class="pl-sub"></div>
      <div class="pl-actions"></div>
    </div>`;

  const mediaHost = el.querySelector('.pl-live');
  const posterHost = el.querySelector('.pl-poster-host');
  const playBtn = el.querySelector('.pl-play');
  const captionEl = el.querySelector('.pl-caption');
  const panelsEl = el.querySelector('.pl-panels');
  const badgeEl = el.querySelector('.fmt-badge');
  const statusEl = el.querySelector('.pl-status');
  const nameEl = el.querySelector('.pl-name');
  const subEl = el.querySelector('.pl-sub');
  const actionsEl = el.querySelector('.pl-actions');

  let cam = null;
  let state = 'idle';        // idle | loading | playing | paused | error | blocked | nourl | noplay
  let want = false;          // user intent: should be playing
  let capPaused = false;
  let destroyed = false;
  let visible = true;
  let hlsObj = null;
  let vid = null;
  let frameEl = null;
  let imgEl = null;          // jpeg still or mjpeg stream img
  let mjpegEl = null;
  let stillTimer = null;
  let lastStillAt = null;
  let loadTimer = null;
  let io = null;
  let autoPaused = false;    // paused automatically (offscreen) vs by the user
  let paneKind = 'idle';     // which panel is currently shown

  /* -- status chip -------------------------------------------------------- */

  function statusMeta() {
    const s = String((cam && cam.status) || 'unknown').toLowerCase();
    const verified = cam && cam.last_verified ? ` · last verified ${String(cam.last_verified).replace('T', ' ')}` : '';
    const map = {
      live: ['live', 'registry health check last found this feed live' + verified],
      stale: ['stale', 'registry health check found the feed not updating' + verified],
      dead: ['dead', 'registry health check found this feed dead' + verified],
      unknown: ['unknown', 'enumerated but not yet health-checked'],
      unverified: ['unverified', 'listed in an aggregator snapshot — never verified'],
    };
    const [label, hint] = map[s] || [s, 'status as recorded in the registry'];
    return { label, hint, cls: s };
  }

  /* -- panels ------------------------------------------------------------- */

  function showPanel(kind, html) {
    paneKind = kind;
    panelsEl.innerHTML = html || '';
    panelsEl.classList.toggle('on', !!html);
    el.classList.toggle('has-panel', !!html);
  }

  function clearPanel() { showPanel('none', ''); }

  function fallbackPanel(title, message) {
    const canOpen = !!(cam && cam.url);
    showPanel('fallback', `
      <div class="plp plp-fallback">
        <div class="plp-title">${WARN_ICON}<span>${esc(title)}</span></div>
        <div class="plp-text">${esc(message)}</div>
        <div class="plp-actions">
          <button type="button" class="btn small" data-pl="retry">Retry</button>
          ${canOpen ? '<button type="button" class="btn small" data-pl="open">Open original</button>' : ''}
          ${canOpen ? '<button type="button" class="btn small ghost" data-pl="copy">Copy URL</button>' : ''}
        </div>
      </div>`);
  }

  function blockedPanel() {
    showPanel('blocked', `
      <div class="plp plp-blocked">
        <div class="plp-shield">${SHIELD_ICON}</div>
        <div class="plp-title">Metadata only — no preview by policy</div>
        <div class="plp-text">${esc((cam && cam.warning) || 'Unsecured camera listed by a public aggregator — may capture private scenes; location approximate; unverified.')}</div>
        <div class="plp-note">Listed for awareness only: never previewed, never probed, never embedded.</div>
      </div>`);
  }

  function noUrlPanel() {
    showPanel('nourl', `
      <div class="plp">
        <div class="plp-title">No stream URL recorded</div>
        <div class="plp-text">This registry row carries metadata only — there is nothing to play.</div>
      </div>`);
  }

  function noPlayPanel() {
    showPanel('noplay', `
      <div class="plp">
        <div class="plp-title">Not embedded by the viewer</div>
        <div class="plp-text">This format (${esc(formatLabel(cam && cam.protocol))}) is opened at its source — the viewer does not guess embeds.</div>
        <div class="plp-actions"><button type="button" class="btn small" data-pl="open">Open original</button>
        <button type="button" class="btn small ghost" data-pl="copy">Copy URL</button></div>
      </div>`);
  }

  function capPanel() {
    const n = LiveBudget.cap;
    showPanel('cap', `
      <div class="plp plp-cap">
        <div class="plp-title">Paused — live cap (${n})</div>
        <div class="plp-text">Concurrent live tiles are capped at ${n}. Resume this one to preempt the oldest.</div>
        <div class="plp-actions"><button type="button" class="btn small" data-pl="resume">Resume</button></div>
      </div>`);
  }

  /* -- media teardown ------------------------------------------------------ */

  function teardownMedia() {
    clearTimeout(loadTimer);
    if (hlsObj) { try { hlsObj.destroy(); } catch (err) { /* noop */ } hlsObj = null; }
    if (vid) {
      try { vid.pause(); } catch (err) { /* noop */ }
      vid.removeAttribute('src');
      try { vid.load(); } catch (err) { /* noop */ }
      if (vid.parentNode) vid.parentNode.removeChild(vid);
      vid = null;
    }
    if (frameEl) { if (frameEl.parentNode) frameEl.parentNode.removeChild(frameEl); frameEl = null; }
    if (mjpegEl) { if (mjpegEl.parentNode) mjpegEl.parentNode.removeChild(mjpegEl); mjpegEl = null; }
    if (imgEl) { if (imgEl.parentNode) imgEl.parentNode.removeChild(imgEl); imgEl = null; }
    mediaHost.innerHTML = '';
    mediaHost.classList.remove('on');
    clearTimeout(stillTimer);
  }

  function stopBudget() {
    LiveBudget.unregister(myId);
  }

  /* -- state handling ------------------------------------------------------ */

  function setState(next) {
    state = next;
    el.dataset.state = next;
    const playing = next === 'playing';
    playBtn.classList.toggle('show', isPlayable() && !playing && next !== 'loading');
    el.classList.toggle('is-playing', playing);
  }

  function isPlayable() {
    if (!cam) return false;
    if (isMetadataOnly(cam)) return false;
    if (!cam.url) return false;
    const proto = String(cam.protocol || '').toLowerCase();
    if (proto === 'jpeg') return false;             // stills have no play action
    if (relayUrl(cam)) return true;                  // iframe rows resolved server-side play through the relay
    if (proto === 'iframe' || proto === 'unknown' || proto === '') return false;
    return true;                                     // youtube | hls | mjpeg
  }

  /* -- format engines ------------------------------------------------------ */

  function play() {
    if (destroyed || !cam) return;
    if (isMetadataOnly(cam)) { blockedPanel(); setState('blocked'); return; }
    if (!cam.url) { noUrlPanel(); setState('nourl'); return; }
    const proto = String(cam.protocol || '').toLowerCase();
    if (proto === 'youtube') return startYT();
    if (proto === 'hls') return startHls();
    if (proto === 'mjpeg') return startMjpeg();
    if (proto === 'jpeg') { startStill(); return; }
    if (proto === 'iframe' && relayUrl(cam)) return startHls();   // server-resolved relay
    return; // iframe/unknown — panel already explains
  }

  function pause(opts2 = {}) {
    if (destroyed) return;
    want = opts2.keepWant ? want : false;
    capPaused = !!opts2.cap;
    if (state !== 'playing') { if (capPaused) capPanel(); return; }
    const proto = String(cam.protocol || '').toLowerCase();
    const relay = !!relayUrl(cam);            // server-relayed iframe rows behave like hls
    if (proto === 'youtube') {
      stopBudget();
      if (frameEl) { if (frameEl.parentNode) frameEl.parentNode.removeChild(frameEl); frameEl = null; }
      setState('idle');
      if (capPaused) capPanel();
    } else if (proto === 'hls' || relay) {
      stopBudget();
      if (vid) { try { vid.pause(); } catch (err) { /* noop */ } }
      setState('paused');
      if (capPaused) capPanel();
    } else if (proto === 'mjpeg') {
      stopBudget();
      if (mjpegEl) { if (mjpegEl.parentNode) mjpegEl.parentNode.removeChild(mjpegEl); mjpegEl = null; }
      setState('idle');
      if (capPaused) capPanel();
    }
  }

  function resume() {
    capPaused = false;
    clearPanelsForResume();
    want = true;
    const proto = String(cam.protocol || '').toLowerCase();
    if ((proto === 'hls' || relayUrl(cam)) && vid && state === 'paused') {
      registerLive(context === 'modal' ? 'modal' : 'stage');
      const p = vid.play();
      if (p && p.catch) p.catch(() => {});
      setState('playing');
    } else {
      play();
    }
  }

  function clearPanelsForResume() {
    if (paneKind === 'cap') clearPanel();
  }

  function registerLive(kind) {
    LiveBudget.register(myId, kind, () => {
      if (destroyed) return;
      capPaused = true;
      pause({ cap: true, keepWant: true });
    });
    LiveBudget.activate(myId);
  }

  function startYT() {
    const id = extractYouTubeId(cam.url);
    if (!id) { fallbackPanel('No embeddable id', 'Could not extract a YouTube video id from this URL.'); setState('error'); return; }
    teardownMedia();
    clearPanel();
    setState('loading');
    want = true;
    registerLive(context === 'modal' ? 'modal' : 'stage');
    const f = document.createElement('iframe');
    f.className = 'pl-frame';
    f.title = cam.name || 'YouTube stream';
    f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
    f.setAttribute('allowfullscreen', '');
    // NOTE: the embed must see a real (origin-level) referrer and an explicit
    // origin param — with no-referrer YouTube answers "Error 153". Site privacy
    // still holds: the referrer is the local 127.0.0.1 origin itself.
    const params = new URLSearchParams({
      autoplay: '1', mute: '1', rel: '0', modestbranding: '1', playsinline: '1',
      origin: location.origin,
    });
    f.src = 'https://www.youtube-nocookie.com/embed/' + id + '?' + params.toString();
    f.addEventListener('load', () => { if (!destroyed) { mediaHost.classList.add('on'); setState('playing'); } });
    frameEl = f;
    mediaHost.appendChild(f);
    // iframes don't reliably fire load errors; treat 'playing' optimistically but keep honest label
    loadTimer = setTimeout(() => { if (!destroyed && state === 'loading') setState('playing'); }, 4000);
  }

  function startHls() {
    teardownMedia();
    clearPanel();
    setState('loading');
    want = true;
    registerLive(context === 'modal' ? 'modal' : 'stage');
    const url = streamUrlFor(cam);            // relay url for server-resolved iframe rows
    vid = document.createElement('video');
    vid.className = 'pl-video';
    vid.muted = true;
    vid.defaultMuted = true;
    vid.playsInline = true;
    vid.setAttribute('playsinline', '');
    vid.setAttribute('muted', '');
    vid.autoplay = true;
    vid.referrerPolicy = 'no-referrer';
    vid.controls = false;
    mediaHost.appendChild(vid);
    mediaHost.classList.add('on');

    let settled = false;
    const fail = (why) => {
      if (settled || destroyed) return;
      settled = true;
      clearTimeout(loadTimer);
      teardownMedia();
      stopBudget();
      const status = cam && cam.status === 'dead' ? ' The registry lists this feed as dead.' : '';
      fallbackPanel('HLS stream did not start',
        (why === 'timeout'
          ? 'The stream did not deliver video in 12 seconds.'
          : 'The feed may be offline, or the browser blocked it (CORS).')
        + status + ' Nothing is shown rather than a fake preview.');
      setState('error');
    };
    const ok = () => {
      if (settled || destroyed) return;
      settled = true;
      clearTimeout(loadTimer);
      setState('playing');
    };
    vid.addEventListener('loadeddata', ok, { once: true });
    vid.addEventListener('error', () => { if (vid && vid.readyState < 2 && !vid.currentSrc) { /* ignore pre-src */ } });
    loadTimer = setTimeout(() => { if (!settled && (!vid || vid.readyState < 2)) fail('timeout'); }, 12000);

    const protoSet = typeof vid.canPlayType === 'function' ? vid.canPlayType('application/vnd.apple.mpegurl') : '';
    if (window.Hls && window.Hls.isSupported()) {
      hlsObj = new window.Hls({ enableWorker: true });
      hlsObj.on(window.Hls.Events.ERROR, (evt, data) => {
        if (data && data.fatal) fail(data.type === window.Hls.ErrorTypes.NETWORK_ERROR ? 'network' : 'fatal');
      });
      hlsObj.attachMedia(vid);
      hlsObj.loadSource(url);
    } else if (protoSet) {
      vid.src = url;
    } else {
      fail('unsupported');
      return;
    }
    const p = vid.play();
    if (p && p.catch) p.catch(() => {
      // autoplay blocked by the browser — keep the poster-ish frame and invite a click
      if (!settled && !destroyed) {
        setState('paused');
        captionMsg('autoplay blocked — click play');
      }
    });
  }

  function startMjpeg() {
    teardownMedia();
    clearPanel();
    setState('loading');
    want = true;
    registerLive(context === 'modal' ? 'modal' : 'stage');
    mjpegEl = document.createElement('img');
    mjpegEl.className = 'pl-video pl-mjpeg';
    mjpegEl.referrerPolicy = 'no-referrer';
    mjpegEl.alt = cam.name || 'mjpeg stream';
    let settled = false;
    mjpegEl.addEventListener('load', () => {
      if (settled || destroyed) return;
      settled = true;
      clearTimeout(loadTimer);
      mediaHost.classList.add('on');
      setState('playing');
    });
    mjpegEl.addEventListener('error', () => {
      if (settled || destroyed) return;
      settled = true;
      clearTimeout(loadTimer);
      stopBudget();
      fallbackPanel('MJPEG stream did not start',
        (cam && cam.status === 'dead' ? 'The registry lists this feed as dead. ' : '')
        + 'The feed may be offline, or the browser blocked it (CORS).');
      setState('error');
    });
    loadTimer = setTimeout(() => { if (!settled && !destroyed) { settled = true; stopBudget(); fallbackPanel('MJPEG stream did not start', 'The stream did not deliver an image in 12 seconds — feed offline or blocked.'); setState('error'); } }, 12000);
    mediaHost.appendChild(mjpegEl);
    mjpegEl.src = cam.url;
  }

  function startStill() {
    if (!cam || !cam.url) return;
    want = true;
    clearPanel();
    if (!imgEl) {
      imgEl = document.createElement('img');
      imgEl.className = 'pl-video pl-still';
      imgEl.referrerPolicy = 'no-referrer';
      imgEl.alt = cam.name || 'still image';
      imgEl.addEventListener('load', () => {
        lastStillAt = new Date();
        captionMsg('updated ' + clockNow());
        el.classList.remove('still-error');
      });
      imgEl.addEventListener('error', () => {
        if (lastStillAt) {
          el.classList.add('still-error');
          captionMsg('refresh failed — last success ' + fmtClockLocal(lastStillAt));
        } else {
          fallbackPanel('Still did not load', 'The image did not load — feed offline or blocked (CORS).');
          setState('error');
        }
      });
      mediaHost.appendChild(imgEl);
      mediaHost.classList.add('on');
    }
    setState('playing');
    imgEl.src = bust(cam.url);
    scheduleStill();
  }

  function fmtClockLocal(d) {
    const p = (x) => (x < 10 ? '0' : '') + x;
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  function scheduleStill() {
    clearTimeout(stillTimer);
    if (destroyed || !imgEl) return;
    const s = Math.max(5, Number((store.settings && store.settings.still_refresh_s) || 30));
    stillTimer = setTimeout(() => {
      if (destroyed || !imgEl) return;
      if (!visible || document.hidden || !want) { scheduleStill(); return; }
      imgEl.src = bust(cam.url);
      scheduleStill();
    }, s * 1000);
  }

  function refreshStill() {
    if (imgEl && cam && cam.url) imgEl.src = bust(cam.url);
    else startStill();
  }

  function captionMsg(text) {
    captionEl.textContent = text || '';
    captionEl.classList.toggle('on', !!text);
  }

  /* -- offscreen / hidden handling ---------------------------------------- */

  function handleHidden(hidden) {
    if (destroyed || !cam) return;
    const lose = hidden;
    const proto = String(cam.protocol || '').toLowerCase();
    const relay = !!relayUrl(cam);            // server-relayed iframe rows behave like hls
    if (lose) {
      if ((proto === 'youtube' || proto === 'hls' || proto === 'mjpeg' || relay) && state === 'playing') {
        autoPaused = true;
        if (proto === 'hls' || relay) {
          stopBudget();
          if (vid) { try { vid.pause(); } catch (err) { /* noop */ } }
          setState('paused');
        } else {
          pause({ keepWant: true });
          setState(proto === 'youtube' ? 'idle' : 'idle');
        }
        captionMsg('paused offscreen');
      }
    } else if (autoPaused) {
      autoPaused = false;
      if (want) { resume(); }
    }
  }

  function setupIO() {
    if (!('IntersectionObserver' in window)) return;
    io = new IntersectionObserver((entries) => {
      const e = entries[0];
      const vis = e.isIntersecting;
      if (vis === visible) return;
      visible = vis;
      handleHidden(!vis || document.hidden);
    }, { rootMargin: '120px' });
    io.observe(el);
  }

  /* -- actions row --------------------------------------------------------- */

  function heartHTML() {
    return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
  }

  function buildActions() {
    const h = opts.handlers || {};
    const fixed = [];
    fixed.push(`<button type="button" class="icon-btn" data-act="heart" title="Favourite (f)">${heartHTML()}</button>`);
    if (context !== 'stage') fixed.push('<button type="button" class="icon-btn" data-act="stage" title="Stage in Watch">' + STAGE_ICON + '</button>');
    fixed.push(`<button type="button" class="icon-btn" data-act="info" title="Details">${INFO_ICON}</button>`);
    if (cam && String(cam.protocol).toLowerCase() === 'jpeg') {
      fixed.push(`<button type="button" class="icon-btn" data-act="still" title="Refresh still">${REFRESH_ICON}</button>`);
    }
    if (cam && cam.url && !isMetadataOnly(cam)) {
      fixed.push(`<button type="button" class="icon-btn" data-act="open" title="Open original">${EXT_ICON}</button>`);
      fixed.push('<button type="button" class="icon-btn" data-act="copy" title="Copy stream URL">' + COPY_ICON + '</button>');
    }
    actionsEl.innerHTML = fixed.join('');

    // heart state
    const heart = actionsEl.querySelector('[data-act="heart"]');
    if (heart && h.isFav) heart.classList.toggle('on', !!h.isFav(cam.camera_id));

    actionsEl.querySelectorAll('button').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const act = b.dataset.act;
        playSound('click');
        if (act === 'heart' && h.onHeart) { Promise.resolve(h.onHeart(cam)).then(() => { if (h.isFav) b.classList.toggle('on', !!h.isFav(cam.camera_id)); }); }
        else if (act === 'stage' && h.onStage) h.onStage(cam);
        else if (act === 'info' && h.onInfo) h.onInfo(cam);
        else if (act === 'open' && h.onOpen) h.onOpen(cam);
        else if (act === 'copy' && h.onCopy) h.onCopy(cam);
        else if (act === 'still') refreshStill();
      });
    });
  }

  /* -- panels wiring ------------------------------------------------------- */

  panelsEl.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-pl]');
    if (!b) return;
    ev.stopPropagation();
    const act = b.dataset.pl;
    playSound('click');
    if (act === 'retry') { clearPanel(); play(); }
    else if (act === 'resume') resume();
    else if (act === 'open' && cam && cam.url) window.open(cam.url, '_blank', 'noopener');
    else if (act === 'copy' && cam && cam.url && opts.handlers && opts.handlers.onCopy) opts.handlers.onCopy(cam);
  });

  playBtn.addEventListener('click', (ev) => {
    ev.stopPropagation();
    playSound('toggle');
    if (want) pause(); else resume();
  });

  mediaHost.addEventListener('click', () => {
    if (state === 'paused' || state === 'idle') resume();
  });

  /* -- camera render ------------------------------------------------------- */

  function render() {
    if (!cam) return;
    el.dataset.proto = String(cam.protocol || 'unknown').toLowerCase();
    el.dataset.status = String(cam.status || 'unknown').toLowerCase();
    el.dataset.policy = isMetadataOnly(cam) ? 'metadata_only' : 'full';

    badgeEl.textContent = formatLabel(cam.protocol);
    badgeEl.className = 'fmt-badge fmt-' + String(cam.protocol || 'unknown').toLowerCase();

    const sm = statusMeta();
    statusEl.textContent = sm.label;
    statusEl.className = 'pl-status st st-' + sm.cls.replace(/[^a-z0-9_-]/g, '');
    statusEl.title = sm.hint;

    if (isMetadataOnly(cam)) el.classList.add('meta-only'); else el.classList.remove('meta-only');

    nameEl.textContent = cam.name || '(unnamed)';
    nameEl.title = cam.name || '';
    const bits = [];
    if (cam.city || cam.country) bits.push([cam.city, cam.country].filter(Boolean).join(', '));
    if (cam.source_family) bits.push(cam.source_family);
    subEl.textContent = bits.join(' · ');

    // idle poster
    posterHost.innerHTML = '';
    posterHost.appendChild(posterEl(cam));

    // single-state panels
    if (isMetadataOnly(cam)) { blockedPanel(); setState('blocked'); buildActions(); return; }
    if (!cam.url && String(cam.protocol).toLowerCase() !== 'iframe') { noUrlPanel(); setState('nourl'); buildActions(); return; }
    if (String(cam.protocol).toLowerCase() === 'jpeg') { buildActions(); if (opts.autoplay) startStill(); return; }
    if ((String(cam.protocol).toLowerCase() === 'iframe' || String(cam.protocol).toLowerCase() === 'unknown') && !relayUrl(cam)) {
      if (cam.url) noPlayPanel(); else noUrlPanel();
      setState(cam.url ? 'noplay' : 'nourl');
      buildActions();
      return;
    }
    // live formats: idle poster + play affordance
    buildActions();
    setState('idle');
    if (opts.autoplay) play();
  }

  function setCamera(next) {
    if (destroyed) return;
    teardownMedia();
    stopBudget();
    clearPanel();
    captionMsg('');
    want = false;
    capPaused = false;
    cam = next;
    render();
  }

  /* -- init ---------------------------------------------------------------- */

  setupIO();
  cam = camera;
  render();
  if (camera && opts.autoplay) play();

  return {
    el,
    api: {
      play: () => { want = true; capPaused = false; clearPanel(); play(); },
      pause: () => pause(),
      toggle: () => { if (state === 'playing') pause(); else play(); },
      resume,
      destroy: () => {
        destroyed = true;
        teardownMedia();
        stopBudget();
        if (io) { io.disconnect(); io = null; }
      },
      refreshStill,
      get state() { return state; },
      get playing() { return state === 'playing'; },
      setCamera,
    },
  };
}

/* shared inline icons used above (declared after use fails in const-land — these are
   function-scope constants initialised before createPlayer runs) */
const STAGE_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>';
const INFO_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>';
const COPY_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

/* ── hover live previews (wall cards; opt-in via settings.live_previews) ── */

export function startLivePreview(camera, hostEl, onEnd) {
  const stopper = { stop() {} };
  if (!camera || isMetadataOnly(camera)) return stopper;
  const proto = String(camera.protocol || '').toLowerCase();
  const relay = !!relayUrl(camera);        // server-relayed iframe rows preview like hls
  if (proto !== 'hls' && proto !== 'mjpeg' && !(proto === 'iframe' && relay)) return stopper;
  if (!camera.url) return stopper;

  const wrap = document.createElement('div');
  wrap.className = 'card-preview';
  hostEl.appendChild(wrap);
  let stopped = false;
  let vid = null;
  let hlsObj = null;
  const id = 'preview-' + camera.camera_id;

  function stop() {
    if (stopped) return;
    stopped = true;
    LiveBudget.unregister(id);
    if (hlsObj) { try { hlsObj.destroy(); } catch (err) { /* noop */ } hlsObj = null; }
    if (vid) { try { vid.pause(); } catch (err) { /* noop */ } }
    wrap.remove();
    if (onEnd) onEnd();
  }

  function fail() { stop(); }

  if (proto === 'hls' || (proto === 'iframe' && relay)) {
    vid = document.createElement('video');
    vid.muted = true;
    vid.defaultMuted = true;
    vid.playsInline = true;
    vid.setAttribute('playsinline', '');
    vid.referrerPolicy = 'no-referrer';
    wrap.appendChild(vid);
    LiveBudget.register(id, 'preview', stop);
    if (window.Hls && window.Hls.isSupported()) {
      hlsObj = new window.Hls({ enableWorker: true });
      let settled = false;
      hlsObj.on(window.Hls.Events.ERROR, (evt, data) => {
        if (data && data.fatal && !settled) { settled = true; fail(); }
      });
      hlsObj.attachMedia(vid);
      hlsObj.loadSource(streamUrlFor(camera));
    } else if (vid.canPlayType('application/vnd.apple.mpegurl')) {
      vid.src = streamUrlFor(camera);
    } else { fail(); return stopper; }
    const p = vid.play();
    if (p && p.catch) p.catch(() => {});
  } else {
    const img = document.createElement('img');
    img.referrerPolicy = 'no-referrer';
    img.alt = '';
    let settled = false;
    img.addEventListener('load', () => { if (!settled) { settled = true; wrap.classList.add('on'); } });
    img.addEventListener('error', () => { if (!settled) { settled = true; fail(); } });
    img.src = camera.url;
    wrap.appendChild(img);
    LiveBudget.register(id, 'preview', stop);
  }

  stopper.stop = stop;
  return stopper;
}

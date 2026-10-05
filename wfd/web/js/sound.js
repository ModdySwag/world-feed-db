/* wfd/web/js/sound.js — synthesized UI sounds (WebAudio; no assets, no CDN).
 *
 * Voices are tiny oscillator/noise envelopes, played through one master gain.
 * The AudioContext is created ONLY after a real user gesture (pointerdown /
 * keydown) — never on page load — so autoplay policies are respected and
 * nothing ever sounds before the user interacts.
 *
 * Public API:
 *   soundGestureHook()          — install the one-time gesture listeners (call at boot)
 *   playSound(name)             — play a voice: click | toggle | navigate |
 *                                 fav_add | fav_remove | success | error |
 *                                 palette_open | palette_close
 *   setSoundEnabled(bool)       — master mute
 *   setSoundVolume(0..1)        — master volume
 *   setSoundReducedMotion(bool) — when true, the 'navigate' whoosh is suppressed
 */
'use strict';

let ctx = null;
let master = null;
let enabled = true;
let volume = 0.35;
let reduced = false;
let broken = false;      // WebAudio unavailable -> all calls no-op
let gestureBound = false;

/* ── lifecycle ─────────────────────────────────────────────────────────── */

export function soundInit() {
  if (ctx || broken) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { broken = true; return; }
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = volume;
    master.connect(ctx.destination);
  } catch (err) {
    broken = true;
    ctx = null;
    master = null;
  }
}

export function soundGestureHook() {
  if (gestureBound) return;
  gestureBound = true;
  const wake = () => {
    soundInit();
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
  };
  // capture phase so the very first click/keypress wakes the context even if
  // the target handler runs later in the same event.
  document.addEventListener('pointerdown', wake, { passive: true, capture: true });
  document.addEventListener('keydown', wake, { capture: true });
}

export function setSoundEnabled(v) { enabled = !!v; }
export function isSoundEnabled() { return enabled; }

export function setSoundVolume(v) {
  volume = Math.min(1, Math.max(0, Number(v) || 0));
  if (master && ctx) {
    const now = ctx.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setTargetAtTime(volume, now, 0.02);
  }
}

export function setSoundReducedMotion(v) { reduced = !!v; }

/* ── tiny synth primitives ─────────────────────────────────────────────── */

function tone(t0, { freq = 440, dur = 0.08, type = 'sine', gain = 0.08, slideTo = 0 }) {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(master);
  osc.start(t0);
  osc.stop(t0 + dur + 0.03);
}

function noiseWhoosh(t0) {
  const dur = 0.22;
  const rate = ctx.sampleRate;
  const buf = ctx.createBuffer(1, Math.max(1, Math.floor(rate * dur)), rate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) {
    // fade the noise so the bandpass sweep reads as a soft whoosh, not a hiss
    data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.Q.value = 1.1;
  bp.frequency.setValueAtTime(420, t0);
  bp.frequency.exponentialRampToValueAtTime(1500, t0 + dur * 0.8);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.05, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(bp).connect(g).connect(master);
  src.start(t0);
  src.stop(t0 + dur + 0.02);
}

/* ── voices ────────────────────────────────────────────────────────────── */

const VOICES = {
  // crisp, very short — UI feedback, not music
  click: (t) => tone(t, { freq: 1400, dur: 0.035, type: 'square', gain: 0.05 }),
  toggle: (t) => tone(t, { freq: 900, dur: 0.045, type: 'triangle', gain: 0.07 }),
  // soft filtered-noise sweep
  navigate: (t) => noiseWhoosh(t),
  // two-note up / down
  fav_add: (t) => { tone(t, { freq: 587.33, dur: 0.07, type: 'triangle', gain: 0.09 }); tone(t + 0.075, { freq: 880, dur: 0.10, type: 'triangle', gain: 0.09 }); },
  fav_remove: (t) => { tone(t, { freq: 880, dur: 0.07, type: 'triangle', gain: 0.08 }); tone(t + 0.075, { freq: 587.33, dur: 0.11, type: 'triangle', gain: 0.08 }); },
  // three-note chime (exports, "all saved" moments)
  success: (t) => { tone(t, { freq: 523.25, dur: 0.11, type: 'sine', gain: 0.07 }); tone(t + 0.08, { freq: 659.25, dur: 0.11, type: 'sine', gain: 0.07 }); tone(t + 0.16, { freq: 783.99, dur: 0.20, type: 'sine', gain: 0.07 }); },
  // two low blips
  error: (t) => { tone(t, { freq: 196, dur: 0.07, type: 'square', gain: 0.05 }); tone(t + 0.1, { freq: 165, dur: 0.10, type: 'square', gain: 0.05 }); },
  palette_open: (t) => tone(t, { freq: 660, dur: 0.09, type: 'sine', gain: 0.06, slideTo: 990 }),
  palette_close: (t) => tone(t, { freq: 990, dur: 0.09, type: 'sine', gain: 0.05, slideTo: 660 }),
};

/* ── play ──────────────────────────────────────────────────────────────── */

export function playSound(name) {
  if (!enabled || !ctx || broken || ctx.state === 'closed') return;
  if (reduced && name === 'navigate') return;           // reduced-motion law: no whoosh
  const voice = VOICES[name];
  if (!voice) return;
  const run = () => {
    try { voice(ctx.currentTime + 0.005); } catch (err) { /* never break the UI for a sound */ }
  };
  if (ctx.state === 'suspended') {
    ctx.resume().then(run).catch(() => {});
  } else {
    run();
  }
}

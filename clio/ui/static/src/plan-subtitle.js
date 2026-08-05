// Pure helpers for plan-preview floating subtitles. No DOM.

import { api } from './api.js';
import { state } from './state.js';
import { buildTimeline } from './plan-timeline.js';

const SENTENCE_BREAKS = '。！？；…!?;';
const BREAK_SET = new Set(SENTENCE_BREAKS.split(''));
const MAX_PLUS_CARRY = 4; // allow punctuation to overflow maxLen slightly

/**
 * Split narration text into subtitle lines by Chinese/ASCII sentence
 * punctuation and newlines; further break lines longer than maxLen.
 * @param {string} text
 * @param {number} [maxLen=16]
 * @returns {string[]}
 */
export function splitSubtitleLines(text, maxLen = 16) {
  const normalized = String(text || '').trim();
  if (!normalized) return [];
  const tokens = [];
  let buf = '';
  for (const ch of normalized) {
    buf += ch;
    if (BREAK_SET.has(ch) || ch === '\n') {
      tokens.push(buf);
      buf = '';
    }
  }
  if (buf.trim()) tokens.push(buf);
  const sentences = tokens.map((t) => t.trim()).filter(Boolean);

  const lines = [];
  for (const sentence of sentences) {
    if (sentence.length <= maxLen + MAX_PLUS_CARRY) {
      lines.push(sentence);
      continue;
    }
    let start = 0;
    while (start < sentence.length) {
      lines.push(sentence.slice(start, start + maxLen));
      start += maxLen;
    }
  }
  return lines;
}

/**
 * Evenly distribute lineCount lines across a segment duration.
 * @param {number} durationSec
 * @param {number} lineCount
 * @returns {Array<{startSec: number, endSec: number, index: number}>}
 */
export function scheduleSubtitleTiming(durationSec, lineCount) {
  const d = Number(durationSec);
  const n = Number(lineCount);
  if (!(d > 0) || !Number.isFinite(d)) return [];
  if (!(n > 0) || !Number.isFinite(n)) return [];
  const step = d / n;
  const out = [];
  for (let i = 0; i < n; i++) {
    const start = i * step;
    const end = i === n - 1 ? d : (i + 1) * step;
    out.push({ startSec: start, endSec: end, index: i });
  }
  return out;
}

/**
 * Index of the subtitle line active at localSec, or null when out of range.
 * Half-open intervals [startSec, endSec).
 * @param {{startSec:number,endSec:number,index:number}[]} schedule
 * @param {number} localSec
 * @returns {number|null}
 */
export function subtitleIndexAtTime(schedule, localSec) {
  if (!Array.isArray(schedule) || schedule.length === 0) return null;
  const t = Number(localSec);
  if (!Number.isFinite(t)) return null;
  for (const slot of schedule) {
    if (t >= slot.startSec && t < slot.endSec) return slot.index;
  }
  return null;
}

const _voiceoverCache = new Map(); // index -> Promise<string|null>

/** Default fetcher: loads the voiceover file via clio api(). */
async function apiFetch(scriptJson) {
  return api('GET', `/api/voiceover?file=${encodeURIComponent(scriptJson)}`);
}

/**
 * Get spoken narration text for a video index. Cached per index.
 * fetchFn returns the raw voiceover JSON (e.g. {voiceover, ...}); the
 * `voiceover` string field is extracted and trimmed here.
 * @param {string|number} index
 * @param {string|null} scriptJson  video.script_json basename
 * @param {function|null} [fetchFn] injectable fetcher (tests); default apiFetch
 * @returns {Promise<string|null>}
 */
export function loadVoiceoverText(index, scriptJson, fetchFn = apiFetch) {
  const key = String(index ?? '');
  const cached = _voiceoverCache.get(key);
  if (cached) return cached;
  if (!scriptJson) {
    const p = Promise.resolve(null);
    _voiceoverCache.set(key, p);
    return p;
  }
  const p = Promise.resolve()
    .then(() => fetchFn(scriptJson))
    .then((d) => {
      const text = d && typeof d.voiceover === 'string' ? d.voiceover.trim() : '';
      return text || null;
    })
    .catch(() => null);
  _voiceoverCache.set(key, p);
  return p;
}

/**
 * Build a context object from the current app state for renderPlanSubtitle.
 * Pure and cheap -> callable from every timeupdate.
 */
function readStateContext() {
  return {
    entity: state.currentEntity,
    previewIndex: state.previewIndex,
    plan: state.plan,
    videos: state.videos,
    previewGlobalSec: state.previewGlobalSec,
  };
}

/** @returns {HTMLElement|null} */
function subtitleElement() {
  return document.getElementById('plan-subtitle');
}

/**
 * Render the active subtitle line into #plan-subtitle; hide when nothing
 * should show. opts.ctx overrides reading app state (tests). opts.textFor
 * resolves the narration text for (index, scriptJson); default loadVoiceoverText.
 *
 * @param {{ctx?: object, textFor?: function}} [opts]
 * @returns {Promise<void>}
 */
export async function renderPlanSubtitle(opts = {}) {
  const el = subtitleElement();
  if (!el) return;
  const c = opts.ctx || readStateContext();
  const textFor = opts.textFor || loadVoiceoverText;
  const clear = () => { el.hidden = true; el.dataset.line = ''; };

  if (c.entity !== 'plan' || !Number.isFinite(c.previewIndex) || c.previewIndex < 0) {
    clear(); return;
  }
  const p = c.plan;
  const seg = p?.sequence?.[c.previewIndex];
  if (!seg) { clear(); return; }

  const idx = String(seg.index ?? '');
  const v = (c.videos || []).find((x) => String(x.index) === idx);
  if (!v || !v.script_json) { clear(); return; }

  const text = await textFor(idx, v.script_json);
  // Stale-guard: user may have sought to another segment while awaiting.
  const live = opts.ctx ? opts.ctx : readStateContext();
  const current = live.entity === 'plan'
    && live.previewIndex === c.previewIndex
    && String(live.plan?.sequence?.[live.previewIndex]?.index ?? '') === idx;
  if (!current || !text) { clear(); return; }

  const lines = splitSubtitleLines(text);
  if (!lines.length) { clear(); return; }

  const tl = buildTimeline((p?.sequence) || []);
  const tseg = tl.segments[c.previewIndex];
  if (!tseg || tseg.duration <= 0) { clear(); return; }

  const schedule = scheduleSubtitleTiming(tseg.duration, lines.length);
  const localSec = Math.min(tseg.duration, Math.max(0, c.previewGlobalSec - tseg.globalStart));
  const lineIdx = subtitleIndexAtTime(schedule, localSec);
  if (lineIdx == null) { clear(); return; }

  const content = lines[lineIdx];
  if (el.dataset.line === String(lineIdx) && !el.hidden && el.textContent === content) {
    return; // no change
  }
  el.textContent = content;
  el.dataset.line = String(lineIdx);
  el.hidden = false;
}

/** Hide the subtitle layer (e.g. leaving plan mode / stopping preview). */
export function hidePlanSubtitle() {
  const el = subtitleElement();
  if (el) { el.hidden = true; el.dataset.line = ''; }
}

/** Production entry point: render from current app state. */
export function renderPlanSubtitleFromState() {
  return renderPlanSubtitle({ textFor: loadVoiceoverText });
}
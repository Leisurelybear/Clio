// Pure helpers for plan-preview floating subtitles. No DOM.

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
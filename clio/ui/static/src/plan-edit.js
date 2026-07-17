/** Pure helpers for plan sequence structural edits (no DOM). */

export function reorderSequence(sequence, fromIndex, toIndex) {
  const arr = sequence.slice();
  if (fromIndex < 0 || toIndex < 0 || fromIndex >= arr.length || toIndex >= arr.length) {
    return arr;
  }
  const [item] = arr.splice(fromIndex, 1);
  arr.splice(toIndex, 0, item);
  return arr;
}

/**
 * Map drag-over target to reorderSequence toIndex (final index of moved item).
 * insertBefore = placeAfter ? over+1 : over; same gap as current → null;
 * toIndex = insertBefore > from ? insertBefore - 1 : insertBefore.
 * @param {number} fromIndex
 * @param {number} overIndex segment under pointer
 * @param {boolean} placeAfter true if pointer in lower half of over segment
 * @param {number} length sequence length
 * @returns {number|null}
 */
export function computeDropToIndex(fromIndex, overIndex, placeAfter, length) {
  const n = Number(length) | 0;
  const from = Number(fromIndex);
  const over = Number(overIndex);
  if (!Number.isFinite(from) || !Number.isFinite(over) || n <= 0) return null;
  if (from < 0 || from >= n || over < 0 || over >= n) return null;

  let insertBefore = placeAfter ? over + 1 : over;
  if (insertBefore < 0) insertBefore = 0;
  if (insertBefore > n) insertBefore = n;

  if (insertBefore === from || insertBefore === from + 1) return null;

  return insertBefore > from ? insertBefore - 1 : insertBefore;
}

/**
 * Pixels to scroll a viewport while dragging near its top/bottom edge.
 * Negative = scroll up. Zero when pointer is in the safe middle band.
 * @param {number} clientY pointer Y
 * @param {number} viewportTop getBoundingClientRect().top
 * @param {number} viewportBottom getBoundingClientRect().bottom
 * @param {number} [edgePx=48] edge band height
 * @param {number} [maxStep=18] max scroll per event at the extreme edge
 * @returns {number}
 */
export function computeDragAutoScrollDelta(
  clientY,
  viewportTop,
  viewportBottom,
  edgePx = 48,
  maxStep = 18,
) {
  const y = Number(clientY);
  const top = Number(viewportTop);
  const bottom = Number(viewportBottom);
  if (!Number.isFinite(y) || !Number.isFinite(top) || !Number.isFinite(bottom)) return 0;
  if (bottom <= top) return 0;
  const edge = Math.max(8, Number(edgePx) || 48);
  const max = Math.max(1, Number(maxStep) || 18);
  if (y < top + edge) {
    const t = Math.min(1, (top + edge - y) / edge);
    return -Math.ceil(max * t);
  }
  if (y > bottom - edge) {
    const t = Math.min(1, (y - (bottom - edge)) / edge);
    return Math.ceil(max * t);
  }
  return 0;
}

export function removeSegment(sequence, index) {
  return sequence.filter((_, i) => i !== index);
}

export function patchSegment(segment, fields) {
  return { ...segment, ...fields };
}

/** Format seconds as MM:SS (minutes may exceed 59 for long clips). */
export function formatTimelineSec(sec) {
  const n = Number(sec);
  if (!Number.isFinite(n) || n < 0) return '00:00';
  const total = Math.floor(n);
  const m = Math.floor(total / 60).toString().padStart(2, '0');
  const s = (total % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function parseTimelineParts(range) {
  const raw = String(range || '').trim();
  if (!raw) return null;
  const parts = raw.split('-');
  if (parts.length < 2) return null;
  return { start: parts[0].trim(), end: parts.slice(1).join('-').trim() };
}

function timecodeToSec(tc) {
  if (!tc) return null;
  const parts = String(tc).split(':').map(Number);
  if (parts.some((x) => !Number.isFinite(x))) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 1) return parts[0];
  return null;
}

/**
 * Set start or end of use_timeline from player seconds.
 * @param {string} currentRange existing "MM:SS-MM:SS" or empty
 * @param {'start'|'end'} which
 * @param {number} sec player currentTime
 * @returns {string}
 */
export function setTimelineBound(currentRange, which, sec) {
  const t = formatTimelineSec(sec);
  const parts = parseTimelineParts(currentRange);
  let startSec = parts ? timecodeToSec(parts.start) : null;
  let endSec = parts ? timecodeToSec(parts.end) : null;
  const newSec = Number.isFinite(sec) && sec >= 0 ? Math.floor(sec) : 0;

  if (which === 'start') {
    startSec = newSec;
    if (endSec == null || endSec <= startSec) endSec = startSec + 5;
  } else {
    endSec = newSec;
    if (startSec == null || startSec >= endSec) startSec = Math.max(0, endSec - 5);
  }
  return `${formatTimelineSec(startSec)}-${formatTimelineSec(endSec)}`;
}

/**
 * Insert a new segment after atIndex (-1 = prepend).
 * @param {Array} sequence
 * @param {number} atIndex index after which to insert; -1 prepends
 * @param {{index: string, title?: string, reason?: string, use_timeline?: string, voiceover_hint?: string}} fields
 */
export function insertSegment(sequence, atIndex, fields) {
  const seg = {
    index: String(fields?.index ?? ''),
    title: fields?.title ?? '',
    reason: fields?.reason ?? '',
    use_timeline: fields?.use_timeline ?? '',
    voiceover_hint: fields?.voiceover_hint ?? '',
  };
  const arr = sequence.slice();
  const insertAt = Math.max(0, Math.min(arr.length, Number(atIndex) + 1));
  arr.splice(insertAt, 0, seg);
  return arr;
}

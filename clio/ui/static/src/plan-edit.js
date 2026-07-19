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
 * @param {number} sec timeline seconds in the same timebase as use_timeline
 *   (segment-local / plan-local — NOT raw player.currentTime when offset_sec applies)
 * @returns {string}
 */
export function setTimelineBound(currentRange, which, sec) {
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
 * Convert player.currentTime to plan use_timeline seconds.
 * Preview seeks with plan_sec + offset_sec; write path must subtract the same offset.
 * @param {number} playerSec player.currentTime
 * @param {number} [offsetSec=0] video.offset_sec (legacy split / original absolute)
 * @returns {number|null} null if playerSec invalid
 */
export function planSecFromPlayer(playerSec, offsetSec = 0) {
  const t = Number(playerSec);
  if (!Number.isFinite(t)) return null;
  const off = Number(offsetSec);
  const o = Number.isFinite(off) && off > 0 ? off : 0;
  return Math.max(0, t - o);
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

/**
 * Expanded index after deleting deletedIndex; newLength is length after delete.
 * @param {number|null|undefined} expanded
 * @param {number} deletedIndex
 * @param {number} newLength
 * @returns {number|null}
 */
export function nextExpandedAfterDelete(expanded, deletedIndex, newLength) {
  if (expanded == null || !Number.isFinite(Number(expanded))) return null;
  const n = Number(newLength) | 0;
  if (n <= 0) return null;
  let e = Number(expanded);
  const d = Number(deletedIndex);
  if (Number.isFinite(d) && e > d) e -= 1;
  if (e < 0) return null;
  if (e >= n) e = n - 1;
  return e;
}

/**
 * Expanded index for a segment inserted after afterIndex (-1 = prepend → index 0).
 * @param {number} afterIndex
 * @returns {number}
 */
export function nextExpandedAfterInsert(afterIndex) {
  const a = Number(afterIndex);
  if (!Number.isFinite(a) || a < -1) return 0;
  return a + 1;
}

/**
 * Expanded index after reorderSequence(from, to).
 * @param {number} fromIndex
 * @param {number} toIndex
 * @param {number|null|undefined} expanded
 * @returns {number|null}
 */
export function nextExpandedAfterMove(fromIndex, toIndex, expanded) {
  if (expanded == null || !Number.isFinite(Number(expanded))) return null;
  const from = Number(fromIndex);
  const to = Number(toIndex);
  let e = Number(expanded);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return e;
  if (e === from) return to;
  if (e > from) e -= 1;
  if (e >= to) e += 1;
  return e;
}

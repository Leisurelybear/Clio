/** Pure plan composite timeline helpers (no DOM). */

function parseTimecode(s) {
  if (!s) return 0;
  const parts = String(s).split(':').map(parseFloat);
  if (parts.length === 3 && parts.every(Number.isFinite)) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2 && parts.every(Number.isFinite)) {
    return parts[0] * 60 + parts[1];
  }
  return parseFloat(s) || 0;
}

function parseRange(useTimeline) {
  const parts = String(useTimeline || '').split('-');
  if (parts.length < 2) return { planStart: 0, planEnd: 0, duration: 0 };
  const planStart = parseTimecode(parts[0].trim());
  const planEnd = parseTimecode(parts[1].trim());
  const duration = Math.max(0, planEnd - planStart);
  return { planStart, planEnd, duration };
}

/**
 * @param {Array<{index?: string, use_timeline?: string}>} sequence
 * @returns {{ segments: Array, total: number }}
 */
export function buildTimeline(sequence) {
  const segs = Array.isArray(sequence) ? sequence : [];
  const segments = [];
  let g = 0;
  for (let i = 0; i < segs.length; i++) {
    const { planStart, planEnd, duration } = parseRange(segs[i]?.use_timeline);
    const globalStart = g;
    const globalEnd = g + duration;
    segments.push({
      segIndex: i,
      videoIndex: String(segs[i]?.index ?? ''),
      planStart,
      planEnd,
      duration,
      globalStart,
      globalEnd,
    });
    g = globalEnd;
  }
  return { segments, total: g };
}

/**
 * @param {{ total?: number }} timeline
 * @param {number} globalSec
 * @returns {number}
 */
export function clampGlobal(timeline, globalSec) {
  const total = timeline?.total || 0;
  const t = Number(globalSec);
  if (!Number.isFinite(t) || t < 0) return 0;
  if (total <= 0) return 0;
  if (t > total) return total;
  return t;
}

/**
 * Next segment index with duration > 0 after fromIndex (exclusive).
 * fromIndex = -1 means first playable.
 * @param {{ segments?: Array }} timeline
 * @param {number} fromIndex
 * @returns {number|null}
 */
export function nextPlayableSegIndex(timeline, fromIndex) {
  const segs = timeline?.segments || [];
  const start = (Number(fromIndex) | 0) + 1;
  for (let i = Math.max(0, start); i < segs.length; i++) {
    if (segs[i].duration > 0) return i;
  }
  return null;
}

/**
 * @param {{ segments?: Array, total?: number }} timeline
 * @param {number} globalSec
 * @returns {{ segIndex: number, localSec: number, planSec: number, videoIndex: string } | null}
 */
export function globalToLocal(timeline, globalSec) {
  const segs = timeline?.segments || [];
  if (!segs.length) return null;
  const t = clampGlobal(timeline, globalSec);

  let idx = segs.length - 1;
  for (let i = 0; i < segs.length; i++) {
    if (t < segs[i].globalEnd) {
      idx = i;
      break;
    }
  }

  if (segs[idx].duration === 0) {
    const n = nextPlayableSegIndex(timeline, idx - 1);
    if (n != null) idx = n;
  }

  const seg = segs[idx];
  const localSec = seg.duration > 0
    ? Math.min(seg.duration, Math.max(0, t - seg.globalStart))
    : 0;
  return {
    segIndex: idx,
    localSec,
    planSec: seg.planStart + localSec,
    videoIndex: seg.videoIndex,
  };
}

/**
 * @param {{ segments?: Array }} timeline
 * @param {number} segIndex
 * @param {number} localSec
 * @returns {number}
 */
export function localToGlobal(timeline, segIndex, localSec) {
  const seg = timeline?.segments?.[segIndex];
  if (!seg) return 0;
  const local = Number(localSec);
  const l = Number.isFinite(local) ? Math.min(seg.duration, Math.max(0, local)) : 0;
  return seg.globalStart + l;
}

/**
 * Width fractions 0..1 per segment (sum ≈ 1).
 * @param {{ segments?: Array, total?: number }} timeline
 * @returns {number[]}
 */
export function segmentWidths(timeline) {
  const segs = timeline?.segments || [];
  const n = segs.length;
  if (!n) return [];
  const total = timeline.total || 0;
  if (total <= 0) return segs.map(() => 1 / n);
  return segs.map((s) => s.duration / total);
}

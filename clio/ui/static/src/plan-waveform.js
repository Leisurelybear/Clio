/** Pure helpers: stitch per-source waveform peaks onto a plan composite timeline. */

/**
 * Slice source peaks for plan-local [planStart, planEnd) on a file covering [0, sourceDurationSec].
 * @param {number[]} peaks
 * @param {number} sourceDurationSec
 * @param {number} planStart
 * @param {number} planEnd
 * @returns {number[]}
 */
export function slicePeaks(peaks, sourceDurationSec, planStart, planEnd) {
  const arr = Array.isArray(peaks) ? peaks : [];
  const n = arr.length;
  const dur = Number(sourceDurationSec);
  if (!n || !(dur > 0)) return [];
  const s = Math.max(0, Number(planStart) || 0);
  const e = Math.max(s, Number(planEnd) || 0);
  const i0 = Math.min(n, Math.max(0, Math.floor((s / dur) * n)));
  const i1 = Math.min(n, Math.max(i0, Math.ceil((Math.min(e, dur) / dur) * n)));
  return arr.slice(i0, i1);
}

/**
 * Max-pool (or pad) peaks to exactly targetLen bins.
 * @param {number[]} peaks
 * @param {number} targetLen
 * @returns {number[]}
 */
export function resamplePeaksMax(peaks, targetLen) {
  const t = Math.max(0, Number(targetLen) | 0);
  const arr = Array.isArray(peaks) ? peaks : [];
  if (t === 0) return [];
  if (!arr.length) return Array(t).fill(0);
  if (arr.length === t) return arr.slice();
  const out = new Array(t);
  for (let i = 0; i < t; i++) {
    const a = Math.floor((i / t) * arr.length);
    const b = Math.max(a + 1, Math.floor(((i + 1) / t) * arr.length));
    let m = 0;
    for (let j = a; j < b && j < arr.length; j++) {
      const v = Number(arr[j]) || 0;
      if (v > m) m = v;
    }
    out[i] = m;
  }
  return out;
}

/**
 * @param {{ segments?: Array, total?: number }} timeline from buildTimeline
 * @param {Record<string, { peaks: number[], duration_sec: number } | null | 'pending' | undefined>} byVideoIndex
 * @param {{ targetBins?: number }} [opts]
 * @returns {{ peaks: number[], total: number, targetBins: number, missingSegIndexes: number[] }}
 */
export function composePlanPeaks(timeline, byVideoIndex, opts = {}) {
  const total = timeline?.total || 0;
  const segs = (timeline?.segments || []).filter((s) => (s.duration || 0) > 0);

  let targetBins = opts.targetBins != null
    ? Number(opts.targetBins)
    : Math.round(total * 2);
  if (!Number.isFinite(targetBins)) targetBins = 400;
  targetBins = Math.max(400, Math.min(2000, targetBins | 0));

  if (!segs.length || total <= 0) {
    return {
      peaks: Array(targetBins).fill(0),
      total,
      targetBins,
      missingSegIndexes: [],
    };
  }

  const bins = segs.map((s) => Math.max(1, Math.round((s.duration / total) * targetBins)));
  let sum = bins.reduce((a, b) => a + b, 0);
  bins[bins.length - 1] = Math.max(1, bins[bins.length - 1] + (targetBins - sum));

  const peaks = [];
  const missingSegIndexes = [];

  segs.forEach((seg, k) => {
    const need = bins[k];
    const entry = byVideoIndex?.[seg.videoIndex];
    if (!entry || entry === 'pending' || !Array.isArray(entry.peaks)) {
      for (let i = 0; i < need; i++) peaks.push(0);
      missingSegIndexes.push(seg.segIndex);
      return;
    }
    const sliced = slicePeaks(
      entry.peaks,
      entry.duration_sec,
      seg.planStart,
      seg.planEnd,
    );
    const part = resamplePeaksMax(sliced, need);
    for (let i = 0; i < part.length; i++) peaks.push(part[i]);
  });

  if (peaks.length > targetBins) {
    return {
      peaks: peaks.slice(0, targetBins),
      total,
      targetBins,
      missingSegIndexes,
    };
  }
  while (peaks.length < targetBins) peaks.push(0);
  return { peaks, total, targetBins, missingSegIndexes };
}

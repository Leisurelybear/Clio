import { describe, it, expect } from 'vitest';
import {
  slicePeaks,
  resamplePeaksMax,
  composePlanPeaks,
} from '../plan-waveform.js';
import { buildTimeline } from '../plan-timeline.js';

describe('slicePeaks', () => {
  const peaks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]; // 10 bins, 10s → 1s each

  it('mid range', () => {
    const s = slicePeaks(peaks, 10, 2, 5);
    expect(s).toEqual([0.2, 0.3, 0.4]);
  });

  it('clamps past duration', () => {
    const s = slicePeaks(peaks, 10, 8, 20);
    expect(s.length).toBeGreaterThan(0);
    expect(s[s.length - 1]).toBe(0.9);
  });

  it('empty on bad input', () => {
    expect(slicePeaks([], 10, 0, 5)).toEqual([]);
    expect(slicePeaks(peaks, 0, 0, 5)).toEqual([]);
  });
});

describe('resamplePeaksMax', () => {
  it('pads zeros when empty source', () => {
    expect(resamplePeaksMax([], 4)).toEqual([0, 0, 0, 0]);
  });

  it('downsamples with max', () => {
    const out = resamplePeaksMax([0, 1, 0, 0.5], 2);
    expect(out).toHaveLength(2);
    expect(out[0]).toBe(1);
    expect(out[1]).toBe(0.5);
  });

  it('identity length', () => {
    expect(resamplePeaksMax([0.2, 0.4], 2)).toEqual([0.2, 0.4]);
  });
});

describe('composePlanPeaks', () => {
  const seq = [
    { index: '001', use_timeline: '00:00-00:10' },
    { index: '002', use_timeline: '00:00-00:05' },
  ];

  it('two segments proportional bins sum to targetBins', () => {
    const tl = buildTimeline(seq);
    // force small target via opts then clamp forces 400 min
    const by = {
      '001': { peaks: Array(20).fill(0.5), duration_sec: 10 },
      '002': { peaks: Array(10).fill(0.8), duration_sec: 5 },
    };
    const r = composePlanPeaks(tl, by, { targetBins: 100 });
    expect(r.targetBins).toBe(400); // clamped min
    expect(r.peaks).toHaveLength(400);
    expect(r.total).toBe(15);
    expect(r.missingSegIndexes).toEqual([]);
  });

  it('missing peaks zero-fills and records missing', () => {
    const tl = buildTimeline(seq);
    const by = {
      '001': { peaks: Array(20).fill(1), duration_sec: 10 },
    };
    const r = composePlanPeaks(tl, by, { targetBins: 600 });
    expect(r.targetBins).toBe(600);
    expect(r.peaks).toHaveLength(600);
    expect(r.missingSegIndexes).toContain(1);
    // some zeros present
    expect(r.peaks.some((p) => p === 0)).toBe(true);
  });

  it('zero-duration segment skipped', () => {
    const tl = buildTimeline([
      { index: 'a', use_timeline: '00:00-00:10' },
      { index: 'b', use_timeline: '' },
    ]);
    const r = composePlanPeaks(tl, {
      a: { peaks: Array(20).fill(0.3), duration_sec: 10 },
    }, { targetBins: 400 });
    expect(r.peaks).toHaveLength(400);
    expect(r.missingSegIndexes).toEqual([]);
  });

  it('clamps targetBins to 2000 max', () => {
    const tl = buildTimeline([{ index: 'a', use_timeline: '00:00-00:10' }]);
    const r = composePlanPeaks(tl, {
      a: { peaks: Array(20).fill(0.1), duration_sec: 10 },
    }, { targetBins: 99999 });
    expect(r.targetBins).toBe(2000);
    expect(r.peaks).toHaveLength(2000);
  });
});

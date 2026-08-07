import { describe, it, expect } from 'vitest';
import {
  planSubtitleBatches,
  scheduleBatchTiming,
  packAtTime,
  computeFontShrink,
} from '../plan-subtitle.js';

describe('planSubtitleBatches', () => {
  it('packs short sentences into a single batch', () => {
    const b = planSubtitleBatches('今天。出发。', { mode: 'auto', maxLines: 2, maxLen: 16 });
    expect(b).toHaveLength(1);
  });

  it('auto: long text packs to maxLines per batch', () => {
    const b = planSubtitleBatches('第一句很长很长很长很长很长啊。第二句也很长很长很长很长。', {
      mode: 'auto', maxLines: 2, maxLen: 10,
    });
    expect(b.length).toBeGreaterThan(1);
    expect(b[0].length).toBeLessThanOrEqual(2);
  });

  it('multi: lines packed into groups of maxLines', () => {
    const b = planSubtitleBatches('一。二。三。四。', { mode: 'multi', maxLines: 2, maxLen: 16 });
    expect(b).toEqual([['一。', '二。'], ['三。', '四。']]);
  });

  it('scroll: single batch with joined full text', () => {
    const b = planSubtitleBatches('一很长段。二很长段。', { mode: 'scroll', maxLines: 1, maxLen: 16 });
    expect(b).toHaveLength(1);
    expect(b[0]).toEqual(['一很长段。二很长段。']);
  });

  it('empty text → []', () => {
    expect(planSubtitleBatches('   ', { mode: 'auto' })).toEqual([]);
  });
});

describe('scheduleBatchTiming', () => {
  it('evenly distributes batches over duration', () => {
    expect(scheduleBatchTiming(30, 3)).toEqual([
      { startSec: 0, endSec: 10, index: 0 },
      { startSec: 10, endSec: 20, index: 1 },
      { startSec: 20, endSec: 30, index: 2 },
    ]);
  });

  it('last batch clamped to duration', () => {
    const s = scheduleBatchTiming(31, 2);
    expect(s[1].endSec).toBe(31);
  });

  it('returns [] for invalid input', () => {
    expect(scheduleBatchTiming(0, 2)).toEqual([]);
    expect(scheduleBatchTiming(30, 0)).toEqual([]);
    expect(scheduleBatchTiming(NaN, 2)).toEqual([]);
  });
});

describe('packAtTime', () => {
  const s = scheduleBatchTiming(30, 2);
  it('returns batch index at t', () => {
    expect(packAtTime(s, 5)).toBe(0);
    expect(packAtTime(s, 15)).toBe(1);
    expect(packAtTime(s, 30)).toBeNull();
  });

  it('empty schedule → null', () => {
    expect(packAtTime([], 5)).toBeNull();
  });
});

describe('computeFontShrink', () => {
  it('returns base when fits', () => {
    expect(computeFontShrink('短', 22, 16, 14)).toBe(22);
  });

  it('shrinks toward min when too long', () => {
    const r = computeFontShrink('x'.repeat(40), 22, 16, 14);
    expect(r).toBeLessThan(22);
    expect(r).toBeGreaterThanOrEqual(14);
  });

  it('never exceeds base or drops below min', () => {
    const r = computeFontShrink('abc', 22, 100, 14);
    expect(r).toBe(22);
  });
});

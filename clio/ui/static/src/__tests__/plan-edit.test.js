import { describe, it, expect } from 'vitest';
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  formatTimelineSec,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
} from '../plan-edit.js';

describe('plan-edit', () => {
  const seq = [{ index: '001' }, { index: '002' }, { index: '003' }];

  it('reorders without mutating input', () => {
    const next = reorderSequence(seq, 0, 2);
    expect(next.map((s) => s.index)).toEqual(['002', '003', '001']);
    expect(seq[0].index).toBe('001');
  });

  it('removeSegment', () => {
    const next = removeSegment(seq, 1);
    expect(next.map((s) => s.index)).toEqual(['001', '003']);
    expect(seq).toHaveLength(3);
  });

  it('patchSegment merges fields', () => {
    const s = { index: '001', title: 'a' };
    const next = patchSegment(s, { title: 'b', use_timeline: '00:00-00:01' });
    expect(next.title).toBe('b');
    expect(next.use_timeline).toBe('00:00-00:01');
    expect(s.title).toBe('a');
  });

  it('formatTimelineSec pads mm:ss', () => {
    expect(formatTimelineSec(0)).toBe('00:00');
    expect(formatTimelineSec(65)).toBe('01:05');
    expect(formatTimelineSec(3723)).toBe('62:03');
  });

  it('setTimelineBound start keeps or invents end', () => {
    expect(setTimelineBound('00:10-00:40', 'start', 15)).toBe('00:15-00:40');
    expect(setTimelineBound('', 'start', 12)).toBe('00:12-00:17');
    expect(setTimelineBound('00:30-00:20', 'start', 25)).toBe('00:25-00:30');
  });

  it('setTimelineBound end keeps or invents start', () => {
    expect(setTimelineBound('00:10-00:40', 'end', 50)).toBe('00:10-00:50');
    expect(setTimelineBound('', 'end', 20)).toBe('00:15-00:20');
    expect(setTimelineBound('00:30-00:20', 'end', 10)).toBe('00:05-00:10');
  });

  it('insertSegment inserts after atIndex without mutating', () => {
    const next = insertSegment(seq, 0, { index: '099', title: 'new' });
    expect(next.map((s) => s.index)).toEqual(['001', '099', '002', '003']);
    expect(seq).toHaveLength(3);
    expect(next[1].title).toBe('new');
    expect(next[1].use_timeline).toBe('');
  });

  it('insertSegment at end when atIndex is last', () => {
    const next = insertSegment(seq, 2, { index: '004' });
    expect(next.map((s) => s.index)).toEqual(['001', '002', '003', '004']);
  });

  it('insertSegment at -1 prepends', () => {
    const next = insertSegment(seq, -1, { index: '000' });
    expect(next.map((s) => s.index)).toEqual(['000', '001', '002', '003']);
  });
});

describe('computeDropToIndex', () => {
  const n = 4;

  it('returns null when dropping on own slot (before or after self)', () => {
    expect(computeDropToIndex(1, 1, false, n)).toBeNull();
    expect(computeDropToIndex(1, 1, true, n)).toBeNull();
    expect(computeDropToIndex(0, 0, false, n)).toBeNull();
    expect(computeDropToIndex(0, 0, true, n)).toBeNull();
  });

  it('maps before overIndex when dragging down', () => {
    // [A,B,C,D] drag A(0) before C(2) → final index 1 → [B,A,C,D]
    expect(computeDropToIndex(0, 2, false, n)).toBe(1);
    const seq = ['A', 'B', 'C', 'D'];
    expect(reorderSequence(seq, 0, 1)).toEqual(['B', 'A', 'C', 'D']);
  });

  it('maps after overIndex when dragging down to end-ish', () => {
    // drag A(0) after C(2) → final 2 → [B,C,A,D]
    expect(computeDropToIndex(0, 2, true, n)).toBe(2);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 0, 2)).toEqual(['B', 'C', 'A', 'D']);
  });

  it('maps after last to end', () => {
    // drag A(0) after D(3) → final 3 → [B,C,D,A]
    expect(computeDropToIndex(0, 3, true, n)).toBe(3);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 0, 3)).toEqual(['B', 'C', 'D', 'A']);
  });

  it('maps before first when dragging up', () => {
    // drag C(2) before A(0) → final 0
    expect(computeDropToIndex(2, 0, false, n)).toBe(0);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 2, 0)).toEqual(['C', 'A', 'B', 'D']);
  });

  it('returns null for out-of-range inputs', () => {
    expect(computeDropToIndex(-1, 0, false, n)).toBeNull();
    expect(computeDropToIndex(0, 9, false, n)).toBeNull();
    expect(computeDropToIndex(0, 0, false, 0)).toBeNull();
  });
});

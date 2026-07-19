import { describe, it, expect } from 'vitest';
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  formatTimelineSec,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
  computeDragAutoScrollDelta,
  nextExpandedAfterDelete,
  nextExpandedAfterInsert,
  nextExpandedAfterMove,
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

describe('computeDragAutoScrollDelta', () => {
  const top = 100;
  const bottom = 500; // viewport height 400

  it('returns 0 in the middle band', () => {
    expect(computeDragAutoScrollDelta(300, top, bottom)).toBe(0);
  });

  it('scrolls up near top edge (negative delta)', () => {
    const d = computeDragAutoScrollDelta(110, top, bottom, 48, 18);
    expect(d).toBeLessThan(0);
  });

  it('scrolls down near bottom edge (positive delta)', () => {
    const d = computeDragAutoScrollDelta(490, top, bottom, 48, 18);
    expect(d).toBeGreaterThan(0);
  });

  it('faster closer to the extreme edge', () => {
    const near = Math.abs(computeDragAutoScrollDelta(140, top, bottom, 48, 18));
    const far = Math.abs(computeDragAutoScrollDelta(105, top, bottom, 48, 18));
    expect(far).toBeGreaterThanOrEqual(near);
  });
});

describe('nextExpandedAfterDelete', () => {
  it('returns null when list becomes empty', () => {
    expect(nextExpandedAfterDelete(0, 0, 0)).toBeNull();
  });

  it('keeps same index when deleting after expanded', () => {
    expect(nextExpandedAfterDelete(1, 2, 3)).toBe(1);
  });

  it('decrements when deleting before expanded', () => {
    expect(nextExpandedAfterDelete(2, 0, 3)).toBe(1);
  });

  it('clamps to last when deleting the expanded last item', () => {
    expect(nextExpandedAfterDelete(2, 2, 2)).toBe(1);
  });

  it('returns null when expanded was null', () => {
    expect(nextExpandedAfterDelete(null, 1, 2)).toBeNull();
  });
});

describe('nextExpandedAfterInsert', () => {
  it('expands the newly inserted index (afterIndex + 1)', () => {
    expect(nextExpandedAfterInsert(0)).toBe(1);
    expect(nextExpandedAfterInsert(-1)).toBe(0);
    expect(nextExpandedAfterInsert(2)).toBe(3);
  });
});

describe('nextExpandedAfterMove', () => {
  it('follows the moved item when it was expanded', () => {
    expect(nextExpandedAfterMove(0, 2, 0)).toBe(2);
    expect(nextExpandedAfterMove(2, 0, 2)).toBe(0);
  });

  it('shifts expanded when another item moves across it', () => {
    expect(nextExpandedAfterMove(0, 2, 2)).toBe(1);
  });

  it('returns null when nothing expanded', () => {
    expect(nextExpandedAfterMove(0, 2, null)).toBeNull();
  });
});

import { describe, it, expect } from 'vitest';
import { reorderSequence, removeSegment, patchSegment } from '../plan-edit.js';

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
});

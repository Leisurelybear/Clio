import { describe, it, expect } from 'vitest';
import { timeFromClientX, playheadRatio, buildWaveformQuery } from '../waveform.js';

describe('timeFromClientX', () => {
  const rect = { left: 100, width: 200 };
  it('maps left edge to 0', () => {
    expect(timeFromClientX(100, rect, 50)).toBe(0);
  });
  it('maps right edge to duration', () => {
    expect(timeFromClientX(300, rect, 50)).toBe(50);
  });
  it('clamps outside', () => {
    expect(timeFromClientX(0, rect, 50)).toBe(0);
    expect(timeFromClientX(999, rect, 50)).toBe(50);
  });
  it('returns 0 if duration invalid', () => {
    expect(timeFromClientX(150, rect, NaN)).toBe(0);
  });
});

describe('playheadRatio', () => {
  it('clamps', () => {
    expect(playheadRatio(5, 10)).toBe(0.5);
    expect(playheadRatio(-1, 10)).toBe(0);
    expect(playheadRatio(99, 10)).toBe(1);
    expect(playheadRatio(1, 0)).toBe(0);
  });
});

describe('buildWaveformQuery', () => {
  it('segment uses compressed play file', () => {
    const q = buildWaveformQuery(
      { file: '001_GL_seg01.mp4', segment_label: '1/2', match: { file: '001_GL_seg01.mp4' } },
      'compressed',
    );
    expect(q.is_segment).toBe('1');
    expect(q.source).toBe('compressed');
    expect(q.file).toContain('seg');
  });

  it('full file prefers original abspath', () => {
    const q = buildWaveformQuery(
      { file: '001_GL.mp4', match: { abs_path: 'D:/GL.MP4', missing: false } },
      'compressed',
    );
    expect(q.abspath).toBe('D:/GL.MP4');
    expect(q.is_segment).toBeUndefined();
  });
});

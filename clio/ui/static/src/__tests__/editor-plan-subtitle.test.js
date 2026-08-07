import { describe, it, expect } from 'vitest';
import { resolveSegmentSubtitleText } from '../plan-subtitle.js';

describe('plan subtitle text source', () => {
  it('prefers the plan subtitle field when set', () => {
    const seg = { index: '001', subtitle: '  我编辑的字幕  ' };
    expect(resolveSegmentSubtitleText(seg, 'AI 原旁白')).toBe('我编辑的字幕');
  });

  it('falls back to voiceover when plan subtitle empty/absent', () => {
    expect(resolveSegmentSubtitleText({ index: '001' }, 'AI 原旁白')).toBe('AI 原旁白');
    expect(resolveSegmentSubtitleText({ index: '001', subtitle: '  ' }, null)).toBe(null);
  });

  it('returns empty when neither source has text', () => {
    expect(resolveSegmentSubtitleText({ index: '001' }, '')).toBe('');
  });
});
import { describe, it, expect, vi } from 'vitest';
import { mergeSubtitle } from '../editor-plan.js';

describe('mergeSubtitle', () => {
  it('preserves other voiceover fields, replaces voiceover', () => {
    const merged = mergeSubtitle({ voiceover: '原文', edit_tip: 'tip', duration_hint_sec: 5 }, '新版');
    expect(merged).toEqual({ voiceover: '新版', edit_tip: 'tip', duration_hint_sec: 5 });
  });

  it('handles null/undefined source', () => {
    expect(mergeSubtitle(null, '新')).toEqual({ voiceover: '新' });
  });
});
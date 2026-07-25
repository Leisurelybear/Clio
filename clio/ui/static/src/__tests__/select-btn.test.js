import { describe, it, expect } from 'vitest';
import { selectVideosButtonHtml, selectVideosButtonLabel } from '../select-btn.js';

describe('selectVideosButtonLabel', () => {
  it('shows 取消选择 while selection mode is on', () => {
    expect(selectVideosButtonLabel(true)).toBe('取消选择');
  });

  it('shows 选择视频 while selection mode is off', () => {
    expect(selectVideosButtonLabel(false)).toBe('选择视频');
  });
});

describe('selectVideosButtonHtml', () => {
  it('embeds the label for both modes', () => {
    expect(selectVideosButtonHtml(true)).toContain('取消选择');
    expect(selectVideosButtonHtml(false)).toContain('选择视频');
    expect(selectVideosButtonHtml(false)).not.toContain('取消选择');
  });
});

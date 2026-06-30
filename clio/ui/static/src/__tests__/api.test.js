import { describe, it, expect } from 'vitest';
import { icon } from '../api.js';

describe('icon()', () => {
  it('returns SVG span for known icon name', () => {
    const result = icon('play');
    expect(result).toContain('<span class="icon">');
    expect(result).toContain('<svg');
    expect(result).toContain('polygon');
  });

  it('returns different SVG for different icon names', () => {
    const play = icon('play');
    const folder = icon('folder');
    expect(play).not.toBe(folder);
  });

  it('falls back to file icon for unknown name', () => {
    const result = icon('nonexistent_icon_name');
    expect(result).toContain('<svg');
  });

  it('returns valid SVG structure for custom size param', () => {
    const result = icon('check', 24);
    expect(result).toContain('<svg viewBox="0 0 24 24">');
    expect(result).toContain('</svg>');
  });
});

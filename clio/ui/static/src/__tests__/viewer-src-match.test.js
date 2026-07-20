import { describe, it, expect } from 'vitest';
import { playerSrcMatchesFile } from '../viewer.js';

describe('playerSrcMatchesFile', () => {
  it('matches exact file query', () => {
    const src = 'http://127.0.0.1:8765/api/video?file=vid.mp4&source=compressed';
    expect(playerSrcMatchesFile(src, 'vid.mp4', 'compressed')).toBe(true);
  });

  it('rejects basename substring false positive', () => {
    const src = 'http://127.0.0.1:8765/api/video?file=other_vid.mp4&source=compressed';
    expect(playerSrcMatchesFile(src, 'vid.mp4', 'compressed')).toBe(false);
  });

  it('rejects different source', () => {
    const src = '/api/video?file=vid.mp4&source=original';
    expect(playerSrcMatchesFile(src, 'vid.mp4', 'compressed')).toBe(false);
  });

  it('handles encoded filenames', () => {
    const name = '街 头.mp4';
    const src = `/api/video?file=${encodeURIComponent(name)}&source=compressed`;
    expect(playerSrcMatchesFile(src, name, 'compressed')).toBe(true);
  });
});

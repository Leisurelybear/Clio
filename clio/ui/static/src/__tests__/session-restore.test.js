import { describe, it, expect } from 'vitest';
import { resolveSessionRestore } from '../session-restore.js';

describe('resolveSessionRestore', () => {
  const videos = [
    { file: '001_a.mp4' },
    { file: '002_b.mp4', missing: true },
    { file: '003_c.mp4' },
  ];

  it('restores last video entity when lastVideo is still available', () => {
    expect(resolveSessionRestore({
      lastEntity: 'video',
      lastVideo: '003_c.mp4',
      videos,
    })).toEqual({ entity: 'video', video: '003_c.mp4' });
  });

  it('falls back to first non-missing video when lastVideo is missing', () => {
    expect(resolveSessionRestore({
      lastEntity: 'video',
      lastVideo: '002_b.mp4',
      videos,
    })).toEqual({ entity: 'video', video: '001_a.mp4' });
  });

  it('falls back to first non-missing video when lastVideo is unknown', () => {
    expect(resolveSessionRestore({
      lastEntity: 'video',
      lastVideo: '999_gone.mp4',
      videos,
    })).toEqual({ entity: 'video', video: '001_a.mp4' });
  });

  it('restores plan/run/config/logs/tokens without requiring a video', () => {
    for (const entity of ['plan', 'run', 'config', 'logs', 'tokens']) {
      expect(resolveSessionRestore({
        lastEntity: entity,
        lastVideo: '003_c.mp4',
        videos,
      })).toEqual({ entity, video: '003_c.mp4' });
    }
  });

  it('defaults to first available video when lastEntity is absent', () => {
    expect(resolveSessionRestore({
      lastEntity: null,
      lastVideo: null,
      videos,
    })).toEqual({ entity: 'video', video: '001_a.mp4' });
  });

  it('returns no video when list is empty', () => {
    expect(resolveSessionRestore({
      lastEntity: 'plan',
      lastVideo: 'x.mp4',
      videos: [],
    })).toEqual({ entity: 'plan', video: null });
  });

  it('ignores invalid lastEntity values', () => {
    expect(resolveSessionRestore({
      lastEntity: 'nope',
      lastVideo: '003_c.mp4',
      videos,
    })).toEqual({ entity: 'video', video: '003_c.mp4' });
  });
});

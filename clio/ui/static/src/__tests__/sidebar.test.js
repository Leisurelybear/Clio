import { describe, it, expect } from 'vitest';
import {
  _findSourceSwitchTarget,
  _sourceSwitchResumePoint,
  _sourceSwitchSeekTime,
} from '../sidebar.js';

describe('_findSourceSwitchTarget', () => {
  it('matches the explicit counterpart file', () => {
    const oldVideo = { file: '001_A.mp4', match: { file: 'A.MP4' }, index: '001' };
    const videos = [
      { file: 'B.MP4', index: '002' },
      { file: 'A.MP4', index: '001' },
    ];

    expect(_findSourceSwitchTarget(oldVideo, videos, oldVideo.match.file).file).toBe('A.MP4');
  });

  it('matches reverse counterpart metadata', () => {
    const oldVideo = { file: 'A.MP4', index: '001' };
    const videos = [
      { file: '001_A.mp4', match: { file: 'A.MP4' }, index: '001' },
    ];

    expect(_findSourceSwitchTarget(oldVideo, videos).file).toBe('001_A.mp4');
  });

  it('falls back to matching by index', () => {
    const oldVideo = { file: 'old.mp4', index: '003' };
    const videos = [
      { file: 'other.mp4', index: '001' },
      { file: 'new.mp4', index: '003' },
    ];

    expect(_findSourceSwitchTarget(oldVideo, videos).file).toBe('new.mp4');
  });

  it('matches external original by abs_path', () => {
    const oldVideo = {
      file: '001_A.mp4',
      match: { file: 'A.MP4', abs_path: 'D:/GoPro/A.MP4' },
      index: '001',
    };
    const videos = [
      { file: 'A.MP4', abs_path: 'D:\GoPro\A.MP4', index: '001' },
      { file: 'B.MP4', abs_path: 'D:/other/B.MP4', index: '002' },
    ];
    expect(
      _findSourceSwitchTarget(oldVideo, videos, oldVideo.match.file, oldVideo.match.abs_path).file
    ).toBe('A.MP4');
  });
});

describe('source switch progress', () => {
  it('adds the original segment offset when switching from compressed media', () => {
    expect(_sourceSwitchSeekTime(
      12,
      'compressed',
      { offset_sec: 120 },
      'original',
      { offset_sec: 120 },
    )).toBe(132);
  });

  it('removes the original segment offset when switching to compressed media', () => {
    expect(_sourceSwitchSeekTime(
      132,
      'original',
      { offset_sec: 120 },
      'compressed',
      { offset_sec: 120 },
    )).toBe(12);
  });

  it('uses the plan global second instead of source media time', () => {
    expect(_sourceSwitchResumePoint(
      true,
      132,
      47.5,
      'original',
      { offset_sec: 120 },
      'compressed',
      { offset_sec: 120 },
    )).toEqual({ globalSec: 47.5 });
  });
});

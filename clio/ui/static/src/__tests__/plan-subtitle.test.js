import { describe, it, expect } from 'vitest';
import {
  splitSubtitleLines,
  scheduleSubtitleTiming,
  subtitleIndexAtTime,
  loadVoiceoverText,
} from '../plan-subtitle.js';

describe('splitSubtitleLines', () => {
  it('splits on Chinese sentence punctuation', () => {
    const lines = splitSubtitleLines('今天天气真好。我们出发吧！去海边。', 16);
    expect(lines).toEqual(['今天天气真好。', '我们出发吧！', '去海边。']);
  });

  it('splits long lines exceeding maxLen', () => {
    const long = '这是一个非常非常非常非常非常非常长的中文句子用来测试换行逻辑';
    const lines = splitSubtitleLines(long, 10);
    expect(lines.length).toBeGreaterThan(1);
    lines.forEach((l) => expect(l.length).toBeLessThanOrEqual(14)); // maxLen + punctuation carryover
  });

  it('splits on newlines too', () => {
    const lines = splitSubtitleLines('第一条\n第二条。', 16);
    expect(lines).toEqual(['第一条', '第二条。']);
  });

  it('empty / whitespace input → []', () => {
    expect(splitSubtitleLines('', 16)).toEqual([]);
    expect(splitSubtitleLines('   ', 16)).toEqual([]);
  });
});

describe('scheduleSubtitleTiming', () => {
  it('evenly distributes 2 lines over 60s', () => {
    const s = scheduleSubtitleTiming(60, 2);
    expect(s).toEqual([
      { startSec: 0, endSec: 30, index: 0 },
      { startSec: 30, endSec: 60, index: 1 },
    ]);
  });

  it('last line clamped to duration', () => {
    const s = scheduleSubtitleTiming(31, 2);
    expect(s[1].endSec).toBe(31);
    expect(s[1].startSec).toBeCloseTo(15.5);
  });

  it('3 lines over 30s', () => {
    const s = scheduleSubtitleTiming(30, 3);
    expect(s.map((x) => x.startSec)).toEqual([0, 10, 20]);
    expect(s[2].endSec).toBe(30);
  });

  it('lineCount 0 → []', () => {
    expect(scheduleSubtitleTiming(60, 0)).toEqual([]);
    expect(scheduleSubtitleTiming(60, -2)).toEqual([]);
  });

  it('non-finite / zero duration → []', () => {
    expect(scheduleSubtitleTiming(0, 3)).toEqual([]);
    expect(scheduleSubtitleTiming(NaN, 3)).toEqual([]);
    expect(scheduleSubtitleTiming(-5, 3)).toEqual([]);
    expect(scheduleSubtitleTiming(Number.POSITIVE_INFINITY, 3)).toEqual([]);
  });
});

describe('subtitleIndexAtTime', () => {
  const schedule = [
    { startSec: 0, endSec: 15, index: 0 },
    { startSec: 15, endSec: 30, index: 1 },
  ];

  it('boundary: startSec inclusive', () => {
    expect(subtitleIndexAtTime(schedule, 0)).toBe(0);
    expect(subtitleIndexAtTime(schedule, 15)).toBe(1);
  });

  it('endSec exclusive', () => {
    expect(subtitleIndexAtTime(schedule, 14.999)).toBe(0);
    expect(subtitleIndexAtTime(schedule, 30)).toBeNull();
  });

  it('mid range', () => {
    expect(subtitleIndexAtTime(schedule, 7)).toBe(0);
    expect(subtitleIndexAtTime(schedule, 22)).toBe(1);
  });

  it('empty schedule → null', () => {
    expect(subtitleIndexAtTime([], 5)).toBeNull();
  });
});

describe('loadVoiceoverText', () => {
  it('returns voiceover text via injected fetcher', async () => {
    const fakeLoader = async () => ({ voiceover: '测试字幕' });
    const text = await loadVoiceoverText('001', 'a.json', fakeLoader);
    expect(text).toBe('测试字幕');
  });

  it('missing script_json → null without fetching', async () => {
    const fetched = [];
    const fakeLoader = async (url) => { fetched.push(url); return null; };
    const text = await loadVoiceoverText('002', null, fakeLoader);
    expect(text).toBeNull();
    expect(fetched).toEqual([]);
  });

  it('loader failure → null', async () => {
    const fakeLoader = async () => { throw new Error('boom'); };
    const text = await loadVoiceoverText('003', 'c.json', fakeLoader);
    expect(text).toBeNull();
  });

  it('caches resolved value: second call does not refetch', async () => {
    let calls = 0;
    const fakeLoader = async () => { calls += 1; return { voiceover: '缓存' }; };
    await loadVoiceoverText('004', 'd.json', fakeLoader);
    await loadVoiceoverText('004', 'd.json', fakeLoader);
    expect(calls).toBe(1);
  });

  it('empty voiceover string → null', async () => {
    const fakeLoader = async () => ({ voiceover: '   ' });
    const text = await loadVoiceoverText('005', 'e.json', fakeLoader);
    expect(text).toBeNull();
  });
});
import { describe, it, expect } from 'vitest';
import {
  inferLogLevel,
  lineMatchesLogFilter,
  filterLogLines,
  logLineClass,
  normalizeLogEntry,
  formatLogTime,
  entryMatchesLogFilter,
  filterLogEntries,
} from '../logs-filter.js';

describe('inferLogLevel', () => {
  it('reads explicit logging tags', () => {
    expect(inferLogLevel('2026-07-20 12:00:00 [ERROR] boom')).toBe('error');
    expect(inferLogLevel('[WARNING] careful')).toBe('warn');
    expect(inferLogLevel('[INFO] ok')).toBe('info');
    expect(inferLogLevel('[DEBUG] detail')).toBe('debug');
  });

  it('detects traceback and failure marks as error', () => {
    expect(inferLogLevel('Traceback (most recent call last):')).toBe('error');
    expect(inferLogLevel('  ✗ 流水线出错')).toBe('error');
    expect(inferLogLevel('pipeline failed')).toBe('error');
    expect(inferLogLevel('HTTP 500: boom')).toBe('error');
  });

  it('detects skip / warning marks as warn', () => {
    expect(inferLogLevel('[跳过] already exists')).toBe('warn');
    expect(inferLogLevel('⚠ ffmpeg missing')).toBe('warn');
    expect(inferLogLevel('skipped clip')).toBe('warn');
  });

  it('defaults plain progress lines to info', () => {
    expect(inferLogLevel('=== AI 分析素材 ===')).toBe('info');
    expect(inferLogLevel('[分析 1/3] clip.mp4')).toBe('info');
    expect(inferLogLevel('')).toBe('info');
  });
});

describe('lineMatchesLogFilter', () => {
  it('passes everything when no filters', () => {
    expect(lineMatchesLogFilter('anything')).toBe(true);
    expect(lineMatchesLogFilter('x', { query: '', level: 'all' })).toBe(true);
  });

  it('filters by level', () => {
    expect(lineMatchesLogFilter('[ERROR] x', { level: 'error' })).toBe(true);
    expect(lineMatchesLogFilter('[INFO] x', { level: 'error' })).toBe(false);
    expect(lineMatchesLogFilter('[跳过] x', { level: 'warn' })).toBe(true);
  });

  it('filters by case-insensitive substring query', () => {
    expect(lineMatchesLogFilter('Hello World', { query: 'world' })).toBe(true);
    expect(lineMatchesLogFilter('Hello World', { query: 'xyz' })).toBe(false);
  });

  it('requires both level and query when both set', () => {
    expect(lineMatchesLogFilter('[ERROR] compress failed', { level: 'error', query: 'compress' })).toBe(true);
    expect(lineMatchesLogFilter('[ERROR] compress failed', { level: 'error', query: 'plan' })).toBe(false);
    expect(lineMatchesLogFilter('[INFO] compress ok', { level: 'error', query: 'compress' })).toBe(false);
  });
});

describe('filterLogLines', () => {
  const lines = [
    '[INFO] start',
    '[跳过] a',
    '[ERROR] boom',
    '=== plan ===',
  ];

  it('returns matching subset', () => {
    expect(filterLogLines(lines, { level: 'error' })).toEqual(['[ERROR] boom']);
    expect(filterLogLines(lines, { query: 'plan' })).toEqual(['=== plan ===']);
  });

  it('handles non-array input', () => {
    expect(filterLogLines(null)).toEqual([]);
  });
});

describe('logLineClass', () => {
  it('maps to css class', () => {
    expect(logLineClass('[ERROR] x')).toBe('log-level-error');
    expect(logLineClass('[INFO] x')).toBe('log-level-info');
  });
});

describe('normalizeLogEntry', () => {
  it('passes through object entries', () => {
    expect(normalizeLogEntry({ ts: 1.5, text: 'hi' })).toEqual({ ts: 1.5, text: 'hi' });
  });

  it('wraps plain strings with null ts', () => {
    expect(normalizeLogEntry('raw')).toEqual({ ts: null, text: 'raw' });
  });

  it('handles null/undefined', () => {
    expect(normalizeLogEntry(null)).toEqual({ ts: null, text: '' });
  });
});

describe('formatLogTime', () => {
  it('returns empty for invalid ts', () => {
    expect(formatLogTime(null)).toBe('');
    expect(formatLogTime(undefined)).toBe('');
    expect(formatLogTime(NaN)).toBe('');
  });

  it('formats local HH:MM:SS for a fixed epoch', () => {
    // Shape only (timezone-dependent wall clock)
    const s = formatLogTime(1721606400);
    expect(s).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe('entryMatchesLogFilter sinceMs', () => {
  const now = 1_000_000_000_000; // ms
  const recent = { ts: (now - 60_000) / 1000, text: '[INFO] recent' };
  const old = { ts: (now - 600_000) / 1000, text: '[INFO] old' };
  const noTs = { ts: null, text: '[INFO] unknown' };

  it('keeps all when sinceMs absent', () => {
    expect(entryMatchesLogFilter(recent, {})).toBe(true);
    expect(entryMatchesLogFilter(old, {})).toBe(true);
  });

  it('keeps only entries within window', () => {
    const opts = { sinceMs: 5 * 60 * 1000, nowMs: now };
    expect(entryMatchesLogFilter(recent, opts)).toBe(true);
    expect(entryMatchesLogFilter(old, opts)).toBe(false);
  });

  it('drops null ts when time filter active', () => {
    expect(entryMatchesLogFilter(noTs, { sinceMs: 60_000, nowMs: now })).toBe(false);
  });

  it('ANDs with level and query', () => {
    const err = { ts: (now - 10_000) / 1000, text: '[ERROR] compress failed' };
    expect(entryMatchesLogFilter(err, {
      sinceMs: 60_000, nowMs: now, level: 'error', query: 'compress',
    })).toBe(true);
    expect(entryMatchesLogFilter(err, {
      sinceMs: 60_000, nowMs: now, level: 'error', query: 'plan',
    })).toBe(false);
  });
});

describe('filterLogEntries', () => {
  it('filters list by sinceMs', () => {
    const now = 2_000_000_000_000;
    const entries = [
      { ts: (now - 10_000) / 1000, text: 'a' },
      { ts: (now - 999_999_000) / 1000, text: 'b' },
    ];
    expect(filterLogEntries(entries, { sinceMs: 60_000, nowMs: now }).map((e) => e.text)).toEqual(['a']);
  });
});

describe('lineMatchesLogFilter with sinceMs on strings', () => {
  it('still filters plain strings by level/query', () => {
    expect(lineMatchesLogFilter('[ERROR] x', { level: 'error' })).toBe(true);
  });
});

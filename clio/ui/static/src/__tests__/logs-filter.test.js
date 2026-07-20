import { describe, it, expect } from 'vitest';
import {
  inferLogLevel,
  lineMatchesLogFilter,
  filterLogLines,
  logLineClass,
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

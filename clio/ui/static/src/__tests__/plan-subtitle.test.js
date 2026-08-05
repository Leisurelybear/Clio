import { describe, it, expect } from 'vitest';
import { splitSubtitleLines } from '../plan-subtitle.js';

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
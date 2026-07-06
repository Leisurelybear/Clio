import { describe, it, expect } from 'vitest';
import { renderRunPreviewHtml } from '../runner.js';

describe('renderRunPreviewHtml', () => {
  it('renders totals and per-step counts', () => {
    const html = renderRunPreviewHtml({
      input: { mode: 'directory', path: 'D:/trip/videos', count: 3 },
      totals: { selected_steps: 2, will_run: 4, will_skip: 1, warnings: 0 },
      steps: [
        { name: 'compress', label: '压缩视频', total: 3, will_run: 2, will_skip: 1, warnings: [] },
        { name: 'analyze', label: 'AI 分析', total: 2, will_run: 2, will_skip: 0, warnings: [] },
      ],
    });

    expect(html).toContain('运行预览');
    expect(html).toContain('D:/trip/videos');
    expect(html).toContain('压缩视频');
    expect(html).toContain('AI 分析');
    expect(html).toContain('待执行');
    expect(html).toContain('4');
    expect(html).toContain('跳过');
    expect(html).toContain('1');
  });

  it('renders warnings and escapes dynamic strings', () => {
    const html = renderRunPreviewHtml({
      input: { mode: 'directory', path: '<script>', count: 0 },
      totals: { selected_steps: 1, will_run: 0, will_skip: 0, warnings: 1 },
      steps: [
        {
          name: 'unknown',
          label: '<b>bad</b>',
          total: 0,
          will_run: 0,
          will_skip: 0,
          warnings: ['未知步骤：<x>'],
        },
      ],
    });

    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('&lt;b&gt;bad&lt;/b&gt;');
    expect(html).toContain('未知步骤：&lt;x&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<b>bad</b>');
  });

  it('renders a neutral state without preview data', () => {
    expect(renderRunPreviewHtml(null)).toContain('选择步骤后显示预览');
  });
});

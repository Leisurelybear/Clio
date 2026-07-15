import { describe, it, expect, beforeEach } from 'vitest';
import {
  buildSkippedDiagnostics,
  renderRunPreviewHtml,
  renderSkippedDiagnosticsHtml,
  collectRunOptions,
} from '../runner.js';

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

describe('collectRunOptions', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input class="run-step-cb" data-step="compress" type="checkbox" checked>
      <input class="run-step-cb" data-step="analyze" type="checkbox" checked>
      <input class="run-step-cb" data-step="plan" type="checkbox">
      <input id="run-day" value="day2">
      <input id="run-use-transcripts" type="checkbox" checked>
      <input id="run-overwrite" type="checkbox">
      <textarea id="run-context-override">[analyze] focus food</textarea>
    `;
  });

  it('collects checked steps and options from the run form', () => {
    const opts = collectRunOptions();
    expect(opts.steps).toEqual(['compress', 'analyze']);
    expect(opts.day_label).toBe('day2');
    expect(opts.use_transcripts).toBe(true);
    expect(opts.overwrite).toBe(false);
    expect(opts.context_override).toBe('[analyze] focus food');
  });

  it('marks overwrite when checkbox is checked', () => {
    document.getElementById('run-overwrite').checked = true;
    expect(collectRunOptions().overwrite).toBe(true);
  });

  it('defaults use_transcripts when checkbox is missing', () => {
    document.getElementById('run-use-transcripts').remove();
    expect(collectRunOptions().use_transcripts).toBe(true);
  });
});

describe('skipped diagnostics', () => {
  it('builds inferred skipped reasons from processing state', () => {
    const diagnostics = buildSkippedDiagnostics({
      steps: ['compress', 'analyze', 'voiceover', 'transcribe', 'plan', 'label'],
      files: {
        GL010683: { compress: 'done', analyze: 'skipped', voiceover: null },
        GL010684: { compress: 'skipped', analyze: 'done', transcribe: 'error' },
      },
    });

    expect(diagnostics).toHaveLength(2);
    expect(diagnostics[0]).toMatchObject({
      file: 'GL010683',
      step: 'analyze',
      label: '分析',
    });
    expect(diagnostics[0].reason).toContain('分析 JSON');
    expect(diagnostics[1]).toMatchObject({
      file: 'GL010684',
      step: 'compress',
      label: '压缩',
    });
  });

  it('renders skipped diagnostics and escapes dynamic strings', () => {
    const html = renderSkippedDiagnosticsHtml([
      {
        file: '<video>',
        step: 'label',
        label: '<b>标号</b>',
        reason: '找不到 <output>',
      },
    ]);

    expect(html).toContain('为什么被跳过');
    expect(html).toContain('&lt;video&gt;');
    expect(html).toContain('&lt;b&gt;标号&lt;/b&gt;');
    expect(html).toContain('找不到 &lt;output&gt;');
    expect(html).not.toContain('<video>');
    expect(html).not.toContain('<b>标号</b>');
  });

  it('renders an empty skipped diagnostics state', () => {
    const html = renderSkippedDiagnosticsHtml([]);

    expect(html).toContain('当前没有 skipped 记录');
  });
});

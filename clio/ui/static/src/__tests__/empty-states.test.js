import { describe, it, expect } from 'vitest';
import { renderEmptyArtifactHtml } from '../empty-states.js';

describe('renderEmptyArtifactHtml', () => {
  it('renders texts empty state with run and rerun CTAs', () => {
    const html = renderEmptyArtifactHtml('texts');
    expect(html).toContain('没有分析结果');
    expect(html).toContain('data-empty-action="run"');
    expect(html).toContain('data-empty-action="rerun-analyze"');
    expect(html).toContain('去运行流水线');
    expect(html).toContain('重跑 AI 分析');
  });

  it('renders voiceover empty state with run and rerun CTAs', () => {
    const html = renderEmptyArtifactHtml('voiceover');
    expect(html).toContain('没有口播文案');
    expect(html).toContain('data-empty-action="run"');
    expect(html).toContain('data-empty-action="rerun-voiceover"');
    expect(html).toContain('去运行流水线');
    expect(html).toContain('重跑口播');
  });

  it('escapes nothing dangerous for known kinds and rejects unknown', () => {
    expect(renderEmptyArtifactHtml('nope')).toContain('未知面板');
  });
});

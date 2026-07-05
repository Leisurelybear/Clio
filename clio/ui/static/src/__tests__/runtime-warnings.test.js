import { describe, it, expect } from 'vitest';
import { buildRuntimeWarnings, renderRuntimeWarnings } from '../runtime-warnings.js';

describe('buildRuntimeWarnings', () => {
  it('warns when debug prompt printing is enabled', () => {
    const warnings = buildRuntimeWarnings({
      config: { ai: { debug_print_prompt: true } },
      hostname: '127.0.0.1',
      hasToken: true,
    });

    expect(warnings).toEqual([
      expect.objectContaining({
        id: 'debug-prompt',
        level: 'warning',
      }),
    ]);
    expect(warnings[0].text).toContain('debug_print_prompt');
  });

  it('does not warn for local hosts when debug prompt printing is disabled', () => {
    const warnings = buildRuntimeWarnings({
      config: { ai: { debug_print_prompt: false } },
      hostname: 'localhost',
      hasToken: false,
    });

    expect(warnings).toEqual([]);
  });

  it('warns when the UI is opened through a LAN host', () => {
    const warnings = buildRuntimeWarnings({
      config: { ai: { debug_print_prompt: false } },
      hostname: '192.168.1.25',
      hasToken: true,
    });

    expect(warnings).toEqual([
      expect.objectContaining({
        id: 'lan-host',
        level: 'warning',
      }),
    ]);
  });

  it('escalates LAN warning when no token is present', () => {
    const warnings = buildRuntimeWarnings({
      config: { ai: { debug_print_prompt: false } },
      hostname: '10.0.0.8',
      hasToken: false,
    });

    expect(warnings).toEqual([
      expect.objectContaining({
        id: 'lan-no-token',
        level: 'danger',
      }),
    ]);
  });
});

describe('renderRuntimeWarnings', () => {
  it('renders warnings as text content', () => {
    const container = document.createElement('div');
    renderRuntimeWarnings(container, [
      { id: 'x', level: 'warning', text: '<script>alert(1)</script>' },
    ]);

    expect(container.querySelector('.runtime-warning')).not.toBeNull();
    expect(container.textContent).toContain('<script>alert(1)</script>');
    expect(container.innerHTML).not.toContain('<script>');
  });

  it('hides the container when there are no warnings', () => {
    const container = document.createElement('div');
    renderRuntimeWarnings(container, []);

    expect(container.hidden).toBe(true);
    expect(container.children.length).toBe(0);
  });
});

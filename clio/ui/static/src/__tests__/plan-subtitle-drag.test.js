import { describe, it, expect, beforeEach } from 'vitest';
import {
  clampPositionPct,
  initSubtitleDrag,
} from '../plan-subtitle.js';

describe('clampPositionPct', () => {
  it('keeps in-range values', () => {
    expect(clampPositionPct(30, 60)).toEqual([30, 60]);
  });

  it('clamps below 0 / above 100', () => {
    expect(clampPositionPct(-5, 120)).toEqual([0, 100]);
  });

  it('non-finite falls back to defaults', () => {
    expect(clampPositionPct(NaN, undefined)).toEqual([50, 8]);
  });
});

describe('initSubtitleDrag', () => {
  beforeEach(() => { document.getElementById('plan-subtitle')?.remove(); });

  function mount() {
    const el = document.createElement('div');
    el.id = 'plan-subtitle'; el.hidden = true;
    el.innerHTML = '<span class="plan-subtitle-handle"></span><span class="plan-subtitle-text"></span>';
    document.body.appendChild(el);
    return el;
  }

  it('drag handle updates position CSS vars and calls onCommit', () => {
    const el = mount();
    const commits = [];
    const handle = el.querySelector('.plan-subtitle-handle');
    const stage = document.createElement('div');
    stage.getBoundingClientRect = () => ({ width: 200, height: 100, left: 0, top: 0 });
    initSubtitleDrag({ handle, stage, onCommit: (p) => commits.push(p) });

    handle.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: 100, clientY: 50 }));
    document.dispatchEvent(new MouseEvent('pointermove', { clientX: 140, clientY: 70 }));
    document.dispatchEvent(new MouseEvent('pointerup'));
    expect(el.style.getPropertyValue('--st-pos-x')).toBeTruthy();
    expect(el.style.getPropertyValue('--st-pos-y')).toBeTruthy();
    expect(commits.length).toBe(1);
  });
});
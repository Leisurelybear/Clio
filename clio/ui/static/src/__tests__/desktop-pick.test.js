import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  isDesktop,
  pickFolder,
  applyPickToInput,
  setBrowseButtonsVisible,
} from '../desktop-pick.js';

describe('desktop-pick', () => {
  beforeEach(() => {
    delete window.pywebview;
    document.body.innerHTML = `
      <input id="p" value="old" />
      <button class="browse-btn" type="button">浏览</button>
    `;
  });

  it('isDesktop false without pywebview', () => {
    expect(isDesktop()).toBe(false);
  });

  it('isDesktop true with api', () => {
    window.pywebview = { api: { pick_folder: vi.fn() } };
    expect(isDesktop()).toBe(true);
  });

  it('pickFolder returns path on ok', async () => {
    window.pywebview = {
      api: {
        pick_folder: vi.fn(async () => ({ ok: true, path: 'D:\\\\trip' })),
      },
    };
    await expect(pickFolder('D:\\\\')).resolves.toBe('D:\\\\trip');
  });

  it('pickFolder returns null on cancel', async () => {
    window.pywebview = {
      api: {
        pick_folder: vi.fn(async () => ({ ok: false, cancelled: true })),
      },
    };
    await expect(pickFolder()).resolves.toBeNull();
  });

  it('pickFolder returns null when not desktop', async () => {
    await expect(pickFolder()).resolves.toBeNull();
  });

  it('applyPickToInput writes only non-null', () => {
    const inp = document.getElementById('p');
    expect(applyPickToInput(inp, null)).toBe(false);
    expect(inp.value).toBe('old');
    expect(applyPickToInput(inp, 'D:\\\\x')).toBe(true);
    expect(inp.value).toBe('D:\\\\x');
  });

  it('setBrowseButtonsVisible hides in serve mode', () => {
    setBrowseButtonsVisible(document);
    expect(document.querySelector('.browse-btn').style.display).toBe('none');
  });
});
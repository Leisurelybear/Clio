import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  captureFrame,
  fadeHide,
  setupFadeOnReady,
  phaseNewSource,
} from '../video-fade.js';

function makeCanvas() {
  const ctx = { clearRect: vi.fn(), drawImage: vi.fn() };
  const canvas = {
    getContext: vi.fn(() => ctx),
    style: {},
    classList: { add: vi.fn(), remove: vi.fn() },
  };
  return { canvas, ctx };
}

function makePlayer() {
  return {
    videoWidth: 1920,
    videoHeight: 1080,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

describe('captureFrame', () => {
  it('returns false when video has no frame', () => {
    const { canvas, ctx } = makeCanvas();
    const player = { videoWidth: 0, videoHeight: 0 };
    expect(captureFrame(player, canvas)).toBe(false);
    expect(ctx.clearRect).toHaveBeenCalled();
  });

  it('draws a snapshot of current frame', () => {
    const { canvas, ctx } = makeCanvas();
    const player = makePlayer();
    expect(captureFrame(player, canvas)).toBe(true);
    expect(canvas.width).toBe(1920);
    expect(canvas.height).toBe(1080);
    expect(ctx.drawImage).toHaveBeenCalledWith(player, 0, 0, 1920, 1080);
  });
});

describe('fadeHide', () => {
  it('adds fade-out class then hides after transition', () => {
    const { canvas } = makeCanvas();
    fadeHide(canvas, 200);
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
    expect(canvas.style.opacity).toBe('0');
    vi.advanceTimersByTime(300);
    expect(canvas.classList.remove).toHaveBeenCalledWith('video-fade-hide');
    expect(canvas.style.visibility).toBe('hidden');
  });
});

describe('phaseFadeOutOnLoadedData', () => {
  it('starts fade on new video loadeddata', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer();
    setupFadeOnReady(player, canvas);
    expect(canvas.style.visibility).not.toBe('hidden');
    // grab registered handler
    const handler = player.addEventListener.mock.calls.find((c) => c[0] === 'loadeddata');
    expect(handler).toBeTruthy();
    handler[1]();
    expect(canvas.style.visibility).toBe('visible');
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
    vi.advanceTimersByTime(300);
    expect(canvas.style.visibility).toBe('hidden');
  });
});

describe('phaseNewSource', () => {
  it('captures old frame, shows overlay, then hides on ready', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer();
    const setSrc = vi.fn();
    // Simulate: old video has a frame
    const drew = phaseNewSource(player, canvas, { setSrc });
    expect(drew).toBe(true);
    expect(canvas.style.visibility).toBe('visible');
    expect(setSrc).toHaveBeenCalled();
  });

  it('shows and stays visible until loadeddata fires', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer();
    const setSrc = vi.fn();
    phaseNewSource(player, canvas, { setSrc });
    const handler = player.addEventListener.mock.calls.find((c) => c[0] === 'loadeddata');
    expect(handler).toBeTruthy();
    handler[1]();
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
  });
});
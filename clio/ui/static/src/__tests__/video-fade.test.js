import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  captureFrame,
  fadeHide,
  scheduleFadeWhenPaintable,
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

function makePlayer(over = {}) {
  return {
    videoWidth: 1920,
    videoHeight: 1080,
    readyState: 0,
    seeking: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    ...over,
  };
}

function tick(raf, { untilHidden = false } = {}) {
  let guard = 0;
  while (guard < 10000) {
    const cb = raf();
    if (cb == null) return;
    if (untilHidden && cb._last) return;
    guard++;
  }
}

beforeEach(() => {
  vi.useFakeTimers();
});

describe('captureFrame', () => {
  it('returns false when video has no frame', () => {
    const { canvas, ctx } = makeCanvas();
    const player = makePlayer({ videoWidth: 0, videoHeight: 0 });
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

describe('scheduleFadeWhenPaintable', () => {
  it('fades immediately when player already had a ready frame', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ readyState: 4 });
    scheduleFadeWhenPaintable(player, canvas, {});
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
  });

  it('keeps overlay visible until frame is painted then fades', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ readyState: 0, seeking: true });
    const raf = vi.fn();
    // Manual stubbing: simulate rAF that re-checks state
    let check = null;
    const stubbedRaf = (cb) => {
      check = cb;
    };
    scheduleFadeWhenPaintable(player, canvas, { raf: stubbedRaf });
    expect(canvas.style.visibility).toBe('visible');
    expect(canvas.classList.add).not.toHaveBeenCalledWith('video-fade-hide');

    // Not ready yet -> stays
    check();
    expect(canvas.classList.add).not.toHaveBeenCalledWith('video-fade-hide');

    // Now the frame is painted (readyState>=2 and not seeking)
    player.seeking = false;
    player.readyState = 2;
    check();
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
  });

  it('fades anyway after timeout so overlay never sticks', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ readyState: 0 });
    let check = null;
    const stubbedRaf = (cb) => { check = cb; };
    scheduleFadeWhenPaintable(player, canvas, {
      raf: stubbedRaf, maxMs: 200, stepMs: 50,
    });
    check(); check(); check(); check();
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
  });

  it('the returned cancel fades immediately', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ readyState: 0, seeking: true });
    let check = null;
    const stubbedRaf = (cb) => { check = cb; };
    const cancel = scheduleFadeWhenPaintable(player, canvas, { raf: stubbedRaf });
    expect(canvas.classList.add).not.toHaveBeenCalledWith('video-fade-hide');
    cancel();
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
    // subsequent polls no longer fire
    expect(canvas.classList.add).toHaveBeenCalledTimes(1);
  });
});

describe('phaseNewSource', () => {
  it('snapshots old frame, shows overlay, then fades when paintable', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ readyState: 0, seeking: true });
    let check = null;
    const stubbedRaf = (cb) => { check = cb; };
    const setSrc = vi.fn();
    const cancel = phaseNewSource(player, canvas, { raf: stubbedRaf, setSrc });
    expect(canvas.style.visibility).toBe('visible');
    expect(setSrc).toHaveBeenCalled();
    player.seeking = false;
    player.readyState = 2;
    check();
    expect(canvas.classList.add).toHaveBeenCalledWith('video-fade-hide');
    cancel();
  });

  it('returns no-op cancel when nothing to capture', () => {
    const { canvas } = makeCanvas();
    const player = makePlayer({ videoWidth: 0, videoHeight: 0 });
    const cancel = phaseNewSource(player, canvas, {});
    expect(typeof cancel).toBe('function');
  });
});
const FADE_MS = 200;
const FADE_HIDE_CLASS = 'video-fade-hide';

/**
 * Draw the current video frame into a snapshot canvas. Returns true if a
 * drawable frame existed, false otherwise (clears canvas to blank).
 * @param {HTMLVideoElement} player
 * @param {HTMLCanvasElement} canvas
 * @returns {boolean}
 */
export function captureFrame(player, canvas) {
  const ctx = canvas.getContext && canvas.getContext('2d');
  if (!ctx) return false;
  const w = Number(player.videoWidth) || 0;
  const h = Number(player.videoHeight) || 0;
  if (!w || !h) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return false;
  }
  canvas.width = w;
  canvas.height = h;
  ctx.drawImage(player, 0, 0, w, h);
  return true;
}

function isPaintable(player) {
  return !player.seeking && (player.readyState ? player.readyState >= 2 : false);
}

/**
 * Fade a snapshot overlay out to hidden.
 * @param {HTMLCanvasElement} canvas
 * @param {number} durationMs
 */
export function fadeHide(canvas, durationMs = FADE_MS) {
  canvas.classList.add(FADE_HIDE_CLASS);
  canvas.style.opacity = '0';
  setTimeout(() => {
    canvas.classList.remove(FADE_HIDE_CLASS);
    canvas.style.visibility = 'hidden';
  }, durationMs + 50);
}

function show(canvas) {
  canvas.style.visibility = 'visible';
  canvas.style.opacity = '1';
  canvas.classList.remove(FADE_HIDE_CLASS);
}

/**
 * Return a cancel function that shows the overlay now and fades it out once
 * the (new) source has actually painted a target frame (readyState >= 2 and
 * not mid-seek). Polls via requestAnimationFrame; bails after a timeout by
 * fading anyway so the overlay never sticks.
 * @param {HTMLVideoElement} player
 * @param {HTMLCanvasElement} canvas
 * @param {{ raf?: Function, maxMs?: number, stepMs?: number }} [opts]
 * @returns {() => void} cancel showing / early fade
 */
export function scheduleFadeWhenPaintable(player, canvas, opts = {}) {
  const raf = opts.raf || (typeof requestAnimationFrame === 'function' ? requestAnimationFrame : null);
  const maxMs = opts.maxMs ?? 1500;
  const stepMs = opts.stepMs ?? 16;
  show(canvas);
  let elapsed = 0;
  let cancelled = false;
  const tryFade = () => {
    if (cancelled) return;
    if (isPaintable(player) || elapsed >= maxMs) {
      fadeHide(canvas);
      return;
    }
    elapsed += stepMs;
    if (raf) raf(tryFade);
    else setTimeout(tryFade, stepMs);
  };
  tryFade();
  return () => {
    cancelled = true;
    fadeHide(canvas);
  };
}

/**
 * Snapshot the current frame, keep it visible while the source switches, and
 * fade it out once the new source has painted a target frame.
 * @param {HTMLVideoElement} player
 * @param {HTMLCanvasElement} canvas
 * @param {{ setSrc?: () => void, maxMs?: number, raf?: Function }} [opts]
 * @returns {() => void} cancels / fades early
 */
export function phaseNewSource(player, canvas, opts = {}) {
  const drew = captureFrame(player, canvas);
  if (!drew) return () => {};
  const cancel = scheduleFadeWhenPaintable(player, canvas, opts);
  if (opts.setSrc) opts.setSrc();
  return cancel;
}
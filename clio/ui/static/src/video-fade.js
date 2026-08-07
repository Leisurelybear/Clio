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
 * Hide the snapshot overlay once the (new) source is ready to paint.
 * @param {HTMLVideoElement} player
 * @param {HTMLCanvasElement} canvas
 */
export function setupFadeOnReady(player, canvas) {
  player.addEventListener('loadeddata', () => {
    show(canvas);
    fadeHide(canvas);
  });
}

/**
 * Snapshot the current frame, keep it visible while the source switches, and
 * fade it out when the new source has its first decoded frame.
 * @param {HTMLVideoElement} player
 * @param {HTMLCanvasElement} canvas
 * @param {{ setSrc?: (() => void) }} [opts]
 * @returns {boolean} whether a frame was captured (overlay shown)
 */
export function phaseNewSource(player, canvas, opts = {}) {
  const drew = captureFrame(player, canvas);
  show(canvas);
  setupFadeOnReady(player, canvas);
  if (opts.setSrc) opts.setSrc();
  return drew;
}
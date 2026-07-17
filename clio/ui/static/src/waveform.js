import { state } from './state.js';
import { api } from './api.js';
import { $ } from './utils.js';

/** @type {number} */
let _pollToken = 0;
/** @type {number[]} */
let _lastPeaks = [];
/** @type {ReturnType<typeof setTimeout> | null} */
let _pollTimer = null;

export function timeFromClientX(clientX, barRect, duration) {
  const dur = Number(duration);
  if (!barRect || !(dur > 0) || !Number.isFinite(dur)) return 0;
  const width = barRect.width || 0;
  if (width <= 0) return 0;
  const x = Math.max(0, Math.min(width, clientX - barRect.left));
  return (x / width) * dur;
}

export function playheadRatio(currentTime, duration) {
  const dur = Number(duration);
  if (!(dur > 0) || !Number.isFinite(dur)) return 0;
  const t = Number(currentTime) || 0;
  return Math.max(0, Math.min(1, t / dur));
}

/**
 * Build query fields for GET /api/waveform (project params added by api()).
 * @param {object|null|undefined} v video list entry
 * @param {string} source 'compressed' | 'original'
 */
export function buildWaveformQuery(v, source) {
  if (!v || !v.file) return null;
  const isSegment = Boolean(v.segment_label);
  /** @type {Record<string, string>} */
  const params = { source: source || 'compressed', file: String(v.file) };

  if (isSegment) {
    params.is_segment = '1';
    // Prefer compressed play-file so peaks duration matches the player.
    if (source === 'compressed') {
      params.source = 'compressed';
      params.file = String(v.file);
    } else if (v.match?.file) {
      params.source = 'compressed';
      params.file = String(v.match.file);
    } else if (v.abs_path) {
      params.abspath = String(v.abs_path);
    }
    return params;
  }

  const orig = v.abs_path || v.match?.abs_path;
  const origMissing = Boolean(v.missing || v.match?.missing);
  if (orig && !origMissing) {
    params.abspath = String(orig);
  }
  // When UI is on compressed full file, still pass compressed basename as file fallback.
  if (source === 'compressed' && v.file) {
    params.file = String(v.file);
    params.source = 'compressed';
  }
  return params;
}

export function drawWaveform(canvas, peaks, opts = {}) {
  if (!canvas) return;
  const peaksArr = Array.isArray(peaks) ? peaks : [];
  const dpr = opts.dpr || (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
  const cssW = opts.width || canvas.clientWidth || 300;
  const cssH = opts.height || canvas.clientHeight || 32;
  const w = Math.max(1, Math.floor(cssW * dpr));
  const h = Math.max(1, Math.floor(cssH * dpr));
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, w, h);
  if (!peaksArr.length) return;

  const mid = h / 2;
  const n = peaksArr.length;
  const barW = Math.max(1, w / n);
  const accent = opts.color || 'rgba(99, 160, 255, 0.75)';
  ctx.fillStyle = accent;
  for (let i = 0; i < n; i++) {
    const amp = Math.max(0, Math.min(1, Number(peaksArr[i]) || 0));
    const bh = Math.max(1, amp * (h * 0.9));
    const x = (i / n) * w;
    ctx.fillRect(x, mid - bh / 2, Math.max(1, barW * 0.85), bh);
  }
}

function _barEls() {
  return {
    bar: $('waveform-bar'),
    canvas: $('waveform-canvas'),
    playhead: $('waveform-playhead'),
    status: $('waveform-status'),
  };
}

export function resetWaveform() {
  _pollToken += 1;
  if (_pollTimer) {
    clearTimeout(_pollTimer);
    _pollTimer = null;
  }
  _lastPeaks = [];
  const { bar, canvas, playhead, status } = _barEls();
  if (bar) {
    bar.hidden = true;
    bar.classList.remove('has-peaks');
  }
  if (status) status.textContent = '';
  if (playhead) playhead.hidden = true;
  if (canvas) {
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

export function setWaveformStatus(text) {
  const { bar, status } = _barEls();
  if (bar) bar.hidden = false;
  if (status) status.textContent = text || '';
  if (bar && text) bar.classList.remove('has-peaks');
}

export function setWaveformPeaks(peaksPayload) {
  const peaks = peaksPayload?.peaks || peaksPayload;
  _lastPeaks = Array.isArray(peaks) ? peaks : [];
  const { bar, canvas, playhead, status } = _barEls();
  if (!bar || !canvas) return;
  bar.hidden = false;
  if (status) status.textContent = '';
  if (_lastPeaks.length) bar.classList.add('has-peaks');
  else bar.classList.remove('has-peaks');
  drawWaveform(canvas, _lastPeaks);
  if (playhead) playhead.hidden = !_lastPeaks.length;
}

export function updateWaveformPlayhead(player) {
  const { bar, playhead } = _barEls();
  if (!bar || !playhead || bar.hidden || !_lastPeaks.length) return;
  const ratio = playheadRatio(player?.currentTime, player?.duration);
  playhead.hidden = false;
  playhead.style.left = `${ratio * 100}%`;
}

export function bindWaveformScrub(player) {
  const { bar } = _barEls();
  if (!bar || bar.dataset.bound === '1') return;
  bar.dataset.bound = '1';

  let dragging = false;

  const seekFromEvent = (e) => {
    if (!player || !(player.duration > 0)) return;
    const rect = bar.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const t = timeFromClientX(clientX, rect, player.duration);
    try {
      player.currentTime = t;
    } catch { /* ignore */ }
    updateWaveformPlayhead(player);
  };

  bar.addEventListener('pointerdown', (e) => {
    dragging = true;
    bar.setPointerCapture?.(e.pointerId);
    seekFromEvent(e);
    e.preventDefault();
  });
  bar.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    seekFromEvent(e);
  });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    try { bar.releasePointerCapture?.(e.pointerId); } catch { /* ignore */ }
  };
  bar.addEventListener('pointerup', endDrag);
  bar.addEventListener('pointercancel', endDrag);

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => {
      if (_lastPeaks.length) {
        const canvas = $('waveform-canvas');
        drawWaveform(canvas, _lastPeaks);
      }
    });
    ro.observe(bar);
  }
}

async function _fetchWaveform(params, token) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, v);
  }
  const body = await api('GET', `/api/waveform?${qs.toString()}`);
  if (token !== _pollToken) return null;
  return body;
}

export async function loadWaveformForCurrentVideo() {
  const token = ++_pollToken;
  if (_pollTimer) {
    clearTimeout(_pollTimer);
    _pollTimer = null;
  }

  const file = state.currentVideo;
  if (!file) {
    resetWaveform();
    return;
  }
  const v = (state.videos || []).find((x) => x.file === file);
  const params = buildWaveformQuery(v || { file }, state.source || 'compressed');
  if (!params) {
    resetWaveform();
    return;
  }

  setWaveformStatus('波形生成中…');

  const poll = async (attempt) => {
    if (token !== _pollToken) return;
    try {
      const body = await _fetchWaveform(params, token);
      if (token !== _pollToken || !body) return;
      if (body.status === 'pending') {
        setWaveformStatus('波形生成中…');
        if (attempt < 120) {
          _pollTimer = setTimeout(() => poll(attempt + 1), 2500);
        } else {
          setWaveformStatus('波形生成超时');
        }
        return;
      }
      if (Array.isArray(body.peaks) || body.status === 'ready') {
        setWaveformPeaks(body);
        const player = $('player');
        if (player) updateWaveformPlayhead(player);
        return;
      }
      setWaveformStatus(body.error || '无波形');
    } catch (err) {
      if (token !== _pollToken) return;
      const msg = err?.message || '波形加载失败';
      // 404 no media
      if (String(msg).includes('404') || String(msg).includes('no media')) {
        setWaveformStatus('无可用音频源');
      } else {
        setWaveformStatus('波形加载失败');
      }
    }
  };

  await poll(0);
}

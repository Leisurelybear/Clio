import { state } from './state.js';
import { $, parseTimecode, fmtTime, setStatus } from './utils.js';
import { icon } from './api.js';

function playVideoSegment(file, seekTo) {
  const player = $('player');
  const doSeek = () => { player.currentTime = seekTo; player.play().catch(() => {}); };
  $('player-name').textContent = file;
  if (player.src && player.src.includes(encodeURIComponent(file)) && player.readyState >= 1) {
    doSeek();
  } else {
    player.onloadedmetadata = () => {
      $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
      doSeek();
    };
    const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
    player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${projParam}`;
  }
}

// ── Preview bar (R-012) ──────────────────────────────────────
function renderPreviewBar() {
  const bar = $('#preview-bar');
  if (!bar) return;
  const isPlan = state.currentEntity === 'plan';
  bar.style.display = isPlan ? '' : 'none';
  if (!isPlan) return;
  const p = state.plan;
  const segBar = $('#preview-seg-bar');
  if (!segBar) return;

  if (!p || !p.sequence || !p.sequence.length) {
    segBar.innerHTML = '<span class="muted">暂无可预览内容</span>';
    return;
  }

  let totalDuration = 0;
  const durations = p.sequence.map(seg => {
    const parts = (seg.use_timeline || '').split('-');
    if (parts.length >= 2) {
      const s = parseTimecode(parts[0].trim());
      const e = parseTimecode(parts[1].trim());
      const d = e - s;
      if (d > 0) { totalDuration += d; return d; }
    }
    return 0;
  });

  const segHtml = p.sequence.map((seg, i) => {
    const w = totalDuration > 0 ? (durations[i] / totalDuration * 100) : (100 / p.sequence.length);
    const cls = i < state.previewIndex ? 'done'
      : i === state.previewIndex && state.previewActive ? 'active'
      : 'pending';
    return `<div class="preview-seg-block ${cls}" data-seg="${i}" style="width:${w}%"></div>`;
  }).join('');

  segBar.innerHTML = segHtml;

  segBar.querySelectorAll('.preview-seg-block').forEach(el => {
    el.onclick = () => {
      const i = parseInt(el.dataset.seg);
      if (state.previewActive && i >= 0 && i < p.sequence.length) {
        state.previewIndex = i;
        _playPreviewSegment();
      }
    };
  });
}

let _dragTargetSeg = -1;

function _setupPreviewBarDrag() {
  const segBar = $('#preview-seg-bar');
  if (!segBar) return;

  const _getDurations = (plan) => {
    let total = 0;
    const durs = (plan.sequence || []).map(seg => {
      const parts = (seg.use_timeline || '').split('-');
      if (parts.length >= 2) {
        const s = parseTimecode(parts[0].trim());
        const e = parseTimecode(parts[1].trim());
        const d = e - s;
        if (d > 0) { total += d; return d; }
      }
      return 0;
    });
    return { total, durs };
  };

  const _onDragMove = (e) => {
    const p = state.plan;
    if (!p || !p.sequence || !p.sequence.length) return;
    const rect = segBar.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, x / rect.width));
    const { total: totalDuration, durs } = _getDurations(p);
    let accum = 0;
    let idx = 0;
    for (let i = 0; i < durs.length; i++) {
      const w = totalDuration > 0 ? durs[i] / totalDuration : 1 / durs.length;
      accum += w;
      if (pct <= accum || i === durs.length - 1) { idx = i; break; }
    }
    segBar.querySelectorAll('.preview-seg-block').forEach(el => {
      el.classList.toggle('active', parseInt(el.dataset.seg) === idx && state.previewActive);
    });
    _dragTargetSeg = idx;
  };

  const _onDragEnd = () => {
    document.removeEventListener('mousemove', _onDragMove);
    document.removeEventListener('mouseup', _onDragEnd);
    if (_dragTargetSeg >= 0 && state.previewActive) {
      state.previewIndex = _dragTargetSeg;
      _playPreviewSegment();
    }
    _dragTargetSeg = -1;
  };

  segBar.onmousedown = (e) => {
    _onDragMove(e);
    document.addEventListener('mousemove', _onDragMove);
    document.addEventListener('mouseup', _onDragEnd);
    e.preventDefault();
  };
}

// ── Preview playback ─────────────────────────────────────────
function startPreview() {
  const p = state.plan;
  if (!p || !p.sequence || !p.sequence.length) return;
  if (state.previewActive) stopPreview();
  state.previewActive = true;
  state.previewIndex = 0;
  setStatus(`预览播放`, 'ok');

  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = `1/${p.sequence.length} ${p.sequence[0]?.title || p.sequence[0]?.index || ''}`;
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('stop', 14)}`;
    playBtn.classList.add('preview-active');
    playBtn.title = '停止预览';
    playBtn.onclick = stopPreview;
  }

  import('./editor.js').then(mod => mod.renderPlan());
  _playPreviewSegment();
}

function stopPreview() {
  state.previewActive = false;
  state.previewIndex = -1;
  state._previewEndTime = null;
  const player = $('player');
  player.pause();

  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = '预览已停止';
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('play', 14)}`;
    playBtn.classList.remove('preview-active');
    playBtn.title = '预览播放';
    playBtn.onclick = startPreview;
  }

  import('./editor.js').then(mod => mod.renderPlan());
  setStatus('预览已停止', '');
}

function _playPreviewSegment() {
  const p = state.plan;
  if (!state.previewActive || !p || state.previewIndex >= p.sequence.length) {
    stopPreview();
    setStatus('预览播放完毕', 'ok');
    return;
  }
  const seg = p.sequence[state.previewIndex];
  const v = state.videos.find(x => x.index === seg.index);
  if (!v) {
    setStatus(`跳过视频 [${seg.index}]，找不到对应文件`, 'warn');
    state.previewIndex++;
    _playPreviewSegment();
    return;
  }
  const parts = (seg.use_timeline || '').split('-');
  const seekTo = parseTimecode(parts[0].trim()) + (v.offset_sec || 0);
  const endTime = parts[1] ? parseTimecode(parts[1].trim()) + (v.offset_sec || 0) : null;

  playVideoSegment(v.file, seekTo);
  state._previewEndTime = endTime;

  setStatus(`预览 [${state.previewIndex + 1}/${p.sequence.length}] ${seg.title || seg.index}`, 'ok');

  document.querySelectorAll('.plan-seg').forEach(el => {
    el.classList.toggle('preview-active', parseInt(el.dataset.previewIndex) === state.previewIndex);
  });

  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = `${state.previewIndex + 1}/${p.sequence.length} ${seg.title || seg.index}`;

  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('stop', 14)}`;
    playBtn.classList.add('preview-active');
    playBtn.title = '停止预览';
    playBtn.onclick = stopPreview;
  }
}

function setupPlayer() {
  const player = $('player');
  // 播放速度控制
  const speedSel = $('playback-speed');
  if (speedSel) {
    speedSel.onchange = () => { player.playbackRate = parseFloat(speedSel.value); };
  }

  player.ontimeupdate = () => {
    $('player-time').textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration)}`;
    if (state.previewActive && !player.seeking && state._previewEndTime !== null && player.currentTime >= state._previewEndTime) {
      state.previewIndex++;
      _playPreviewSegment();
    }
  };
  player.onloadedmetadata = () => {
    $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
  };
  player.onended = () => {
    if (state.previewActive) {
      state.previewIndex++;
      _playPreviewSegment();
    }
  };
  player.onerror = () => setStatus('视频加载失败', 'err');

  // Preview bar buttons
  const prevBtn = $('#btn-prev-seg');
  if (prevBtn) {
    prevBtn.innerHTML = `${icon('chevron_right', 14)}`;
    prevBtn.style.transform = 'scaleX(-1)';
    prevBtn.onclick = () => {
      if (!state.previewActive) return;
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      state.previewIndex = Math.max(0, state.previewIndex - 1);
      _playPreviewSegment();
    };
  }
  const nextBtn = $('#btn-next-seg');
  if (nextBtn) {
    nextBtn.innerHTML = `${icon('chevron_right', 14)}`;
    nextBtn.onclick = () => {
      if (!state.previewActive) return;
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      state.previewIndex = Math.min(p.sequence.length - 1, state.previewIndex + 1);
      _playPreviewSegment();
    };
  }
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('play', 14)}`;
    playBtn.onclick = startPreview;
  }

  _setupPreviewBarDrag();
}

export {
  playVideoSegment,
  startPreview,
  stopPreview,
  _playPreviewSegment,
  setupPlayer,
  renderPreviewBar,
};

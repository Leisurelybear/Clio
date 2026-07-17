import { state } from './state.js';
import { $, parseTimecode, fmtTime, setStatus, escapeHtml, clearDirty } from './utils.js';
import { icon } from './api.js';

function playVideoSegment(file, seekTo) {
  state.currentVideo = file;
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
    const tokenParam = sessionStorage.getItem('api_token');
    const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
    const v = (state.videos || []).find(x => x.file === file);
    const absParam = v?.abs_path ? `&abspath=${encodeURIComponent(v.abs_path)}` : '';
    player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${absParam}${projParam}${extraParam}`;
  }
}

// ── Preview bar (R-012) ──────────────────────────────────────
function renderPreviewBar() {
  const bar = $('preview-bar');
  if (!bar) return;
  const isPlan = state.currentEntity === 'plan';
  bar.style.display = isPlan ? 'flex' : 'none';
  if (!isPlan) return;
  const p = state.plan;
  const segBar = $('preview-seg-bar');
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
    const label = `${i + 1}`;
    const tooltip = `${seg.title || ''} [${seg.use_timeline || ''}]`.trim();
    return `<div class="preview-seg-block ${cls}" data-seg="${i}" style="width:${w}%" title="${escapeHtml(tooltip)}"><span class="preview-seg-label">${label}</span></div>`;
  }).join('');

  segBar.innerHTML = segHtml;

  segBar.querySelectorAll('.preview-seg-block').forEach(el => {
    el.onclick = () => {
      const i = parseInt(el.dataset.seg);
      if (i < 0 || i >= p.sequence.length) return;
      if (state.previewActive) {
        state.previewIndex = i;
        _playPreviewSegment();
      } else {
        startPreview(i);
      }
    };
  });
}

let _dragTargetSeg = -1;

function _setupPreviewBarDrag() {
  const segBar = $('preview-seg-bar');
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
function _setPlayBtnPause() {
  const btn = $('btn-play-preview');
  if (!btn) return;
  btn.innerHTML = `${icon('pause', 14)}`;
  btn.classList.add('preview-active');
  btn.title = '暂停';
  btn.onclick = togglePreviewPlayback;
}

function _setPlayBtnPlay(title) {
  const btn = $('btn-play-preview');
  if (!btn) return;
  btn.innerHTML = `${icon('play', 14)}`;
  btn.classList.remove('preview-active');
  btn.title = title || '预览播放';
  btn.onclick = togglePreviewPlayback;
}

function togglePreviewPlayback() {
  if (!state.previewActive) {
    startPreview();
    return;
  }
  const player = $('player');
  if (player.paused) {
    player.play().catch(() => {});
    _setPlayBtnPause();
  } else {
    player.pause();
    _setPlayBtnPlay('继续');
  }
}

function startPreview(startIndex) {
  const p = state.plan;
  if (!p || !p.sequence || !p.sequence.length) return;
  if (state.previewActive) stopPreview();
  state.previewActive = true;
  state.previewIndex = typeof startIndex === 'number' ? startIndex : 0;
  setStatus(`预览播放`, 'ok');

  renderPreviewBar();
  const segNameEl = $('preview-seg-name');
  if (segNameEl) segNameEl.textContent = `1/${p.sequence.length} ${p.sequence[0]?.title || p.sequence[0]?.index || ''}`;
  _setPlayBtnPause();

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
  const segNameEl = $('preview-seg-name');
  if (segNameEl) segNameEl.textContent = '预览已停止';
  _setPlayBtnPlay('预览播放');

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
  const segNameEl = $('preview-seg-name');
  if (segNameEl) segNameEl.textContent = `${state.previewIndex + 1}/${p.sequence.length} ${seg.title || seg.index}`;

  _setPlayBtnPause();
}

function _autoSwitchSegment(file) {
  if (state.currentVideo === file) return;
  state.currentVideo = file;
  clearDirty();
  state.texts = null;
  state.voiceover = null;
  state.transcript = null;

  $('player-name').textContent = file;

  import('./sidebar-data.js').then(mod => mod.renderVideoList());

  const v = state.videos.find(x => x.file === file);
  if (!v) return;

  Promise.all([
    v.text_json
      ? import('./api.js').then(m => m.api('GET', `/api/texts?file=${encodeURIComponent(v.text_json)}`)).then(d => { state.texts = d; }).catch(() => {})
      : Promise.resolve(),
    v.script_json
      ? import('./api.js').then(m => m.api('GET', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`)).then(d => { state.voiceover = d; }).catch(() => {})
      : Promise.resolve(),
    v.transcript_file
      ? import('./api.js').then(m => m.api('GET', `/api/transcripts?video=${encodeURIComponent(v.file)}`)).then(d => { state.transcript = d; }).catch(() => {})
      : Promise.resolve(),
  ]).then(() => {
    import('./editor.js').then(mod => mod.renderActiveTab());
  });
}

function _checkSegmentBoundary(player) {
  const currentFile = state.currentVideo;
  if (!currentFile) return;
  const curVid = state.videos.find(v => v.file === currentFile);
  if (!curVid || !curVid.segment_matches || curVid.segment_matches.length < 2) return;

  const parts = currentFile.split('_');
  if (parts.length < 2) return;
  const origStem = parts.slice(1).join('_');

  const segments = state.videos
    .filter(v => v.source === 'original' && v.file.endsWith(origStem))
    .sort((a, b) => (a.offset_sec || 0) - (b.offset_sec || 0));

  if (segments.length < 2) return;

  let activeSeg = segments[0];
  for (let i = segments.length - 1; i >= 0; i--) {
    if (player.currentTime >= (segments[i].offset_sec || 0)) {
      activeSeg = segments[i];
      break;
    }
  }

  if (activeSeg.file !== currentFile) {
    _autoSwitchSegment(activeSeg.file);
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
      return;
    }
    if (state.source === 'original' && state.currentEntity === 'video') {
      _checkSegmentBoundary(player);
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
  const prevBtn = $('btn-prev-seg');
  if (prevBtn) {
    prevBtn.innerHTML = `${icon('chevron_right', 14)}`;
    prevBtn.style.transform = 'scaleX(-1)';
    prevBtn.onclick = () => {
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      if (!state.previewActive) { startPreview(0); return; }
      state.previewIndex = Math.max(0, state.previewIndex - 1);
      _playPreviewSegment();
    };
  }
  const nextBtn = $('btn-next-seg');
  if (nextBtn) {
    nextBtn.innerHTML = `${icon('chevron_right', 14)}`;
    nextBtn.onclick = () => {
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      if (!state.previewActive) { startPreview(0); return; }
      state.previewIndex = Math.min(p.sequence.length - 1, state.previewIndex + 1);
      _playPreviewSegment();
    };
  }
  const playBtn = $('btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('play', 14)}`;
    playBtn.onclick = togglePreviewPlayback;
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

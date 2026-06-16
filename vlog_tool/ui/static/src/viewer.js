import { state } from './state.js';
import { $, parseTimecode, fmtTime, setStatus } from './utils.js';

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

// ── Preview playback ─────────────────────────────────────────
function startPreview() {
  const p = state.plan;
  if (!p || !p.sequence || !p.sequence.length) return;
  // 如果已在预览，先停止
  if (state.previewActive) stopPreview();
  state.previewActive = true;
  state.previewIndex = 0;
  setStatus(`预览播放`, 'ok');
  // Import renderPlan dynamically or have it passed in - avoid circular deps
  // renderPlan is imported in editor.js which we can't import here (circular)
  // We'll use a callback pattern or import the render module
  // For now, we'll import renderPlan from editor.js — this won't create a true circular
  // because viewer -> editor -> viewer is a cycle. Let's use an injection pattern instead.
  // Actually, looking at the code: viewer.js needs to call renderPlan().
  // And editor.js doesn't call playVideoSegment or startPreview/stopPreview in a circular way.
  // editor.js calls playVideoSegment in renderPlan(), but renderPlan is in editor.
  // So: editor -> viewer (playVideoSegment).
  // And viewer -> nothing from editor except renderPlan in start/stopPreview.
  // We can break this by passing renderPlan as a callback.
  // For now, use dynamic import:
  import('./editor.js').then(mod => mod.renderPlan());
  _playPreviewSegment();
}

function stopPreview() {
  state.previewActive = false;
  state.previewIndex = -1;
  state._previewEndTime = null;
  const player = $('player');
  player.pause();
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

  // 更新高亮
  document.querySelectorAll('.plan-seg').forEach(el => {
    el.classList.toggle('preview-active', parseInt(el.dataset.previewIndex) === state.previewIndex);
  });
  // 更新预览计数器
  const counterEl = document.querySelector('#btn-stop-preview + span');
  if (counterEl) counterEl.textContent = `${state.previewIndex + 1}/${p.sequence.length}`;
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
    // 预览模式：到达结束时间自动推进
    if (state.previewActive && state._previewEndTime !== null && player.currentTime >= state._previewEndTime) {
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
}

export {
  playVideoSegment,
  startPreview,
  stopPreview,
  _playPreviewSegment,
  setupPlayer,
};

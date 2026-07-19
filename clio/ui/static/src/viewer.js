import { state } from './state.js';
import { $, fmtTime, setStatus, escapeHtml, clearDirty } from './utils.js';
import { icon } from './api.js';
import {
  loadWaveformForCurrentVideo,
  updateWaveformPlayhead,
  bindWaveformScrub,
} from './waveform.js';
import {
  buildTimeline,
  clampGlobal,
  globalToLocal,
  localToGlobal,
  nextPlayableSegIndex,
  segmentWidths,
} from './plan-timeline.js';

function isGlobalTimelineUi() {
  return state.currentEntity === 'plan'
    && Array.isArray(state.plan?.sequence)
    && state.plan.sequence.length > 0;
}

function getPlanTimeline() {
  return buildTimeline(state.plan?.sequence || []);
}

function updateCompositeClock() {
  if (!isGlobalTimelineUi()) return;
  const tl = getPlanTimeline();
  const g = clampGlobal(tl, state.previewGlobalSec);
  const el = $('player-time');
  if (el) el.textContent = `成片 ${fmtTime(g)} / ${fmtTime(tl.total)}`;
}

function _updatePlayheadDom(tl) {
  const ph = $('preview-playhead');
  if (!ph || !tl || tl.total <= 0) return;
  const g = clampGlobal(tl, state.previewGlobalSec);
  ph.style.left = `${(g / tl.total) * 100}%`;
}

function _syncPlanExpandFromPreview() {
  if (state.previewIndex < 0) return;
  // Don't collapse/switch expand while the user is mid-edit in another row
  // (full renderPlan would destroy focus and IME composition).
  const ae = document.activeElement;
  const planList = document.getElementById('plan-list');
  if (
    ae
    && planList
    && planList.contains(ae)
    && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')
  ) {
    const editingLi = ae.closest('[data-preview-index]');
    const editingIdx = editingLi ? parseInt(editingLi.dataset.previewIndex, 10) : NaN;
    if (Number.isFinite(editingIdx) && editingIdx !== state.previewIndex) {
      // Catch up expand once the user leaves the field (do not leave accordion
      // permanently lagging previewIndex).
      if (!ae.dataset.planExpandResyncBound) {
        ae.dataset.planExpandResyncBound = '1';
        ae.addEventListener('blur', () => {
          delete ae.dataset.planExpandResyncBound;
          // Defer past focus move so activeElement is no longer this field
          setTimeout(() => _syncPlanExpandFromPreview(), 0);
        }, { once: true });
      }
      return;
    }
  }
  import('./editor-plan.js').then((mod) => {
    if (typeof mod.setPlanExpandedIndex === 'function') {
      mod.setPlanExpandedIndex(state.previewIndex);
    }
  }).catch(() => { /* ignore */ });
}

/**
 * Load source video and seek. Does not always force play.
 * @param {{ file: string, abs_path?: string }} v
 * @param {number} seekSec
 * @param {boolean} wantPlay
 */
function _loadAndSeekSource(v, seekSec, wantPlay) {
  const player = $('player');
  const doSeek = () => {
    player.currentTime = seekSec;
    if (wantPlay) player.play().catch(() => {});
    else player.pause();
  };
  state.currentVideo = v.file;
  $('player-name').textContent = v.file;
  const same =
    player.src
    && player.src.includes(encodeURIComponent(v.file))
    && player.readyState >= 1;
  if (same) {
    doSeek();
  } else {
    player.onloadedmetadata = () => {
      if (!isGlobalTimelineUi()) {
        $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
      }
      doSeek();
    };
    const projParam = state.currentProjectName
      ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
    const tokenParam = sessionStorage.getItem('api_token');
    const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
    const absParam = v?.abs_path ? `&abspath=${encodeURIComponent(v.abs_path)}` : '';
    player.src = `/api/video?file=${encodeURIComponent(v.file)}&source=${state.source}${absParam}${projParam}${extraParam}`;
  }
  loadWaveformForCurrentVideo();
}

function playVideoSegment(file, seekTo) {
  const v = (state.videos || []).find((x) => x.file === file) || { file };
  _loadAndSeekSource(v, seekTo, true);
}

/**
 * Seek to a composite global second on the plan timeline.
 * @param {number} globalSec
 * @param {{ play?: boolean, syncExpand?: boolean }} [opts]
 *   play: true force play; false force pause; omit = keep current play/pause
 */
function seekToGlobal(globalSec, opts = {}) {
  const tl = getPlanTimeline();
  const loc = globalToLocal(tl, globalSec);
  if (!loc) return;

  const player = $('player');
  const wasPlaying = player && !player.paused;
  let wantPlay;
  if (opts.play === true) wantPlay = true;
  else if (opts.play === false) wantPlay = false;
  else wantPlay = wasPlaying;

  state.previewIndex = loc.segIndex;
  state.previewGlobalSec = clampGlobal(tl, globalSec);

  const v = state.videos.find((x) => x.index === loc.videoIndex);
  if (!v) {
    setStatus(`跳过视频 [${loc.videoIndex}]，找不到对应文件`, 'warn');
    updateCompositeClock();
    renderPreviewBar();
    if (opts.syncExpand !== false) _syncPlanExpandFromPreview();
    return;
  }

  const seekSec = loc.planSec + (v.offset_sec || 0);
  const seg = tl.segments[loc.segIndex];
  state._previewEndTime = seg
    ? seg.planEnd + (v.offset_sec || 0)
    : null;

  _loadAndSeekSource(v, seekSec, wantPlay);

  const p = state.plan;
  if (p?.sequence?.length) {
    const s = p.sequence[loc.segIndex];
    setStatus(
      `预览 [${loc.segIndex + 1}/${p.sequence.length}] ${s?.title || s?.index || ''}`,
      'ok',
    );
    const segNameEl = $('preview-seg-name');
    if (segNameEl) {
      segNameEl.textContent = `${loc.segIndex + 1}/${p.sequence.length} ${s?.title || s?.index || ''}`;
    }
    document.querySelectorAll('.plan-seg').forEach((el) => {
      el.classList.toggle(
        'preview-active',
        parseInt(el.dataset.previewIndex, 10) === loc.segIndex,
      );
    });
  }

  updateCompositeClock();
  renderPreviewBar();
  if (opts.syncExpand !== false) _syncPlanExpandFromPreview();
}

function _advanceToNextPlayable() {
  const tl = getPlanTimeline();
  const next = nextPlayableSegIndex(tl, state.previewIndex);
  if (next == null) {
    stopPreview();
    setStatus('预览播放完毕', 'ok');
    return;
  }
  state.previewActive = true;
  seekToGlobal(tl.segments[next].globalStart, { play: true });
}

// ── Preview bar (R-012 / R-031a global scrub) ──────────────────
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

  const tl = buildTimeline(p.sequence);
  const widths = segmentWidths(tl);
  const segHtml = p.sequence.map((seg, i) => {
    const w = (widths[i] || 0) * 100;
    const cls = state.previewIndex < 0
      ? 'pending'
      : i < state.previewIndex
        ? 'done'
        : i === state.previewIndex
          ? 'active'
          : 'pending';
    const tooltip = `${seg.title || ''} [${seg.use_timeline || ''}]`.trim();
    return `<div class="preview-seg-block ${cls}" data-seg="${i}" style="width:${w}%" title="${escapeHtml(tooltip)}"><span class="preview-seg-label">${i + 1}</span></div>`;
  }).join('');

  const pct = tl.total > 0
    ? (clampGlobal(tl, state.previewGlobalSec) / tl.total) * 100
    : 0;
  segBar.innerHTML = `${segHtml}<div class="preview-playhead" id="preview-playhead" style="left:${pct}%"></div>`;

  segBar.querySelectorAll('.preview-seg-block').forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const i = parseInt(el.dataset.seg, 10);
      if (!Number.isFinite(i) || i < 0 || i >= p.sequence.length) return;
      const g = tl.segments[i].globalStart;
      seekToGlobal(g, { play: false });
    };
  });

  if (isGlobalTimelineUi()) updateCompositeClock();
}

let _scrubbing = false;
let _lastSeekTs = 0;

function _setupPreviewBarDrag() {
  const segBar = $('preview-seg-bar');
  if (!segBar) return;

  const globalFromEvent = (e) => {
    const p = state.plan;
    if (!p?.sequence?.length) return null;
    const tl = buildTimeline(p.sequence);
    if (tl.total <= 0) return { tl, g: 0 };
    const rect = segBar.getBoundingClientRect();
    if (rect.width <= 0) return { tl, g: 0 };
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    return { tl, g: pct * tl.total };
  };

  const onMove = (e) => {
    if (!_scrubbing) return;
    const hit = globalFromEvent(e);
    if (!hit) return;
    state.previewGlobalSec = hit.g;
    _updatePlayheadDom(hit.tl);
    updateCompositeClock();
    const now = performance.now();
    if (now - _lastSeekTs >= 50) {
      _lastSeekTs = now;
      seekToGlobal(hit.g, { play: false, syncExpand: false });
    }
  };

  const onUp = (e) => {
    if (!_scrubbing) return;
    _scrubbing = false;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    const hit = globalFromEvent(e);
    if (hit) seekToGlobal(hit.g, { play: false, syncExpand: true });
  };

  segBar.onmousedown = (e) => {
    if (e.button !== 0) return;
    _scrubbing = true;
    _lastSeekTs = 0;
    onMove(e);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
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
  setStatus('预览播放', 'ok');

  const tl = buildTimeline(p.sequence);
  let idx = typeof startIndex === 'number' ? startIndex : 0;
  if (tl.segments[idx]?.duration <= 0) {
    const n = nextPlayableSegIndex(tl, idx - 1);
    idx = n == null ? 0 : n;
  }
  state.previewIndex = idx;
  const g = tl.segments[idx]?.globalStart ?? 0;

  renderPreviewBar();
  const seg = p.sequence[state.previewIndex];
  const segNameEl = $('preview-seg-name');
  if (segNameEl) {
    segNameEl.textContent = `${state.previewIndex + 1}/${p.sequence.length} ${seg?.title || seg?.index || ''}`;
  }
  _setPlayBtnPause();

  // Expand before first plan paint so accordion matches previewIndex immediately
  import('./editor-plan.js').then((mod) => {
    if (typeof mod.setPlanExpandedIndex === 'function') {
      mod.setPlanExpandedIndex(state.previewIndex, { render: false });
    }
    return import('./editor.js').then((ed) => ed.renderPlan());
  }).catch(() => {
    import('./editor.js').then((mod) => mod.renderPlan());
  });
  seekToGlobal(g, { play: true });
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

  import('./editor.js').then((mod) => mod.renderPlan());
  setStatus('预览已停止', '');
}

function _playPreviewSegment() {
  const tl = getPlanTimeline();
  if (!tl.segments.length || state.previewIndex < 0 || state.previewIndex >= tl.segments.length) {
    if (state.previewActive) {
      stopPreview();
      setStatus('预览播放完毕', 'ok');
    }
    return;
  }
  if (tl.segments[state.previewIndex].duration <= 0) {
    const n = nextPlayableSegIndex(tl, state.previewIndex);
    if (n == null) {
      if (state.previewActive) stopPreview();
      return;
    }
    state.previewIndex = n;
  }
  seekToGlobal(tl.segments[state.previewIndex].globalStart, {
    play: state.previewActive,
  });
}

function _autoSwitchSegment(file) {
  if (state.currentVideo === file) return;
  state.currentVideo = file;
  clearDirty();
  state.texts = null;
  state.voiceover = null;
  state.transcript = null;

  $('player-name').textContent = file;

  import('./sidebar-data.js').then((mod) => mod.renderVideoList());

  const v = state.videos.find((x) => x.file === file);
  if (!v) return;

  Promise.all([
    v.text_json
      ? import('./api.js').then((m) => m.api('GET', `/api/texts?file=${encodeURIComponent(v.text_json)}`)).then((d) => { state.texts = d; }).catch(() => {})
      : Promise.resolve(),
    v.script_json
      ? import('./api.js').then((m) => m.api('GET', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`)).then((d) => { state.voiceover = d; }).catch(() => {})
      : Promise.resolve(),
    v.transcript_file
      ? import('./api.js').then((m) => m.api('GET', `/api/transcripts?video=${encodeURIComponent(v.file)}`)).then((d) => { state.transcript = d; }).catch(() => {})
      : Promise.resolve(),
  ]).then(() => {
    import('./editor.js').then((mod) => mod.renderActiveTab());
  });
}

function _checkSegmentBoundary(player) {
  const currentFile = state.currentVideo;
  if (!currentFile) return;
  const curVid = state.videos.find((v) => v.file === currentFile);
  if (!curVid || !curVid.segment_matches || curVid.segment_matches.length < 2) return;

  const parts = currentFile.split('_');
  if (parts.length < 2) return;
  const origStem = parts.slice(1).join('_');

  const segments = state.videos
    .filter((v) => v.source === 'original' && v.file.endsWith(origStem))
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

  bindWaveformScrub(player);

  player.ontimeupdate = () => {
    updateWaveformPlayhead(player);

    if (isGlobalTimelineUi() && state.previewIndex >= 0) {
      const tl = getPlanTimeline();
      const seg = tl.segments[state.previewIndex];
      const v = state.videos.find((x) => x.index === seg?.videoIndex);
      const offset = v?.offset_sec || 0;
      if (seg && seg.duration > 0) {
        const planSec = Math.max(0, player.currentTime - offset);
        const local = Math.min(seg.duration, Math.max(0, planSec - seg.planStart));
        state.previewGlobalSec = localToGlobal(tl, state.previewIndex, local);
        _updatePlayheadDom(tl);
      }
      updateCompositeClock();
    } else {
      $('player-time').textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration)}`;
    }

    if (
      state.previewActive
      && !player.seeking
      && state._previewEndTime !== null
      && player.currentTime >= state._previewEndTime
    ) {
      _advanceToNextPlayable();
      return;
    }
    if (state.source === 'original' && state.currentEntity === 'video') {
      _checkSegmentBoundary(player);
    }
  };
  player.onloadedmetadata = () => {
    if (isGlobalTimelineUi()) updateCompositeClock();
    else $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
  };
  player.onended = () => {
    if (state.previewActive) {
      _advanceToNextPlayable();
    }
  };
  player.onerror = () => setStatus('视频加载失败', 'err');

  // Preview bar buttons
  const prevBtn = $('btn-prev-seg');
  if (prevBtn) {
    prevBtn.innerHTML = `${icon('chevron_right', 14)}`;
    prevBtn.style.transform = 'scaleX(-1)';
    prevBtn.onclick = () => {
      const tl = getPlanTimeline();
      if (!tl.segments.length) return;
      let i = state.previewIndex;
      if (i < 0) i = 0;
      const cur = tl.segments[i];
      const local = state.previewGlobalSec - (cur?.globalStart || 0);
      if (local > 0.5 && cur) {
        seekToGlobal(cur.globalStart, { play: state.previewActive });
        return;
      }
      let p = i - 1;
      while (p >= 0 && tl.segments[p].duration <= 0) p--;
      if (p < 0) p = nextPlayableSegIndex(tl, -1) ?? 0;
      seekToGlobal(tl.segments[p].globalStart, { play: state.previewActive });
      if (state.previewActive) _setPlayBtnPause();
    };
  }
  const nextBtn = $('btn-next-seg');
  if (nextBtn) {
    nextBtn.innerHTML = `${icon('chevron_right', 14)}`;
    nextBtn.onclick = () => {
      const tl = getPlanTimeline();
      const n = nextPlayableSegIndex(
        tl,
        state.previewIndex < 0 ? -1 : state.previewIndex,
      );
      if (n == null) return;
      seekToGlobal(tl.segments[n].globalStart, { play: state.previewActive });
      if (state.previewActive) _setPlayBtnPause();
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
  seekToGlobal,
};

import { state } from './state.js';
import {
  $, $$, escapeHtml, setStatus,
  updateSidebarDay, updateEntityUI,
} from './utils.js';
import { api } from './api.js';
import { stopPreview } from './viewer.js';
import {
  loadProjects, loadConfig, loadPlans, loadProject, loadVideos, saveProject,
  updateSelectBtnVisibility, renderSteps, renderVideoList,
} from './sidebar-data.js';

// ── Selection ──────────────────────────────────────────────────

async function selectVideo(file) {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换视频吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'video';
  state.currentVideo = file;
  state.dirty = false;
  state.texts = null;
  state.voiceover = null;
  state.transcript = null;
  state._refineError = null;

  const v = state.videos.find(x => x.file === file);
  if (!v) return;

  const player = $('player');
  const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
  const tokenParam = sessionStorage.getItem('api_token');
  const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
  player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${projParam}${extraParam}`;
  $('player-name').textContent = file;

  if (v.text_json) {
    try {
      state.texts = await api('GET', `/api/texts?file=${encodeURIComponent(v.text_json)}`);
    } catch (e) { setStatus('texts 加载失败: ' + e.message, 'err'); }
  }
  if (v.script_json) {
    try {
      state.voiceover = await api('GET', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`);
    } catch (e) { setStatus('voiceover 加载失败: ' + e.message, 'err'); }
  }
  if (v.transcript_file) {
    try {
      state.transcript = await api('GET', `/api/transcripts?video=${encodeURIComponent(v.file)}`);
    } catch (e) { setStatus('transcript 加载失败: ' + e.message, 'err'); }
  }
  if (!state.plan) {
    try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
    catch (e) { /* plan 可选, 加载失败不报错 */ }
  }

  renderVideoList();
  import('./editor.js').then(mod => mod.renderActiveTab());
  updateEntityUI();
}

async function selectPlan(dayOverride) {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到规划吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.add('plan-mode');
  state.currentEntity = 'plan';
  state.dirty = false;
  if (dayOverride) state.currentDay = dayOverride;
  const runner = await import('./runner.js');
  runner._stopRunPoll();
  try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
  catch (e) { state.plan = null; }
  updateSidebarDay();
  updateEntityUI();
  updateSelectBtnVisibility();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectRun() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到运行吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'run';
  state.dirty = false;
  updateEntityUI();
  updateSelectBtnVisibility();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectConfig() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到设置吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'config';
  state.dirty = false;
  try {
    const resp = await api('GET', '/api/config/raw');
    if (resp.needs_init) {
      state.configRaw = null;
      state._needsConfigInit = true;
    } else {
      state.configRaw = resp;
      state._needsConfigInit = false;
    }
  } catch (e) {
    setStatus('配置加载失败: ' + e.message, 'err');
    state.configRaw = {};
    state._needsConfigInit = false;
  }
  updateEntityUI();
  updateSelectBtnVisibility();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectLogs() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到日志吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'logs';
  state.dirty = false;
  updateEntityUI();
  updateSelectBtnVisibility();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectTokens() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到统计吗？')) return;
  }
  if (state.previewActive) stopPreview();
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'tokens';
  state.dirty = false;
  updateEntityUI();
  updateSelectBtnVisibility();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

function toggleSelection() {
  state.selectionMode = !state.selectionMode;
  if (!state.selectionMode) {
    state.selectedFiles = [];
  }
  renderVideoList();
  const btn = document.getElementById('btn-select-videos');
  if (btn) {
    if (state.selectionMode) {
      btn.innerHTML = '<span class="icon">✕</span> 取消选择';
      btn.style.border = '1px solid var(--warn)';
    } else {
      btn.innerHTML = '<span class="icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></span> 选择视频';
      btn.style.border = '';
    }
  }
}

async function setSource(source) {
  if (source === state.source) return;
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换源吗？')) return;
  }
  if (state.previewActive) stopPreview();
  const oldVideo = state.videos.find(x => x.file === state.currentVideo);
  const oldMatchFile = oldVideo?.match?.file;
  $('player-pane').classList.remove('plan-mode');
  state.source = source;
  state.currentVideo = null;
  state.selectionMode = false;
  state.selectedFiles = [];
  state.texts = null;
  state.voiceover = null;
  $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === source));
  saveProject();
  try {
    await loadVideos();
    const target = oldVideo ? state.videos.find(v => v.file === oldMatchFile || v.match?.file === oldVideo.file) : null;
    if (state.videos.length) {
      if (state.currentEntity === 'plan') {
        import('./editor.js').then(mod => mod.renderActiveTab());
        if (target) {
          state.currentVideo = target.file;
          const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
          $('player').src = `/api/video?file=${encodeURIComponent(target.file)}&source=${source}${projParam}`;
          $('player-name').textContent = target.file;
          setStatus(`已切到 ${source} 视图`, 'ok');
        } else {
          $('player').removeAttribute('src');
          $('player-name').textContent = '请选择左侧视频或规划节点';
          setStatus(`已切到 ${source} 视图（仍停留在规划）`, 'ok');
        }
      } else {
        await selectVideo(target ? target.file : state.videos[0].file);
      }
    } else {
      $('player').removeAttribute('src');
      $('player-name').textContent = '请选择左侧视频';
      setStatus(`当前视图没有视频 (${source})`, 'warn');
    }
  } catch (e) {
    setStatus('切换源失败: ' + e.message, 'err');
  }
}

async function switchToOriginalThenCompress() {
  await setSource('original');
}

function goToRunTab() {
  $('player-pane').classList.remove('plan-mode');
  state.currentEntity = 'run';
  updateEntityUI();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

// ── Rerun progress overlay ──

let _rerunPollTimer = null;
let _rerunPollStart = 0;
const RERUN_POLL_TIMEOUT = 120_000;

function showRerunProgress(task, file) {
  const overlay = $('rerun-overlay');
  if (!overlay) return;
  overlay.classList.add('active');
  overlay.style.display = 'block';
  overlay.dataset.active = 'true';

  overlay.querySelector('.rerun-title').textContent = `重跑 ${task}`;
  overlay.querySelector('.rerun-file').textContent = file;
  overlay.querySelector('.rerun-status').textContent = '启动中...';
  overlay.querySelector('.rerun-progress-fill').style.width = '0%';
  overlay.querySelector('.rerun-logs').innerHTML = '<div class="rerun-log-line">连接中...</div>';

  if (_rerunPollTimer) clearInterval(_rerunPollTimer);
  _rerunPollStart = Date.now();
  _rerunPollTimer = setInterval(() => pollRerunStatus(task, file), 1500);
  pollRerunStatus(task, file);
}

function hideRerunProgress() {
  const overlay = $('rerun-overlay');
  if (!overlay) return;
  overlay.classList.remove('active');
  overlay.style.display = 'none';
  if (_rerunPollTimer) {
    clearInterval(_rerunPollTimer);
    _rerunPollTimer = null;
  }
}

function _rerunPollError(statusEl, label, msg) {
  const overlay = $('rerun-overlay');
  if (!overlay) return;
  overlay.dataset.active = 'false';
  if (_rerunPollTimer) { clearInterval(_rerunPollTimer); _rerunPollTimer = null; }
  if (statusEl) statusEl.innerHTML = `<span class="err">✗ ${escapeHtml(label)}</span>`;
  setStatus(msg, 'err');
  setTimeout(hideRerunProgress, 8000);
}

async function pollRerunStatus(task, file) {
  const overlay = $('rerun-overlay');
  if (!overlay || overlay.dataset.active !== 'true') return;

  try {
    const s = await api('GET', '/api/run/status');
    const fill = overlay.querySelector('.rerun-progress-fill');
    const statusEl = overlay.querySelector('.rerun-status');
    const logsEl = overlay.querySelector('.rerun-logs');

    if (Date.now() - _rerunPollStart > RERUN_POLL_TIMEOUT) {
      return _rerunPollError(statusEl, '超时', '重跑超时，请检查后端状态');
    }

    if (s.status === 'idle' || s.status === 'unknown') {
      if (Date.now() - _rerunPollStart > 10_000) {
        return _rerunPollError(statusEl, '未启动', '重跑任务未启动');
      }
      return;
    }

    if (fill && s.total > 0) {
      const pct = Math.round(s.current / s.total * 100);
      fill.style.width = Math.min(pct, 100) + '%';
    }

    if (statusEl) {
      statusEl.textContent = s.message || s.phase || '运行中...';
    }

    if (logsEl && s.logs && s.logs.length) {
      logsEl.innerHTML = s.logs.map(line =>
        `<div class="rerun-log-line">${escapeHtml(line)}</div>`
      ).join('');
      logsEl.scrollTop = logsEl.scrollHeight;
    }

    if (s.status === 'done') {
      overlay.dataset.active = 'false';
      if (_rerunPollTimer) {
        clearInterval(_rerunPollTimer);
        _rerunPollTimer = null;
      }
      if (statusEl) statusEl.innerHTML = '<span class="ok">✓ 完成</span>';
      setStatus('重跑完成', 'ok');
      setTimeout(() => {
        hideRerunProgress();
        refreshAfterRerun(task, file);
      }, 2000);
    } else if (s.status === 'error') {
      overlay.dataset.active = 'false';
      if (_rerunPollTimer) {
        clearInterval(_rerunPollTimer);
        _rerunPollTimer = null;
      }
      if (statusEl) statusEl.innerHTML = '<span class="err">✗ 出错</span>';
      setStatus('重跑出错', 'err');
      setTimeout(() => {
        hideRerunProgress();
      }, 8000);
    }
  } catch (e) {
    // poll error, ignore
  }
}

async function refreshAfterRerun(task, file) {
  await loadVideos();

  if (file && state.currentVideo === file) {
    const v = state.videos.find(x => x.file === file);
    if (!v) return;
    try {
      if ((task === 'texts' || task === 'all') && v.text_json) {
        state.texts = await api('GET', `/api/texts?file=${encodeURIComponent(v.text_json)}`);
      }
      if ((task === 'voiceover' || task === 'all') && v.script_json) {
        state.voiceover = await api('GET', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`);
      }
      import('./editor.js').then(mod => mod.renderActiveTab());
      updateEntityUI();
    } catch (e) {
      // content may not exist yet, ignore
    }
  }

  renderSteps();
}

// ── Directory browser ──
window._browseResolve = null;

function openBrowseDir(targetInputId) {
  const modal = $('modal-browse-dir');
  if (!modal) return;
  window._browseResolve = (path) => {
    const inp = document.getElementById(targetInputId);
    if (inp) inp.value = path;
  };
  modal.style.display = 'flex';
}

async function loadBrowseDir(path) {
  const pathEl = $('browse-path');
  const listEl = $('browse-dir-list');
  const upBtn = $('browse-up');
  const selectBtn = $('browse-select');
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  upBtn.style.display = 'none';
  selectBtn.disabled = true;
  try {
    const r = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(path)}`);
    if (r.error) { pathEl.textContent = '错误: ' + r.error; return; }
    pathEl.textContent = r.path || '(选择驱动器)';
    selectBtn.disabled = r.is_drive_list;
    if (r.is_drive_list) {
      upBtn.style.display = 'none';
    } else {
      upBtn.style.display = '';
      upBtn.onclick = () => loadBrowseDir(r.parent || '');
    }
    if (r.is_drive_list) {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${d}">📁 ${d}</div>`
      ).join('');
    } else {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${d}">📁 ${d.replace(/^.*[\\/]/, '')}</div>`
      ).join('');
    }
    listEl.querySelectorAll('.browse-item').forEach(el => {
      el.onclick = () => {
        loadBrowseDir(el.dataset.path);
      };
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

export {
  loadProjects,
  loadConfig,
  loadPlans,
  loadProject,
  loadVideos,
  saveProject,
  renderSteps,
  renderVideoList,
  selectVideo,
  selectPlan,
  selectRun,
  selectConfig,
  selectLogs,
  selectTokens,
  setSource,
  openBrowseDir,
  loadBrowseDir,
  switchToOriginalThenCompress,
  goToRunTab,
  toggleSelection,
  showRerunProgress,
  hideRerunProgress,
  pollRerunStatus,
};

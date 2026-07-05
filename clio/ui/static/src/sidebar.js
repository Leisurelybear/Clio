import { state } from './state.js';
import {
  $, $$, setStatus, fmtTime,
  updateSidebarDay, updateEntityUI,
} from './utils.js';
import { api } from './api.js';
import { stopPreview } from './viewer.js';
import { showRerunProgress, hideRerunProgress } from './sidebar-rerun.js';
import { openBrowseDir, loadBrowseDir } from './sidebar-browse.js';
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

  if (state.source === 'original') {
    player.onloadedmetadata = () => {
      $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
      if ((v.offset_sec || 0) > 0) {
        player.currentTime = v.offset_sec;
      }
    };
  }

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
    const [raw, global, project] = await Promise.all([
      api('GET', '/api/config/raw'),
      api('GET', '/api/config/global'),
      api('GET', '/api/config/project'),
    ]);
    if (raw.needs_init || project.needs_init) {
      state.configRaw = null;
      state.configGlobal = global || {};
      state.configProject = null;
      state._needsConfigInit = true;
    } else {
      state.configRaw = raw;
      state.configGlobal = global || {};
      state.configProject = project || {};
      state._needsConfigInit = false;
    }
  } catch (e) {
    setStatus('配置加载失败: ' + e.message, 'err');
    state.configRaw = {};
    state.configGlobal = {};
    state.configProject = {};
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

function sameVideoIndex(a, b) {
  if (a === undefined || a === null || b === undefined || b === null) return false;
  const left = String(a).trim();
  const right = String(b).trim();
  if (!left || !right) return false;
  if (left === right) return true;
  const leftNum = Number.parseInt(left, 10);
  const rightNum = Number.parseInt(right, 10);
  return Number.isFinite(leftNum) && Number.isFinite(rightNum) && leftNum === rightNum;
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
    const target = oldVideo
      ? state.videos.find(v =>
          v.file === oldMatchFile
          || v.match?.file === oldVideo.file
          || sameVideoIndex(v.index, oldVideo.index)
        )
      : null;
    if (state.videos.length) {
      if (state.currentEntity === 'plan') {
        import('./editor.js').then(mod => mod.renderActiveTab());
        if (target) {
          state.currentVideo = target.file;
          const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
          const tokenParam = sessionStorage.getItem('api_token');
          const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
          $('player').src = `/api/video?file=${encodeURIComponent(target.file)}&source=${source}${projParam}${extraParam}`;
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
};

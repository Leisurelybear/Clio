import { state } from './state.js';
import {
  $, $$,
  escapeHtml,
  setStatus,
  updateSaveBtn,
  updateSidebarDay,
  updateProjectSidebar,
  updateEntityUI,
} from './utils.js';
import { api, icon } from './api.js';
import { stopPreview } from './viewer.js';

// ── Data loading ───────────────────────────────────────────────

async function loadProjects() {
  try {
    const r = await api('GET', '/api/projects');
    state.projects = r.projects || [];
    state.lastProject = r.last_project || null;
    state.currentProject = state.projects.find(p => p.is_current) || null;
    if (state.currentProject && !state.currentProjectName) {
      state.currentProjectName = state.currentProject.name;
    }
    updateProjectSidebar();
  } catch (e) {
    state.projects = [];
    state.currentProject = null;
    state.currentProjectName = null;
    state.lastProject = null;
    updateProjectSidebar();
  }
}

async function loadConfig() {
  state.config = await api('GET', '/api/config');
  $('proj-name').textContent = state.config.input_dir;
  $('proj-name').title = `input: ${state.config.input_dir}\noutput: ${state.config.output_dir}`;
}

async function loadPlans() {
  try {
    const r = await api('GET', '/api/plans');
    state.availablePlans = r.plans || [];
  } catch (e) {
    state.availablePlans = [];
  }
}

async function loadVideos() {
  const r = await api('GET', `/api/videos?source=${state.source}`);
  state.videos = r.videos;
  state.groups = r.groups || {};
  $('video-count').textContent = `(${state.videos.length})`;
  renderVideoList();
}

async function loadProject() {
  try {
    const proj = await api('GET', '/api/project');
    if (proj.currentDay) state.currentDay = proj.currentDay;
    if (proj.source && proj.source !== state.source) {
      state.source = proj.source;
      $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === state.source));
    }
    state.steps = proj.steps || {};
    state.projectName = proj.name || '';
    if (proj.lastEntity && ['video', 'plan', 'run', 'config', 'logs'].includes(proj.lastEntity)) {
      state.lastEntity = proj.lastEntity;
    }
    if (proj.lastVideo) state.lastVideo = proj.lastVideo;
  } catch (e) { /* 非关键, 静默忽略 */ }
}

async function saveProject(extra) {
  try {
    await api('PUT', '/api/project', Object.assign({
      currentDay: state.currentDay,
      source: state.source,
      lastEntity: state.currentEntity,
      lastVideo: state.currentVideo,
      name: state.projectName || undefined,
    }, extra || {}));
  } catch (e) { /* 静默 */ }
}

function renderSteps() {
  const ul = $('step-list');
  if (!ul) return;
  const labels = { compress: '压缩', analyze: '分析', scripts: '口播', transcribe: '转录', plan: '规划', label: '标号', cut: '裁剪' };
  ul.innerHTML = '';
  for (const [key, label] of Object.entries(labels)) {
    const done = state.steps[key];
    const li = document.createElement('li');
    li.className = 'step-item' + (done ? ' done' : '');
    li.innerHTML = `<span class="step-icon">${icon(done ? 'check' : 'circle', 14)}</span><span class="step-label">${label}</span>`;
    ul.appendChild(li);
  }
}

function renderVideoItem(v) {
  const li = document.createElement('li');
  li.className = 'video-item';
  if (state.currentVideo === v.file) li.classList.add('active');
  if (!v.match) li.classList.add('no-match');

  let display = v.file.replace(/^\d+_/, '');
  if (v.segment_label) {
    display = display.replace(/_seg\d+$/i, '') + ` [seg ${v.segment_label}]`;
  }

  const tCls = v.text_json ? 'has' : 'miss';
  const sCls = v.script_json ? 'has' : 'miss';
  const tTransCls = v.transcript_file ? 'has' : 'miss';
  const tLabel = v.text_json ? `${icon('check', 12)} texts` : '· texts';
  const sLabel = v.script_json ? `${icon('check', 12)} voiceover` : '· voiceover';
  const tTransLabel = v.transcript_file ? `${icon('check', 12)} trans.` : '· trans.';
  const counterpartLabel = state.source === 'compressed' ? '原' : '压';
  let matchBadge;
  if (v.match) {
    if (v.segment_matches && v.segment_matches.length > 1) {
      const segList = v.segment_matches.map(m => m.file).join(', ');
      matchBadge = `<span class="match-badge" title="${escapeHtml(segList)}">→ ${counterpartLabel}: ${v.segment_matches.length} 段</span>`;
    } else {
      matchBadge = `<span class="match-badge" title="${escapeHtml(v.match.file)}">→ ${counterpartLabel}: ${escapeHtml(v.match.file)}</span>`;
    }
  } else {
    matchBadge = `<span class="match-badge miss" title="没有对应的${state.source === 'compressed' ? '原视频' : '压缩视频'}">无对应</span>`;
  }
  li.innerHTML = `
    <div class="video-name">${v.index ? '[' + v.index + '] ' : ''}${escapeHtml(display)}</div>
    ${v.title ? `<div class="video-title">${escapeHtml(v.title)}</div>` : ''}
    <div class="video-match">${matchBadge}</div>
    <div class="video-meta">
      <span class="${tCls}">${tLabel}</span>
      &nbsp;
      <span class="${sCls}">${sLabel}</span>
      &nbsp;
      <span class="${tTransCls}">${tTransLabel}</span>
    </div>
    <div class="video-actions">
      <button class="menu-btn" title="操作">⋮</button>
      <div class="menu-dropdown">
        ${state.source === 'original'
          ? `<button class="menu-item" data-action="compress" title="用 ffmpeg 将原视频压缩为 640p">压缩视频</button>
             <button class="menu-item" data-action="transcribe" title="用 faster-whisper 提取音频转文字">Whisper 转录</button>
             <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">AI分析视频</button>
             <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">重跑口播文案</button>
             <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">重跑全部</button>`
          : `<button class="menu-item" data-action="compress" disabled style="opacity:0.4" title="视频已压缩">压缩视频</button>
             <button class="menu-item" data-action="analyze" title="调用 AI 重新分析视频内容">AI分析视频</button>
             <button class="menu-item" data-action="voiceover" title="基于分析结果，重新用 AI 生成口播解说文案">重跑口播文案</button>
             <button class="menu-item" data-action="all" title="依次执行 AI 分析 + 口播文案">重跑全部</button>`
        }
      </div>
    </div>
  `;

  li.onclick = (e) => {
    if (e.target.closest('.video-actions')) return;
    selectVideo(v.file);
  };

  // ── Dot-menu toggle (portal 方案：移到 body 下逃逸侧栏) ──
  const menuBtn = li.querySelector('.menu-btn');
  const dropdown = li.querySelector('.menu-dropdown');
  menuBtn.onclick = (e) => {
    e.stopPropagation();
    if (_portalDropdown) { _portalDropdown.remove(); _portalDropdown = null; }
    if (_portalCloseHandler) { document.removeEventListener('click', _portalCloseHandler); _portalCloseHandler = null; }
    const rect = menuBtn.getBoundingClientRect();
    const clone = dropdown.cloneNode(true);
    clone.classList.add('open');
    clone.style.cssText = 'position:fixed;top:' + (rect.bottom + 4) + 'px;right:auto;left:' + Math.max(4, rect.right - 160) + 'px;z-index:10000;min-width:160px;width:auto;';
    document.body.appendChild(clone);
    _portalDropdown = clone;
    clone.querySelectorAll('.menu-item').forEach(item => {
      item.onclick = async (ev) => {
        ev.stopPropagation(); if (item.disabled) return;
        clone.remove(); _portalDropdown = null;
        if (_portalCloseHandler) { document.removeEventListener('click', _portalCloseHandler); _portalCloseHandler = null; }
        const task = item.dataset.action;
        const file = v.file;
        setStatus(`正在重跑 ${task} (${file})...`, 'ok');
        try {
          const r = await api('POST', '/api/rerun', {
            video: file, task: task, source: state.source, index: v.index || undefined,
          });
          if (r.ok) { setStatus(r.message || `${task} 已启动`, 'ok'); showRerunProgress(task, file); }
          else { throw new Error(r.error || '重跑失败'); }
        } catch (e) { setStatus('重跑失败: ' + e.message, 'err'); }
      };
    });
    if (!_portalCloseHandler) {
      _portalCloseHandler = (ev) => {
        if (_portalDropdown && !_portalDropdown.contains(ev.target) && !ev.target.closest('.menu-btn')) {
          _portalDropdown.remove(); _portalDropdown = null;
          document.removeEventListener('click', _portalCloseHandler);
          _portalCloseHandler = null;
        }
      };
      setTimeout(() => document.addEventListener('click', _portalCloseHandler), 0);
    }
  };

  return li;
}

function renderVideoList() {
  const ul = $('video-list');
  ul.innerHTML = '';
  if (!state.videos.length) {
    const isCompressedEmpty = state.source === 'compressed';
    if (isCompressedEmpty) {
      ul.innerHTML = `
        <li class="empty-state">
          ${icon('folder', 36)}
          <h4>暂无压缩视频</h4>
          <p>未找到压缩后的视频文件（output/compressed/）</p>
          <p class="hint">请先压缩原视频，或切换到「原视频」视图查看素材</p>
          <p style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
            <button class="sidebar-btn" onclick="switchToOriginalThenCompress()" style="background:var(--accent);color:#fff;border:none;padding:7px 14px;border-radius:var(--radius-sm);cursor:pointer;font:inherit;font-size:var(--text-sm)">${icon('folder', 14)} 切换到原视频</button>
            <button class="sidebar-btn" onclick="goToRunTab()" title="运行流水线中的压缩步骤" style="background:var(--bg-surface-2);color:var(--text-primary);border:1px solid var(--border);padding:7px 14px;border-radius:var(--radius-sm);cursor:pointer;font:inherit;font-size:var(--text-sm)">${icon('play', 14)} 去压缩视频</button>
          </p>
          <p class="hint" style="margin-top:8px">素材目录: ${escapeHtml(state.config?.input_dir || '未知')}</p>
        </li>
      `;
    } else {
      ul.innerHTML = `
        <li class="empty-state">
          ${icon('video', 36)}
          <h4>暂无视频素材</h4>
          <p>请将视频文件（.mp4/.mov/.mkv等）放入素材目录</p>
          <p class="hint">素材目录: ${escapeHtml(state.config?.input_dir || '未知')}</p>
        </li>
      `;
    }
    return;
  }

  // Split into grouped vs ungrouped
  const grouped = state.videos.filter(v => v.group_key);
  const ungrouped = state.videos.filter(v => !v.group_key);

  // --- Grouped section ---
  const groups = {};
  for (const v of grouped) {
    (groups[v.group_key] ??= []).push(v);
  }

  for (const [key, items] of Object.entries(groups)) {
    const header = document.createElement('li');
    header.className = 'video-group-header';
    const isExpanded = state.expandedGroups[key] !== false;
    header.innerHTML = `
      <span class="group-toggle">${isExpanded ? '▼' : '▶'}</span>
      <span class="group-name">${escapeHtml(key)}</span>
      <span class="group-count-badge">(${items.length} 段)</span>
    `;
    header.onclick = (e) => {
      e.stopPropagation();
      const wasExpanded = state.expandedGroups[key] !== false;
      state.expandedGroups[key] = !wasExpanded;
      const childUl = header.nextElementSibling;
      if (childUl) {
        childUl.style.display = state.expandedGroups[key] ? '' : 'none';
        header.querySelector('.group-toggle').textContent = state.expandedGroups[key] ? '▼' : '▶';
      }
    };
    ul.appendChild(header);

    const childUl = document.createElement('ul');
    childUl.className = 'video-group-children';
    childUl.style.display = isExpanded ? '' : 'none';
    for (const v of items) {
      childUl.appendChild(renderVideoItem(v));
    }
    ul.appendChild(childUl);
  }

  // --- Ungrouped section ---
  for (const v of ungrouped) {
    ul.appendChild(renderVideoItem(v));
  }
}

function _resetDropdownPosition(dropdown) {
  dropdown.style.position = '';
  dropdown.style.top = '';
  dropdown.style.right = '';
  dropdown.style.left = '';
  dropdown.style.zIndex = '';
}

// ── Selection ──────────────────────────────────────────────────

async function selectVideo(file) {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换视频吗？')) return;
  }
  if (state.previewActive) stopPreview();
  state.currentEntity = 'video';
  state.currentVideo = file;
  state.dirty = false;
  state.texts = null;
  state.voiceover = null;
  state.transcript = null;

  const v = state.videos.find(x => x.file === file);
  if (!v) return;

  const player = $('player');
  const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
  player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${projParam}`;
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
  state.currentEntity = 'plan';
  state.dirty = false;
  if (dayOverride) state.currentDay = dayOverride;
  // 停止运行轮询，防止其完成回调清空 state.plan
  const runner = await import('./runner.js');
  runner._stopRunPoll();
  try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
  catch (e) { state.plan = null; }
  updateSidebarDay();
  updateEntityUI();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectRun() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到运行吗？')) return;
  }
  if (state.previewActive) stopPreview();
  state.currentEntity = 'run';
  state.dirty = false;
  updateEntityUI();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectConfig() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到设置吗？')) return;
  }
  if (state.previewActive) stopPreview();
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
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function selectLogs() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到日志吗？')) return;
  }
  if (state.previewActive) stopPreview();
  state.currentEntity = 'logs';
  state.dirty = false;
  updateEntityUI();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

async function setSource(source) {
  if (source === state.source) return;
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换源吗？')) return;
  }
  if (state.previewActive) stopPreview();
  state.source = source;
  state.currentVideo = null;
  state.texts = null;
  state.voiceover = null;
  $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === source));
  saveProject();  // 持久化 source 选择
  try {
    await loadVideos();
    if (state.videos.length) {
      if (state.currentEntity === 'plan') {
        // stay in plan: don't auto-select a video, just clear the player
        $('player').removeAttribute('src');
        $('player-name').textContent = '请选择左侧视频或规划节点';
        // re-render plan so segment click handlers use the new source's v.file
        import('./editor.js').then(mod => mod.renderActiveTab());
        setStatus(`已切到 ${source} 视图（仍停留在规划）`, 'ok');
      } else {
        await selectVideo(state.videos[0].file);
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

// ── Empty-state helpers ──
async function switchToOriginalThenCompress() {
  await setSource('original');
}

function goToRunTab() {
  state.currentEntity = 'run';
  updateEntityUI();
  import('./editor.js').then(mod => mod.renderActiveTab());
}

// ── Directory browser ──
// _browseResolve exposed on window for cross-module access (main.js reads it)
window._browseResolve = null;

function openBrowseDir(targetInputId) {
  const modal = $('modal-browse-dir');
  if (!modal) return;
  window._browseResolve = (path) => {
    const inp = document.getElementById(targetInputId);
    if (inp) inp.value = path;
  };
  modal.style.display = 'flex';
  loadBrowseDir('');
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
    // click to navigate
    listEl.querySelectorAll('.browse-item').forEach(el => {
      el.onclick = () => {
        loadBrowseDir(el.dataset.path);
      };
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

/* ── Dropdown portal ── */
let _portalDropdown = null;
let _portalCloseHandler = null;

/* ── Rerun progress overlay (single-video rerun) ── */
let _rerunPollTimer = null;
let _rerunPollStart = 0;
const RERUN_POLL_TIMEOUT = 120_000; // 120s without terminal state = give up

function showRerunProgress(task, file) {
  const overlay = $('rerun-overlay');
  if (!overlay) return;
  overlay.classList.add('active');
  overlay.style.display = 'block';
  overlay.dataset.active = 'true';

  // Reset display
  overlay.querySelector('.rerun-title').textContent = `重跑 ${task}`;
  overlay.querySelector('.rerun-file').textContent = file;
  overlay.querySelector('.rerun-status').textContent = '启动中...';
  overlay.querySelector('.rerun-progress-fill').style.width = '0%';
  overlay.querySelector('.rerun-logs').innerHTML = '<div class="rerun-log-line">连接中...</div>';

  // Start polling
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

    // Timeout: no terminal state within RERUN_POLL_TIMEOUT
    if (Date.now() - _rerunPollStart > RERUN_POLL_TIMEOUT) {
      return _rerunPollError(statusEl, '超时', '重跑超时，请检查后端状态');
    }

    // Idle before first progress: task may have failed to start
    if (s.status === 'idle' || s.status === 'unknown') {
      if (Date.now() - _rerunPollStart > 10_000) {
        return _rerunPollError(statusEl, '未启动', '重跑任务未启动');
      }
      return;
    }

    // Update progress bar
    if (fill && s.total > 0) {
      const pct = Math.round(s.current / s.total * 100);
      fill.style.width = Math.min(pct, 100) + '%';
    }

    // Update status text
    if (statusEl) {
      statusEl.textContent = s.message || s.phase || '运行中...';
    }

    // Update log lines
    if (logsEl && s.logs && s.logs.length) {
      logsEl.innerHTML = s.logs.map(line =>
        `<div class="rerun-log-line">${escapeHtml(line)}</div>`
      ).join('');
      logsEl.scrollTop = logsEl.scrollHeight;
    }

    // Terminal states
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
  // Reload videos list to pick up new sidecar files
  await loadVideos();

  // If the rerun's video is still the current selection, reload its data
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
  setSource,
  openBrowseDir,
  loadBrowseDir,
  switchToOriginalThenCompress,
  goToRunTab,
  showRerunProgress,
  hideRerunProgress,
  pollRerunStatus,
};

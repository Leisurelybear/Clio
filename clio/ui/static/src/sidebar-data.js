import { state } from './state.js';
import {
  $, $$, escapeHtml, setStatus, updateProjectSidebar,
} from './utils.js';
import { api, icon } from './api.js';
import { updateRunFilesBadge } from './runner.js';

// ── Data loading ───────────────────────────────────────────────

export async function loadProjects() {
  try {
    const r = await api('GET', '/api/projects');
    state.projects = r.projects || [];
    state.lastProject = r.last_project || null;
    state.currentProject = state.projects.find(p => p.is_current) || null;
    if (state.currentProject) {
      if (!state.currentProjectName) state.currentProjectName = state.currentProject.name;
      if (!state.currentProjectInputDir) state.currentProjectInputDir = state.currentProject.input_dir;
    }
    updateProjectSidebar();
  } catch (e) {
    state.projects = [];
    state.currentProject = null;
    state.currentProjectName = null;
    state.currentProjectInputDir = null;
    state.lastProject = null;
    updateProjectSidebar();
  }
}

export async function loadConfig() {
  try {
    state.config = await api('GET', '/api/config');
  } catch {
    state.config = { input_dir: '(加载失败)', output_dir: '' };
  }
  $('proj-name').textContent = state.config.input_dir;
  $('proj-name').title = `input: ${state.config.input_dir}\noutput: ${state.config.output_dir}`;
}

export async function loadPlans() {
  try {
    const r = await api('GET', '/api/plans');
    state.availablePlans = r.plans || [];
  } catch (e) {
    state.availablePlans = [];
  }
}

export function updateSelectBtnVisibility() {
  const btn = document.getElementById('btn-select-videos');
  if (!btn) return;
  const visible = state.videos.length > 0 && state.currentEntity === 'run';
  btn.style.display = visible ? 'flex' : 'none';
  if (!visible && state.selectionMode) {
    state.selectionMode = false;
    state.selectedFiles = [];
    renderVideoList();
  }
}

export async function loadVideos() {
  const r = await api('GET', `/api/videos?source=${state.source}`);
  state.videos = r.videos;
  state.groups = r.groups || {};
  $('video-count').textContent = `(${state.videos.length})`;
  updateSelectBtnVisibility();
  renderVideoList();
}

export async function loadProject() {
  try {
    const proj = await api('GET', '/api/project');
    if (proj.currentDay) state.currentDay = proj.currentDay;
    if (proj.source && proj.source !== state.source) {
      state.source = proj.source;
      $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === state.source));
    }
    state.steps = proj.steps || {};
    state.projectName = proj.name || '';
    if (proj.lastEntity && ['video', 'plan', 'run', 'config', 'logs', 'tokens'].includes(proj.lastEntity)) {
      state.lastEntity = proj.lastEntity;
    }
    if (proj.lastVideo) state.lastVideo = proj.lastVideo;
  } catch (e) { /* 非关键, 静默忽略 */ }
}

export async function saveProject(extra) {
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

export function renderSteps() {
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

// ── Video list rendering ───────────────────────────────────────

let _portalDropdown = null;
let _portalCloseHandler = null;

function renderVideoItem(v) {
  const li = document.createElement('li');
  let checkboxHtml = '';
  let selectedClass = '';
  if (state.selectionMode) {
    const isSelected = state.selectedFiles.includes(v.file);
    selectedClass = isSelected ? ' selected' : '';
    checkboxHtml = `<input type="checkbox" class="video-checkbox" data-file="${v.file}" ${isSelected ? 'checked' : ''}>`;
  }
  li.className = 'video-item' + selectedClass;
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
  li.innerHTML = `<div class="video-name-row">${checkboxHtml}
    <div class="video-name">${v.index ? '[' + v.index + '] ' : ''}${escapeHtml(display)}</div></div>
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
    if (state.selectionMode) {
      if (e.target.closest('.video-checkbox')) return;
      const cb = li.querySelector('.video-checkbox');
      if (cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change', { bubbles: true })); }
      return;
    }
    import('./sidebar.js').then(mod => mod.selectVideo(v.file));
  };

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
          if (r.ok) {
            setStatus(r.message || `${task} 已启动`, 'ok');
            import('./sidebar-rerun.js').then(mod => mod.showRerunProgress(task, file));
          } else { throw new Error(r.error || '重跑失败'); }
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

  if (state.selectionMode) {
    const cb = li.querySelector('.video-checkbox');
    if (cb) {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        if (cb.checked) {
          if (!state.selectedFiles.includes(v.file)) state.selectedFiles.push(v.file);
        } else {
          state.selectedFiles = state.selectedFiles.filter(f => f !== v.file);
        }
        renderVideoList();
      });
    }
  }

  return li;
}

export function renderVideoList() {
  const ul = $('video-list');
  ul.innerHTML = '';
  if (state.selectionMode) {
    const headerDiv = document.createElement('div');
    headerDiv.className = 'selection-header';
    const allSelected = state.videos.length > 0 && state.selectedFiles.length === state.videos.length;
    headerDiv.innerHTML = `
      <span class="selection-count">已选: ${state.selectedFiles.length}/${state.videos.length}</span>
      <span class="selection-action" data-action="all">${allSelected ? '取消全选' : '全选'}</span>
    `;
    headerDiv.querySelector('[data-action="all"]').onclick = () => {
      if (allSelected) {
        state.selectedFiles = [];
      } else {
        state.selectedFiles = state.videos.map(v => v.file);
      }
      renderVideoList();
    };
    ul.appendChild(headerDiv);
  }
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

  const grouped = state.videos.filter(v => v.group_key);
  const ungrouped = state.videos.filter(v => !v.group_key);

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

  for (const v of ungrouped) {
    ul.appendChild(renderVideoItem(v));
  }

  updateRunFilesBadge();
}

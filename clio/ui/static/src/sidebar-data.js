import { state } from './state.js';
import {
  $, $$, escapeHtml, setStatus, updateProjectSidebar,
} from './utils.js';
import { api, icon } from './api.js';
import { updateRunFilesBadge } from './runner.js';

// ── Video removal helper ──────────────────────────────────────

export async function removeVideoFromProject(file, absPath = null) {
  try {
    const r = await api('GET', '/api/videos/selected');
    const videos = (r.videos || []).slice();
    const norm = (p) => String(p || '').replace(/\\/g, '/').toLowerCase();
    const targetAbs = absPath ? norm(absPath) : '';
    const display = String(file || '');
    const baseName = display.replace(/^.*[\\/]/, '');
    // "001_GL010695.MP4" → "GL010695.MP4"
    const stripped = baseName.replace(/^\d+_/, '');

    let idx = -1;
    if (targetAbs) {
      idx = videos.findIndex(p => norm(p) === targetAbs);
    }
    if (idx === -1) {
      idx = videos.findIndex(p => {
        const n = norm(p);
        const leaf = n.split('/').pop() || '';
        return (
          leaf === baseName.toLowerCase()
          || leaf === stripped.toLowerCase()
          || n.endsWith('/' + baseName.toLowerCase())
          || n.endsWith('/' + stripped.toLowerCase())
          || n === display.toLowerCase()
        );
      });
    }
    if (idx === -1) {
      setStatus('未在项目视频列表中找到该文件', 'err');
      return;
    }
    videos.splice(idx, 1);
    await api('PUT', '/api/videos/selected', { videos });
    await loadVideos();
    setStatus(`已移除 ${stripped || baseName || file}`, 'ok');
  } catch (e) {
    setStatus('移除失败: ' + e.message, 'err');
  }
}

// ── Data loading ───────────────────────────────────────────────

export async function loadProjects() {
  try {
    const r = await api('GET', '/api/projects');
    state.projects = r.projects || [];
    state.lastProject = r.last_project || null;
    state.currentProject = state.projects.find(p => p.is_current) || null;
    if (state.currentProject) {
      if (!state.currentProjectName) state.currentProjectName = state.currentProject.name;
      if (!state.currentProjectDir) state.currentProjectDir = state.currentProject.project_dir;
    }
    updateProjectSidebar();
  } catch (e) {
    state.projects = [];
    state.currentProject = null;
    state.currentProjectName = null;
    state.currentProjectDir = null;
    state.lastProject = null;
    updateProjectSidebar();
  }
}

export async function loadConfig() {
  try {
    state.config = await api('GET', '/api/config');
  } catch {
    state.config = { project_dir: '(加载失败)', output_dir: '' };
  }
  $('proj-name').textContent = state.config.project_dir || '';
  $('proj-name').title = `project: ${state.config.project_dir || ''}\noutput: ${state.config.output_dir || ''}`;
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
  // Hint when project has no selected originals yet
  if (state.source === 'original' && state.videos.length === 0) {
    try {
      const sel = await api('GET', '/api/videos/selected');
      const n = (sel.videos || []).length;
      if (n === 0) {
        setStatus('项目尚无视频，点击「添加视频」从磁盘选择素材（或运行 python main.py migrate）', 'ok');
      }
    } catch (_) { /* ignore */ }
  }
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

function scrollActiveVideoIntoView() {
  requestAnimationFrame(() => {
    const active = document.querySelector('#video-list .video-item.active');
    if (active) {
      active.scrollIntoView({ block: 'nearest' });
    }
  });
}

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
  if (v.missing) li.classList.add('missing');

  let display = v.file.replace(/^\d+_/, '');
  if (v.segment_label) {
    display = display.replace(/_seg\d+$/i, '') + ` [seg ${v.segment_label}]`;
  }
  if (v.missing) {
    display = display + ' (离线)';
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
      matchBadge = `<button type="button" class="match-badge match-jump" title="${escapeHtml(segList)}">→ ${counterpartLabel}: ${escapeHtml(v.index || '')}/${v.segment_matches.length} 段</button>`;
    } else {
      matchBadge = `<button type="button" class="match-badge match-jump" title="${escapeHtml(v.match.file)}">→ ${counterpartLabel}: ${escapeHtml(v.match.file)}</button>`;
    }
  } else {
    matchBadge = `<span class="match-badge miss" title="没有对应的${state.source === 'compressed' ? '原视频' : '压缩视频'}">无对应</span>`;
  }
  const stepBadges = [
    {label:'压缩', done: state.source === 'compressed'},
    {label:'分析', done: !!v.text_json},
    {label:'口播', done: !!v.script_json},
    {label:'转录', done: !!v.transcript_file},
  ].map(s => `<span class="video-step-badge ${s.done ? 'done' : 'pending'}">${s.label}</span>`).join('');

  const durHtml = v.duration_sec ? `<span class="video-duration">${Math.round(v.duration_sec)}s</span>` : '';

  li.innerHTML = `<div class="video-thumb">${icon('video')}</div>
    <div class="video-info">
      <div class="video-name">${checkboxHtml}${v.index ? '[' + v.index + '] ' : ''}${escapeHtml(display)}${durHtml}</div>
      <div class="video-step-badges">${stepBadges}</div>
      ${v.title ? `<div class="video-title">${escapeHtml(v.title)}</div>` : ''}
      <div class="video-match">${matchBadge}</div>
    </div>
      <div class="video-actions">
        <button class="menu-btn" title="操作">⋮</button>
        <div class="menu-dropdown">
          ${state.source === 'original'
            ? (v.missing
               ? `<button class="menu-item" disabled style="opacity:0.4" title="文件离线">压缩视频</button>
               <button class="menu-item" disabled style="opacity:0.4" title="文件离线">Whisper 转录</button>
               <div class="menu-divider"></div>
               <button class="menu-item menu-item-danger" data-action="remove" title="从项目中移除该视频">从项目移除</button>`
               : `<button class="menu-item" data-action="compress" title="用 ffmpeg 将原视频压缩为 640p">压缩视频</button>
               <button class="menu-item" data-action="transcribe" title="用 faster-whisper 提取音频转文字">Whisper 转录</button>
               <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">AI分析视频</button>
               <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">重跑口播文案</button>
               <button class="menu-item" disabled style="opacity:0.4" title="请先压缩视频">重跑全部</button>
               <div class="menu-divider"></div>
               <button class="menu-item menu-item-danger" data-action="remove" title="从项目中移除该视频">从项目移除</button>`)
            : `<button class="menu-item" data-action="compress" disabled style="opacity:0.4" title="视频已压缩">压缩视频</button>
               <button class="menu-item" data-action="analyze" title="调用 AI 重新分析视频内容">AI分析视频</button>
               <button class="menu-item" data-action="voiceover" title="基于分析结果，重新用 AI 生成口播解说文案">重跑口播文案</button>
               <button class="menu-item" data-action="all" title="依次执行 AI 分析 + 口播文案">重跑全部</button>`
          }
        </div>
      </div>
  `;

  li.onclick = (e) => {
    if (e.target.closest('.match-jump')) return;
    if (e.target.closest('.video-actions')) return;
    if (v.missing) {
      setStatus('该视频文件当前不可用（路径离线或不存在）', 'warn');
      return;
    }
    if (state.selectionMode) {
      if (e.target.closest('.video-checkbox')) return;
      const cb = li.querySelector('.video-checkbox');
      if (cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change', { bubbles: true })); }
      return;
    }
    import('./sidebar.js').then(mod => mod.selectVideo(v.file));
  };

  const matchJump = li.querySelector('.match-jump');
  if (matchJump) {
    matchJump.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      import('./sidebar.js').then(mod => mod.jumpToCounterpart(v));
    };
  }

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
        if (task === 'remove') {
          if (confirm(`确定从项目中移除 ${file} 吗？`)) {
            await removeVideoFromProject(file, v.abs_path || (v.match && v.match.abs_path) || null);
          }
          return;
        }
        setStatus(`正在重跑 ${task} (${file})...`, 'ok');
        try {
          const r = await api('POST', '/api/rerun', {
            video: file,
            task: task,
            source: state.source,
            index: v.index || undefined,
            abspath: v.abs_path || (v.match && v.match.abs_path) || undefined,
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
        </li>
      `;
    } else {
      ul.innerHTML = `
        <li class="empty-state">
          ${icon('video', 36)}
          <h4>暂无视频素材</h4>
          <p>项目 <code>videos.json</code> 中还没有选中的原始视频</p>
          <p class="hint">点击上方「添加视频」从磁盘勾选素材；旧项目可运行 <code>python main.py migrate</code></p>
          <p style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
            <button class="sidebar-btn" id="empty-add-videos" style="background:var(--accent);color:#fff;border:none;padding:7px 14px;border-radius:var(--radius-sm);cursor:pointer;font:inherit;font-size:var(--text-sm)">${icon('plus', 14)} 添加视频</button>
          </p>
        </li>
      `;
      const addBtn = ul.querySelector('#empty-add-videos');
      if (addBtn) {
        addBtn.onclick = () => {
          import('./sidebar-video-manage.js').then(m => m.openVideoManager());
        };
      }
    }
    return;
  }

  const groups = {};
  for (const v of state.videos.filter(v => v.group_key)) {
    (groups[v.group_key] ??= []).push(v);
  }
  const renderedGroups = new Set();

  for (const v of state.videos) {
    if (!v.group_key) {
      ul.appendChild(renderVideoItem(v));
      continue;
    }
    const key = v.group_key;
    if (renderedGroups.has(key)) continue;
    renderedGroups.add(key);
    const items = groups[key] || [];
    if (items.some(item => item.file === state.currentVideo)) {
      state.expandedGroups[key] = true;
    }
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

  scrollActiveVideoIntoView();
  updateRunFilesBadge();
}

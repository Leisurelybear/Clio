import { state } from './state.js';
import { $, $$, escapeHtml, setStatus, updateSidebarDay } from './utils.js';
import { api, submitToken } from './api.js';
import { initLayout } from './layout.js';
import { initTheme, toggleTheme } from './theme.js';
import { addToast } from './toast.js';
import { updateRuntimeWarnings } from './runtime-warnings.js';
import { setupPlayer } from './viewer.js';
import { save, initProjectConfig, renderActiveTab, refineCurrentFile } from './editor.js';
import {
  loadProjects,
  loadConfig,
  loadProject,
  loadPlans,
  loadVideos,
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
  hideRerunProgress,
} from './sidebar.js';

// Expose functions referenced by inline onclick handlers in HTML
window.switchToOriginalThenCompress = switchToOriginalThenCompress;
window.goToRunTab = goToRunTab;
window.initProjectConfig = initProjectConfig;
window.refineCurrentFile = refineCurrentFile;
window.addToast = addToast;

async function init() {
  initLayout();
  initTheme();

  // 从 URL 读取 project + project_dir 参数
  const urlParams = new URLSearchParams(window.location.search);
  const urlProject = urlParams.get('project');
  const urlProjectDir = urlParams.get('project_dir');
  if (urlProject) {
    state.currentProjectName = urlProject;
  }
  if (urlProjectDir) {
    state.currentProjectDir = urlProjectDir;
  }

  // Auto-capture token from URL
  const urlToken = urlParams.get('token');
  if (urlToken) {
    sessionStorage.setItem('api_token', urlToken);
    const newUrl = location.pathname + (location.hash || '');
    history.replaceState(null, '', newUrl);
  }

  // 新建/打开项目模态框（必须在 try 之前绑定，空状态时也会用到）
  const newModal = $('modal-new-project');
  $('btn-new-project').onclick = () => { newModal.style.display = 'flex'; };
  $('np-cancel').onclick = () => { newModal.style.display = 'none'; };
  newModal.querySelector('.modal-backdrop').onclick = () => { newModal.style.display = 'none'; };
  $('np-create').onclick = async () => {
    const name = $('np-name').value.trim();
    const projectDir = $('np-input-dir').value.trim();
    const outputDir = $('np-output-dir').value.trim();
    if (!name || !projectDir) { setStatus('Please fill in name and project directory', 'warn'); return; }
    try {
      const body = { name, project_dir: projectDir };
      if (outputDir) body.output_dir = outputDir;
      const r = await api('POST', '/api/project/create', body);
      if (r.ok) {
        newModal.style.display = 'none';
        window.location.search = `?project=${encodeURIComponent(name)}&project_dir=${encodeURIComponent(projectDir)}`;
      } else {
        setStatus('Create failed: ' + (r.error || 'unknown error'), 'err');
      }
    } catch (e) {
      setStatus('Create failed: ' + e.message, 'err');
    }
  };

  const openModal = $('modal-open-project');
  $('btn-open-project').onclick = async () => {
    openModal.style.display = 'flex';
    try {
      const r = await api('GET', '/api/projects');
      const allProjects = r.projects || [];
      const openList = $('project-list-modal');
      openList.innerHTML = allProjects.length
        ? allProjects.map(p => {
          const isLegacy = p.legacy;
          const needsVideos = p.needs_videos;
          const cardClass = `project-card ${p.is_current ? 'active' : ''} ${isLegacy ? 'project-card-legacy' : ''}`;
          const legacyBadge = isLegacy
            ? '<span class="legacy-badge">需迁移</span>'
            : (needsVideos ? '<span class="legacy-badge">无视频</span>' : '');
          const migrateBtn = isLegacy
            ? '<button class="project-card-migrate" title="迁移到新结构 (videos.json)">迁移</button>'
            : '';
          return `
          <div class="${cardClass}" data-name="${escapeHtml(p.name || '')}" data-project-dir="${escapeHtml(p.project_dir || p.input_dir || '')}" data-legacy="${isLegacy}" data-needs-videos="${needsVideos}">
            <div class="project-card-header">
              <span class="project-card-name">${escapeHtml(p.name)} ${p.is_current ? '(current)' : ''} ${legacyBadge}</span>
              <span class="project-card-actions">
                ${migrateBtn}
                <button class="project-card-remove" title="Remove from project list">✕</button>
              </span>
            </div>
            <div class="project-card-meta">
              Project: ${escapeHtml(p.project_dir || p.input_dir || '')}<br>
              Output: ${escapeHtml(p.output_dir || '')}<br>
              Steps: ${[['compress','compress'],['analyze','analyze'],['scripts','scripts'],['plan','plan'],['label','label'],['cut','cut']]
                .map(([k,l]) => p.steps?.[k] ? `<span class="step-dot done" title="${l} done">${l}</span>` : `<span class="step-dot" title="${l} pending">${l}</span>`)
                .join(' ')}
            </div>
          </div>`;
        }).join('')
        : '<p class="muted">No projects yet. Create one first.</p>';
      function _setupRemoveBtn(card, name, projectDir) {
        const removeBtn = card.querySelector('.project-card-remove');
        if (!removeBtn) return;
        removeBtn.onclick = async (e) => {
          e.stopPropagation();
          if (!confirm(`Remove "${name}" from project list?`)) return;
          const r2 = await api('POST', '/api/project/remove', { project_dir: projectDir });
          if (r2.ok) {
            if (name === state.currentProject?.name && projectDir === state.currentProjectDir) {
              openModal.style.display = 'none';
              window.location.search = '';
            } else {
              $('btn-open-project').click();
            }
          }
        };
      }
      function _setupMigrateBtn(card, name, projectDir) {
        const btn = card.querySelector('.project-card-migrate');
        if (!btn) return;
        btn.onclick = async (e) => {
          e.stopPropagation();
          if (!confirm(`迁移项目 "${name}" 到新结构？\n将生成 videos.json 并移除 paths.input_dir。`)) return;
          btn.disabled = true;
          btn.textContent = '迁移中...';
          try {
            const r = await api('POST', '/api/project/migrate', { project_dir: projectDir });
            if (r.ok) {
              setStatus(r.migrated ? `已迁移: ${name}` : (r.message || '已是新结构'), 'ok');
              // reload project list
              $('btn-open-project').click();
            } else {
              setStatus('迁移失败: ' + (r.error || 'unknown'), 'err');
              btn.disabled = false;
              btn.textContent = '迁移';
            }
          } catch (err) {
            setStatus('迁移失败: ' + err.message, 'err');
            btn.disabled = false;
            btn.textContent = '迁移';
          }
        };
      }
      openList.querySelectorAll('.project-card').forEach(card => {
        const name = card.dataset.name;
        const projectDir = card.dataset.projectDir;
        _setupRemoveBtn(card, name, projectDir);
        _setupMigrateBtn(card, name, projectDir);
        card.onclick = (e) => {
          if (e.target.closest('.project-card-remove') || e.target.closest('.project-card-migrate')) return;
          const isLegacy = card.dataset.legacy === 'true';
          if (isLegacy) {
            setStatus('该项目仍含 paths.input_dir，请先点击「迁移」或运行 python main.py migrate', 'warn');
            return;
          }
          if (projectDir === state.currentProjectDir) { openModal.style.display = 'none'; return; }
          if (state.dirty && !confirm('Switch project? Unsaved changes will be lost.')) return;
          openModal.style.display = 'none';
          window.location.search = `?project=${encodeURIComponent(name)}&project_dir=${encodeURIComponent(projectDir)}`;
        };
      });
    } catch (e) {
      $('project-list-modal').innerHTML = '<p class="err">Failed to load projects: ' + escapeHtml(e.message) + '</p>';
    }
  };
  $('op-cancel').onclick = () => { openModal.style.display = 'none'; };
  openModal.querySelector('.modal-backdrop').onclick = () => { openModal.style.display = 'none'; };
  $('op-open-path').onclick = async () => {
    const path = $('op-custom-path').value.trim();
    if (!path) { setStatus('Please enter a project directory path', 'warn'); return; }
    try {
      const r = await api('POST', '/api/project/add', { project_dir: path });
      if (r.ok) {
        openModal.style.display = 'none';
        const name = r.project?.name || path.split(/[\\/]/).pop();
        window.location.search = `?project=${encodeURIComponent(name)}&project_dir=${encodeURIComponent(path)}`;
      } else {
        setStatus('Open failed: ' + (r.error || 'unknown error'), 'err');
      }
    } catch (e) {
      setStatus('Open failed: ' + e.message, 'err');
    }
  };
  $('op-custom-path').onkeydown = (e) => {
    if (e.key === 'Enter') $('op-open-path').click();
  };

  // ---- Always register event handlers (before first async, so they work in empty state) ----
  $$('.source-toggle button').forEach(b => {
    b.onclick = () => setSource(b.dataset.source);
  });
  $$('.project-item').forEach(p => {
    p.onclick = (e) => {
      if (p.classList.contains('disabled')) {
        const name = p.querySelector('.name').textContent;
        setStatus(`「${name}」功能待对应 R-XXX 实现`, 'warn');
        return;
      }
      if (e.target.tagName === 'SELECT') return;
      if (p.dataset.entity === 'plan') selectPlan();
      else if (p.dataset.entity === 'run') selectRun();
      else if (p.dataset.entity === 'config') selectConfig();
      else if (p.dataset.entity === 'logs') selectLogs();
      else if (p.dataset.entity === 'tokens') selectTokens();
    };
  });
  document.body.addEventListener('click', e => {
    const btn = e.target.closest('.browse-btn');
    if (btn) openBrowseDir(btn.dataset.target);
  });
  const browseSelect = $('browse-select');
  if (browseSelect) {
    browseSelect.onclick = () => {
      const pathEl = $('browse-path');
      if (!pathEl || !window._browseResolve) return;
      window._browseResolve(pathEl.textContent);
      window._browseResolve = null;
      $('modal-browse-dir').style.display = 'none';
    };
  }
  const browseCancel = $('browse-cancel');
  if (browseCancel) {
    browseCancel.onclick = () => {
      window._browseResolve = null;
      $('modal-browse-dir').style.display = 'none';
    };
  }
  $('btn-reload').onclick = async () => {
    try {
      const cur = state.currentVideo;
      await loadProject();
      renderSteps();
      await loadVideos();
      if (cur && state.videos.find(x => x.file === cur)) {
        await selectVideo(cur);
      } else if (state.videos.length) {
        await selectVideo(state.videos[0].file);
      }
      setStatus('已重新加载', 'ok');
    } catch (e) { setStatus('重载失败: ' + e.message, 'err'); }
  };
  document.getElementById('btn-theme').onclick = toggleTheme;
  $('btn-save').onclick = save;
  document.getElementById('btn-select-videos').addEventListener('click', toggleSelection);
  document.getElementById('btn-add-videos').addEventListener('click', () => import('./sidebar-video-manage.js').then(m => m.openVideoManager()));
  $$('.tab').forEach(t => t.onclick = () => { state.currentTab = t.dataset.tab; renderActiveTab(); });
  setupPlayer();
  document.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 's' && mod) { e.preventDefault(); save(); }
    if (e.key === 'Escape') {
      $$('.modal').forEach(m => { if (m.style.display !== 'none') m.style.display = 'none'; });
    }
    if (mod && e.key >= '1' && e.key <= '5') {
      e.preventDefault();
      const items = $$('.project-item:not(.disabled)');
      const idx = parseInt(e.key) - 1;
      if (idx < items.length) items[idx].click();
    }
  });
  window.addEventListener('beforeunload', (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = '有未保存的修改'; }
  });
  const browseModal = $('modal-browse-dir');
  if (browseModal) {
    const backdrop = browseModal.querySelector('.modal-backdrop');
    if (backdrop) backdrop.onclick = () => { window._browseResolve = null; browseModal.style.display = 'none'; };
  }
  const rerunClose = $('rerun-close');
  if (rerunClose) rerunClose.onclick = hideRerunProgress;
  // Wire up auth modal
  document.getElementById('auth-submit')?.addEventListener('click', submitToken);
  document.getElementById('auth-token-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitToken();
  });
  // ---- End event handlers ----

  try {
    await loadProjects();
    // 检查上次使用的项目是否为旧版
    function _isLastProjectLegacy() {
      if (!state.lastProject || !state.projects) return false;
      return state.projects.some(p => p.name === state.lastProject && p.legacy);
    }
    // 如果没有 URL 指定项目，也没有上次使用的项目，显示打开界面
    if (!urlProject && !state.lastProject && !state.currentProject) {
      $('proj-name').textContent = '—';
      $('proj-name-sidebar').textContent = '—';
      $('btn-open-project').click();
      setStatus('No project loaded. Select a project to begin.', 'warn');
      return;
    }
    // 如果上次使用的项目是旧版，跳过自动跳转，让用户新建项目
    if (!urlProject && !urlProjectDir && _isLastProjectLegacy()) {
      state.lastProject = null;
      $('proj-name').textContent = '—';
      $('proj-name-sidebar').textContent = '—';
      $('btn-open-project').click();
      setStatus('上次使用的项目是旧版，请新建项目', 'warn');
      return;
    }
    // 如果 URL 没有指定项目，但有上次使用的项目，自动跳转
    if (!urlProject && !urlProjectDir && state.lastProject && state.lastProject !== state.currentProject?.name) {
      const projectDirParam = state.currentProjectDir ? `&project_dir=${encodeURIComponent(state.currentProjectDir)}` : '';
      window.location.search = `?project=${encodeURIComponent(state.lastProject)}${projectDirParam}`;
      return;
    }
    // 如果 URL 指定了项目，但当前不是该项目，需要重载
    const urlProjectObj = state.projects?.find(p => p.name === urlProject || p.project_dir === urlProjectDir);
    if (urlProjectObj?.legacy) {
      state.currentProjectName = null;
      state.currentProjectDir = null;
      $('proj-name').textContent = '—';
      $('proj-name-sidebar').textContent = '—';
      $('btn-open-project').click();
      setStatus('URL 指向的是旧版项目，不支持打开，请新建项目', 'warn');
      return;
    }
    if (urlProjectDir && (!state.currentProject || state.currentProjectDir !== urlProjectDir)) {
      state.currentProjectName = urlProject;
      state.currentProjectDir = urlProjectDir;
    } else if (urlProject && (!state.currentProject || state.currentProject.name !== urlProject)) {
      state.currentProjectName = urlProject;
    }
    await loadConfig();
    updateRuntimeWarnings(state.config);
    await loadProject();
    renderSteps();
    // 检查项目是否缺少 project.yaml，提示用户创建
    (async () => {
      if (!state.currentProjectName) return;
      try {
        const check = await api('GET', '/api/config/raw');
        if (check.needs_init) {
          // 在状态栏显示可操作的提示
          const el = $('status');
          el.innerHTML = `Project has no project.yaml, <button onclick="initProjectConfig()" style="background:none;border:1px solid currentColor;border-radius:3px;padding:2px 8px;cursor:pointer;color:inherit;font:inherit">create one now</button>`;
          el.className = 'status warn';
        }
      } catch {
        // ignore
      }
    })();
    await loadPlans();
    // 自动选择第一个可用 plan（如果有）
    if (state.availablePlans.length) {
      // 如果 project 指定的 day 有对应 plan 则保留, 否则用第一个
      const hasDay = state.availablePlans.some(p => p.day_label === state.currentDay);
      if (!hasDay) state.currentDay = state.availablePlans[0].day_label;
      updateSidebarDay();
      try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
      catch (e) { /* ignore */ }
    }
    await loadVideos();
    if (state.videos.length) {
      await selectVideo(state.videos[0].file);
    } else {
      setStatus('No video files in project directory', 'warn');
      renderVideoList(); // 显示空状态
    }
  } catch (e) {
    $('proj-name').textContent = '(加载失败)';
    $('proj-name-sidebar').textContent = '(加载失败)';
    setStatus('Init failed: ' + e.message, 'err');
  }
}

init();

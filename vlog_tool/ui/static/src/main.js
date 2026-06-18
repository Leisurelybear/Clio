import { state } from './state.js';
import { $, $$, escapeHtml, setStatus, updateSidebarDay } from './utils.js';
import { api } from './api.js';
import { setupPlayer } from './viewer.js';
import { save, initProjectConfig, renderActiveTab } from './editor.js';
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
  setSource,
  openBrowseDir,
  loadBrowseDir,
  switchToOriginalThenCompress,
  goToRunTab,
  hideRerunProgress,
} from './sidebar.js';

// Expose functions referenced by inline onclick handlers in HTML
window.switchToOriginalThenCompress = switchToOriginalThenCompress;
window.goToRunTab = goToRunTab;
window.initProjectConfig = initProjectConfig;

async function init() {
  // 从 URL 读取 project 参数
  const urlParams = new URLSearchParams(window.location.search);
  const urlProject = urlParams.get('project');
  if (urlProject) {
    state.currentProjectName = urlProject;
  }

  try {
    await loadProjects();
    // 如果 URL 没有指定项目，但有上次使用的项目，自动跳转
    if (!urlProject && state.lastProject && state.lastProject !== state.currentProject?.name) {
      window.location.search = `?project=${encodeURIComponent(state.lastProject)}`;
      return;
    }
    // 如果 URL 指定了项目，但当前不是该项目，需要重载
    if (urlProject && (!state.currentProject || state.currentProject.name !== urlProject)) {
      state.currentProjectName = urlProject;
    }
    await loadConfig();
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
          el.innerHTML = `该项目无专属配置，<button onclick="initProjectConfig()" style="background:none;border:1px solid currentColor;border-radius:3px;padding:2px 8px;cursor:pointer;color:inherit;font:inherit">立即创建 project.yaml</button>`;
          el.className = 'status warn';
        }
      } catch {
        // 静默忽略
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
      setStatus('项目目录下没有视频文件', 'warn');
      renderVideoList(); // 显示空状态
    }
  } catch (e) {
    setStatus('初始化失败: ' + e.message, 'err');
  }

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
      // 点中 select 下拉框时不切换实体（由 select.onchange 处理）
      if (e.target.tagName === 'SELECT') return;
      if (p.dataset.entity === 'plan') selectPlan();
      else if (p.dataset.entity === 'run') selectRun();
      else if (p.dataset.entity === 'config') selectConfig();
      else if (p.dataset.entity === 'logs') selectLogs();
    };
  });

  // Browse buttons — 事件委托以覆盖动态创建的按钮
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
  $('btn-save').onclick = save;
  $$('.tab').forEach(t => t.onclick = () => { state.currentTab = t.dataset.tab; renderActiveTab(); });

  setupPlayer();

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); }
  });

  window.addEventListener('beforeunload', (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = '有未保存的修改'; }
  });

  // New project modal
  const newModal = $('modal-new-project');
  $('btn-new-project').onclick = () => { newModal.style.display = 'flex'; };
  $('np-cancel').onclick = () => { newModal.style.display = 'none'; };
  newModal.querySelector('.modal-backdrop').onclick = () => { newModal.style.display = 'none'; };
  $('np-create').onclick = async () => {
    const name = $('np-name').value.trim();
    const inputDir = $('np-input-dir').value.trim();
    const outputDir = $('np-output-dir').value.trim();
    if (!name || !inputDir) { setStatus('请填写项目名称和素材目录', 'warn'); return; }
    try {
      const body = { name, input_dir: inputDir };
      if (outputDir) body.output_dir = outputDir;
      const r = await api('POST', '/api/project/create', body);
      if (r.ok) {
        newModal.style.display = 'none';
        window.location.search = `?project=${encodeURIComponent(name)}`;
      } else {
        setStatus('创建失败: ' + (r.error || '未知错误'), 'err');
      }
    } catch (e) {
      setStatus('创建失败: ' + e.message, 'err');
    }
  };

  // Open project modal
  const openModal = $('modal-open-project');
  const openList = $('project-list-modal');
  $('btn-open-project').onclick = async () => {
    openModal.style.display = 'flex';
    // 刷新项目列表
    try {
      const r = await api('GET', '/api/projects');
      const allProjects = r.projects || [];
      openList.innerHTML = allProjects.length
        ? allProjects.map(p => `
          <div class="project-card ${p.is_current ? 'active' : ''}" data-name="${escapeHtml(p.name)}">
            <div class="project-card-name">${escapeHtml(p.name)} ${p.is_current ? '(当前)' : ''}</div>
            <div class="project-card-meta">
              素材目录: ${escapeHtml(p.input_dir)}<br>
              输出目录: ${escapeHtml(p.output_dir)}<br>
              步骤: ${[['compress','压缩'],['analyze','分析'],['scripts','口播'],['plan','规划'],['label','标号'],['cut','裁剪']]
                .map(([k,l]) => p.steps?.[k] ? `<span class="step-dot done" title="${l}已完成">✓${l}</span>` : `<span class="step-dot" title="${l}未完成">○${l}</span>`)
                .join(' ')}
            </div>
          </div>
        `).join('')
        : '<p class="muted">暂无项目，请先新建</p>';
      // 点击卡片切换项目
      openList.querySelectorAll('.project-card').forEach(card => {
        card.onclick = () => {
          const name = card.dataset.name;
          if (name === state.currentProject?.name) {
            openModal.style.display = 'none';
            return;
          }
          if (state.dirty && !confirm('切换项目将丢弃当前修改，确定吗？')) return;
          openModal.style.display = 'none';
          window.location.search = `?project=${encodeURIComponent(name)}`;
        };
      });
    } catch (e) {
      openList.innerHTML = '<p class="err">加载项目列表失败: ' + escapeHtml(e.message) + '</p>';
    }
  };
  $('op-cancel').onclick = () => { openModal.style.display = 'none'; };
  openModal.querySelector('.modal-backdrop').onclick = () => { openModal.style.display = 'none'; };
  // 自定义路径打开项目
  $('op-open-path').onclick = async () => {
    const path = $('op-custom-path').value.trim();
    if (!path) { setStatus('请输入项目目录路径', 'warn'); return; }
    try {
      const r = await api('POST', '/api/project/add', { input_dir: path });
      if (r.ok) {
        openModal.style.display = 'none';
        const name = r.project?.name || path.split(/[\\/]/).pop();
        window.location.search = `?project=${encodeURIComponent(name)}`;
      } else {
        setStatus('打开项目失败: ' + (r.error || '未知错误'), 'err');
      }
    } catch (e) {
      setStatus('打开项目失败: ' + e.message, 'err');
    }
  };
  // Enter 键触发打开
  $('op-custom-path').onkeydown = (e) => {
    if (e.key === 'Enter') $('op-open-path').click();
  };

  // Browse modal backdrop close
  const browseModal = $('modal-browse-dir');
  if (browseModal) {
    const backdrop = browseModal.querySelector('.modal-backdrop');
    if (backdrop) backdrop.onclick = () => { window._browseResolve = null; browseModal.style.display = 'none'; };
  }

  // Rerun close button
  const rerunClose = $('rerun-close');
  if (rerunClose) rerunClose.onclick = hideRerunProgress;
}

init();

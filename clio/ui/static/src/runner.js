import { state } from './state.js';
import {
  $,
  escapeHtml,
  setStatus,
  updateSidebarDay,
} from './utils.js';
import { api, icon } from './api.js';
import { addToast } from './toast.js';

let _runEventSource = null;
let _lastRunDay = 'day1';
let _runActive = false;
let _lastProgressSnapshot = null;
let _lastRunSteps = [];

const STEPS_KEY = 'vlog_ui_run_steps';

const RUN_STEPS = [
  { key: 'compress', label: '压缩原视频', hint: '将原片压缩为 640p，为 AI 分析做准备' },
  { key: 'analyze', label: 'AI 分析', hint: '提交 Gemini 分析压缩后的视频内容' },
  { key: 'voiceover', label: '生成口播文案', hint: '基于分析结果生成每段的口播脚本' },
  { key: 'transcribe', label: 'Whisper 语音转录', hint: '用 faster-whisper 转录音频为文字（需安装）' },
  { key: 'plan', label: 'vlog 剪辑规划', hint: '根据所有素材生成剪辑顺序和时间轴' },
  { key: 'label', label: '烧录序号', hint: '在压缩视频左上角标上序号便于剪映对照' },
];

function loadStepSelection() {
  try {
    const raw = localStorage.getItem(STEPS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveStepSelection(checks, useTranscripts) {
  try {
    localStorage.setItem(STEPS_KEY, JSON.stringify({ steps: checks, use_transcripts: useTranscripts }));
  } catch { /* ignore */ }
}

function renderRun() {
  _lastRunDay = state.currentDay || 'day1';
  const pane = $('tab-run');
  const saved = loadStepSelection();
  const savedSteps = saved.steps || {};
  const savedUseTrans = saved.use_transcripts !== false;

  const stepChecks = RUN_STEPS.map(s => {
    const checked = savedSteps[s.key] !== false;
    const isPlan = s.key === 'plan';
    return `
      <div class="run-step-wrap">
        <label class="run-step ${isPlan ? 'run-step-plan' : ''}">
          <input type="checkbox" class="run-step-cb" data-step="${s.key}" ${checked ? 'checked' : ''}>
          <span class="run-step-label">${s.label}</span>
          <span class="run-step-hint">${s.hint}</span>
        </label>
        ${isPlan ? `
        <div class="run-step-sub">
          <label class="run-option">
            <span class="run-option-label">分集</span>
            <input id="run-day" class="run-option-input" value="${escapeHtml(state.currentDay)}">
          </label>
          <label class="run-option run-option-check">
            <input type="checkbox" id="run-use-transcripts" ${savedUseTrans ? 'checked' : ''}>
            <span>使用语音转录优化剪辑规划</span>
          </label>
        </div>
        ` : ''}
      </div>
    `;
  }).join('');

  pane.innerHTML = `
    <h3>运行流水线</h3>
    <p class="hint">选择要执行的步骤后点击「运行选中步骤」</p>
    <label class="run-option">
      <span class="run-option-label">本次素材目录</span>
      <span class="input-with-browse">
        <input id="run-input-dir" class="run-option-input" value="${escapeHtml(state.config?.input_dir || state.currentProjectInputDir || '')}" placeholder="留空则使用当前项目的 input_dir">
        <button class="browse-btn" data-target="run-input-dir" type="button">浏览</button>
      </span>
    </label>
    <p class="hint" style="margin-top:-4px">仅影响本次运行，不会写入 project.yaml。未选择具体文件时，将处理该目录下的所有视频。</p>
    <div class="run-step-list">${stepChecks}</div>
    <details class="run-prompt-section" style="margin:12px 0">
      <summary style="cursor:pointer;font-size:var(--text-sm);color:var(--text-secondary);user-select:none">⌨ 高级提示词（可选）</summary>
      <div style="margin-top:8px">
        <textarea id="run-context-override" class="run-prompt-input" placeholder="在本次运行时临时向所有 AI 添加额外指令。&#10;&#10;每条指令一行，支持按步骤前缀:&#10;[analyze] 注意画面中的食物特写&#10;[voiceover] 使用更口语化的风格&#10;[plan] 优先选取运动镜头&#10;&#10;不带前缀的指令将应用于所有步骤。&#10;这些提示仅在本次运行有效，不会保存到配置中。" rows="4" style="width:100%;box-sizing:border-box;padding:8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-input,#1e1e1e);color:var(--text-primary);font-size:var(--text-sm);resize:vertical;font-family:inherit"></textarea>
      </div>
    </details>
    <div style="display:flex;gap:8px;align-items:center;margin-top:12px">
      <button id="btn-run-start" class="btn-primary">${getRunButtonText()}</button>
      <span id="run-files-badge" class="run-files-badge" style="display:none"></span>
      <button id="btn-run-cancel" class="btn-secondary" style="display:none">取消</button>
      <label class="run-option-check" id="option-overwrite-wrap" style="display:none">
        <input type="checkbox" id="run-overwrite">
        <span>覆盖现有输出</span>
      </label>
    </div>
    <div id="run-progress" style="margin-top:12px"></div>
    <div id="run-state-container"></div>
  `;

  // wire step checkbox change → persist
  document.querySelectorAll('.run-step-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const checks = {};
      document.querySelectorAll('.run-step-cb').forEach(c => {
        checks[c.dataset.step] = c.checked;
      });
      saveStepSelection(checks, $('run-use-transcripts')?.checked ?? true);
      togglePlanSubOptions();
    });
  });
  // wire use_transcripts change → persist
  const useTransCb = $('run-use-transcripts');
  if (useTransCb) {
    useTransCb.addEventListener('change', () => {
      const checks = {};
      document.querySelectorAll('.run-step-cb').forEach(c => {
        checks[c.dataset.step] = c.checked;
      });
      saveStepSelection(checks, useTransCb.checked);
    });
  }

  togglePlanSubOptions();
  updateRunFilesBadge();

  const runBtn = $('btn-run-start');
  runBtn.onclick = startRun;
  if (_runActive) { runBtn.disabled = true; runBtn.textContent = '运行中...'; }
  const cancelBtn = $('btn-run-cancel');
  if (cancelBtn) cancelBtn.onclick = cancelRun;
  _startRunSSE();
}

function togglePlanSubOptions() {
  const planCb = document.querySelector('.run-step-cb[data-step="plan"]');
  const sub = document.querySelector('.run-step-sub');
  if (!sub) return;
  const enabled = planCb?.checked ?? true;
  sub.style.opacity = enabled ? '1' : '0.35';
  sub.querySelectorAll('input, button').forEach(el => el.disabled = !enabled);
}

function getRunButtonText() {
  if (state.selectionMode && state.selectedFiles.length > 0) {
    return `${icon('play', 16)} 运行选中步骤 (${state.selectedFiles.length})`;
  }
  return `${icon('play', 16)} 运行选中步骤`;
}

function updateRunFilesBadge() {
  const badge = $('run-files-badge');
  const overwrap = $('option-overwrite-wrap');
  if (!badge || !overwrap) return;
  if (state.selectionMode && state.selectedFiles.length > 0) {
    const numFiles = state.selectedFiles.length;
    badge.textContent = `(${numFiles} 个视频)`;
    badge.style.display = 'inline';
    overwrap.style.display = 'flex';
  } else {
    badge.style.display = 'none';
    overwrap.style.display = 'none';
  }
}

async function startRun() {
  const btn = $('btn-run-start');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = '启动中...';
  const checked = [...document.querySelectorAll('.run-step-cb:checked')].map(cb => cb.dataset.step);
  if (!checked.length) {
    btn.disabled = false;
    btn.textContent = '运行选中步骤';
    setStatus('请至少选择一个步骤', 'warn');
    return;
  }
  _lastRunDay = ($('run-day')?.value.trim() || state.currentDay);
  _lastRunSteps = checked.slice();
  _stopRunSSE();
  try {
    const body = {
      day_label: _lastRunDay,
      steps: checked,
      use_transcripts: $('run-use-transcripts').checked,
    };
    const runInputDir = $('run-input-dir')?.value?.trim();
    if (runInputDir) {
      body.input_dir = runInputDir;
    }
    if (state.selectionMode && state.selectedFiles.length > 0) {
      body.files = state.selectedFiles;
    }
    const overwriteCb = $('run-overwrite');
    if (overwriteCb && overwriteCb.checked) {
      body.overwrite = true;
    }
    const contextOverride = $('run-context-override')?.value?.trim();
    if (contextOverride) {
      body.context_override = contextOverride;
    }
    const r = await api('POST', '/api/run/start', body);
    if (r.ok) {
      _runActive = true;
      const msg = r.message || '流水线已启动';
      setStatus(msg, 'ok');
      addToast(msg, 'success');
      $('run-progress').innerHTML = '<p class="muted">流水线已启动，等待进度...</p>';
      _startRunSSE();
    } else {
      throw new Error(r.error || '启动失败');
    }
  } catch (e) {
    $('run-progress').innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
    const msg = '启动失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
    btn.disabled = false;
    btn.innerHTML = `${icon('play', 16)} 运行选中步骤`;
  }
}

async function cancelRun() {
  const btn = $('btn-run-cancel');
  if (btn) { btn.disabled = true; btn.innerHTML = '⏹ 正在取消...'; }
  try {
    const r = await api('POST', '/api/run/cancel', {});
    const msg = r.message || '取消请求已发送';
    setStatus(msg, 'warn');
    addToast(msg, 'warning');
  } catch (e) {
    const msg = '取消失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
    if (btn) { btn.disabled = false; btn.innerHTML = '取消'; }
  }
}

function _startRunSSE() {
  _stopRunSSE();
  let url = '/api/run/stream';
  let sep = '?';
  const addQuery = (key, value) => {
    if (!value) return;
    url += sep + key + '=' + encodeURIComponent(value);
    sep = '&';
  };
  if (state.currentProjectName) {
    addQuery('project', state.currentProjectName);
  }
  if (state.currentProjectInputDir) {
    addQuery('input_dir', state.currentProjectInputDir);
  }
  addQuery('token', sessionStorage.getItem('api_token'));
  _runEventSource = new EventSource(url);
  _runEventSource.onmessage = (event) => {
    try {
      const s = JSON.parse(event.data);
      _handleRunStatus(s);
    } catch { /* ignore parse errors */ }
  };
  _runEventSource.onerror = () => {
    // EventSource auto-reconnects on connection loss
  };
}

function _stopRunSSE() {
  if (_runEventSource) {
    _runEventSource.close();
    _runEventSource = null;
  }
}

async function _handleRunStatus(s) {
  const prog = $('run-progress');
  const btn = $('btn-run-start');
  if (!prog) return;
  if (s.rerun) return;
    if (s.status === 'idle' || s.status === 'unknown') {
      _lastProgressSnapshot = null;
      _runActive = false;
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      const cancelBtn = $('btn-run-cancel');
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (!s.running) {
        prog.innerHTML = '<p class="muted">尚未运行</p>';
        renderProcessingState($('run-state-container'));
      }
      return;
    }
    if (s.status === 'running') {
      const stale = !s.running;
      if (stale) {
        _runActive = false;
        if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
        const cancelBtn = $('btn-run-cancel');
        if (cancelBtn) cancelBtn.style.display = 'none';
        const logsHtml = s.logs?.length ? `<div class="run-logs">${s.logs.map(l => `<div class="run-log-line">${escapeHtml(l)}</div>`).join('')}</div>` : '';
        prog.innerHTML = `
          <p class="warn">⚠ 上次运行时意外中断，以下为残留进度（已失效）</p>
          <p><strong>阶段:</strong> ${escapeHtml(s.phase || '')}</p>
          <p><strong>进度:</strong> ${s.current}/${s.total}</p>
          <p><strong>状态:</strong> ${escapeHtml(s.message || '')}</p>
          ${logsHtml}
        `;
        renderProcessingState($('run-state-container'));
      } else {
        if (btn) { btn.disabled = true; btn.textContent = '运行中...'; }
        const cancelBtn = $('btn-run-cancel');
        if (cancelBtn) { cancelBtn.style.display = ''; cancelBtn.disabled = false; }
        const pct = s.total > 0 ? Math.round(s.current / s.total * 100) : 0;
        const eta = s.eta_sec ? `，预计剩余 ${Math.round(s.eta_sec)} 秒` : '';
        const logsHtml = s.logs?.length ? `<div class="run-logs">${s.logs.map(l => `<div class="run-log-line">${escapeHtml(l)}</div>`).join('')}</div>` : '';
        prog.innerHTML = `
          <p><strong>阶段:</strong> ${escapeHtml(s.phase || '')}</p>
          <p><strong>进度:</strong> ${s.current}/${s.total} (${pct}%)${eta}</p>
          <p><strong>状态:</strong> ${escapeHtml(s.message || '')}</p>
          <div style="background:#333;border-radius:3px;height:8px;margin:8px 0">
            <div style="background:var(--accent);border-radius:3px;height:100%;width:${pct}%"></div>
          </div>
          <div id="stale-warn" style="display:none;margin-top:8px;padding:8px;background:var(--warning-bg,#2a2520);border:1px solid var(--warning-border,#b8860b);border-radius:6px;font-size:var(--text-sm)">
            ⏳ 进度长时间未更新，可能正在后台下载模型（约 1-2 GB）或网络连接异常<br>
            <span style="color:var(--text-secondary)">可前往 <a href="#" id="link-stale-settings" style="text-decoration:underline;color:var(--accent)" onclick="event.preventDefault();import('./sidebar.js').then(function(m){m.selectConfig()})">设置 → Whisper 模型管理</a> 检查模型状态</span>
          </div>
          ${logsHtml}
        `;
        // 超时停滞检测：如果 current/total/message 无变化超过 60 秒，显示提示
        const snapKey = s.current + '/' + s.total + '/' + s.message;
        const now = Date.now();
        if (!_lastProgressSnapshot || _lastProgressSnapshot.key !== snapKey) {
          _lastProgressSnapshot = { key: snapKey, timestamp: now };
        } else if (now - _lastProgressSnapshot.timestamp > 60000) {
          var staleEl = $('stale-warn');
          if (staleEl) staleEl.style.display = '';
        }
      }
    } else if (s.status === 'done') {
      _lastProgressSnapshot = null;
      _runActive = false;
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      const cancelBtn = $('btn-run-cancel');
      if (cancelBtn) cancelBtn.style.display = 'none';
      const logsHtml = s.logs?.length ? `<div class="run-logs">${s.logs.map(l => `<div class="run-log-line">${escapeHtml(l)}</div>`).join('')}</div>` : '';
      prog.innerHTML = `<p class="ok">✓ 流水线完成</p><p>${escapeHtml(s.message || '')}</p>${logsHtml}`;
      setStatus('流水线完成', 'ok');
      addToast(s.message || '流水线完成', 'success');
      renderProcessingState($('run-state-container'));
      // 检查是否有转录失败（如缺少模型），弹出下载引导
      (async () => {
        try {
          const ps = await api('GET', '/api/processing-state');
          const hasTranscribeErr = Object.values(ps.files || {}).some(function(f) { return f.transcribe === 'error'; });
          if (hasTranscribeErr) {
            const warn = document.createElement('div');
            warn.id = 'run-transcribe-warn';
            warn.style.cssText = 'margin-top:12px;padding:12px;background:var(--warning-bg,#2a2520);border:1px solid var(--warning-border,#b8860b);border-radius:6px';
            warn.innerHTML = `
              <p style="margin:0 0 8px;font-weight:600">❗ 部分视频转录失败</p>
              <p style="margin:0 0 8px;font-size:var(--text-sm);color:var(--text-secondary)">Whisper 模型未下载，请前往 <a href="#" id="link-go-settings" style="text-decoration:underline;color:var(--accent)">设置 → Whisper 模型管理</a> 手动下载模型（约 1-2 GB），再重跑「Whisper 转录」。</p>
            `;
            prog.appendChild(warn);
            var settingsLink = $('link-go-settings');
            if (settingsLink) {
              settingsLink.onclick = function(e) { e.preventDefault(); import('./sidebar.js').then(function(s) { s.selectConfig(); }); };
            }
          }
        } catch { /* 静默 */ }
      })();
      state.currentDay = _lastRunDay;
      state.plan = null;
      await import('./sidebar.js').then(mod => mod.loadPlans());
      updateSidebarDay();
      import('./sidebar.js').then(mod => mod.renderSteps());
      import('./sidebar.js').then(mod => mod.saveProject());
      try { state.plan = await api('GET', `/api/plan?day=${_lastRunDay}`); } catch {}
      await import('./sidebar.js').then(mod => mod.loadVideos());
      const completedSteps = Array.isArray(s.steps) ? s.steps : _lastRunSteps;
      if (state.currentEntity === 'run') {
        await _showRunCompletionTarget(completedSteps);
      } else if (state.currentEntity === 'plan') {
        import('./sidebar.js').then(mod => mod.selectPlan());
      }
    } else if (s.status === 'cancelled') {
      _lastProgressSnapshot = null;
      _runActive = false;
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      const cancelBtn = $('btn-run-cancel');
      if (cancelBtn) cancelBtn.style.display = 'none';
      const logsHtml = s.logs?.length ? `<div class="run-logs">${s.logs.map(l => `<div class="run-log-line">${escapeHtml(l)}</div>`).join('')}</div>` : '';
      prog.innerHTML = `<p class="warn">⏹ 流水线已取消</p><p>${escapeHtml(s.message || '')}</p>${logsHtml}`;
      setStatus('流水线已取消', 'warn');
      addToast(s.message || '流水线已取消', 'warning');
      renderProcessingState($('run-state-container'));
    } else if (s.status === 'error') {
      _lastProgressSnapshot = null;
      _runActive = false;
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      const cancelBtn = $('btn-run-cancel');
      if (cancelBtn) cancelBtn.style.display = 'none';
      const logsHtml = s.logs?.length ? `<div class="run-logs">${s.logs.map(l => `<div class="run-log-line">${escapeHtml(l)}</div>`).join('')}</div>` : '';
      prog.innerHTML = `<p class="err">✗ 流水线出错</p><p>${escapeHtml(s.message || '')}</p>${logsHtml}`;
      setStatus('流水线出错', 'err');
      addToast(s.message || '流水线出错', 'error', 6000);
      renderProcessingState($('run-state-container'));
    }
}

function _stopRunPoll() {
  _stopRunSSE();
}

function _completionTargetForSteps(steps) {
  const stepSet = new Set(Array.isArray(steps) ? steps : []);
  if (stepSet.has('plan')) return { entity: 'plan' };
  if (stepSet.has('voiceover')) return { entity: 'video', tab: 'voiceover' };
  if (stepSet.has('transcribe')) return { entity: 'video', tab: 'transcript' };
  if (stepSet.has('analyze')) return { entity: 'video', tab: 'texts' };
  if (stepSet.has('compress') || stepSet.has('label')) return { entity: 'video', tab: state.currentTab || 'texts' };
  return null;
}

async function _showRunCompletionTarget(steps) {
  const target = _completionTargetForSteps(steps);
  if (!target) return;
  const sidebar = await import('./sidebar.js');
  if (target.entity === 'plan') {
    await sidebar.selectPlan(_lastRunDay);
    return;
  }
  state.currentTab = target.tab;
  if (state.source !== 'compressed') {
    await sidebar.setSource('compressed');
    return;
  }
  const preferred = state.currentVideo && state.videos.some(v => v.file === state.currentVideo)
    ? state.currentVideo
    : state.videos[0]?.file;
  if (preferred) {
    await sidebar.selectVideo(preferred);
  }
}

const _STEP_LABELS_SHORT = { compress: '压缩', analyze: '分析', voiceover: '口播', transcribe: '转录' };
const _STATUS_ICON = { done: '✅', skipped: '⏭️', error: '✗' };

async function renderProcessingState(container) {
  try {
    const st = await api('GET', '/api/processing-state');
    const files = st.files;
    const stepKeys = ['compress', 'analyze', 'voiceover', 'transcribe'];
    const entries = Object.entries(files).sort((a, b) => a[0].localeCompare(b[0]));
    if (!entries.length) { if (container) container.innerHTML = ''; return; }
    let html = '<h4 style="margin:12px 0 4px">处理状态</h4><div class="state-table"><div class="state-row state-header"><span class="state-file">文件</span>';
    for (const k of stepKeys) html += `<span class="state-cell">${_STEP_LABELS_SHORT[k]}</span>`;
    html += '</div>';
    for (const [file, steps] of entries) {
      html += `<div class="state-row"><span class="state-file">${escapeHtml(file)}</span>`;
      for (const k of stepKeys) {
        const v = steps[k];
        html += `<span class="state-cell">${v ? _STATUS_ICON[v] || v : ''}</span>`;
      }
      html += '</div>';
    }
    html += '</div>';
    if (container) container.innerHTML = html;
  } catch { /* ignore */ }
}

export {
  renderRun,
  startRun,
  _stopRunPoll,
  updateRunFilesBadge,
  _completionTargetForSteps,
};

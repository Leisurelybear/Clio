import { state } from './state.js';
import {
  $,
  escapeHtml,
  setStatus,
  updateSidebarDay,
} from './utils.js';
import { api, icon } from './api.js';

let _runPollTimer = null;
let _lastRunDay = 'day1';

const RUN_STEPS = [
  { key: 'compress', label: '压缩原视频', hint: '将原片压缩为 640p，为 AI 分析做准备' },
  { key: 'analyze', label: 'AI 分析', hint: '提交 Gemini 分析压缩后的视频内容' },
  { key: 'voiceover', label: '生成口播文案', hint: '基于分析结果生成每段的口播脚本' },
  { key: 'transcribe', label: 'Whisper 语音转录', hint: '用 faster-whisper 转录音频为文字（需安装）' },
  { key: 'plan', label: 'vlog 剪辑规划', hint: '根据所有素材生成剪辑顺序和时间轴' },
  { key: 'label', label: '烧录序号', hint: '在压缩视频左上角标上序号便于剪映对照' },
];

function renderRun() {
  // 从 state 同步当前分集（避免残留 done 处理器把 day 覆写成硬编码默认值）
  _lastRunDay = state.currentDay || 'day1';
  const pane = $('tab-run');
  const stepChecks = RUN_STEPS.map(s => `
    <label class="run-step">
      <input type="checkbox" class="run-step-cb" data-step="${s.key}" checked>
      <span class="run-step-label">${s.label}</span>
      <span class="run-step-hint">${s.hint}</span>
    </label>
  `).join('');
  pane.innerHTML = `
    <h3>运行流水线</h3>
    <p class="hint">选择要执行的步骤后点击「运行选中步骤」</p>
    <label>分集 <input id="run-day" value="${escapeHtml(state.currentDay)}"></label>
    <div class="run-step-list">${stepChecks}</div>
    <div class="run-options" style="margin:8px 0">
      <label class="run-option" style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:var(--text-sm)">
        <input type="checkbox" id="run-use-transcripts" checked>
        <span>使用语音转录优化剪辑规划</span>
      </label>
    </div>
    <button id="btn-run-start" class="btn-primary">${icon('play', 16)} 运行选中步骤</button>
    <div id="run-progress" style="margin-top:12px">
      <p class="muted">尚未运行</p>
    </div>
  `;
  $('btn-run-start').onclick = startRun;
  if (_runPollTimer) clearInterval(_runPollTimer);
  _runPollTimer = setInterval(pollRunStatus, 2000);
  pollRunStatus();
}

async function startRun() {
  const btn = $('btn-run-start');
  const prog = $('run-progress');
  const checked = [...document.querySelectorAll('.run-step-cb:checked')].map(cb => cb.dataset.step);
  if (!checked.length) {
    setStatus('请至少选择一个步骤', 'warn');
    return;
  }
  _lastRunDay = ($('run-day')?.value.trim() || state.currentDay);
  if (_runPollTimer) clearInterval(_runPollTimer);
  btn.disabled = true;
  btn.textContent = '启动中...';
  try {
    const r = await api('POST', '/api/run/start', {
      day_label: _lastRunDay,
      steps: checked,
      use_transcripts: $('run-use-transcripts').checked,
    });
    if (r.ok) {
      setStatus(r.message || '流水线已启动', 'ok');
      prog.innerHTML = '<p class="muted">流水线已启动，等待进度...</p>';
      _runPollTimer = setInterval(pollRunStatus, 2000);
    } else {
      throw new Error(r.error || '启动失败');
    }
  } catch (e) {
    prog.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
    setStatus('启动失败: ' + e.message, 'err');
    btn.disabled = false;
    btn.innerHTML = `${icon('play', 16)} 运行选中步骤`;
  }
}

async function pollRunStatus() {
  const prog = $('run-progress');
  const btn = $('btn-run-start');
  if (!prog) return;  // not on run tab
  try {
    const s = await api('GET', '/api/run/status');
    if (s.rerun) return;
    if (s.status === 'idle' || s.status === 'unknown') {
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      if (!s.running) {
        prog.innerHTML = '<p class="muted">尚未运行</p>';
      }
      return;
    }
    if (s.status === 'running') {
      const stale = !s.running;
      if (stale) {
        if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
        prog.innerHTML = `
          <p class="warn">⚠ 上次运行时意外中断，以下为残留进度（已失效）</p>
          <p><strong>阶段:</strong> ${escapeHtml(s.phase || '')}</p>
          <p><strong>进度:</strong> ${s.current}/${s.total}</p>
          <p><strong>状态:</strong> ${escapeHtml(s.message || '')}</p>
        `;
      } else {
        if (btn) { btn.disabled = true; btn.textContent = '运行中...'; }
        const pct = s.total > 0 ? Math.round(s.current / s.total * 100) : 0;
        const eta = s.eta_sec ? `，预计剩余 ${Math.round(s.eta_sec)} 秒` : '';
        prog.innerHTML = `
          <p><strong>阶段:</strong> ${escapeHtml(s.phase || '')}</p>
          <p><strong>进度:</strong> ${s.current}/${s.total} (${pct}%)${eta}</p>
          <p><strong>状态:</strong> ${escapeHtml(s.message || '')}</p>
          <div style="background:#333;border-radius:3px;height:8px;margin:8px 0">
            <div style="background:#4a9eff;border-radius:3px;height:100%;width:${pct}%"></div>
          </div>
        `;
      }
    } else if (s.status === 'done') {
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      prog.innerHTML = `<p class="ok">✓ 流水线完成</p><p>${escapeHtml(s.message || '')}</p>`;
      setStatus('流水线完成', 'ok');
      state.currentDay = _lastRunDay;
      state.plan = null;
      await import('./sidebar.js').then(mod => mod.loadPlans());
      updateSidebarDay();
      import('./sidebar.js').then(mod => mod.renderSteps());
      import('./sidebar.js').then(mod => mod.saveProject());
      try { state.plan = await api('GET', `/api/plan?day=${_lastRunDay}`); } catch {}
      await import('./sidebar.js').then(mod => mod.loadVideos());
      if (state.currentEntity === 'plan') import('./sidebar.js').then(mod => mod.selectPlan());
    } else if (s.status === 'error') {
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 16)} 运行选中步骤`; }
      prog.innerHTML = `<p class="err">✗ 流水线出错</p><p>${escapeHtml(s.message || '')}</p>`;
      setStatus('流水线出错', 'err');
    }
  } catch (e) {
    // poll error, ignore
  }
}

function _stopRunPoll() {
  if (_runPollTimer) {
    clearInterval(_runPollTimer);
    _runPollTimer = null;
  }
}

export {
  renderRun,
  startRun,
  pollRunStatus,
  _stopRunPoll,
};

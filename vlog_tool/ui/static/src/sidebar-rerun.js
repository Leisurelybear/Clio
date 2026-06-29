import { state } from './state.js';
import { $, escapeHtml, setStatus, updateEntityUI } from './utils.js';
import { api } from './api.js';
import { loadVideos, renderSteps } from './sidebar-data.js';

let _rerunPollTimer = null;
let _rerunPollStart = 0;
const RERUN_POLL_TIMEOUT = 120_000;

export function showRerunProgress(task, file) {
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

export function hideRerunProgress() {
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

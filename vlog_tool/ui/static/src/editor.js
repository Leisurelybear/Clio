import { state } from './state.js';
import {
  $, $$,
  escapeHtml,
  parseTimecode,
  fmtTime,
  markDirty,
  updateSaveBtn,
  setStatus,
  updateSidebarDay,
  setDeep,
} from './utils.js';
import { api, icon } from './api.js';
import { playVideoSegment, renderPreviewBar, startPreview, stopPreview, _playPreviewSegment } from './viewer.js';

// ── Rendering ──────────────────────────────────────────────────

function renderActiveTab() {
  if (state.currentEntity === 'plan') {
    renderPlan();
    return;
  }
  if (state.currentEntity === 'run') {
    import('./runner.js').then(mod => mod.renderRun());
    return;
  }
  if (state.currentEntity === 'config') {
    renderConfig();
    return;
  }
  if (state.currentEntity === 'logs') {
    renderLogs();
    return;
  }
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === state.currentTab));
  $$('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `tab-${state.currentTab}`));
  if (state.currentTab === 'texts') renderTexts();
  else if (state.currentTab === 'voiceover') renderVoiceover();
  else if (state.currentTab === 'transcript') renderTranscript();
}

function renderTexts() {
  const t = state.texts;
  const pane = $('tab-texts');
  if (!t) {
    pane.innerHTML = '<p class="muted">当前视频没有对应的 texts JSON</p>';
    return;
  }
  pane.innerHTML = `
    <h3>基础信息</h3>
    <label>标题 <input data-field="title"></label>
    <label>位置 <input data-field="location"></label>
    <label>情绪 <input data-field="mood"></label>
    <label>建议用途 <input data-field="suggested_use"></label>
    <label>摘要 <textarea data-field="summary" rows="3"></textarea></label>
    <h3>时间轴 (timeline) — ${(t.timeline || []).length} 段</h3>
    <p class="hint">点击 segment 跳到该时间；点击文字框可编辑</p>
    <ol id="timeline-list"></ol>
  `;
  for (const k of ['title', 'location', 'mood', 'suggested_use']) {
    const el = pane.querySelector(`[data-field="${k}"]`);
    el.value = t[k] || '';
    el.oninput = () => { t[k] = el.value; markDirty(); };
  }
  const sumEl = pane.querySelector('[data-field="summary"]');
  sumEl.value = t.summary || '';
  sumEl.oninput = () => { t.summary = sumEl.value; markDirty(); };

  const ol = pane.querySelector('#timeline-list');
  for (const seg of (t.timeline || [])) {
    const li = document.createElement('li');
    li.className = 'timeline-seg';
    li.innerHTML = `
      <div class="seg-time">${escapeHtml(seg.start)} - ${escapeHtml(seg.end)}</div>
      <textarea data-seg-desc rows="2">${escapeHtml(seg.description || '')}</textarea>
    `;
    li.onclick = (e) => {
      if (e.target.tagName === 'TEXTAREA') return;
      const p = $('player');
      const curV = state.videos.find(x => x.file === state.currentVideo);
      p.currentTime = parseTimecode(seg.start) + (curV?.offset_sec || 0);
      p.play().catch(() => {});
    };
    li.querySelector('textarea').oninput = (e) => {
      seg.description = e.target.value;
      markDirty();
    };
    ol.appendChild(li);
  }
}

function renderVoiceover() {
  const v = state.voiceover;
  const pane = $('tab-voiceover');
  if (!v) {
    pane.innerHTML = '<p class="muted">当前视频没有对应的 voiceover JSON</p>';
    return;
  }
  pane.innerHTML = `
    <h3>口播文案</h3>
    <label>标题 <input data-field="title"></label>
    <label>口播文案 <textarea data-field="voiceover" rows="10"></textarea></label>
    <h3>剪辑提示</h3>
    <label>剪辑提示 <textarea data-field="edit_tip" rows="2"></textarea></label>
    <label>预计时长 (秒) <input data-field="duration_hint_sec" type="number" min="0" step="0.5"></label>
  `;
  for (const k of ['title', 'voiceover', 'edit_tip']) {
    const el = pane.querySelector(`[data-field="${k}"]`);
    el.value = v[k] || '';
    el.oninput = () => { v[k] = el.value; markDirty(); };
  }
  const dEl = pane.querySelector('[data-field="duration_hint_sec"]');
  dEl.value = v.duration_hint_sec ?? '';
  dEl.oninput = () => { v.duration_hint_sec = parseFloat(dEl.value) || 0; markDirty(); };
}

function renderTranscript() {
  const t = state.transcript;
  const pane = $('tab-transcript');
  if (!t || !t.ok) {
    pane.innerHTML = '<p class="muted">当前视频没有转录数据。</p><p class="hint">请先运行流水线中的「转录」步骤，或在 CLI 执行 <code>python main.py transcribe</code>。</p>';
    renderWhisperInstallPrompt(pane);
    // Check if install is already running — show progress immediately
    (async () => {
      try {
        const s = await api('GET', '/api/whisper/install/status');
        if (s.running && s.status === 'downloading') {
          const prog = $('install-progress');
          if (prog) prog.style.display = 'block';
          const btn = $('btn-install-whisper');
          if (btn) { btn.disabled = true; btn.textContent = '下载中...'; }
          if (_installPollTimer) clearInterval(_installPollTimer);
          _installPollTimer = setInterval(pollWhisperInstall, 1000);
          pollWhisperInstall();
        }
      } catch { /* ignore */ }
    })();
    return;
  }
  const segments = t.segments || [];
  pane.innerHTML = `
    <h3>语音转录 (ASR) — ${segments.length} 段</h3>
    <p class="hint">点击 segment 跳到对应时间；双击文字框可编辑；修改后需点击「保存」</p>
    <ol id="transcript-list"></ol>
  `;

  const ol = pane.querySelector('#transcript-list');
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    const li = document.createElement('li');
    li.className = 'transcript-seg';
    const startStr = fmtTime(seg.start || 0);
    const endStr = fmtTime(seg.end || 0);
    const confidence = seg.avg_logprob != null
      ? `<span class="muted" title="avg_logprob=${seg.avg_logprob.toFixed(2)}">${Math.round(Math.max(0, Math.min(100, (1 + (seg.avg_logprob || 0)) * 100)))}%</span>`
      : '';
    li.innerHTML = `
      <div class="seg-time">${escapeHtml(startStr)} - ${escapeHtml(endStr)} ${confidence}
        <button class="seg-del" data-index="${i}" title="删除此段">×</button>
      </div>
      <div class="seg-text" data-seg-index="${i}">${escapeHtml(seg.text || '')}</div>
    `;
    li.onclick = () => {
      const player = $('player');
      const v = state.videos.find(x => x.file === state.currentVideo);
      player.currentTime = seg.start + (v?.offset_sec || 0);
      player.play().catch(() => {});
    };
    const textDiv = li.querySelector('.seg-text');
    textDiv.ondblclick = (e) => {
      e.stopPropagation();
      const origV = state.videos.find(x => x.file === state.currentVideo);
      const inp = document.createElement('textarea');
      inp.className = 'seg-text-edit';
      inp.value = seg.text || '';
      inp.rows = 2;
      textDiv.replaceWith(inp);
      inp.focus();
      inp.onblur = async () => {
        const newText = inp.value;
        if (newText === seg.text) {
          const newDiv = document.createElement('div');
          newDiv.className = 'seg-text';
          newDiv.dataset.segIndex = i;
          newDiv.textContent = seg.text;
          inp.replaceWith(newDiv);
          newDiv.ondblclick = textDiv.ondblclick;
          return;
        }
        const v = origV || state.videos.find(x => x.file === state.currentVideo);
        if (!v) { setStatus('找不到当前视频', 'err'); return; }
        try {
          const r = await api('PUT', `/api/transcripts?video=${encodeURIComponent(v.file)}`, {
            segment_index: i,
            text: newText,
          });
          if (r.ok) {
            seg.text = newText;
            setStatus('转录文本已保存', 'ok');
          } else {
            setStatus('保存失败: ' + (r.error || '未知错误'), 'err');
          }
        } catch (e) {
          setStatus('保存失败: ' + e.message, 'err');
        }
        const newDiv = document.createElement('div');
        newDiv.className = 'seg-text';
        newDiv.dataset.segIndex = i;
        newDiv.textContent = seg.text;
        inp.replaceWith(newDiv);
        newDiv.ondblclick = textDiv.ondblclick;
      };
      inp.onkeydown = (e) => {
        if (e.key === 'Escape') { inp.blur(); }
      };
    };
    const delBtn = li.querySelector('.seg-del');
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`确定删除第 ${i + 1} 段转录？`)) return;
      const v = state.videos.find(x => x.file === state.currentVideo);
      if (!v) { setStatus('找不到当前视频', 'err'); return; }
      try {
        const r = await api('PUT', `/api/transcripts?video=${encodeURIComponent(v.file)}`, {
          segment_index: i, delete: true,
        });
        if (r.ok) {
          segments.splice(i, 1);
          setStatus('已删除', 'ok');
          renderTranscript();
        } else {
          setStatus('删除失败: ' + (r.error || '未知错误'), 'err');
        }
      } catch (e) {
        setStatus('删除失败: ' + e.message, 'err');
      }
    };
    ol.appendChild(li);
  }
}

let _installPollTimer = null;

async function renderWhisperInstallPrompt(pane) {
  let check;
  try { check = await api('GET', '/api/whisper/check'); } catch { return; }
  if (!check) return;
  const installed = check.installed;
  const cachePath = check.cache_path;
  if (installed && cachePath) {
    let hasCachedModel = false;
    try {
      const st = await api('GET', '/api/whisper/install/status');
      if (st.status === 'done') { hasCachedModel = true; }
    } catch { /* ignore */ }
  }
  const div = document.createElement('div');
  div.id = 'whisper-install-prompt';
  div.style.cssText = 'margin-top:12px;padding:12px;background:var(--warning-bg,#2a2520);border:1px solid var(--warning-border,#b8860b);border-radius:6px';
  div.innerHTML = `
    <p style="margin:0 0 8px;font-weight:600">${installed ? '⚠ Whisper 模型未缓存' : '⚠ 需要安装 Whisper'}</p>
    <p style="margin:0 0 8px;font-size:var(--text-sm);color:var(--text-secondary)">${installed ? '模型文件尚未下载到本地缓存，需要下载约 1-2 GB。' : '语音转录依赖 faster-whisper，需要先安装依赖并下载模型。'}</p>
    <button id="btn-install-whisper" class="btn-primary">${icon('download', 14)} 下载模型</button>
    <div id="install-progress" style="display:none;margin-top:8px">
      <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);margin-bottom:4px">
        <span id="install-msg">准备中...</span>
        <span id="install-speed"></span>
      </div>
      <div style="background:#333;border-radius:3px;height:8px;overflow:hidden">
        <div id="install-bar" style="background:#4a9eff;border-radius:3px;height:100%;width:0%"></div>
      </div>
      <p id="install-eta" class="muted" style="font-size:var(--text-xs);margin:4px 0 0"></p>
    </div>
    <div id="install-error" style="display:none;margin-top:8px;font-size:var(--text-sm);color:var(--err)"></div>
  `;
  pane.appendChild(div);

  const btn = $('btn-install-whisper');
  if (!btn) return;
  btn.onclick = async () => {
    btn.disabled = true;
    btn.textContent = '正在启动下载...';
    const prog = $('install-progress');
    if (prog) prog.style.display = 'block';
    try {
      const r = await api('POST', '/api/whisper/install', {});
      if (!r.ok) throw new Error(r.error || '启动失败');
      btn.textContent = '下载中...';
      if (_installPollTimer) clearInterval(_installPollTimer);
      _installPollTimer = setInterval(pollWhisperInstall, 1000);
      pollWhisperInstall();
    } catch (e) {
      btn.disabled = false;
      btn.innerHTML = `${icon('download', 14)} 下载模型`;
      const errEl = $('install-error');
      if (errEl) { errEl.style.display = 'block'; errEl.textContent = '启动下载失败: ' + e.message; }
    }
  };
}

async function pollWhisperInstall() {
  try {
    const s = await api('GET', '/api/whisper/install/status');
    const bar = $('install-bar');
    const msg = $('install-msg');
    const speed = $('install-speed');
    const eta = $('install-eta');
    const errEl = $('install-error');
    if (!s.running && s.status === 'idle') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      return;
    }
    if (s.status === 'downloading') {
      if (bar) bar.style.width = (s.progress_pct || 0) + '%';
      if (msg) msg.textContent = s.message || '下载中...';
      if (speed && s.speed) speed.textContent = s.speed;
      if (eta) {
        if (s.eta_sec != null) {
          const m = Math.floor(s.eta_sec / 60);
          const sec = s.eta_sec % 60;
          eta.textContent = `预计剩余 ${m} 分 ${sec} 秒`;
        } else {
          eta.textContent = '';
        }
      }
    } else if (s.status === 'done') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      if (bar) bar.style.width = '100%';
      if (msg) msg.textContent = '✔ 模型下载完成';
      if (eta) eta.textContent = '';
      // R-016c: auto-retry transcribe after download
      await retryTranscribe();
    } else if (s.status === 'error') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      const btn = $('btn-install-whisper');
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('download', 14)} 重试下载`; }
      if (errEl) { errEl.style.display = 'block'; errEl.textContent = s.message || '下载失败'; }
    }
  } catch { /* ignore polling errors */ }
}

function renderModelManagement() {
  const div = document.createElement('div');
  div.id = 'whisper-model-mgmt';
  div.style.cssText = 'margin-top:12px;padding:12px;background:var(--bg-surface,#1e1e1e);border:1px solid var(--border,#333);border-radius:6px';
  div.innerHTML = `
    <p style="margin:0 0 8px;font-weight:600">Whisper 模型管理</p>
    <div id="model-mgmt-content">
      <p class="muted">加载中...</p>
    </div>
  `;
  return div;
}

async function _loadModelMgmt() {
  const container = $('model-mgmt-content');
  if (!container) {
    setStatus('模型管理: DOM 未就绪', 'warn');
    return;
  }
  // 防止无限「加载中...」: 10 秒后显示超时提示
  const timeoutId = setTimeout(() => {
    if (container && container.querySelector('.muted')) {
      container.innerHTML = '<p class="err">请求超时 — 请确认后端服务运行正常。</p>';
    }
  }, 10000);
  try {
    const data = await api('GET', '/api/whisper/models');
    if (!data.ok) { container.innerHTML = '<p class="err">加载模型列表失败</p>'; return; }

    const current = data.current_model || 'medium';
    const avail = data.available || [];
    const cached = data.cached || [];

    let html = '<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:end">';

    html += '<div style="flex:1;min-width:140px">';
    html += '<label style="font-size:var(--text-xs);color:var(--text-secondary)">当前模型</label>';
    html += '<select id="model-size-select" style="width:100%;margin-top:2px">';
    for (const m of avail) {
      const sel = m.name === current ? ' selected' : '';
      const cachedIcon = cached.some(c => c.name === m.name && c.valid) ? ' ✓' : '';
      html += `<option value="${escapeHtml(m.name)}"${sel}>${escapeHtml(m.label)}${cachedIcon}</option>`;
    }
    html += '</select></div>';

    html += '<div>';
    const alreadyCached = cached.some(c => c.name === current && c.valid);
    html += `<button id="btn-model-download" class="btn-primary" style="font-size:var(--text-sm)"${alreadyCached ? ' disabled' : ''}>${icon('download', 14)} ${alreadyCached ? '已下载' : '下载模型'}</button>`;
    html += '</div>';

    html += '<div style="font-size:var(--text-xs);color:var(--text-secondary);white-space:nowrap">';
    html += `可用空间: ${escapeHtml(data.free_display || '?')}`;
    html += '</div>';

    html += '</div>';

    if (cached.length) {
      html += '<div style="margin-top:8px">';
      html += '<p style="font-size:var(--text-xs);color:var(--text-secondary);margin:0 0 4px">已缓存模型:</p>';
      for (const m of cached) {
        const validCls = m.valid ? 'ok' : 'err';
        html += '<div style="display:flex;gap:8px;align-items:center;padding:4px 0;font-size:var(--text-xs)">';
        html += `<span style="flex:1">${escapeHtml(m.name)} <span class="${validCls}">${m.valid ? '✓' : '✗ (不完整)'}</span> <span class="muted">${escapeHtml(m.size_display)}</span></span>`;
        html += `<button class="btn-delete-model" data-model="${escapeHtml(m.name)}" style="background:none;border:1px solid var(--err,#c44);color:var(--err,#c44);padding:2px 8px;border-radius:3px;cursor:pointer;font-size:var(--text-xs)">删除</button>`;
        html += '</div>';
      }
      html += '</div>';
    } else {
      html += '<p class="muted" style="margin-top:8px;font-size:var(--text-xs)">尚未缓存任何模型。请先下载。</p>';
    }

    html += '<div id="model-dl-progress" style="display:none;margin-top:8px">';
    html += '<div style="display:flex;justify-content:space-between;font-size:var(--text-xs);margin-bottom:4px">';
    html += '<span id="model-dl-msg"></span><span id="model-dl-speed"></span></div>';
    html += '<div style="background:#333;border-radius:3px;height:6px;overflow:hidden">';
    html += '<div id="model-dl-bar" style="background:#4a9eff;border-radius:3px;height:100%;width:0%"></div></div>';
    html += '<p id="model-dl-eta" class="muted" style="font-size:var(--text-xs);margin:2px 0 0"></p>';
    html += '</div>';

    container.innerHTML = html;

    const sel = $('model-size-select');
    if (sel) {
      sel.onchange = async () => {
        const newModel = sel.value;
        // 立即更新下载按钮状态（不等待后端返回）
        const dlBtn = $('btn-model-download');
        const isCached = cached.some(c => c.name === newModel && c.valid);
        if (dlBtn) {
          dlBtn.disabled = isCached;
          dlBtn.innerHTML = isCached ? '已下载' : `${icon('download', 14)} 下载模型`;
        }
        try {
          const r = await api('PUT', '/api/whisper/model', { model_size: newModel });
          if (r.ok) {
            setStatus(`模型已切换为 ${newModel}`, 'ok');
          } else {
            setStatus('切换模型失败: ' + (r.error || ''), 'err');
            sel.value = current;
          }
        } catch (e) {
          setStatus('切换模型失败: ' + e.message, 'err');
          sel.value = current;
        }
      };
    }

    const dlBtn = $('btn-model-download');
    if (dlBtn) {
      dlBtn.onclick = async () => {
        dlBtn.disabled = true;
        dlBtn.textContent = '启动下载...';
        const prog = $('model-dl-progress');
        if (prog) prog.style.display = 'block';
        try {
          const r = await api('POST', '/api/whisper/install', {});
          if (!r.ok) throw new Error(r.error || '启动失败');
          dlBtn.textContent = '下载中...';
          if (_installPollTimer) clearInterval(_installPollTimer);
          _installPollTimer = setInterval(_pollModelDl, 1000);
          _pollModelDl();
        } catch (e) {
          dlBtn.disabled = false;
          dlBtn.innerHTML = `${icon('download', 14)} 下载模型`;
          const progMsg = $('model-dl-msg');
          if (progMsg) progMsg.textContent = '启动失败: ' + e.message;
        }
      };
    }

    container.querySelectorAll('.btn-delete-model').forEach(btn => {
      btn.onclick = async () => {
        const modelName = btn.dataset.model;
        if (!confirm(`确定删除模型 ${modelName}？将释放磁盘空间。`)) return;
        try {
          const r = await api('POST', '/api/whisper/models/delete', { name: modelName });
          if (r.ok) {
            setStatus(`模型 ${modelName} 已删除`, 'ok');
            _loadModelMgmt();
          } else {
            setStatus('删除失败: ' + (r.error || ''), 'err');
          }
        } catch (e) {
          setStatus('删除失败: ' + e.message, 'err');
        }
      };
    });
    clearTimeout(timeoutId);
    // Resume polling if download is still in progress
    try {
      const st = await api('GET', '/api/whisper/install/status');
      if (st.running || st.status === 'downloading') {
        const prog = $('model-dl-progress');
        if (prog) prog.style.display = 'block';
        const dlBtn = $('btn-model-download');
        if (dlBtn) { dlBtn.disabled = true; dlBtn.textContent = '下载中...'; }
        if (_installPollTimer) clearInterval(_installPollTimer);
        _installPollTimer = setInterval(_pollModelDl, 1000);
        _pollModelDl();
      }
    } catch { /* polling resume not critical */ }
  } catch (e) {
    clearTimeout(timeoutId);
    if (container) container.innerHTML = `<p class="err">加载失败: ${escapeHtml(e.message)}</p>`;
  }
}

async function _pollModelDl() {
  try {
    const s = await api('GET', '/api/whisper/install/status');
    const bar = $('model-dl-bar');
    const msg = $('model-dl-msg');
    const speed = $('model-dl-speed');
    const eta = $('model-dl-eta');
    const dlBtn = $('btn-model-download');
    if (!s.running && s.status === 'idle') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      return;
    }
    if (s.status === 'downloading') {
      if (bar) bar.style.width = (s.progress_pct || 0) + '%';
      if (msg) msg.textContent = s.message || '下载中...';
      if (speed && s.speed) speed.textContent = s.speed;
      if (eta) {
        if (s.eta_sec != null) {
          const m = Math.floor(s.eta_sec / 60);
          const sec = s.eta_sec % 60;
          eta.textContent = `预计剩余 ${m} 分 ${sec} 秒`;
        } else { eta.textContent = ''; }
      }
    } else if (s.status === 'done') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      if (bar) bar.style.width = '100%';
      if (msg) msg.textContent = '✔ 下载完成';
      if (eta) eta.textContent = '';
      if (dlBtn) { dlBtn.disabled = false; dlBtn.innerHTML = `${icon('download', 14)} 下载模型`; }
      _loadModelMgmt();
      retryTranscribe();
    } else if (s.status === 'error') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      if (dlBtn) { dlBtn.disabled = false; dlBtn.innerHTML = `${icon('download', 14)} 重试下载`; }
      if (msg) msg.textContent = s.message || '下载失败';
    }
  } catch { /* ignore */ }
}

async function retryTranscribe() {
  const v = state.videos.find(x => x.file === state.currentVideo);
  if (!v || !v.file) return;
  try {
    const r = await api('POST', '/api/rerun', {
      video: v.file,
      task: 'transcribe',
      source: 'compressed',
    });
    if (r.ok) {
      setStatus('模型下载完成，正在重新转录...', 'ok');
      // Poll for transcription to complete, then refresh
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          state.transcript = await api('GET', `/api/transcripts?video=${encodeURIComponent(v.file)}`);
        } catch { /* not ready yet */ }
        if ((state.transcript && state.transcript.ok) || attempts > 30) {
          clearInterval(poll);
          renderTranscript();
        }
      }, 2000);
    }
  } catch (e) {
    setStatus('自动转录失败: ' + e.message, 'err');
  }
}

function renderPlan() {
  const p = state.plan;
  const pane = $('tab-plan');
  $('player-pane').classList.add('plan-mode');
  renderPreviewBar();
  if (!p) {
    pane.innerHTML = `
      <h3>vlog 剪辑规划</h3>
      <p class="muted">当前项目没有编排文件。</p>
      <p class="hint">请先运行流水线中的「vlog 剪辑规划」步骤，或在 CLI 执行 <code>python main.py plan</code>。</p>
    `;
    return;
  }
  pane.innerHTML = `
    <h3>编排元信息</h3>
    ${state.availablePlans.length >= 1 ? `
    <label>分集
      <select id="plan-day-select">
        ${state.availablePlans.map(dp =>
          `<option value="${dp.day_label}" ${dp.day_label === state.currentDay ? 'selected' : ''}>${dp.day_label}</option>`
        ).join('')}
      </select>
    </label>
    ` : ''}
    <label>主题 <input data-field="theme"></label>
    <label>开场提示 <textarea data-field="opening_tip" rows="2"></textarea></label>
    <label>收尾提示 <textarea data-field="ending_tip" rows="2"></textarea></label>
    <h3>顺序 (sequence) — ${(p.sequence || []).length} 项</h3>
    <p class="hint">点击 segment 跳到对应视频</p>
    <ol id="plan-list"></ol>
  `;
  const daySelect = pane.querySelector('#plan-day-select');
  if (daySelect) {
    daySelect.onchange = async () => {
      const day = daySelect.value;
      if (day === state.currentDay) return;
      if (state.dirty && !confirm('切换分集将丢弃当前修改，确定吗？')) { daySelect.value = state.currentDay; return; }
      state.currentDay = day;
      state.plan = null;
      state.dirty = false;
      updateSidebarDay();
      await import('./sidebar.js').then(mod => mod.saveProject());
      // Re-select the plan for the new day — import sidebar dynamically to avoid circular deps
      await import('./sidebar.js').then(mod => mod.selectPlan());
    };
  }
  for (const k of ['theme', 'opening_tip', 'ending_tip']) {
    const el = pane.querySelector(`[data-field="${k}"]`);
    el.value = p[k] || '';
    el.oninput = () => { p[k] = el.value; markDirty(); };
  }
  const ol = pane.querySelector('#plan-list');
  (p.sequence || []).forEach((seg, i) => {
    const li = document.createElement('li');
    li.className = 'plan-seg' + (state.previewActive && state.previewIndex === i ? ' preview-active' : '');
    li.dataset.previewIndex = i;
    li.innerHTML = `
      <div class="seg-time">${escapeHtml(seg.use_timeline || '')} <span class="muted">视频 [${escapeHtml(seg.index || '?')}]</span></div>
      <div class="seg-title">${escapeHtml(seg.title || '')}</div>
      <label>理由 <input value="${escapeHtml(seg.reason || '')}" data-k="reason"></label>
      <label>口播提示 <textarea rows="2" data-k="voiceover_hint">${escapeHtml(seg.voiceover_hint || '')}</textarea></label>
    `;
    li.onclick = (e) => {
      if (e.target.matches('input, textarea')) return;
      const v = state.videos.find(x => x.index === seg.index);
      if (!v) { setStatus(`找不到视频 [${seg.index}]，请重新生成规划`, 'warn'); return; }
      if (state.previewActive) {
        state.previewIndex = i;
        _playPreviewSegment();
      } else {
        startPreview(i);
      }
    };
    li.querySelectorAll('[data-k]').forEach(inp => {
      inp.oninput = (e) => {
        p.sequence[i][e.target.dataset.k] = e.target.value;
        markDirty();
      };
    });
    ol.appendChild(li);
  });

  // ── 裁剪区块 ─────────────────────────────────────────────────────
  const cutSection = document.createElement('div');
  cutSection.className = 'cut-section';
  cutSection.innerHTML = `
    <h3>裁剪此分集</h3>
    <p class="hint">基于规划 ${escapeHtml(state.currentDay)} 裁剪所有片段</p>
    <label>视频来源
      <select id="cut-source">
        <option value="compressed" selected>压缩版 (compressed)</option>
        <option value="original">原片 (original)</option>
      </select>
    </label>
    <label><input type="checkbox" id="cut-reencode"> 重新编码 (默认 -c copy 快速)</label>
    <label>输出目录 (留空则 output/cuts/&lt;day&gt;)
      <span class="input-with-browse"><input id="cut-outdir" placeholder="例如 E:/剪辑素材/第一天"><button class="browse-btn" data-target="cut-outdir" type="button">浏览</button></span></label>
    <button id="btn-cut-exec" class="btn-primary">${icon('cut', 16)} 执行裁剪</button>
    <div id="cut-result" style="margin-top:12px"></div>
  `;
  pane.appendChild(cutSection);
  $('btn-cut-exec').onclick = executeCut;
}

async function executeCut() {
  const btn = $('btn-cut-exec');
  const result = $('cut-result');
  btn.disabled = true;
  btn.textContent = '裁剪中...';
  result.innerHTML = '<p class="muted">请等待，正在裁剪视频片段...</p>';
  try {
    const dayLabel = state.currentDay;
    // 先校验规划文件是否存在
    let planCheck;
    try { planCheck = await api('GET', `/api/plan?day=${dayLabel}`); }
    catch (e) {
      result.innerHTML = `<p class="err">规划文件不存在: 请先运行 CLI 命令 <code>python main.py plan --day ${escapeHtml(dayLabel)}</code> 生成规划。</p>`;
      setStatus('裁剪失败: 规划文件不存在', 'err');
      btn.disabled = false;
      btn.textContent = '执行裁剪';
      return;
    }
    const r = await api('POST', '/api/cut', {
      day_label: dayLabel,
      source: $('cut-source').value,
      reencode: $('cut-reencode').checked,
      output_dir: $('cut-outdir').value.trim() || null,
    });
    if (r.ok) {
      result.innerHTML = `<p class="ok">裁剪完成</p><p>输出目录: ${escapeHtml(r.output_dir)}</p>`;
      setStatus('裁剪完成', 'ok');
      state.steps.cut = true;
      import('./sidebar.js').then(mod => mod.renderSteps());
      import('./sidebar.js').then(mod => mod.saveProject());
    } else {
      throw new Error(r.error || '裁剪失败');
    }
  } catch (e) {
    result.innerHTML = `<p class="err">错误: ${escapeHtml(e.message)}</p>`;
    setStatus('裁剪失败: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '执行裁剪';
  }
}

async function save() {
  if (!state.dirty) { setStatus('没有改动需要保存', 'warn'); return; }
  const entity = state.currentEntity;
  const day = state.currentDay;
  const tab = state.currentTab;
  const videoFile = state.currentVideo;
  const planData = state.plan;
  const textsData = state.texts;
  const voiceoverData = state.voiceover;
  const configRaw = state.configRaw;
  try {
    if (entity === 'run') {
      setStatus('当前视图不需要保存', 'warn');
      return;
    }
    if (entity === 'config') {
      const r = await api('PUT', '/api/config/raw', configRaw);
      if (r.error) throw new Error(r.error);
      state.dirty = false;
      updateSaveBtn();
      setStatus('配置已保存（需重启服务生效）', 'ok');
      return;
    }
    if (entity === 'plan') {
      const r = await api('PUT', `/api/plan?day=${day}`, planData);
      if (!r.ok) throw new Error(r.error);
    } else {
      const v = state.videos.find(x => x.file === videoFile);
      if (tab === 'texts') {
        if (!v || !v.text_json) throw new Error('当前视频没有 texts JSON');
        const r = await api('PUT', `/api/texts?file=${encodeURIComponent(v.text_json)}`, textsData);
        if (!r.ok) throw new Error(r.error);
      } else if (tab === 'voiceover') {
        if (!v || !v.script_json) throw new Error('当前视频没有 voiceover JSON');
        const r = await api('PUT', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`, voiceoverData);
        if (!r.ok) throw new Error(r.error);
      }
    }
    state.dirty = false;
    updateSaveBtn();
    setStatus('已保存', 'ok');
  } catch (e) {
    setStatus('保存失败: ' + e.message, 'err');
  }
}

async function initProjectConfig() {
  try {
    const btn = $('btn-config-init');
    if (btn) { btn.disabled = true; btn.textContent = '创建中...'; }
    const r = await api('POST', '/api/config/init', {});
    if (r.ok) {
      setStatus('项目配置文件已创建', 'ok');
      // 重新加载配置
      state.configRaw = await api('GET', '/api/config/raw');
      state._needsConfigInit = false;
      renderActiveTab();
    } else {
      setStatus('创建失败: ' + (r.error || '未知错误'), 'err');
    }
  } catch (e) {
    setStatus('创建失败: ' + e.message, 'err');
  } finally {
    const btn = $('btn-config-init');
    if (btn) { btn.disabled = false; btn.textContent = '为该项目创建配置文件'; }
  }
}

function labelFromPath(path) {
  return path ? path.split('.').pop() : 'config';
}

function _renderConfigForm(obj, path) {
  if (obj === null || obj === undefined) {
    return `<span class="config-null">(空)</span>`;
  }
  if (typeof obj === 'boolean') {
    return `<label class="config-field config-bool"><span class="config-key">${labelFromPath(path)}</span> <input type="checkbox" data-path="${path}" ${obj ? 'checked' : ''}></label>`;
  }
  if (typeof obj === 'number') {
    const isInt = Number.isInteger(obj);
    return `<label class="config-field config-num"><span class="config-key">${labelFromPath(path)}</span> <input type="number" data-path="${path}" step="${isInt ? '1' : 'any'}" value="${obj}"></label>`;
  }
  if (typeof obj === 'string') {
    const multiline = path === 'ai.context' || obj.length > 80 || obj.includes('\n');
    if (multiline) {
      let hint = '';
      if (path === 'ai.context') {
        hint = '<br><span class="hint">项目特定背景（如拍摄地点、行程安排），将追加到默认模板 <code>trip_context.md</code> 之后。留空则仅使用默认模板。</span>';
      }
      return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}</span> <textarea data-path="${path}" rows="4">${escapeHtml(obj)}</textarea>${hint}</label>`;
    }
    const isPwd = path.endsWith('api_key');
    return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}</span> <input type="${isPwd ? 'password' : 'text'}" data-path="${path}" value="${escapeHtml(obj)}"></label>`;
  }
  if (Array.isArray(obj)) {
    const allStr = obj.every(x => typeof x === 'string');
    if (allStr) {
      return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend><label class="config-field config-str"><textarea data-path="${path}" rows="${Math.max(2, obj.length)}">${escapeHtml(obj.join('\n'))}</textarea><span class="hint">每行一项</span></label></fieldset>`;
    }
    return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend>${obj.map((item, i) =>
      `<div class="config-array-item">${_renderConfigForm(item, path + '[' + i + ']')}</div>`
    ).join('')}</fieldset>`;
  }
  if (typeof obj === 'object') {
    let html = `<fieldset class="config-fieldset"><legend>${labelFromPath(path) || '配置'}</legend>`;
    for (const [key, val] of Object.entries(obj)) {
      if (key === 'context_file') continue; // context 已替代，隐藏避免混淆
      html += _renderConfigForm(val, path ? `${path}.${key}` : key);
    }
    html += '</fieldset>';
    return html;
  }
  return `<span class="muted">${escapeHtml(String(obj))}</span>`;
}

function renderConfig() {
  const pane = $('tab-config');
  if (state._needsConfigInit) {
    pane.innerHTML = `
      <h3>项目配置初始化</h3>
      <p class="muted">该项目还没有专属配置文件。</p>
      <p class="hint">创建后将以当前全局配置为模板，后续修改只影响本项目。</p>
      <button id="btn-config-init" class="btn-primary" style="margin-top:12px">${icon('settings', 16)} 为该项目创建配置文件</button>
    `;
    const btn = $('btn-config-init');
    if (btn) btn.onclick = initProjectConfig;
    return;
  }
  if (!state.configRaw || Object.keys(state.configRaw).length === 0) {
    pane.innerHTML = '<p class="muted">配置数据不可用</p>';
    return;
  }
  const isFallback = state.configRaw._config_source === 'global_fallback';
  // 排除 meta 字段
  const { _config_source, _needsConfigInit, ...configData } = state.configRaw;
  pane.innerHTML = (isFallback ? `
    <div class="config-fallback-warn" style="background:var(--warning-bg,#fff3cd);border:1px solid var(--warning-border,#ffc107);border-radius:6px;padding:10px 14px;margin-bottom:12px;display:flex;align-items:flex-start;gap:8px;font-size:var(--text-sm);color:var(--text-primary)">
      <span style="font-size:18px;line-height:1">⚠️</span>
      <span>当前显示的是全局配置（回退）。该项目没有专属 <code>project.yaml</code>，修改将影响所有项目。建议<a href="#" onclick="initProjectConfig();return false" style="text-decoration:underline;color:var(--accent)">创建专属配置</a>。</span>
    </div>
  ` : '') + `
  <div style="margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:12px">
    <button id="btn-env-toggle" class="btn-secondary" style="font-size:var(--text-sm)">${icon('file-text', 14)} 编辑 .env 文件</button>
    <div id="env-editor" style="display:none;margin-top:8px">
      <textarea id="env-textarea" style="width:100%;min-height:160px;font-family:var(--font-mono,monospace);font-size:var(--text-xs,12px);padding:8px;background:var(--bg-surface);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)" spellcheck="false"></textarea>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button id="btn-env-save" class="btn-primary" style="font-size:var(--text-sm)">${icon('check', 14)} 保存 .env</button>
        <span id="env-save-msg" class="muted" style="font-size:var(--text-xs);align-self:center"></span>
      </div>
    </div>
  </div>
  <div class="config-form">${_renderConfigForm(configData, '')}</div>`;
  // ai.context 空时显示"添加默认模板"按钮
  const ctxTextarea = pane.querySelector('textarea[data-path="ai.context"]');
  if (ctxTextarea && !ctxTextarea.value.trim()) {
    const btn = document.createElement('button');
    btn.className = 'btn-primary';
    btn.style.cssText = 'margin-top:6px;font-size:var(--text-sm);padding:5px 12px;';
    btn.innerHTML = `${icon('plus', 14)} 添加默认模板`;
    btn.onclick = () => {
      const template = '## 项目背景\n- 拍摄地点：[填写拍摄地点]\n- 行程安排：[填写行程安排]\n- 人物/事件：[填写人物或事件]\n- 注意事项：[填写注意事项]\n\n请根据以上信息调整 AI 的分析和口播生成方向。';
      ctxTextarea.value = template;
      setDeep(state.configRaw, 'ai.context', template);
      markDirty();
      btn.remove();
    };
    ctxTextarea.parentNode.appendChild(btn);
  }

  // bind change handlers
  pane.querySelectorAll('[data-path]').forEach(el => {
    const onchange = () => {
      let val;
      if (el.type === 'checkbox') {
        val = el.checked;
      } else if (el.type === 'number') {
        val = el.value.includes('.') ? parseFloat(el.value) : (el.value === '' ? '' : parseInt(el.value, 10));
        if (isNaN(val)) val = el.value;
      } else {
        val = el.value;
      }
      setDeep(state.configRaw, el.dataset.path, val);
      markDirty();
    };
    el.onchange = onchange;
    if (el.tagName === 'INPUT' && el.type === 'text') {
      el.oninput = onchange;
    }
    if (el.tagName === 'TEXTAREA') {
      el.oninput = onchange;
    }
  });

  // ---- .env file editor ----
  const envToggle = $('btn-env-toggle');
  const envEditor = $('env-editor');
  const envTextarea = $('env-textarea');
  const envSave = $('btn-env-save');
  const envMsg = $('env-save-msg');
  let envData = { content: '' };
  if (envToggle && envEditor) {
    envToggle.onclick = async () => {
      const visible = envEditor.style.display !== 'none';
      envEditor.style.display = visible ? 'none' : 'block';
      envToggle.innerHTML = visible ? `${icon('file-text', 14)} 编辑 .env 文件` : `${icon('x', 14)} 收起`;
      if (!visible && !envData.content) {
        try {
          envData = await api('GET', '/api/env');
          envTextarea.value = envData.content || '';
        } catch (e) {
          envMsg.textContent = '加载失败';
        }
      }
    };
  }
  if (envSave && envTextarea && envMsg) {
    envSave.onclick = async () => {
      envMsg.textContent = '保存中...';
      try {
        const r = await api('PUT', '/api/env', { content: envTextarea.value });
        if (r.ok) {
          envMsg.textContent = `✓ 已保存到 ${r.path}`;
          envData.content = envTextarea.value;
        } else {
          envMsg.textContent = `✗ ${r.error || '保存失败'}`;
        }
      } catch (e) {
        envMsg.textContent = `✗ 保存失败: ${e.message || e}`;
      }
    };
  }

  // Append Whisper model management section at the bottom of config tab
  pane.appendChild(renderModelManagement());
  _loadModelMgmt();
}

let _logsTimer = null;
let _logsOffset = 0;
let _logsAutoScroll = true;

function renderLogs() {
  const pane = $('tab-logs');
  _logsOffset = 0;
  if (_logsTimer) { clearInterval(_logsTimer); _logsTimer = null; }
  pane.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;padding:8px;border-bottom:1px solid var(--border);flex-shrink:0">
      <span style="font-weight:600">会话日志</span>
      <label style="margin-left:auto;display:flex;align-items:center;gap:4px;cursor:pointer">
        <input type="checkbox" id="logs-autoscroll" checked> 自动滚动
      </label>
      <button class="btn-secondary" id="btn-logs-clear">清空</button>
    </div>
    <div id="logs-view" style="flex:1;overflow-y:auto;padding:8px;font-family:var(--font-mono,monospace);font-size:var(--text-xs,12px);line-height:1.6;background:#1a1a1a;white-space:pre-wrap;word-break:break-all"></div>
  `;
  const view = $('logs-view');
  const cb = $('logs-autoscroll');
  if (cb) cb.onchange = () => { _logsAutoScroll = cb.checked; };
  $('btn-logs-clear').onclick = async () => {
    try {
      await api('POST', '/api/logs/clear', {});
      view.innerHTML = '';
      _logsOffset = 0;
    } catch { /* ignore */ }
  };
  _logsTimer = setInterval(async () => {
    try {
      const r = await api('GET', `/api/logs?offset=${_logsOffset}`);
      if (!r || !r.logs) return;
      for (const line of r.logs) {
        const d = document.createElement('div');
        d.textContent = line;
        view.appendChild(d);
      }
      _logsOffset = r.total;
      if (_logsAutoScroll) view.scrollTop = view.scrollHeight;
    } catch { /* ignore */ }
  }, 2000);
  // Initial fetch
  (async () => {
    try {
      const r = await api('GET', '/api/logs?offset=0');
      if (r && r.logs) {
        view.innerHTML = r.logs.map(l => `<div>${escapeHtml(l)}</div>`).join('');
        _logsOffset = r.total;
        if (_logsAutoScroll) view.scrollTop = view.scrollHeight;
      }
    } catch { /* ignore */ }
  })();
}

export {
  renderActiveTab,
  renderLogs,
  renderTexts,
  renderVoiceover,
  renderPlan,
  renderConfig,
  executeCut,
  save,
  initProjectConfig,
};

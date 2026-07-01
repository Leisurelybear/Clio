import { state } from './state.js';
import { $, $$, escapeHtml, markDirty, updateSaveBtn, setStatus, setDeep } from './utils.js';
import { api, icon } from './api.js';
import { renderActiveTab } from './editor.js';


export function labelFromPath(path) {
  return path ? path.split('.').pop() : 'config';
}


function _resolveDescPath(path, descriptions) {
  if (!descriptions) return null;
  if (descriptions[path]) return path;
  const m = path.match(/^(ai\.(?:providers|tasks))\.([^.]+)\.(.+)$/);
  if (m) {
    const candidate = `${m[1]}.{name}.${m[3]}`;
    if (descriptions[candidate]) return candidate;
  }
  return null;
}


export function _renderTooltip(path, desc) {
  if (!desc) return '';
  return `<span class="config-desc-icon" data-desc-path="${path}" tabindex="0">
    <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><circle cx="8" cy="8" r="7"/><text x="8" y="10" text-anchor="middle" font-size="9" fill="white" font-weight="bold">?</text></svg>
    <span class="config-desc-tooltip">${escapeHtml(desc)}</span>
  </span>`;
}


export function _renderConfigForm(obj, path, descriptions = null) {
  if (obj === null || obj === undefined) {
    return `<span class="config-null">(空)</span>`;
  }
  const descPath = _resolveDescPath(path, descriptions);
  const tip = descPath ? _renderTooltip(path, descriptions[descPath]) : '';
  if (typeof obj === 'boolean') {
    return `<label class="config-field config-bool"><span class="config-key">${labelFromPath(path)}${tip}</span> <input type="checkbox" data-path="${path}" ${obj ? 'checked' : ''}></label>`;
  }
  if (typeof obj === 'number') {
    const isInt = Number.isInteger(obj);
    return `<label class="config-field config-num"><span class="config-key">${labelFromPath(path)}${tip}</span> <input type="number" data-path="${path}" step="${isInt ? '1' : 'any'}" value="${obj}"></label>`;
  }
  if (typeof obj === 'string') {
    const multiline = path === 'ai.context' || obj.length > 80 || obj.includes('\n');
    if (multiline) {
      let hint = '';
      if (path === 'ai.context') {
        hint = '<br><span class="hint">项目特定背景（如拍摄地点、行程安排），将追加到默认模板 <code>trip_context.md</code> 之后。留空则仅使用默认模板。</span>';
      }
      return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}${tip}</span> <textarea data-path="${path}" rows="4">${escapeHtml(obj)}</textarea>${hint}</label>`;
    }
    const isPwd = path.endsWith('api_key');
    let hint = '';
    if (path.endsWith('api_key_env')) {
      hint = '<br><span class="hint">环境变量名称（如 <code>GEMINI_API_KEY</code>），实际密钥值写在项目根目录的 <code>.env</code> 文件中</span>';
    } else if (path.endsWith('base_url')) {
      hint = '<br><span class="hint">API 基础地址。Gemini 留空即可；OpenAI 兼容接口必填，如 <code>https://api.deepseek.com/v1</code></span>';
    } else if (path.endsWith('api_key')) {
      hint = '<br><span class="hint">API 密钥（直接填入）。<strong>不推荐</strong>，建议使用 <code>api_key_env</code> 配合 <code>.env</code> 文件更安全</span>';
    }
    return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}${tip}</span> <input type="${isPwd ? 'password' : 'text'}" data-path="${path}" value="${escapeHtml(obj)}"></label>${hint}`;
  }
  if (Array.isArray(obj)) {
    const allStr = obj.every(x => typeof x === 'string');
    if (allStr) {
      return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend><label class="config-field config-str"><textarea data-path="${path}" rows="${Math.max(2, obj.length)}">${escapeHtml(obj.join('\n'))}</textarea><span class="hint">每行一项</span></label></fieldset>`;
    }
    return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend>${obj.map((item, i) =>
      `<div class="config-array-item">${_renderConfigForm(item, path + '[' + i + ']', descriptions)}</div>`
    ).join('')}</fieldset>`;
  }
  if (typeof obj === 'object') {
    let html = `<fieldset class="config-fieldset"><legend>${labelFromPath(path) || '配置'}${tip}</legend>`;
    for (const [key, val] of Object.entries(obj)) {
      if (key === 'context_file') continue;
      html += _renderConfigForm(val, path ? `${path}.${key}` : key, descriptions);
    }
    html += '</fieldset>';
    return html;
  }
  return `<span class="muted">${escapeHtml(String(obj))}</span>`;
}


export async function initProjectConfig() {
  try {
    const btn = $('btn-config-init');
    if (btn) { btn.disabled = true; btn.textContent = '创建中...'; }
    const r = await api('POST', '/api/config/init', {});
    if (r.ok) {
      setStatus('项目配置文件已创建', 'ok');
      const [raw, global, project] = await Promise.all([
        api('GET', '/api/config/raw'),
        api('GET', '/api/config/global'),
        api('GET', '/api/config/project'),
      ]);
      state.configRaw = raw;
      state.configGlobal = global || {};
      state.configProject = project || {};
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


function _tabBtn(label, tabKey, active) {
  return `<button class="config-tab-btn${active ? ' active' : ''}" data-config-tab="${tabKey}">${label}</button>`;
}

function _renderFallbackWarn() {
  return `<div class="config-fallback-warn" style="background:var(--warning-bg,#fff3cd);border:1px solid var(--warning-border,#ffc107);border-radius:6px;padding:10px 14px;margin-bottom:12px;display:flex;align-items:flex-start;gap:8px;font-size:var(--text-sm);color:var(--text-primary)">
    <span style="font-size:18px;line-height:1">⚠️</span>
    <span>当前显示的是全局配置（回退）。该项目没有专属 <code>project.yaml</code>，修改将影响所有项目。建议<a href="#" onclick="initProjectConfig();return false" style="text-decoration:underline;color:var(--accent)">创建专属配置</a>。</span>
  </div>`;
}

function _renderEnvEditor() {
  return `<div style="margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:12px">
    <button id="btn-env-toggle" class="btn-secondary" style="font-size:var(--text-sm)">${icon('file-text', 14)} 编辑 .env 文件</button>
    <div id="env-editor" style="display:none;margin-top:8px">
      <textarea id="env-textarea" style="width:100%;min-height:160px;font-family:var(--font-mono,monospace);font-size:var(--text-xs,12px);padding:8px;background:var(--bg-surface);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)" spellcheck="false"></textarea>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button id="btn-env-save" class="btn-primary" style="font-size:var(--text-sm)">${icon('check', 14)} 保存 .env</button>
        <span id="env-save-msg" class="muted" style="font-size:var(--text-xs);align-self:center"></span>
      </div>
    </div>
  </div>`;
}

function _attachEnvEditor() {
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
}

function _attachConfigForm(pane, sourceObj, descriptions) {
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
      setDeep(sourceObj, el.dataset.path, val);
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
  pane.querySelectorAll('.config-desc-icon').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      el.classList.toggle('show');
    };
  });
}

function _attachContextTemplate(pane) {
  const ctxTextarea = pane.querySelector('textarea[data-path="ai.context"]');
  if (ctxTextarea && !ctxTextarea.value.trim()) {
    const btn = document.createElement('button');
    btn.className = 'btn-primary';
    btn.style.cssText = 'margin-top:6px;font-size:var(--text-sm);padding:5px 12px;';
    btn.innerHTML = `${icon('plus', 14)} 添加默认模板`;
    btn.onclick = () => {
      const template = '## 项目背景\n- 拍摄地点：[填写拍摄地点]\n- 行程安排：[填写行程安排]\n- 人物/事件：[填写人物或事件]\n- 注意事项：[填写注意事项]\n\n请根据以上信息调整 AI 的分析和口播生成方向。';
      ctxTextarea.value = template;
      setDeep(state.configProject, 'ai.context', template);
      markDirty();
      btn.remove();
    };
    ctxTextarea.parentNode.appendChild(btn);
  }
}


export function renderConfig() {
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
  const active = state.configTab || 'project';
  const descs = state.configRaw._descriptions || {};

  let contentHtml = '';
  if (active === 'project') {
    const projectData = state.configProject || {};
    contentHtml = `<div class="config-form">${_renderConfigForm(projectData, '', descs)}</div>`;
  } else if (active === 'global') {
    const { _config_source, _needsConfigInit, _descriptions, ...configData } = state.configRaw;
    const globalData = state.configGlobal || {};
    contentHtml = _renderEnvEditor()
      + `<div class="config-form">${_renderConfigForm(globalData, '', descs)}</div>`;
  } else {
    // Merged tab: read-only merged view
    const { _config_source, _needsConfigInit, _descriptions, ...configData } = state.configRaw;
    contentHtml = `<p class="hint" style="margin-bottom:8px">以下为全局 + 项目各层合并后的有效配置。只读。</p>
      <div class="config-form config-merged">${_renderConfigForm(configData, '', descs)}</div>`;
  }

  pane.innerHTML = `
    <div class="config-tab-bar">
      ${_tabBtn('项目', 'project', active === 'project')}
      ${_tabBtn('全局', 'global', active === 'global')}
      ${_tabBtn('合并视图', 'merged', active === 'merged')}
    </div>
    ${isFallback ? _renderFallbackWarn() : ''}
    <div id="config-tab-content">${contentHtml}</div>`;

  // Tab switching
  pane.querySelectorAll('.config-tab-btn').forEach(btn => {
    btn.onclick = () => {
      state.configTab = btn.dataset.configTab;
      state.dirty = false;
      updateSaveBtn();
      renderConfig();
    };
  });

  // Hide save button for merged tab (read-only)
  const saveBtn = $('btn-save');
  if (saveBtn) {
    saveBtn.style.display = active === 'merged' ? 'none' : '';
  }

  // Attach change handlers for the active tab
  if (active === 'global') {
    _attachConfigForm(pane, state.configGlobal || {}, descs);
    _attachEnvEditor();
  } else if (active === 'project') {
    _attachConfigForm(pane, state.configProject || {}, descs);
    _attachContextTemplate(pane);
  }

  // Model management stays in global tab (system-level)
  if (active === 'global') {
    pane.querySelector('#config-tab-content')?.appendChild(renderModelManagement());
    _loadModelMgmt();
  }
}





let _logsTimer = null;
let _logsOffset = 0;
let _logsAutoScroll = true;

export function renderLogs() {
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


export async function renderTokens() {
  const pane = $('tab-tokens');
  pane.innerHTML = '<p class="muted">加载中...</p>';
  try {
    const data = await api('GET', '/api/token-usage');
    if (!data || !data.total) {
      pane.innerHTML = '<p class="muted">暂无 token 使用数据。运行流水线后会自动记录。</p>';
      return;
    }
    const t = data.total;
    const totalHtml = `
      <div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);flex-wrap:wrap">
        <div class="token-card"><div class="token-card-value">${t.total_tokens.toLocaleString()}</div><div class="token-card-label">总 Token</div></div>
        <div class="token-card"><div class="token-card-value">${t.prompt_tokens.toLocaleString()}</div><div class="token-card-label">Prompt</div></div>
        <div class="token-card"><div class="token-card-value">${t.completion_tokens.toLocaleString()}</div><div class="token-card-label">Completion</div></div>
      </div>`;

    let modelHtml = '<h4 style="margin:var(--space-2) 0">按模型</h4><table class="token-table"><tr><th>模型</th><th>调用次数</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const [model, m] of Object.entries(data.by_model || {})) {
      modelHtml += `<tr><td>${escapeHtml(model)}</td><td>${m.calls}</td><td>${m.prompt_tokens.toLocaleString()}</td><td>${m.completion_tokens.toLocaleString()}</td><td>${m.total_tokens.toLocaleString()}</td></tr>`;
    }
    modelHtml += '</table>';

    let taskHtml = '<h4 style="margin:var(--space-2) 0">按任务</h4><table class="token-table"><tr><th>任务</th><th>调用次数</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const [task, tk] of Object.entries(data.by_task || {})) {
      taskHtml += `<tr><td>${escapeHtml(task)}</td><td>${tk.calls}</td><td>${tk.prompt_tokens.toLocaleString()}</td><td>${tk.completion_tokens.toLocaleString()}</td><td>${tk.total_tokens.toLocaleString()}</td></tr>`;
    }
    taskHtml += '</table>';

    let historyHtml = '<h4 style="margin:var(--space-2) 0">历史记录</h4><table class="token-table"><tr><th>时间</th><th>任务</th><th>模型</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const h of (data.history || []).slice().reverse().slice(0, 100)) {
      historyHtml += `<tr><td class="token-time">${escapeHtml(h.timestamp || '')}</td><td>${escapeHtml(h.task || '')}</td><td>${escapeHtml(h.model || '')}</td><td>${(h.prompt_tokens || 0).toLocaleString()}</td><td>${(h.completion_tokens || 0).toLocaleString()}</td><td>${(h.total_tokens || 0).toLocaleString()}</td></tr>`;
    }
    historyHtml += '</table>';

    pane.innerHTML = `<div style="padding:var(--space-2)">${totalHtml}${modelHtml}${taskHtml}${historyHtml}</div>`;
  } catch (e) {
    pane.innerHTML = `<p class="muted">加载失败: ${escapeHtml(e.message || e)}</p>`;
  }
}


let _installPollTimer = null;

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
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">';
    html += '<p id="model-dl-eta" class="muted" style="font-size:var(--text-xs);margin:0"></p>';
    html += '<button id="btn-cancel-dl" style="background:none;border:1px solid var(--err,#c44);color:var(--err,#c44);padding:2px 10px;border-radius:3px;cursor:pointer;font-size:var(--text-xs);display:none">取消下载</button>';
    html += '</div>';
    html += '</div>';

    container.innerHTML = html;

    const sel = $('model-size-select');
    if (sel) {
      sel.onchange = async () => {
        const newModel = sel.value;
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
        const cancelBtn = $('btn-cancel-dl');
        if (cancelBtn) cancelBtn.style.display = '';
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

    const cancelBtn = $('btn-cancel-dl');
    if (cancelBtn) {
      cancelBtn.onclick = async () => {
        try {
          await api('POST', '/api/whisper/install/cancel', {});
        } catch { /* ignore */ }
        if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
        const prog = $('model-dl-progress');
        if (prog) prog.style.display = 'none';
        cancelBtn.style.display = 'none';
        const dlBtn = $('btn-model-download');
        if (dlBtn) { dlBtn.disabled = false; dlBtn.innerHTML = `${icon('download', 14)} 下载模型`; }
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
    try {
      const st = await api('GET', '/api/whisper/install/status');
      if (st.running || st.status === 'downloading') {
        const prog = $('model-dl-progress');
        if (prog) prog.style.display = 'block';
        const cancelBtn = $('btn-cancel-dl');
        if (cancelBtn) cancelBtn.style.display = '';
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
    const cancelBtn = $('btn-cancel-dl');
    if (!s.running && s.status === 'idle') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      if (cancelBtn) cancelBtn.style.display = 'none';
      return;
    }
    if (s.status === 'downloading') {
      if (cancelBtn) cancelBtn.style.display = '';
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
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (bar) bar.style.width = '100%';
      if (msg) msg.textContent = '✔ 下载完成';
      if (eta) eta.textContent = '';
      if (dlBtn) { dlBtn.disabled = false; dlBtn.innerHTML = `${icon('download', 14)} 下载模型`; }
      _loadModelMgmt();
    } else if (s.status === 'error') {
      if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (dlBtn) { dlBtn.disabled = false; dlBtn.innerHTML = `${icon('download', 14)} 重试下载`; }
      if (msg) msg.textContent = s.message || '下载失败';
    }
  } catch { /* ignore */ }
}

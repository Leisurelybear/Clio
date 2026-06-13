import { state } from './state.js';
import {
  $, $$,
  escapeHtml,
  parseTimecode,
  markDirty,
  updateSaveBtn,
  setStatus,
  updateSidebarDay,
  setDeep,
} from './utils.js';
import { api, icon } from './api.js';
import { playVideoSegment, startPreview, stopPreview } from './viewer.js';

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
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === state.currentTab));
  $$('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `tab-${state.currentTab}`));
  if (state.currentTab === 'texts') renderTexts();
  else if (state.currentTab === 'voiceover') renderVoiceover();
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
      p.currentTime = parseTimecode(seg.start);
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

function renderPlan() {
  const p = state.plan;
  const pane = $('tab-plan');
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
    <div style="display:flex;gap:6px;margin-bottom:8px;">
      ${state.previewActive
        ? `<button id="btn-stop-preview" class="btn-primary" style="flex:1">${icon('stop', 16)} 停止预览</button>
           <span class="hint" style="display:flex;align-items:center;color:var(--accent);font-weight:500;">${state.previewIndex + 1}/${(p.sequence || []).length}</span>`
        : `<button id="btn-start-preview" class="btn-primary" style="flex:1">${icon('play', 16)} 预览播放</button>`
      }
    </div>
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
  // Preview buttons
  const startBtn = $('btn-start-preview');
  if (startBtn) startBtn.onclick = startPreview;
  const stopBtn = $('btn-stop-preview');
  if (stopBtn) stopBtn.onclick = stopPreview;

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
      const seekTo = parseTimecode((seg.use_timeline || '').split('-')[0].trim()) + (v.offset_sec || 0);
      playVideoSegment(v.file, seekTo);
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
  try {
    if (state.currentEntity === 'run') {
      setStatus('当前视图不需要保存', 'warn');
      return;
    }
    if (state.currentEntity === 'config') {
      const r = await api('PUT', '/api/config/raw', state.configRaw);
      if (r.error) throw new Error(r.error);
      state.dirty = false;
      updateSaveBtn();
      setStatus('配置已保存（需重启服务生效）', 'ok');
      return;
    }
    if (state.currentEntity === 'plan') {
      const r = await api('PUT', `/api/plan?day=${state.currentDay}`, state.plan);
      if (!r.ok) throw new Error(r.error);
    } else {
      const tab = state.currentTab;
      const v = state.videos.find(x => x.file === state.currentVideo);
      if (tab === 'texts') {
        if (!v || !v.text_json) throw new Error('当前视频没有 texts JSON');
        const r = await api('PUT', `/api/texts?file=${encodeURIComponent(v.text_json)}`, state.texts);
        if (!r.ok) throw new Error(r.error);
      } else if (tab === 'voiceover') {
        if (!v || !v.script_json) throw new Error('当前视频没有 voiceover JSON');
        const r = await api('PUT', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`, state.voiceover);
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
    const isPwd = path.endsWith('api_key') || path.endsWith('api_key_env');
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
  ` : '') + `<div class="config-form">${_renderConfigForm(configData, '')}</div>`;
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
}

export {
  renderActiveTab,
  renderTexts,
  renderVoiceover,
  renderPlan,
  renderConfig,
  executeCut,
  save,
  initProjectConfig,
};

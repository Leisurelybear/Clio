const state = {
  config: null,
  configRaw: null,
  source: 'compressed',
  videos: [],
  currentEntity: 'video',  // 'video' | 'plan' | 'cut' | 'config'
  currentVideo: null,
  currentDay: 'day1',
  availablePlans: [],
  currentTab: 'texts',
  texts: null,
  voiceover: null,
  plan: null,
  dirty: false,
};

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function setStatus(msg, kind = '') {
  const el = $('status');
  el.textContent = msg || '';
  el.className = 'status ' + kind;
  if (msg) {
    const captured = msg;
    setTimeout(() => { if (el.textContent === captured) el.textContent = ''; }, 4000);
  }
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    const txt = await r.text();
    let detail = txt;
    try { detail = JSON.parse(txt).error || txt; } catch {}
    throw new Error(`HTTP ${r.status}: ${detail}`);
  }
  if (r.status === 204) return null;
  const ct = r.headers.get('Content-Type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

function fmtTime(sec) {
  if (!Number.isFinite(sec)) return '00:00';
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = Math.floor(sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function parseTimecode(s) {
  if (!s) return 0;
  const parts = String(s).split(':').map(parseFloat);
  if (parts.length === 3 && parts.every(Number.isFinite)) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2 && parts.every(Number.isFinite)) {
    return parts[0] * 60 + parts[1];
  }
  return parseFloat(s) || 0;
}

function getDeep(obj, path) {
  return String(path).split('.').reduce((o, k) => (o != null ? o[k] : undefined), obj);
}

function setDeep(obj, path, value) {
  const keys = String(path).split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!cur[keys[i]] || typeof cur[keys[i]] !== 'object') cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
}

function markDirty() { state.dirty = true; updateSaveBtn(); }

function updateSaveBtn() {
  const btn = $('btn-save');
  btn.classList.toggle('dirty', state.dirty);
  btn.textContent = state.dirty ? '保存 (有改动)' : '保存';
}

async function loadConfig() {
  state.config = await api('GET', '/api/config');
  $('proj-name').textContent = state.config.output_dir;
  $('proj-name').title = `input: ${state.config.input_dir}\noutput: ${state.config.output_dir}`;
}

async function loadPlans() {
  try {
    const r = await api('GET', '/api/plans');
    state.availablePlans = r.plans || [];
  } catch (e) {
    state.availablePlans = [];
  }
}

function updateSidebarDay() {
  const el = document.querySelector('.project-item[data-entity="plan"] .muted');
  if (el) el.textContent = state.currentDay;
  const badge = $('plan-badge');
  if (badge) badge.textContent = state.currentDay;
}

async function loadVideos() {
  const r = await api('GET', `/api/videos?source=${state.source}`);
  state.videos = r.videos;
  $('video-count').textContent = `(${state.videos.length})`;
  renderVideoList();
}

function renderVideoList() {
  const ul = $('video-list');
  ul.innerHTML = '';
  for (const v of state.videos) {
    const li = document.createElement('li');
    li.className = 'video-item';
    if (state.currentVideo === v.file) li.classList.add('active');
    if (!v.match) li.classList.add('no-match');
    const display = v.file.replace(/^\d+_/, '');
    const tCls = v.text_json ? 'has' : 'miss';
    const sCls = v.script_json ? 'has' : 'miss';
    const tLabel = v.text_json ? '✓ texts' : '· texts';
    const sLabel = v.script_json ? '✓ voiceover' : '· voiceover';
    const counterpartLabel = state.source === 'compressed' ? '原' : '压';
    const matchBadge = v.match
      ? `<span class="match-badge" title="${escapeHtml(v.match.file)}">→ ${counterpartLabel}: ${escapeHtml(v.match.file)}</span>`
      : `<span class="match-badge miss" title="没有对应的${state.source === 'compressed' ? '原视频' : '压缩视频'}">无对应</span>`;
    li.innerHTML = `
      <div class="video-name">${v.index ? '[' + v.index + '] ' : ''}${escapeHtml(display)} ${matchBadge}</div>
      <div class="video-meta">
        <span class="${tCls}">${tLabel}</span>
        &nbsp;
        <span class="${sCls}">${sLabel}</span>
      </div>
    `;
    li.onclick = () => selectVideo(v.file);
    ul.appendChild(li);
  }
}

async function selectVideo(file) {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换视频吗？')) return;
  }
  state.currentEntity = 'video';
  state.currentVideo = file;
  state.dirty = false;
  state.texts = null;
  state.voiceover = null;

  const v = state.videos.find(x => x.file === file);
  if (!v) return;

  const player = $('player');
  player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}`;
  $('player-name').textContent = file;

  if (v.text_json) {
    try {
      state.texts = await api('GET', `/api/texts?file=${encodeURIComponent(v.text_json)}`);
    } catch (e) { setStatus('texts 加载失败: ' + e.message, 'err'); }
  }
  if (v.script_json) {
    try {
      state.voiceover = await api('GET', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`);
    } catch (e) { setStatus('voiceover 加载失败: ' + e.message, 'err'); }
  }
  if (!state.plan) {
    try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
    catch (e) { /* plan 可选, 加载失败不报错 */ }
  }

  renderVideoList();
  renderActiveTab();
  updateEntityUI();
}

async function selectPlan(dayOverride) {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到规划吗？')) return;
  }
  state.currentEntity = 'plan';
  state.dirty = false;
  if (dayOverride) state.currentDay = dayOverride;
  if (!state.plan) {
    try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
    catch (e) { state.plan = null; }
  }
  updateSidebarDay();
  updateEntityUI();
  renderActiveTab();
}

async function selectConfig() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到设置吗？')) return;
  }
  state.currentEntity = 'config';
  state.dirty = false;
  try {
    state.configRaw = await api('GET', '/api/config/raw');
  } catch (e) {
    setStatus('配置加载失败: ' + e.message, 'err');
    state.configRaw = {};
  }
  updateEntityUI();
  renderActiveTab();
}

async function selectCut() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到裁剪吗？')) return;
  }
  state.currentEntity = 'cut';
  state.dirty = false;
  updateEntityUI();
  renderActiveTab();
}

function updateEntityUI() {
  const cls = state.currentEntity === 'plan' ? 'entity-plan'
    : state.currentEntity === 'cut' ? 'entity-cut'
    : state.currentEntity === 'config' ? 'entity-config'
    : 'entity-video';
  $('editor').className = cls;
  $$('.project-item').forEach(p => p.classList.remove('active'));
  if (state.currentEntity === 'plan') {
    document.querySelector('.project-item[data-entity="plan"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'cut') {
    document.querySelector('.project-item[data-entity="cut"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'config') {
    document.querySelector('.project-item[data-entity="config"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  }
}

function playVideoSegment(file, seekTo) {
  const player = $('player');
  const doSeek = () => { player.currentTime = seekTo; player.play().catch(() => {}); };
  $('player-name').textContent = file;
  if (player.src && player.src.includes(encodeURIComponent(file)) && player.readyState >= 1) {
    doSeek();
  } else {
    const onLoaded = () => { doSeek(); player.removeEventListener('loadedmetadata', onLoaded); };
    player.addEventListener('loadedmetadata', onLoaded);
    player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}`;
  }
}

async function setSource(source) {
  if (source === state.source) return;
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换源吗？')) return;
  }
  state.source = source;
  state.currentVideo = null;
  state.texts = null;
  state.voiceover = null;
  $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === source));
  try {
    await loadVideos();
    if (state.videos.length) {
      if (state.currentEntity === 'plan') {
        // stay in plan: don't auto-select a video, just clear the player
        $('player').removeAttribute('src');
        $('player-name').textContent = '请选择左侧视频或规划节点';
        // re-render plan so segment click handlers use the new source's v.file
        renderActiveTab();
        setStatus(`已切到 ${source} 视图（仍停留在规划）`, 'ok');
      } else {
        await selectVideo(state.videos[0].file);
      }
    } else {
      $('player').removeAttribute('src');
      $('player-name').textContent = '请选择左侧视频';
      setStatus(`当前视图没有视频 (${source})`, 'warn');
    }
  } catch (e) {
    setStatus('切换源失败: ' + e.message, 'err');
  }
}

function renderActiveTab() {
  if (state.currentEntity === 'plan') {
    renderPlan();
    return;
  }
  if (state.currentEntity === 'cut') {
    renderCut();
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
      <h3>日 vlog 规划</h3>
      <p class="muted">当前项目没有规划文件。</p>
      <p class="hint">请先通过 CLI 运行 <code>python main.py plan</code> 生成规划。</p>
    `;
    return;
  }
  pane.innerHTML = `
    <h3>日 vlog 元信息</h3>
    ${state.availablePlans.length >= 2 ? `
    <label>日标签
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
      if (state.dirty && !confirm('切换日标签将丢弃当前修改，确定吗？')) { daySelect.value = state.currentDay; return; }
      state.currentDay = day;
      state.plan = null;
      state.dirty = false;
      updateSidebarDay();
      await selectPlan();
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
    li.className = 'plan-seg';
    li.innerHTML = `
      <div class="seg-time">${escapeHtml(seg.use_timeline || '')} <span class="muted">视频 [${escapeHtml(seg.index || '?')}]</span></div>
      <div class="seg-title">${escapeHtml(seg.title || '')}</div>
      <label>理由 <input value="${escapeHtml(seg.reason || '')}" data-k="reason"></label>
      <label>口播提示 <textarea rows="2" data-k="voiceover_hint">${escapeHtml(seg.voiceover_hint || '')}</textarea></label>
    `;
    li.onclick = (e) => {
      if (e.target.matches('input, textarea')) return;
      const v = state.videos.find(x => x.index === seg.index);
      if (!v) { setStatus(`找不到视频 [${seg.index}]`, 'warn'); return; }
      const seekTo = parseTimecode((seg.use_timeline || '').split('-')[0].trim());
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
}

function renderCut() {
  const pane = $('tab-cut');
  const planHint = state.plan
    ? `基于规划: ${escapeHtml(state.currentDay)}`
    : `<span class="err">暂无规划，请先运行 CLI <code>python main.py plan</code></span>`;
  pane.innerHTML = `
    <h3>裁剪设置</h3>
    <p class="hint">${planHint}</p>
    <label>视频来源
      <select id="cut-source">
        <option value="compressed" selected>压缩版 (compressed)</option>
        <option value="original">原片 (original)</option>
      </select>
    </label>
    <label><input type="checkbox" id="cut-reencode"> 重新编码 (默认 -c copy 快速)</label>
    <label>输出目录 (留空则 output/cuts/&lt;day&gt;)
      <input id="cut-outdir" placeholder="例如 E:/剪辑素材/第一天"></label>
    <hr>
    <button id="btn-cut-exec" class="primary" ${state.plan ? '' : 'disabled'}>执行裁剪</button>
    <div id="cut-result" style="margin-top:12px"></div>
  `;
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
    const multiline = obj.length > 80 || obj.includes('\n');
    if (multiline) {
      return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}</span> <textarea data-path="${path}" rows="4">${escapeHtml(obj)}</textarea></label>`;
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
      html += _renderConfigForm(val, path ? `${path}.${key}` : key);
    }
    html += '</fieldset>';
    return html;
  }
  return `<span class="muted">${escapeHtml(String(obj))}</span>`;
}

function renderConfig() {
  const pane = $('tab-config');
  if (!state.configRaw || Object.keys(state.configRaw).length === 0) {
    pane.innerHTML = '<p class="muted">配置数据不可用</p>';
    return;
  }
  pane.innerHTML = `<div class="config-form">${_renderConfigForm(state.configRaw, '')}</div>`;
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

async function save() {
  if (!state.dirty) { setStatus('没有改动需要保存', 'warn'); return; }
  try {
  if (state.currentEntity === 'cut') {
    setStatus('裁剪不需要保存', 'warn');
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

async function init() {
  try {
    await loadConfig();
    await loadPlans();
    // 自动选择第一个可用 plan（如果有）
    if (state.availablePlans.length) {
      state.currentDay = state.availablePlans[0].day_label;
      updateSidebarDay();
      // 预加载 plan 数据
      try { state.plan = await api('GET', `/api/plan?day=${state.currentDay}`); }
      catch (e) { /* ignore */ }
    }
    await loadVideos();
    if (state.videos.length) {
      await selectVideo(state.videos[0].file);
    } else {
      setStatus('output_dir 下没有视频文件', 'warn');
    }
  } catch (e) {
    setStatus('初始化失败: ' + e.message, 'err');
  }

  $$('.source-toggle button').forEach(b => {
    b.onclick = () => setSource(b.dataset.source);
  });

  $$('.project-item').forEach(p => {
    p.onclick = () => {
      if (p.classList.contains('disabled')) {
        const name = p.querySelector('.name').textContent;
        setStatus(`「${name}」功能待对应 R-XXX 实现`, 'warn');
        return;
      }
      if (p.dataset.entity === 'plan') selectPlan();
      else if (p.dataset.entity === 'cut') selectCut();
      else if (p.dataset.entity === 'config') selectConfig();
    };
  });

  $('btn-reload').onclick = async () => {
    try {
      const cur = state.currentVideo;
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

  const player = $('player');
  player.ontimeupdate = () => {
    $('player-time').textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration)}`;
  };
  player.onloadedmetadata = () => {
    $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
  };
  player.onerror = () => setStatus('视频加载失败', 'err');

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); }
  });

  window.addEventListener('beforeunload', (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = '有未保存的修改'; }
  });
}

init();

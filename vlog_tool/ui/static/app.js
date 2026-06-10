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
  projectName: null,
  projects: [],
  currentProject: null,
  currentProjectName: null,
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
  // 自动附加 project 查询参数
  const sep = url.includes('?') ? '&' : '?';
  if (state.currentProjectName) {
    url += `${sep}project=${encodeURIComponent(state.currentProjectName)}`;
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

async function loadProjects() {
  try {
    const r = await api('GET', '/api/projects');
    state.projects = r.projects || [];
    state.currentProject = state.projects.find(p => p.is_current) || null;
    if (state.currentProject && !state.currentProjectName) {
      state.currentProjectName = state.currentProject.name;
    }
    updateProjectSidebar();
  } catch (e) {
    state.projects = [];
    state.currentProject = null;
    state.currentProjectName = null;
    updateProjectSidebar();
  }
}

function updateProjectSidebar() {
  const el = $('proj-name-sidebar');
  if (el) el.textContent = state.currentProject?.name || state.projectName || '未命名';
}

async function loadConfig() {
  state.config = await api('GET', '/api/config');
  $('proj-name').textContent = state.config.input_dir;
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
  const sel = $('plan-day-select-sidebar');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = state.availablePlans.map(p =>
    `<option value="${escapeHtml(p.day_label)}">${escapeHtml(p.day_label)}</option>`
  ).join('');
  sel.value = state.currentDay;
  sel.onchange = async () => {
    const day = sel.value;
    if (day === state.currentDay) return;
    if (state.dirty && !confirm('切换分集将丢弃当前修改，确定吗？')) { sel.value = state.currentDay; return; }
    state.currentDay = day;
    state.plan = null;  // 总是清空，保证下次点 plan tab 时重新拉取
    state.dirty = false;
    saveProject();
    if (state.currentEntity === 'plan') {
      await selectPlan();
    }
  };
}

async function loadVideos() {
  const r = await api('GET', `/api/videos?source=${state.source}`);
  state.videos = r.videos;
  $('video-count').textContent = `(${state.videos.length})`;
  renderVideoList();
}

async function loadProject() {
  try {
    const proj = await api('GET', '/api/project');
    if (proj.currentDay) state.currentDay = proj.currentDay;
    if (proj.source && proj.source !== state.source) {
      state.source = proj.source;
      $$('.source-toggle button').forEach(b => b.classList.toggle('active', b.dataset.source === state.source));
    }
    state.steps = proj.steps || {};
    state.projectName = proj.name || '';
    if (proj.lastEntity && ['video', 'plan', 'cut', 'config'].includes(proj.lastEntity)) {
      state.lastEntity = proj.lastEntity;
    }
    if (proj.lastVideo) state.lastVideo = proj.lastVideo;
  } catch (e) { /* 非关键, 静默忽略 */ }
}

function renderSteps() {
  const ul = $('step-list');
  if (!ul) return;
  const labels = { compress: '压缩', analyze: '分析', scripts: '口播', plan: '规划', label: '标号', cut: '裁剪' };
  ul.innerHTML = '';
  for (const [key, label] of Object.entries(labels)) {
    const done = state.steps[key];
    const li = document.createElement('li');
    li.className = 'step-item' + (done ? ' done' : '');
    li.innerHTML = `<span class="step-icon">${done ? '✓' : '○'}</span><span class="step-label">${label}</span>`;
    ul.appendChild(li);
  }
}

async function saveProject(extra) {
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

function renderVideoList() {
  const ul = $('video-list');
  ul.innerHTML = '';
  if (!state.videos.length) {
    ul.innerHTML = `
      <li class="empty-state">
        <span class="icon">📁</span>
        <h4>暂无视频素材</h4>
        <p>请将视频文件（.mp4/.mov/.mkv等）放入素材目录</p>
        <p class="hint">素材目录: ${state.config?.input_dir || '未知'}</p>
      </li>
    `;
    return;
  }
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
      <div class="video-actions">
        <button class="menu-btn" title="操作">⋮</button>
        <div class="menu-dropdown">
          <button class="menu-item" data-action="texts">重跑 texts</button>
          <button class="menu-item" data-action="voiceover">重跑 voiceover</button>
          <button class="menu-item" data-action="all">重跑全部</button>
        </div>
      </div>
    `;
    li.onclick = (e) => {
      if (e.target.closest('.video-actions')) return;
      selectVideo(v.file);
    };
    // ── Dot-menu toggle ──
    const menuBtn = li.querySelector('.menu-btn');
    const dropdown = li.querySelector('.menu-dropdown');
    menuBtn.onclick = (e) => {
      e.stopPropagation();
      // close all other dropdowns first
      document.querySelectorAll('.menu-dropdown.open').forEach(d => { if (d !== dropdown) d.classList.remove('open'); });
      dropdown.classList.toggle('open');
    };
    // close on click outside
    document.addEventListener('click', () => dropdown.classList.remove('open'), { once: true });
    // ── Menu item click ──
    dropdown.querySelectorAll('.menu-item').forEach(item => {
      item.onclick = async (e) => {
        e.stopPropagation();
        dropdown.classList.remove('open');
        const task = item.dataset.action;
        const file = v.file;
        setStatus(`正在重跑 ${task} (${file})...`, 'ok');
        try {
          const r = await api('POST', '/api/rerun', {
            video: file,
            task: task,
            source: state.source,
          });
          if (r.ok) {
            setStatus(r.message || `${task} 已启动`, 'ok');
          } else {
            throw new Error(r.error || '重跑失败');
          }
        } catch (e) {
          setStatus('重跑失败: ' + e.message, 'err');
        }
      };
    });
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
  const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
  player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${projParam}`;
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

async function selectRun() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到运行吗？')) return;
  }
  state.currentEntity = 'run';
  state.dirty = false;
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
    const resp = await api('GET', '/api/config/raw');
    if (resp.needs_init) {
      state.configRaw = null;
      state._needsConfigInit = true;
    } else {
      state.configRaw = resp;
      state._needsConfigInit = false;
    }
  } catch (e) {
    setStatus('配置加载失败: ' + e.message, 'err');
    state.configRaw = {};
    state._needsConfigInit = false;
  }
  updateEntityUI();
  renderActiveTab();
}

async function initProjectConfig() {
  try {
    const btn = $('btn-config-init');
    if (btn) { btn.disabled = true; btn.textContent = '创建中...'; }
    const r = await api('POST', '/api/config/init');
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
    : state.currentEntity === 'run' ? 'entity-run'
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
  } else if (state.currentEntity === 'run') {
    document.querySelector('.project-item[data-entity="run"]').classList.add('active');
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
    const projParam = state.currentProjectName ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
    player.src = `/api/video?file=${encodeURIComponent(file)}&source=${state.source}${projParam}`;
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
  saveProject();  // 持久化 source 选择
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
  if (state.currentEntity === 'run') {
    renderRun();
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
      saveProject();
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
      <span class="input-with-browse"><input id="cut-outdir" placeholder="例如 E:/剪辑素材/第一天"><button class="browse-btn" data-target="cut-outdir" type="button">浏览</button></span></label>
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
      state.steps.cut = true;
      renderSteps();
      saveProject();
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

/* ── Directory browser ── */
let _browseResolve = null;  // callback(path) when user selects

function openBrowseDir(targetInputId) {
  const modal = $('modal-browse-dir');
  if (!modal) return;
  _browseResolve = (path) => {
    const inp = document.getElementById(targetInputId);
    if (inp) inp.value = path;
  };
  modal.style.display = 'flex';
  loadBrowseDir('');
}

async function loadBrowseDir(path) {
  const pathEl = $('browse-path');
  const listEl = $('browse-dir-list');
  const upBtn = $('browse-up');
  const selectBtn = $('browse-select');
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  upBtn.style.display = 'none';
  selectBtn.disabled = true;
  try {
    const r = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(path)}`);
    if (r.error) { pathEl.textContent = '错误: ' + r.error; return; }
    pathEl.textContent = r.path || '(选择驱动器)';
    selectBtn.disabled = r.is_drive_list;
    if (r.is_drive_list) {
      upBtn.style.display = 'none';
    } else {
      upBtn.style.display = '';
      upBtn.onclick = () => loadBrowseDir(r.parent || '');
    }
    if (r.is_drive_list) {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${d}">📁 ${d}</div>`
      ).join('');
    } else {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${d}">📁 ${d.replace(/^.*[\\/]/, '')}</div>`
      ).join('');
    }
    // click to navigate
    listEl.querySelectorAll('.browse-item').forEach(el => {
      el.onclick = () => {
        loadBrowseDir(el.dataset.path);
      };
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}
let _runPollTimer = null;
let _lastRunDay = 'day1';

const RUN_STEPS = [
  { key: 'analyze', label: '压缩 + AI 分析', hint: '将原片压缩为 640p，提交 Gemini 分析' },
  { key: 'voiceover', label: '生成口播文案', hint: '基于分析结果生成每段的口播脚本' },
  { key: 'plan', label: '日 vlog 规划', hint: '根据所有素材生成剪辑顺序和时间轴' },
  { key: 'label', label: '烧录序号', hint: '在压缩视频左上角标上序号便于剪映对照' },
];

function renderRun() {
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
    <button id="btn-run-start" class="primary">▶ 运行选中步骤</button>
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
  _lastRunDay = $('run-day').value.trim() || state.currentDay;
  if (_runPollTimer) clearInterval(_runPollTimer);
  btn.disabled = true;
  btn.textContent = '启动中...';
  try {
    const r = await api('POST', '/api/run/start', {
      day_label: _lastRunDay,
      steps: checked,
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
    btn.textContent = '▶ 运行选中步骤';
  }
}

async function pollRunStatus() {
  const prog = $('run-progress');
  const btn = $('btn-run-start');
  if (!prog) return;  // not on run tab
  try {
    const s = await api('GET', '/api/run/status');
    if (s.status === 'idle' || s.status === 'unknown') {
      if (btn) { btn.disabled = false; btn.textContent = '▶ 运行选中步骤'; }
      if (!s.running) {
        prog.innerHTML = '<p class="muted">尚未运行</p>';
      }
      return;
    }
    if (s.running) {
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
    } else if (s.status === 'done') {
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.textContent = '▶ 运行选中步骤'; }
      prog.innerHTML = `<p class="ok">✓ 流水线完成</p><p>${escapeHtml(s.message || '')}</p>`;
      setStatus('流水线完成', 'ok');
      state.currentDay = _lastRunDay;
      state.plan = null;
      await loadPlans();
      updateSidebarDay();
      renderSteps();
      saveProject();
      try { state.plan = await api('GET', `/api/plan?day=${_lastRunDay}`); } catch {}
      await loadVideos();
      if (state.currentEntity === 'plan') selectPlan();
    } else if (s.status === 'error') {
      _stopRunPoll();
      if (btn) { btn.disabled = false; btn.textContent = '▶ 运行选中步骤'; }
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
  if (state._needsConfigInit) {
    pane.innerHTML = `
      <h3>项目配置初始化</h3>
      <p class="muted">该项目还没有专属配置文件。</p>
      <p class="hint">创建后将以当前全局配置为模板，后续修改只影响本项目。</p>
      <button id="btn-config-init" class="primary" style="margin-top:12px;padding:10px 20px;width:100%;">为该项目创建配置文件</button>
    `;
    const btn = $('btn-config-init');
    if (btn) btn.onclick = initProjectConfig;
    return;
  }
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
  if (state.currentEntity === 'cut' || state.currentEntity === 'run') {
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

async function init() {
  // 从 URL 读取 project 参数
  const urlParams = new URLSearchParams(window.location.search);
  const urlProject = urlParams.get('project');
  if (urlProject) {
    state.currentProjectName = urlProject;
  }

  try {
    await loadProjects();
    // 如果 URL 指定了项目，但当前不是该项目，需要重载
    if (urlProject && (!state.currentProject || state.currentProject.name !== urlProject)) {
      state.currentProjectName = urlProject;
    }
    await loadConfig();
    await loadProject();
    renderSteps();
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
      else if (p.dataset.entity === 'cut') selectCut();
      else if (p.dataset.entity === 'run') selectRun();
      else if (p.dataset.entity === 'config') selectConfig();
    };
  });

  // Browse buttons
  document.querySelectorAll('.browse-btn').forEach(btn => {
    btn.onclick = () => openBrowseDir(btn.dataset.target);
  });
  const browseSelect = $('browse-select');
  if (browseSelect) {
    browseSelect.onclick = () => {
      const pathEl = $('browse-path');
      if (!pathEl || !_browseResolve) return;
      _browseResolve(pathEl.textContent);
      _browseResolve = null;
      $('modal-browse-dir').style.display = 'none';
    };
  }
  const browseCancel = $('browse-cancel');
  if (browseCancel) {
    browseCancel.onclick = () => {
      _browseResolve = null;
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
    if (backdrop) backdrop.onclick = () => { _browseResolve = null; browseModal.style.display = 'none'; };
  }
}

init();

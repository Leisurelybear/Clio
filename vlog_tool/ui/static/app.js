const state = {
  config: null,
  source: 'compressed',
  videos: [],
  currentEntity: 'video',  // 'video' | 'plan'
  currentVideo: null,
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
    try { state.plan = await api('GET', '/api/plan?day=day1'); }
    catch (e) { /* plan 可选, 加载失败不报错 */ }
  }

  renderVideoList();
  renderActiveTab();
  updateEntityUI();
}

async function selectPlan() {
  if (state.dirty) {
    if (!confirm('当前 tab 有未保存的修改，确定切换到规划吗？')) return;
  }
  state.currentEntity = 'plan';
  state.dirty = false;
  if (!state.plan) {
    try { state.plan = await api('GET', '/api/plan?day=day1'); }
    catch (e) { state.plan = null; }
  }
  updateEntityUI();
  renderActiveTab();
}

function updateEntityUI() {
  $('editor').className = state.currentEntity === 'plan' ? 'entity-plan' : 'entity-video';
  $$('.project-item').forEach(p => p.classList.remove('active'));
  if (state.currentEntity === 'plan') {
    document.querySelector('.project-item[data-entity="plan"]').classList.add('active');
    // plan mode: no video is "selected" (the player is independent)
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
    pane.innerHTML = '<p class="muted">没有找到 day1_plan.json</p>';
    return;
  }
  pane.innerHTML = `
    <h3>日 vlog 元信息</h3>
    <label>主题 <input data-field="theme"></label>
    <label>开场提示 <textarea data-field="opening_tip" rows="2"></textarea></label>
    <label>收尾提示 <textarea data-field="ending_tip" rows="2"></textarea></label>
    <h3>顺序 (sequence) — ${(p.sequence || []).length} 项</h3>
    <p class="hint">点击 segment 跳到对应视频</p>
    <ol id="plan-list"></ol>
  `;
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

async function save() {
  if (!state.dirty) { setStatus('没有改动需要保存', 'warn'); return; }
  try {
    if (state.currentEntity === 'plan') {
      const r = await api('PUT', '/api/plan?day=day1', state.plan);
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

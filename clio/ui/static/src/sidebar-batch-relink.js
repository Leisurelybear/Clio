import { $, escapeHtml, setStatus } from './utils.js';
import { api } from './api.js';
import { addToast } from './toast.js';
import { matchBatchRelink } from './offline-media.js';
import { state } from './state.js';

let _path = '';
let _pendingMatches = [];
let _inited = false;

export function openBatchRelinkModal() {
  _ensureInit();
  const modal = $('modal-batch-relink');
  if (!modal) return;
  _pendingMatches = [];
  const result = $('br-result');
  if (result) result.innerHTML = '';
  const apply = $('br-apply');
  if (apply) apply.disabled = true;
  modal.style.display = 'flex';
  _loadDir('');
}

export function closeBatchRelinkModal() {
  const modal = $('modal-batch-relink');
  if (modal) modal.style.display = 'none';
  _pendingMatches = [];
  _path = '';
}

async function _loadDir(path) {
  _path = path || '';
  const pathEl = $('br-path');
  const listEl = $('br-list');
  const upBtn = $('br-up');
  const scanBtn = $('br-scan');
  if (!pathEl || !listEl) return;
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  if (upBtn) upBtn.style.display = 'none';
  if (scanBtn) scanBtn.disabled = true;
  try {
    const dirsRes = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(_path)}`);
    if (dirsRes.error) {
      pathEl.textContent = '错误: ' + dirsRes.error;
      return;
    }
    pathEl.textContent = dirsRes.path || '(请选择目录)';
    if (dirsRes.parent && !dirsRes.is_drive_list && upBtn) {
      upBtn.style.display = '';
      upBtn.onclick = () => _loadDir(dirsRes.parent || '');
    }
    if (scanBtn) scanBtn.disabled = !!dirsRes.is_drive_list;

    let html = '';
    if (dirsRes.is_drive_list) {
      html = (dirsRes.dirs || []).map(d =>
        `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d)}</div>`
      ).join('');
    } else {
      html = (dirsRes.dirs || []).map(d =>
        `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d.replace(/^.*[\\/]/, ''))}</div>`
      ).join('');
      if (!(dirsRes.dirs || []).length) {
        html = '<p class="muted">此目录无子文件夹（仍可扫描本层视频）</p>';
      }
    }
    listEl.innerHTML = html;
    listEl.querySelectorAll('.browse-item[data-path]').forEach(el => {
      el.onclick = () => _loadDir(el.dataset.path);
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

async function _scanAndMatch() {
  const result = $('br-result');
  const apply = $('br-apply');
  const scanBtn = $('br-scan');
  if (!result || !_path) return;
  if (scanBtn) {
    scanBtn.disabled = true;
    scanBtn.textContent = '扫描中...';
  }
  result.innerHTML = '<p class="muted">正在扫描视频并匹配…</p>';
  try {
    const videosRes = await api('GET', `/api/fs/videos?path=${encodeURIComponent(_path)}`);
    const candidates = (videosRes.files || []).map(f => ({
      path: f.path,
      name: f.name || f.path,
    }));
    const offline = (state.videos || [])
      .filter(v => v.missing)
      .map(v => ({
        file: v.file,
        abs_path: v.abs_path || v.match?.abs_path || null,
      }));
    const match = matchBatchRelink(offline, candidates);
    _pendingMatches = match.matched;
    if (apply) apply.disabled = match.matched.length === 0;

    let html = `<p><strong>匹配 ${match.matched.length}</strong> · 未匹配 ${match.unmatched.length}`;
    if (match.ambiguous.length) html += ` · 歧义 ${match.ambiguous.length}`;
    html += ` · 候选 ${candidates.length}</p>`;
    if (match.matched.length) {
      html += '<ul class="br-match-list">' + match.matched.map(m =>
        `<li><code>${escapeHtml(m.file)}</code><br><span class="muted">${escapeHtml(m.old_path)} → ${escapeHtml(m.new_path)}</span></li>`
      ).join('') + '</ul>';
    }
    if (match.ambiguous.length) {
      html += '<p class="warn">以下文件名在目录中出现多次，已跳过：' +
        match.ambiguous.map(a => escapeHtml(a.basename)).join(', ') + '</p>';
    }
    if (!match.matched.length) {
      html += '<p class="muted">没有可应用的匹配。确认目录中包含与离线视频同名的文件。</p>';
    }
    result.innerHTML = html;
  } catch (e) {
    result.innerHTML = `<p class="err">扫描失败: ${escapeHtml(e.message)}</p>`;
    _pendingMatches = [];
    if (apply) apply.disabled = true;
  } finally {
    if (scanBtn) {
      scanBtn.disabled = false;
      scanBtn.textContent = '扫描此目录并匹配';
    }
  }
}

async function _applyMatches() {
  if (!_pendingMatches.length) return;
  const apply = $('br-apply');
  if (apply?.disabled) return;
  if (apply) {
    apply.disabled = true;
    apply.textContent = '应用中...';
  }
  let ok = 0;
  let fail = 0;
  for (const m of _pendingMatches) {
    try {
      const r = await api('PUT', '/api/videos/relink', {
        old_path: m.old_path,
        new_path: m.new_path,
      });
      if (r.ok) ok++;
      else fail++;
    } catch {
      fail++;
    }
  }
  const msg = `批量关联完成：成功 ${ok}` + (fail ? `，失败 ${fail}` : '');
  setStatus(msg, fail ? 'warn' : 'ok');
  addToast(msg, fail ? 'warning' : 'success', 6000);
  if (apply) {
    apply.textContent = '应用匹配';
    apply.disabled = true;
  }
  closeBatchRelinkModal();
  const { loadVideos } = await import('./sidebar-data.js');
  await loadVideos();
}

function _ensureInit() {
  if (_inited) return;
  if (!$('modal-batch-relink')) return;
  _inited = true;
  $('br-cancel')?.addEventListener('click', closeBatchRelinkModal);
  $('br-scan')?.addEventListener('click', () => { _scanAndMatch(); });
  $('br-apply')?.addEventListener('click', () => { _applyMatches(); });
  $('modal-batch-relink')?.querySelector('.modal-backdrop')?.addEventListener('click', (e) => e.stopPropagation());
}

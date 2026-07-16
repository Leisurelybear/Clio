import { $, escapeHtml, setStatus } from './utils.js';
import { api } from './api.js';
import { addToast } from './toast.js';

let _oldPath = '';
let _browsePath = '';
let _inited = false;

function _parentDir(path) {
  const s = String(path || '').replace(/[/\\]+$/, '');
  if (!s) return '';
  const idx = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
  if (idx <= 0) return '';
  // Keep drive root like "D:"
  if (/^[a-zA-Z]:$/.test(s.slice(0, idx))) return s.slice(0, idx + 1);
  return s.slice(0, idx);
}

export function openRelinkModal({ oldPath, displayName } = {}) {
  _ensureInit();
  const modal = $('modal-relink');
  if (!modal) return;
  _oldPath = oldPath || displayName || '';
  const oldEl = $('relink-old-path');
  const input = $('relink-new-path');
  const hint = $('relink-hint');
  if (oldEl) oldEl.textContent = _oldPath || '(未知)';
  if (input) input.value = _oldPath || '';
  if (hint) {
    const name = displayName || (_oldPath.replace(/^.*[\\/]/, '') || '视频');
    hint.textContent = `「${name}」当前离线。可直接粘贴/输入新路径，或点「浏览」选择文件。`;
  }
  const panel = $('relink-browse-panel');
  if (panel) panel.style.display = 'none';
  const toggle = $('relink-toggle-browse');
  if (toggle) toggle.textContent = '浏览';
  modal.style.display = 'flex';
  setTimeout(() => {
    input?.focus();
    input?.select();
  }, 0);
}

export function closeRelinkModal() {
  const modal = $('modal-relink');
  if (modal) modal.style.display = 'none';
  _oldPath = '';
  _browsePath = '';
}

async function _submitRelink() {
  const input = $('relink-new-path');
  const newPath = (input?.value || '').trim();
  if (!newPath) {
    setStatus('请输入或选择新路径', 'warn');
    addToast('请输入或选择新路径', 'warning');
    return;
  }
  if (newPath === _oldPath) {
    setStatus('新路径与原路径相同，无需关联', 'warn');
    return;
  }
  const btn = $('relink-confirm');
  if (btn?.disabled) return;
  if (btn) {
    btn.disabled = true;
    btn.textContent = '关联中...';
  }
  try {
    const r = await api('PUT', '/api/videos/relink', {
      old_path: _oldPath,
      new_path: newPath,
    });
    if (r.ok) {
      const msg = `已重新关联: ${newPath}`;
      setStatus(msg, 'ok');
      addToast(msg, 'success');
      closeRelinkModal();
      const { loadVideos } = await import('./sidebar-data.js');
      await loadVideos();
    } else {
      const msg = '重新关联失败: ' + (r.error || '未知错误');
      setStatus(msg, 'err');
      addToast(msg, 'error', 6000);
    }
  } catch (e) {
    const msg = '重新关联失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '确认关联';
    }
  }
}

function _toggleBrowse() {
  const panel = $('relink-browse-panel');
  const toggle = $('relink-toggle-browse');
  if (!panel) return;
  const opening = panel.style.display === 'none' || !panel.style.display;
  if (opening) {
    panel.style.display = '';
    if (toggle) toggle.textContent = '收起浏览';
    const start = _parentDir(_oldPath);
    _loadBrowse(start);
  } else {
    panel.style.display = 'none';
    if (toggle) toggle.textContent = '浏览';
  }
}

async function _loadBrowse(path) {
  _browsePath = path || '';
  const pathEl = $('relink-browse-path');
  const listEl = $('relink-browse-list');
  const upBtn = $('relink-browse-up');
  if (!pathEl || !listEl) return;
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  if (upBtn) upBtn.style.display = 'none';
  try {
    const dirsRes = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(_browsePath)}`);
    if (dirsRes.error) {
      pathEl.textContent = '错误: ' + dirsRes.error;
      return;
    }
    pathEl.textContent = dirsRes.path || '(请选择目录)';
    if (dirsRes.parent && !dirsRes.is_drive_list && upBtn) {
      upBtn.style.display = '';
      upBtn.onclick = () => _loadBrowse(dirsRes.parent || '');
    }

    let videosRes = { files: [] };
    if (_browsePath && !dirsRes.is_drive_list) {
      videosRes = await api('GET', `/api/fs/videos?path=${encodeURIComponent(_browsePath)}`);
    }

    let html = '';
    if (dirsRes.is_drive_list) {
      html = (dirsRes.dirs || []).map(d =>
        `<div class="browse-item" data-kind="dir" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d)}</div>`
      ).join('');
    } else {
      html = (dirsRes.dirs || []).map(d =>
        `<div class="browse-item" data-kind="dir" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d.replace(/^.*[\\/]/, ''))}</div>`
      ).join('');
      html += (videosRes.files || []).map(f => {
        const name = (f.name || f.path || '').replace(/^.*[\\/]/, '');
        const sizeStr = f.size > 1024 * 1024 * 1024
          ? (f.size / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
          : (f.size / (1024 * 1024)).toFixed(1) + ' MB';
        return `<div class="browse-item video-file" data-kind="file" data-path="${escapeHtml(f.path)}" title="点击选中此文件">
          🎬 ${escapeHtml(name)}
          <span class="file-size">${sizeStr}</span>
        </div>`;
      }).join('');
      if (!(dirsRes.dirs || []).length && !(videosRes.files || []).length) {
        html = '<p class="muted">此目录无子文件夹或视频文件</p>';
      }
    }
    listEl.innerHTML = html;
    listEl.querySelectorAll('.browse-item[data-path]').forEach(el => {
      el.onclick = () => {
        const kind = el.dataset.kind;
        const p = el.dataset.path;
        if (kind === 'dir') {
          _loadBrowse(p);
        } else if (kind === 'file') {
          const input = $('relink-new-path');
          if (input) input.value = p;
          listEl.querySelectorAll('.browse-item.video-file').forEach(x => x.classList.remove('selected'));
          el.classList.add('selected');
          setStatus(`已选择: ${p}`, 'ok');
          input?.focus();
        }
      };
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

function _ensureInit() {
  if (_inited) return;
  const modal = $('modal-relink');
  if (!modal) return;
  _inited = true;
  $('relink-cancel')?.addEventListener('click', closeRelinkModal);
  $('relink-confirm')?.addEventListener('click', () => { _submitRelink(); });
  $('relink-toggle-browse')?.addEventListener('click', _toggleBrowse);
  const input = $('relink-new-path');
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        _submitRelink();
      }
    });
  }
  // backdrop does not close (same as video manager)
  modal.querySelector('.modal-backdrop')?.addEventListener('click', (e) => {
    e.stopPropagation();
  });
}

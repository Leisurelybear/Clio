import { $, escapeHtml, setStatus } from './utils.js';
import { api } from './api.js';
import { loadVideos } from './sidebar-data.js';
import { addToast } from './toast.js';

let _currentPath = '';
let _selectedFiles = new Set();
let _allVideoFiles = [];

export function openVideoManager() {
  const modal = $('modal-video-manage');
  if (!modal) return;
  _selectedFiles.clear();
  _allVideoFiles = [];
  modal.style.display = 'flex';
  _vmLoadDir('');
}

export function closeVideoManager() {
  const modal = $('modal-video-manage');
  if (!modal) return;
  modal.style.display = 'none';
  _selectedFiles.clear();
  _allVideoFiles = [];
}

function _vmUpdateSelectedCount() {
  const el = $('vm-selected-count');
  if (el) el.textContent = `已选 ${_selectedFiles.size} 个文件`;
  const addBtn = $('vm-add');
  if (addBtn) addBtn.disabled = _selectedFiles.size === 0;
}

async function _vmLoadDir(path) {
  const pathEl = $('vm-path');
  const listEl = $('vm-list');
  const upBtn = $('vm-up');
  const addBtn = $('vm-add');
  const selectAllBtn = $('vm-select-all');
  _currentPath = path;
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  upBtn.style.display = 'none';
  addBtn.disabled = true;
  _allVideoFiles = [];
  _selectedFiles.clear();
  _vmUpdateSelectedCount();
  try {
    const dirsRes = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(path)}`);
    if (dirsRes.error) { pathEl.textContent = '错误: ' + dirsRes.error; return; }
    pathEl.textContent = dirsRes.path || '(请选择目录)';

    let videosRes = { files: [] };
    if (path) {
      videosRes = await api('GET', `/api/fs/videos?path=${encodeURIComponent(path)}`);
    }

    if (dirsRes.parent && !dirsRes.is_drive_list) {
      upBtn.style.display = '';
      upBtn.onclick = () => _vmLoadDir(dirsRes.parent || '');
    } else {
      upBtn.style.display = 'none';
    }

    const isDriveList = dirsRes.is_drive_list;
    let html = '';
    if (isDriveList) {
      html = (dirsRes.dirs || []).map(d =>
        `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d)}</div>`
      ).join('');
      selectAllBtn.style.display = 'none';
    } else {
      selectAllBtn.style.display = '';
      _allVideoFiles = (videosRes.files || []).slice();
      selectAllBtn.textContent = '全选';
      selectAllBtn.onclick = () => {
        const allSelected = _allVideoFiles.length > 0 && _selectedFiles.size === _allVideoFiles.length;
        if (allSelected) {
          _selectedFiles.clear();
          selectAllBtn.textContent = '全选';
        } else {
          _allVideoFiles.forEach(f => _selectedFiles.add(f.path));
          selectAllBtn.textContent = '取消全选';
        }
        _vmRenderEntries(listEl, dirsRes.dirs || [], videosRes.files || []);
        _vmUpdateSelectedCount();
      };
      html = _buildListHtml(dirsRes.dirs || [], videosRes.files || []);
    }

    listEl.innerHTML = html;
    _bindListEvents(listEl);
    _vmUpdateSelectedCount();
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

function _buildListHtml(dirs, files) {
  const dirItems = dirs.map(d =>
    `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d.replace(/^.*[\\/]/, ''))}</div>`
  ).join('');
  const fileItems = files.map(f => {
    const checked = _selectedFiles.has(f.path) ? 'checked' : '';
    const sizeStr = f.size > 1024 * 1024 * 1024
      ? (f.size / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
      : (f.size / (1024 * 1024)).toFixed(1) + ' MB';
    const name = f.name.replace(/^.*[\\/]/, '');
    return `<label class="browse-item video-file">
      <input type="checkbox" class="vm-file-cb" data-path="${escapeHtml(f.path)}" ${checked}>
      <span>🎬 ${escapeHtml(name)}</span>
      <span class="file-size">${sizeStr}</span>
    </label>`;
  }).join('');
  return dirItems + fileItems;
}

function _vmRenderEntries(listEl, dirs, files) {
  listEl.innerHTML = _buildListHtml(dirs, files);
  _bindListEvents(listEl);
}

function _bindListEvents(listEl) {
  listEl.querySelectorAll('.browse-item[data-path]').forEach(el => {
    el.onclick = (e) => {
      if (e.target.closest('.video-file')) return;
      _vmLoadDir(el.dataset.path);
    };
  });
  listEl.querySelectorAll('.vm-file-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        _selectedFiles.add(cb.dataset.path);
      } else {
        _selectedFiles.delete(cb.dataset.path);
      }
      _vmUpdateSelectedCount();
    });
  });
}

async function _vmAddSelected() {
  if (_selectedFiles.size === 0) return;
  const addBtn = $('vm-add');
  addBtn.disabled = true;
  addBtn.textContent = '保存中...';
  try {
    const current = await api('GET', '/api/videos/selected');
    const existing = new Set((current.videos || []).map(p => p.replace(/\\/g, '/')));
    const newVideos = [..._selectedFiles].map(p => p.replace(/\\/g, '/'));
    newVideos.forEach(p => existing.add(p));
    const merged = [...existing];
    const r = await api('PUT', '/api/videos/selected', { videos: merged });
    if (r && r.rejected_count) {
      const msg = `已添加，但有 ${r.rejected_count} 个路径被拒绝（扩展名无效或无法解析）`;
      setStatus(msg, 'warn');
      addToast(msg, 'warning', 6000);
    } else {
      const msg = `已添加 ${newVideos.length} 个视频`;
      setStatus(msg, 'ok');
      addToast(msg, 'success');
    }
    closeVideoManager();
    await loadVideos();
  } catch (e) {
    const msg = '添加视频失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  } finally {
    addBtn.disabled = false;
    addBtn.textContent = '添加选中';
  }
}

const _VIDEO_EXTS_DND = new Set(['.mp4', '.mov', '.mkv', '.mts', '.m2ts', '.avi', '.wmv', '.flv', '.webm', '.3gp', '.mpg', '.mpeg']);

function _vmDropNames(dt) {
  const names = [];
  // Try items first (more reliable across browsers)
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      if (item.kind !== 'file') continue;
      const f = item.getAsFile();
      if (!f || !f.name) continue;
      const dot = f.name.lastIndexOf('.');
      if (dot > 0 && _VIDEO_EXTS_DND.has(f.name.slice(dot).toLowerCase())) {
        names.push(f.name);
      }
    }
    return names;
  }
  // Fallback to dt.files
  const files = dt.files;
  if (files) {
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      if (!f || !f.name) continue;
      const dot = f.name.lastIndexOf('.');
      if (dot > 0 && _VIDEO_EXTS_DND.has(f.name.slice(dot).toLowerCase())) {
        names.push(f.name);
      }
    }
  }
  return names;
}

function _vmDropAbsolutePaths(dt) {
  const paths = [];
  // Chrome/Edge on Windows: file.path gives full path
  const files = dt.files;
  if (files) {
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      if (f && f.path && typeof f.path === 'string') {
        paths.push(f.path);
      }
    }
  }
  // URI list fallback
  try {
    const uris = dt.getData('text/uri-list');
    if (uris) {
      for (const line of uris.split('\n')) {
        const uri = line.trim();
        if (uri.startsWith('file:///')) {
          let p = decodeURIComponent(uri.slice(8));
          if (p.match(/^[a-zA-Z]:/)) p = p[0].toUpperCase() + p.slice(1);
          paths.push(p);
        }
      }
    }
  } catch {}
  return paths;
}

function _vmInitDragDrop() {
  const listEl = $('vm-list');
  if (!listEl) return;
  listEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    listEl.classList.add('drop-zone-active');
  });
  listEl.addEventListener('dragleave', () => {
    listEl.classList.remove('drop-zone-active');
  });
  listEl.addEventListener('drop', (e) => {
    e.preventDefault();
    listEl.classList.remove('drop-zone-active');
    try {
      const dt = e.dataTransfer;
      if (!dt) return;
      // Strategy 1: absolute paths (Chrome/Edge Windows)
      const absPaths = _vmDropAbsolutePaths(dt);
      if (absPaths.length > 0) {
        let added = 0;
        let ignored = 0;
        for (const p of absPaths) {
          const base = p.replace(/^.*[\\/]/, '');
          const dot = base.lastIndexOf('.');
          const ext = dot > 0 ? base.slice(dot).toLowerCase() : '';
          if (!_VIDEO_EXTS_DND.has(ext)) {
            ignored++;
            continue;
          }
          if (!_selectedFiles.has(p)) { _selectedFiles.add(p); added++; }
        }
        if (added > 0) {
          _vmRenderEntries($('vm-list'), [...document.querySelectorAll('#vm-list .browse-item[data-path]')].map(el => el.dataset.path), [..._allVideoFiles]);
          _vmUpdateSelectedCount();
        }
        if (ignored > 0) {
          addToast(`已忽略 ${ignored} 个非视频文件`, 'warning');
        }
        if (added === 0 && ignored === 0) {
          addToast('没有可添加的视频路径', 'info');
        }
        return;
      }
      // Strategy 2: match filenames against current directory listing
      if (_allVideoFiles.length === 0) {
        addToast('无法解析拖入路径，请切换到含视频的目录后勾选添加', 'warning');
        return;
      }
      const names = _vmDropNames(dt);
      if (names.length === 0) return;
      let matched = 0;
      for (const f of _allVideoFiles) {
        const fname = f.name.replace(/^.*[\\/]/, '');
        if (names.includes(fname) && !_selectedFiles.has(f.path)) {
          _selectedFiles.add(f.path);
          matched++;
        }
      }
      if (matched > 0) {
        _vmRenderEntries($('vm-list'), [...document.querySelectorAll('#vm-list .browse-item[data-path]')].map(el => el.dataset.path), [..._allVideoFiles]);
        _vmUpdateSelectedCount();
      }
    } catch (err) {
      console.warn('video-manage drop error:', err);
    }
  });
}

async function _vmHandleMkdir() {
  const name = prompt('输入新文件夹名称：');
  if (!name || !name.trim()) return;
  try {
    const r = await api('POST', '/api/fs/mkdir', { parent: _currentPath, name: name.trim() });
    if (r.ok) {
      _vmLoadDir(_currentPath);
    } else {
      alert('创建失败: ' + (r.error || '未知错误'));
    }
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
}

function _vmInit() {
  const modal = $('modal-video-manage');
  if (!modal) return;
  // backdrop intentionally does NOT close — only Cancel button closes
  $('vm-cancel').onclick = closeVideoManager;
  $('vm-add').onclick = _vmAddSelected;
  $('vm-mkdir').onclick = _vmHandleMkdir;
  _vmInitDragDrop();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _vmInit);
} else {
  _vmInit();
}


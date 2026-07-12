import { $, escapeHtml } from './utils.js';
import { api } from './api.js';
import { loadVideos } from './sidebar-data.js';

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
    if (!isDriveList) {
      _bindListEvents(listEl);
    }
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
    await api('PUT', '/api/videos/selected', { videos: merged });
    closeVideoManager();
    await loadVideos();
  } catch (e) {
    addBtn.disabled = false;
    addBtn.textContent = '添加选中';
  }
}

function _vmInit() {
  const modal = $('modal-video-manage');
  if (!modal) return;
  modal.querySelector('.modal-backdrop').onclick = closeVideoManager;
  $('vm-cancel').onclick = closeVideoManager;
  $('vm-add').onclick = _vmAddSelected;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _vmInit);
} else {
  _vmInit();
}

export { openVideoManager, closeVideoManager };

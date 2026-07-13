import { $, escapeHtml } from './utils.js';
import { api } from './api.js';

window._browseResolve = null;

export function openBrowseDir(targetInputId) {
  const modal = $('modal-browse-dir');
  if (!modal) return;
  window._browseResolve = (path) => {
    const inp = document.getElementById(targetInputId);
    if (inp) inp.value = path;
  };
  modal.style.display = 'flex';
  loadBrowseDir('');
}

let _browseCurrentPath = '';

export async function loadBrowseDir(path) {
  _browseCurrentPath = path;
  const pathEl = $('browse-path');
  const listEl = $('browse-dir-list');
  const upBtn = $('browse-up');
  const selectBtn = $('browse-select');
  const mkdirBtn = $('browse-mkdir');
  pathEl.textContent = '加载中...';
  listEl.innerHTML = '';
  upBtn.style.display = 'none';
  selectBtn.disabled = true;
  mkdirBtn.style.display = 'none';
  try {
    const r = await api('GET', `/api/fs/dirs?path=${encodeURIComponent(path)}`);
    if (r.error) { pathEl.textContent = '错误: ' + r.error; return; }
    pathEl.textContent = r.path || '(选择驱动器)';
    selectBtn.disabled = r.is_drive_list;
    if (r.is_drive_list) {
      upBtn.style.display = 'none';
      mkdirBtn.style.display = 'none';
    } else {
      upBtn.style.display = '';
      mkdirBtn.style.display = '';
      upBtn.onclick = () => loadBrowseDir(r.parent || '');
    }
    if (r.is_drive_list) {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d)}</div>`
      ).join('');
    } else {
      listEl.innerHTML = r.dirs.map(d =>
        `<div class="browse-item" data-path="${escapeHtml(d)}">📁 ${escapeHtml(d.replace(/^.*[\\/]/, ''))}</div>`
      ).join('');
    }
    listEl.querySelectorAll('.browse-item').forEach(el => {
      el.onclick = () => {
        loadBrowseDir(el.dataset.path);
      };
    });
  } catch (e) {
    pathEl.textContent = '加载失败: ' + e.message;
  }
}

$('browse-mkdir').onclick = async () => {
  const name = prompt('输入新文件夹名称：');
  if (!name || !name.trim()) return;
  try {
    const r = await api('POST', '/api/fs/mkdir', { parent: _browseCurrentPath, name: name.trim() });
    if (r.ok) {
      loadBrowseDir(_browseCurrentPath);
    } else {
      alert('创建失败: ' + (r.error || '未知错误'));
    }
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
};

export function isDesktop() {
  return !!(window.pywebview && window.pywebview.api);
}

export async function pickFolder(initialDir = '') {
  const api = window.pywebview?.api;
  if (!api?.pick_folder) return null;
  const r = await api.pick_folder(initialDir || '');
  if (!r || r.cancelled) return null;
  if (!r.ok) throw new Error(r.error || '选择目录失败');
  return r.path || null;
}

export async function pickFile(initialDir = '', kind = 'video') {
  const api = window.pywebview?.api;
  if (!api?.pick_file) return null;
  const r = await api.pick_file(initialDir || '', kind);
  if (!r || r.cancelled) return null;
  if (!r.ok) throw new Error(r.error || '选择文件失败');
  return r.path || null;
}

export async function pickFiles(initialDir = '', kind = 'video') {
  const api = window.pywebview?.api;
  if (!api?.pick_files) return null;
  const r = await api.pick_files(initialDir || '', kind);
  if (!r || r.cancelled) return null;
  if (!r.ok) throw new Error(r.error || '选择文件失败');
  return Array.isArray(r.paths) ? r.paths : null;
}

export function applyPickToInput(inputEl, path) {
  if (!inputEl || path == null || path === '') return false;
  inputEl.value = path;
  inputEl.dispatchEvent(new Event('input', { bubbles: true }));
  inputEl.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}

export function setBrowseButtonsVisible(root = document) {
  const show = isDesktop();
  root.querySelectorAll('.browse-btn, [data-desktop-browse]').forEach((btn) => {
    btn.style.display = show ? '' : 'none';
  });
}
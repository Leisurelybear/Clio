import { state } from './state.js';

function $(id) {
  return document.getElementById(id);
}

function $$(sel) {
  return document.querySelectorAll(sel);
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
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

function setStatus(msg, kind = '') {
  const el = $('status');
  if (!el) return;
  el.textContent = msg || '';
  el.className = 'status ' + kind;
  if (msg) {
    const captured = msg;
    // Errors stick longer so users can read them; info/ok clear quickly
    const ttl = kind === 'err' || kind === 'error' ? 8000 : 4000;
    setTimeout(() => { if (el.textContent === captured) el.textContent = ''; }, ttl);
  }
}

function updateSidebarDay() {
  const el = document.querySelector('.project-item[data-entity="plan"] .muted');
  if (el) el.textContent = state.currentDay;
}

function updateProjectSidebar() {
  const el = $('proj-name-sidebar');
  if (el) el.textContent = state.currentProject?.name || state.projectName || '未命名';
}

function updateEntityUI() {
  const saveBtn = $('btn-save');
  if (saveBtn) saveBtn.style.display = '';
  const cls = state.currentEntity === 'plan' ? 'entity-plan'
    : state.currentEntity === 'run' ? 'entity-run'
    : state.currentEntity === 'config' ? 'entity-config'
    : state.currentEntity === 'logs' ? 'entity-logs'
    : state.currentEntity === 'tokens' ? 'entity-tokens'
    : 'entity-video';
  $('editor').className = cls;
  const previewBar = $('preview-bar');
  if (previewBar) previewBar.style.display = state.currentEntity === 'plan' ? 'flex' : 'none';
  $$('.project-item').forEach(p => p.classList.remove('active'));
  if (state.currentEntity === 'plan') {
    document.querySelector('.project-item[data-entity="plan"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'run') {
    document.querySelector('.project-item[data-entity="run"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'config') {
    document.querySelector('.project-item[data-entity="config"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'logs') {
    document.querySelector('.project-item[data-entity="logs"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  } else if (state.currentEntity === 'tokens') {
    document.querySelector('.project-item[data-entity="tokens"]').classList.add('active');
    $$('.video-item').forEach(v => v.classList.remove('active'));
  }
}

export {
  $, $$,
  escapeHtml,
  fmtTime,
  parseTimecode,
  getDeep,
  setDeep,
  markDirty,
  updateSaveBtn,
  setStatus,
  updateSidebarDay,
  updateProjectSidebar,
  updateEntityUI,
};

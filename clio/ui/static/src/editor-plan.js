import { state } from './state.js';
import { $, escapeHtml, markDirty, clearDirty, updateSidebarDay, setStatus } from './utils.js';
import { api, icon } from './api.js';
import { renderPreviewBar, startPreview, _playPreviewSegment } from './viewer.js';
import { addToast } from './toast.js';
import { resolveEditorSaveTarget } from './editor-save.js';
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
  computeDragAutoScrollDelta,
} from './plan-edit.js';

let _readinessTimer = null;
let _lastReadiness = { ok: true, errors: [], warnings: [] };
let _dragFromIndex = null;
let _dropToIndex = null;
let _highlightTimer = null;

function planScrollParent() {
  return document.querySelector('#tab-plan');
}

/** Scroll the plan pane when the pointer nears its top/bottom during drag. */
function autoScrollDuringDrag(clientY) {
  const scroller = planScrollParent();
  if (!scroller || _dragFromIndex == null) return;
  const rect = scroller.getBoundingClientRect();
  const delta = computeDragAutoScrollDelta(clientY, rect.top, rect.bottom);
  if (delta) scroller.scrollTop += delta;
}

export function configSaveStatusForTab(tab) {
  if (tab === 'project') {
    return { message: '项目配置已保存，立即生效', level: 'ok' };
  }
  if (tab === 'global') {
    return {
      message: '全局配置已保存并热加载；正在运行中的任务仍使用启动时配置',
      level: 'ok',
    };
  }
  return { message: '合并视图为只读，无法保存', level: 'warn' };
}

function applySequence(next, opts = {}) {
  if (!state.plan) return;
  state.plan.sequence = next;
  markDirty();
  renderPlan();
  const hi = opts.highlightIndex;
  if (hi == null || hi < 0) return;
  const el = document.querySelector(`#plan-list [data-preview-index="${hi}"]`);
  if (!el) return;
  el.classList.add('plan-seg-just-moved');
  try {
    el.scrollIntoView({ block: 'nearest' });
  } catch { /* ignore */ }
  if (_highlightTimer) clearTimeout(_highlightTimer);
  _highlightTimer = setTimeout(() => {
    el.classList.remove('plan-seg-just-moved');
    _highlightTimer = null;
  }, 700);
}

function clearDropIndicator() {
  document.querySelectorAll('.plan-seg-drop-before, .plan-seg-drop-after').forEach((node) => {
    node.classList.remove('plan-seg-drop-before', 'plan-seg-drop-after');
  });
  _dropToIndex = null;
}

/** Paint insert line for pending toIndex (final index of moved item). */
function paintDropIndicator(fromIndex, toIndex, length) {
  clearDropIndicator();
  if (toIndex == null || length <= 0) return;
  _dropToIndex = toIndex;
  const list = document.querySelectorAll('#plan-list .plan-seg');
  if (!list.length) return;
  const insertBefore = toIndex < fromIndex ? toIndex : toIndex + 1;
  if (insertBefore >= length) {
    list[length - 1]?.classList.add('plan-seg-drop-after');
  } else {
    list[insertBefore]?.classList.add('plan-seg-drop-before');
  }
}

function scheduleReadinessCheck() {
  if (_readinessTimer) clearTimeout(_readinessTimer);
  _readinessTimer = setTimeout(() => {
    _readinessTimer = null;
    refreshReadinessPanel();
  }, 400);
}

async function refreshReadinessPanel() {
  const panel = $('plan-readiness');
  if (!panel || !state.plan) return;
  panel.innerHTML = '<p class="muted">检查规划就绪状态…</p>';
  try {
    const r = await api('POST', '/api/plan/readiness', {
      day: state.currentDay || 'day1',
      source: $('cut-source')?.value || 'compressed',
      plan: state.plan,
    });
    const errors = r.errors || [];
    const warnings = r.warnings || [];
    _lastReadiness = { ok: !!r.ok, errors, warnings };
    renderReadinessList(panel, errors, warnings);
    updateActionButtonsGate();
  } catch (e) {
    panel.innerHTML = `<p class="err">就绪检查失败: ${escapeHtml(e.message || e)}</p>`;
    _lastReadiness = { ok: false, errors: [{ message: String(e.message || e) }], warnings: [] };
    updateActionButtonsGate();
  }
}

function renderReadinessList(panel, errors, warnings) {
  if (!errors.length && !warnings.length) {
    panel.innerHTML = '<p class="ok">规划检查通过，可以裁剪/导出。</p>';
    return;
  }
  const parts = ['<h3>导出/裁剪检查</h3>'];
  if (errors.length) {
    parts.push('<ul class="plan-readiness-errors">');
    for (const issue of errors) {
      const idx = issue.segment_index;
      parts.push(
        `<li class="plan-issue-error" data-seg="${idx != null ? idx : ''}">${escapeHtml(issue.message || issue.code || '错误')}</li>`
      );
    }
    parts.push('</ul>');
  }
  if (warnings.length) {
    parts.push('<ul class="plan-readiness-warnings">');
    for (const issue of warnings) {
      const idx = issue.segment_index;
      parts.push(
        `<li class="plan-issue-warn" data-seg="${idx != null ? idx : ''}">${escapeHtml(issue.message || issue.code || '警告')}</li>`
      );
    }
    parts.push('</ul>');
  }
  panel.innerHTML = parts.join('');
  panel.querySelectorAll('[data-seg]').forEach((el) => {
    el.onclick = () => {
      const i = el.getAttribute('data-seg');
      if (i === '' || i == null) return;
      document.querySelector(`[data-preview-index="${i}"]`)?.scrollIntoView({ block: 'nearest' });
    };
  });
}

function updateActionButtonsGate() {
  const hasErrors = (_lastReadiness.errors || []).length > 0;
  const cutBtn = $('btn-cut-exec');
  const expBtn = $('btn-jianying-export');
  if (cutBtn) {
    cutBtn.disabled = hasErrors;
    cutBtn.title = hasErrors ? '请先修复规划错误' : '';
  }
  if (expBtn) {
    expBtn.disabled = hasErrors;
    expBtn.title = hasErrors ? '请先修复规划错误' : '';
  }
}

function ensureSavedBeforeAction() {
  if (!state.dirty) return true;
  alert('有未保存的规划修改，请先保存后再裁剪/导出。');
  return false;
}

function confirmWarningsIfNeeded() {
  const warnings = _lastReadiness.warnings || [];
  const errors = _lastReadiness.errors || [];
  if (errors.length) {
    addToast(errors[0].message || '规划存在错误，无法继续', 'error', 6000);
    return false;
  }
  if (warnings.length) {
    const preview = warnings.slice(0, 5).map((w) => w.message).join('\n');
    return confirm(`规划存在警告：\n${preview}\n\n仍要继续？`);
  }
  return true;
}

function playerCurrentTimeSec() {
  const player = $('player');
  if (!player) return null;
  const t = player.currentTime;
  return Number.isFinite(t) ? t : null;
}

function applyTimelineBound(segIndex, which) {
  const p = state.plan;
  if (!p?.sequence?.[segIndex]) return;
  const sec = playerCurrentTimeSec();
  if (sec == null) {
    addToast('请先在播放器中打开对应视频', 'warning');
    return;
  }
  const next = setTimelineBound(p.sequence[segIndex].use_timeline || '', which, sec);
  p.sequence[segIndex] = patchSegment(p.sequence[segIndex], { use_timeline: next });
  markDirty();
  renderPlan();
}

function promptInsertAfter(afterIndex) {
  const p = state.plan;
  if (!p) return;
  const videos = state.videos || [];
  const options = videos
    .filter((v) => v.index)
    .map((v) => `${v.index} ${v.title || v.file || ''}`.trim());
  const hint = options.length
    ? `可选 index 示例: ${options.slice(0, 8).join(' | ')}`
    : '输入视频 index，例如 001';
  const raw = prompt(`在第 ${afterIndex + 1} 段后插入片段\n${hint}\n\n视频 index:`, '');
  if (raw == null) return;
  const index = String(raw).trim();
  if (!index) {
    addToast('index 不能为空', 'warning');
    return;
  }
  const v = videos.find((x) => String(x.index) === index);
  const title = v?.title || v?.file || '';
  applySequence(insertSegment(p.sequence, afterIndex, { index, title }));
}

export function renderPlan() {
  const p = state.plan;
  const pane = $('tab-plan');
  $('player-pane').classList.add('plan-mode');
  renderPreviewBar();
  if (!p) {
    pane.innerHTML = `
      <h3>vlog 剪辑规划</h3>
      <p class="muted">当前项目没有编排文件。</p>
      <p class="hint">请先运行流水线中的「vlog 剪辑规划」步骤，或在 CLI 执行 <code>python main.py plan</code>。</p>
    `;
    return;
  }
  if (!Array.isArray(p.sequence)) p.sequence = [];

  pane.innerHTML = `
    <h3>编排元信息</h3>
    ${state.availablePlans.length >= 1 ? `
    <label>分集
      <select id="plan-day-select">
        ${state.availablePlans.map(dp =>
          `<option value="${dp.day_label}" ${dp.day_label === state.currentDay ? 'selected' : ''}>${dp.day_label}</option>`
        ).join('')}
      </select>
    </label>
    ` : ''}
    <label>标题 <input data-field="day_title"></label>
    <label>主题 <input data-field="theme"></label>
    <label>开场提示 <textarea data-field="opening_tip" rows="2"></textarea></label>
    <label>收尾提示 <textarea data-field="ending_tip" rows="2"></textarea></label>
    <h3>顺序 (sequence) — ${p.sequence.length} 项</h3>
    <p class="hint">拖动手柄或使用 ↑↓ 调整顺序；点击片段跳转预览</p>
    <ol id="plan-list"></ol>
    <div id="plan-readiness" class="plan-readiness cut-section"></div>
  `;
  const daySelect = pane.querySelector('#plan-day-select');
  if (daySelect) {
    daySelect.onchange = async () => {
      const day = daySelect.value;
      if (day === state.currentDay) return;
      if (state.dirty && !confirm('切换分集将丢弃当前修改，确定吗？')) { daySelect.value = state.currentDay; return; }
      state.currentDay = day;
      state.plan = null;
      clearDirty();
      updateSidebarDay();
      await import('./sidebar.js').then(mod => mod.saveProject());
      await import('./sidebar.js').then(mod => mod.selectPlan());
    };
  }
  for (const k of ['day_title', 'theme', 'opening_tip', 'ending_tip']) {
    const el = pane.querySelector(`[data-field="${k}"]`);
    if (!el) continue;
    el.value = p[k] || '';
    el.oninput = () => {
      p[k] = el.value;
      markDirty();
      scheduleReadinessCheck();
    };
  }
  const ol = pane.querySelector('#plan-list');
  p.sequence.forEach((seg, i) => {
    const li = document.createElement('li');
    li.className = 'plan-seg' + (state.previewActive && state.previewIndex === i ? ' preview-active' : '');
    li.dataset.previewIndex = String(i);
    li.draggable = true;
    li.innerHTML = `
      <div class="plan-seg-toolbar">
        <span class="plan-drag-handle" title="拖拽排序" aria-hidden="true">⠿</span>
        <button type="button" class="plan-move-btn" data-move="up" title="上移" ${i === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" class="plan-move-btn" data-move="down" title="下移" ${i === p.sequence.length - 1 ? 'disabled' : ''}>↓</button>
        <button type="button" class="plan-ins-btn" data-ins title="在此后插入片段">+插入</button>
        <button type="button" class="plan-del-btn" data-del title="删除片段">删除</button>
        <span class="muted">视频 [${escapeHtml(seg.index || '?')}]</span>
      </div>
      <label>标题 <input value="${escapeHtml(seg.title || '')}" data-k="title"></label>
      <label class="plan-timeline-row">时间轴
        <input value="${escapeHtml(seg.use_timeline || '')}" data-k="use_timeline" placeholder="00:10-00:45">
        <button type="button" class="plan-tl-btn" data-tl="start" title="用播放器当前位置作为起点">起点</button>
        <button type="button" class="plan-tl-btn" data-tl="end" title="用播放器当前位置作为终点">终点</button>
      </label>
      <label>理由 <input value="${escapeHtml(seg.reason || '')}" data-k="reason"></label>
      <label>口播提示 <textarea rows="2" data-k="voiceover_hint">${escapeHtml(seg.voiceover_hint || '')}</textarea></label>
    `;
    li.onclick = (e) => {
      if (e.target.closest('input, textarea, button, .plan-drag-handle')) return;
      const v = state.videos.find(x => x.index === seg.index);
      if (!v) { setStatus(`找不到视频 [${seg.index}]，请重新生成规划`, 'warn'); return; }
      if (state.previewActive) {
        state.previewIndex = i;
        _playPreviewSegment();
      } else {
        startPreview(i);
      }
    };
    li.querySelectorAll('[data-k]').forEach(inp => {
      inp.oninput = (e) => {
        p.sequence[i] = patchSegment(p.sequence[i], { [e.target.dataset.k]: e.target.value });
        markDirty();
        scheduleReadinessCheck();
      };
    });
    li.querySelector('[data-move="up"]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (i <= 0) return;
      applySequence(reorderSequence(p.sequence, i, i - 1), { highlightIndex: i - 1 });
    });
    li.querySelector('[data-move="down"]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (i >= p.sequence.length - 1) return;
      applySequence(reorderSequence(p.sequence, i, i + 1), { highlightIndex: i + 1 });
    });
    li.querySelector('[data-ins]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      promptInsertAfter(i);
    });
    li.querySelector('[data-del]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!confirm(`删除第 ${i + 1} 段「${seg.title || seg.index || ''}」？`)) return;
      applySequence(removeSegment(p.sequence, i));
    });
    li.querySelectorAll('[data-tl]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        applyTimelineBound(i, btn.dataset.tl);
      });
    });
    li.addEventListener('dragstart', (e) => {
      _dragFromIndex = i;
      _dropToIndex = null;
      li.classList.add('plan-seg-dragging');
      e.dataTransfer.effectAllowed = 'move';
      try {
        e.dataTransfer.setData('text/plain', String(i));
      } catch { /* ignore */ }
    });
    li.addEventListener('dragend', () => {
      li.classList.remove('plan-seg-dragging');
      clearDropIndicator();
      _dragFromIndex = null;
    });
    li.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (_dragFromIndex == null) return;
      autoScrollDuringDrag(e.clientY);
      const rect = li.getBoundingClientRect();
      const placeAfter = e.clientY > rect.top + rect.height / 2;
      const to = computeDropToIndex(_dragFromIndex, i, placeAfter, p.sequence.length);
      if (to == null) {
        clearDropIndicator();
        return;
      }
      paintDropIndicator(_dragFromIndex, to, p.sequence.length);
    });
    li.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (_dragFromIndex == null) return;
      const rect = li.getBoundingClientRect();
      const placeAfter = e.clientY > rect.top + rect.height / 2;
      const to = computeDropToIndex(_dragFromIndex, i, placeAfter, p.sequence.length);
      const from = _dragFromIndex;
      clearDropIndicator();
      _dragFromIndex = null;
      li.classList.remove('plan-seg-dragging');
      if (to == null) return;
      applySequence(reorderSequence(p.sequence, from, to), { highlightIndex: to });
    });
    ol.appendChild(li);
  });

  ol.addEventListener('dragleave', (e) => {
    if (!ol.contains(e.relatedTarget)) {
      clearDropIndicator();
    }
  });

  // Pane-level dragover: keep scrolling when pointer is in empty chrome / padding
  pane.addEventListener('dragover', (e) => {
    if (_dragFromIndex == null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    autoScrollDuringDrag(e.clientY);
  });

  // Prepend control when sequence empty or for first insert
  const insertBar = document.createElement('div');
  insertBar.className = 'plan-insert-bar';
  insertBar.innerHTML = `<button type="button" id="btn-plan-insert-end" class="btn-secondary">在末尾插入片段</button>`;
  ol.parentNode?.insertBefore(insertBar, ol.nextSibling);
  insertBar.querySelector('#btn-plan-insert-end')?.addEventListener('click', () => {
    const n = p.sequence?.length || 0;
    promptInsertAfter(n - 1); // -1 when empty → prepend
  });

  const cutSection = document.createElement('div');
  cutSection.className = 'cut-section';
  cutSection.innerHTML = `
    <h3>裁剪此分集</h3>
    <p class="hint">基于规划 ${escapeHtml(state.currentDay)} 裁剪所有片段</p>
    <label>视频来源
      <select id="cut-source">
        <option value="compressed" selected>压缩版 (compressed)</option>
        <option value="original">原片 (original)</option>
      </select>
    </label>
    <label><input type="checkbox" id="cut-reencode"> 重新编码 (默认 -c copy 快速)</label>
    <label>输出目录 (留空则 output/cuts/&lt;day&gt;)
      <span class="input-with-browse"><input id="cut-outdir" placeholder="例如 E:/剪辑素材/第一天"><button class="browse-btn" data-target="cut-outdir" type="button">浏览</button></span></label>
    <div class="cut-actions" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;align-items:center;">
      <button id="btn-cut-exec" class="btn-primary" type="button">${icon('cut', 16)} 执行裁剪</button>
      <button id="btn-cut-open-dir" class="btn-secondary" type="button" title="在资源管理器中打开裁剪输出目录">${icon('folder', 16)} 打开目录</button>
    </div>
    <div id="cut-result" style="margin-top:12px"></div>
  `;
  pane.appendChild(cutSection);

  const exportSection = document.createElement('div');
  exportSection.className = 'cut-section';
  exportSection.style.marginTop = '16px';
  exportSection.innerHTML = `
    <h3>导出到剪映</h3>
    <p class="hint">生成剪映专业版可直接打开的草稿文件</p>
    <button id="btn-jianying-export" class="btn-primary">${icon('export', 16)} 导出到剪映</button>
    <div id="export-result" style="margin-top:8px;font-size:var(--text-sm)"></div>
  `;
  pane.appendChild(exportSection);

  $('cut-source')?.addEventListener('change', () => scheduleReadinessCheck());

  $('btn-cut-open-dir')?.addEventListener('click', async () => {
    const custom = $('cut-outdir')?.value?.trim();
    let path = custom;
    if (!path) {
      const base = state.config?.output_dir || '';
      const day = state.currentDay || 'day1';
      if (!base) {
        setStatus('无法解析默认裁剪目录（output_dir 未知）', 'warn');
        return;
      }
      path = `${String(base).replace(/[\\/]+$/, '')}/cuts/${day}`;
    }
    try {
      const r = await api('POST', '/api/fs/reveal', { path });
      if (r.ok) setStatus(`已打开: ${r.path || path}`, 'ok');
      else throw new Error(r.error || '打开失败');
    } catch (e) {
      setStatus('打开目录失败: ' + e.message, 'err');
    }
  });

  $('btn-jianying-export')?.addEventListener('click', async () => {
    const btn = $('btn-jianying-export');
    if (btn?.disabled) return;
    if (!ensureSavedBeforeAction()) return;
    await refreshReadinessPanel();
    if (!confirmWarningsIfNeeded()) return;
    const force = (_lastReadiness.warnings || []).length > 0;
    const resultDiv = $('export-result');
    resultDiv.innerHTML = '<span class="muted">导出中…</span>';
    if (btn) {
      btn.disabled = true;
      btn.dataset.prevLabel = btn.innerHTML;
      btn.textContent = '导出中...';
    }
    try {
      const r = await api('POST', '/api/export', {
        day: state.currentDay || 'day1',
        format: 'jianying',
        force,
      });
      resultDiv.innerHTML = `<span style="color:var(--ok,#484)">✓ 已导出到 ${escapeHtml(r.path)}</span>`;
      addToast('已导出到剪映', 'success');
    } catch (e) {
      resultDiv.innerHTML = `<span style="color:var(--err,#c44)">✗ 导出失败: ${escapeHtml(e.message || e)}</span>`;
      addToast('导出失败: ' + (e.message || e), 'error', 6000);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.prevLabel || `${icon('export', 16)} 导出到剪映`;
      }
      updateActionButtonsGate();
    }
  });
  $('btn-cut-exec').onclick = executeCut;
  scheduleReadinessCheck();
}


export async function executeCut() {
  const btn = $('btn-cut-exec');
  const result = $('cut-result');
  if (btn?.disabled) return;
  if (!ensureSavedBeforeAction()) return;
  await refreshReadinessPanel();
  if (!confirmWarningsIfNeeded()) return;
  const force = (_lastReadiness.warnings || []).length > 0;
  btn.disabled = true;
  btn.textContent = '裁剪中...';
  result.innerHTML = '<p class="muted">请等待，正在裁剪视频片段...</p>';
  try {
    const dayLabel = state.currentDay;
    try {
      await api('GET', `/api/plan?day=${dayLabel}`);
    } catch (e) {
      result.innerHTML = `<p class="err">规划文件不存在: 请先运行 CLI 命令 <code>python main.py plan --day ${escapeHtml(dayLabel)}</code> 生成规划。</p>`;
      setStatus('裁剪失败: 规划文件不存在', 'err');
      btn.disabled = false;
      btn.textContent = '执行裁剪';
      updateActionButtonsGate();
      return;
    }
    const body = {
      day_label: dayLabel,
      source: $('cut-source').value,
      reencode: $('cut-reencode').checked,
      output_dir: $('cut-outdir').value.trim() || null,
      force,
      overwrite: false,
    };
    let r;
    try {
      r = await api('POST', '/api/cut', body);
    } catch (e) {
      if (e.status === 409 && e.body?.code === 'cut_output_exists') {
        const count = e.body.count || e.body.files?.length || '?';
        const dir = e.body.output_dir || body.output_dir || '';
        const preview = e.body.preview || (e.body.files || []).slice(0, 8).join('、') || '';
        const ok = confirm(
          `输出目录已有 ${count} 个裁剪视频，是否覆盖重剪？\n\n` +
          `目录: ${dir}\n` +
          (preview ? `示例: ${preview}\n\n` : '\n') +
          '将先备份旧文件，生成新裁剪成功后再删除备份。'
        );
        if (!ok) {
          result.innerHTML = '<p class="muted">已取消覆盖裁剪</p>';
          setStatus('已取消裁剪', 'warn');
          return;
        }
        r = await api('POST', '/api/cut', { ...body, overwrite: true });
      } else {
        throw e;
      }
    }
    result.innerHTML = `<p class="ok">裁剪完成</p><p>输出目录: ${escapeHtml(r.output_dir)}</p>`;
    setStatus('裁剪完成', 'ok');
    addToast('裁剪完成', 'success');
    state.steps.cut = true;
    import('./sidebar.js').then(mod => mod.renderSteps());
    import('./sidebar.js').then(mod => mod.saveProject());
  } catch (e) {
    result.innerHTML = `<p class="err">错误: ${escapeHtml(e.message)}</p>`;
    const msg = '裁剪失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  } finally {
    btn.disabled = false;
    btn.textContent = '执行裁剪';
    updateActionButtonsGate();
  }
}


export async function save() {
  if (!state.dirty) { setStatus('没有改动需要保存', 'warn'); return; }
  const entity = state.currentEntity;
  const day = state.currentDay;
  const tab = state.currentTab;
  const videoFile = state.currentVideo;
  const planData = state.plan;
  const textsData = state.texts;
  const voiceoverData = state.voiceover;
  const target = resolveEditorSaveTarget({
    entity,
    tab,
    configTab: state.configTab,
  });
  if (target.action === 'noop') {
    setStatus(target.reason || '当前页无可保存内容', 'warn');
    return;
  }
  try {
    if (target.action === 'config') {
      const ct = target.configTab || 'global';
      let r;
      if (ct === 'global') {
        r = await api('PUT', '/api/config/global', state.configGlobal);
      } else {
        r = await api('PUT', '/api/config/project', state.configProject);
      }
      if (r.error) throw new Error(r.error);
      clearDirty();
      const status = configSaveStatusForTab(ct);
      setStatus(status.message, status.level);
      addToast(status.message, status.level === 'ok' ? 'success' : 'warning');
      return;
    }
    if (target.action === 'plan') {
      await api('PUT', `/api/plan?day=${day}`, planData);
    } else if (target.action === 'texts') {
      const v = state.videos.find(x => x.file === videoFile);
      if (!v || !v.text_json) throw new Error('当前视频没有 texts JSON');
      await api('PUT', `/api/texts?file=${encodeURIComponent(v.text_json)}`, textsData);
    } else if (target.action === 'voiceover') {
      const v = state.videos.find(x => x.file === videoFile);
      if (!v || !v.script_json) throw new Error('当前视频没有 voiceover JSON');
      await api('PUT', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`, voiceoverData);
    } else {
      setStatus('当前页无可保存内容', 'warn');
      return;
    }
    clearDirty();
    setStatus('已保存', 'ok');
    addToast('已保存', 'success');
    if (target.action === 'plan') scheduleReadinessCheck();
  } catch (e) {
    const msg = '保存失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  }
}

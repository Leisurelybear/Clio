import { state } from './state.js';
import { $, escapeHtml, markDirty, updateSidebarDay, setStatus, updateSaveBtn } from './utils.js';
import { api, icon } from './api.js';
import { renderPreviewBar, startPreview, _playPreviewSegment } from './viewer.js';
import { addToast } from './toast.js';


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
      await import('./sidebar.js').then(mod => mod.saveProject());
      await import('./sidebar.js').then(mod => mod.selectPlan());
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
    li.className = 'plan-seg' + (state.previewActive && state.previewIndex === i ? ' preview-active' : '');
    li.dataset.previewIndex = i;
    li.innerHTML = `
      <div class="seg-time">${escapeHtml(seg.use_timeline || '')} <span class="muted">视频 [${escapeHtml(seg.index || '?')}]</span></div>
      <div class="seg-title">${escapeHtml(seg.title || '')}</div>
      <label>理由 <input value="${escapeHtml(seg.reason || '')}" data-k="reason"></label>
      <label>口播提示 <textarea rows="2" data-k="voiceover_hint">${escapeHtml(seg.voiceover_hint || '')}</textarea></label>
    `;
    li.onclick = (e) => {
      if (e.target.matches('input, textarea')) return;
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
        p.sequence[i][e.target.dataset.k] = e.target.value;
        markDirty();
      };
    });
    ol.appendChild(li);
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
    <button id="btn-cut-exec" class="btn-primary">${icon('cut', 16)} 执行裁剪</button>
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

  $('btn-jianying-export')?.addEventListener('click', async () => {
    const btn = $('btn-jianying-export');
    if (btn?.disabled) return;
    const resultDiv = $('export-result');
    resultDiv.innerHTML = '<span class="muted">导出中…</span>';
    if (btn) {
      btn.disabled = true;
      btn.dataset.prevLabel = btn.innerHTML;
      btn.textContent = '导出中...';
    }
    try {
      const r = await api('POST', '/api/export', { day: state.currentDay || 'day1', format: 'jianying' });
      if (r.ok) {
        resultDiv.innerHTML = `<span style="color:var(--ok,#484)">✓ 已导出到 ${escapeHtml(r.path)}</span>`;
        addToast('已导出到剪映', 'success');
      } else {
        resultDiv.innerHTML = `<span style="color:var(--err,#c44)">✗ ${escapeHtml(r.error || '导出失败')}</span>`;
        addToast(r.error || '导出失败', 'error', 6000);
      }
    } catch (e) {
      resultDiv.innerHTML = `<span style="color:var(--err,#c44)">✗ 导出失败: ${escapeHtml(e.message || e)}</span>`;
      addToast('导出失败: ' + (e.message || e), 'error', 6000);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.prevLabel || `${icon('export', 16)} 导出到剪映`;
      }
    }
  });
  $('btn-cut-exec').onclick = executeCut;
}


export async function executeCut() {
  const btn = $('btn-cut-exec');
  const result = $('cut-result');
  btn.disabled = true;
  btn.textContent = '裁剪中...';
  result.innerHTML = '<p class="muted">请等待，正在裁剪视频片段...</p>';
  try {
    const dayLabel = state.currentDay;
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
      addToast('裁剪完成', 'success');
      state.steps.cut = true;
      import('./sidebar.js').then(mod => mod.renderSteps());
      import('./sidebar.js').then(mod => mod.saveProject());
    } else {
      throw new Error(r.error || '裁剪失败');
    }
  } catch (e) {
    result.innerHTML = `<p class="err">错误: ${escapeHtml(e.message)}</p>`;
    const msg = '裁剪失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  } finally {
    btn.disabled = false;
    btn.textContent = '执行裁剪';
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
  const configRaw = state.configRaw;
  try {
    if (entity === 'run') {
      setStatus('当前视图不需要保存', 'warn');
      return;
    }
    if (entity === 'config') {
      const tab = state.configTab || 'global';
      let r;
      if (tab === 'global') {
        r = await api('PUT', '/api/config/global', state.configGlobal);
      } else if (tab === 'project') {
        r = await api('PUT', '/api/config/project', state.configProject);
      } else {
        setStatus('合并视图为只读，无法保存', 'warn');
        return;
      }
      if (r.error) throw new Error(r.error);
      state.dirty = false;
      updateSaveBtn();
      const status = configSaveStatusForTab(tab);
      setStatus(status.message, status.level);
      addToast(status.message, status.level === 'ok' ? 'success' : 'warning');
      return;
    }
    if (entity === 'plan') {
      const r = await api('PUT', `/api/plan?day=${day}`, planData);
      if (!r.ok) throw new Error(r.error);
    } else {
      const v = state.videos.find(x => x.file === videoFile);
      if (tab === 'texts') {
        if (!v || !v.text_json) throw new Error('当前视频没有 texts JSON');
        const r = await api('PUT', `/api/texts?file=${encodeURIComponent(v.text_json)}`, textsData);
        if (!r.ok) throw new Error(r.error);
      } else if (tab === 'voiceover') {
        if (!v || !v.script_json) throw new Error('当前视频没有 voiceover JSON');
        const r = await api('PUT', `/api/voiceover?file=${encodeURIComponent(v.script_json)}`, voiceoverData);
        if (!r.ok) throw new Error(r.error);
      }
    }
    state.dirty = false;
    updateSaveBtn();
    setStatus('已保存', 'ok');
    addToast('已保存', 'success');
  } catch (e) {
    const msg = '保存失败: ' + e.message;
    setStatus(msg, 'err');
    addToast(msg, 'error', 6000);
  }
}

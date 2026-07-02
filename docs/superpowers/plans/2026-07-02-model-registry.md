# R-017: Model Registry & Task Binding UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Settings AI config form with a structured model registry (provider list in Global tab) and task binding panel (dropdowns in Project tab).

**Architecture:** Pure frontend replacement — no new backend APIs. Reuses existing `PUT /api/config/global` and `PUT /api/config/project`. ProviderConfig gains a `models: list[str]` field. Capability validation (gemini → video tasks) computed on the frontend.

**Tech Stack:** Python 3.11+ dataclasses, vanilla JS (ES modules), CSS custom properties.

**Files touched:**
- `clio/config/models.py` — add `models` field
- `clio/config/parsers.py` — read `models` field
- `clio/config/descriptions.py` — add description
- `clio/tests/test_config.py` — test `models` field
- `clio/ui/static/src/editor-config.js` — replace AI form rendering
- `clio/ui/static/style.css` — provider cards, tag input, modal styles

---

### Task 1: Backend data model — `ProviderConfig.models`

**Files:**
- Modify: `clio/config/models.py:19-29`
- Modify: `clio/config/parsers.py:22-36`
- Modify: `clio/config/descriptions.py:26`
- Test: `clio/tests/test_config.py`

- [ ] **Step 1: Add `models` field to `ProviderConfig`**

In `clio/config/models.py`, add after line 29:

```python
    models: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Read `models` in `_parse_providers()`**

In `clio/config/parsers.py`, add after line 34:

```python
            models=cfg.get("models", []),
```

The full `ProviderConfig(...)` call becomes:

```python
        providers[name] = ProviderConfig(
            name=name,
            type=cfg.get("type", "gemini"),
            api_key=_resolve_api_key(cfg),
            api_key_env=cfg.get("api_key_env", ""),
            base_url=cfg.get("base_url", ""),
            poll_interval_sec=cfg.get("poll_interval_sec", 5),
            retry_attempts=cfg.get("retry_attempts", 2),
            requests_per_minute=cfg.get("requests_per_minute", 0),
            max_tokens=cfg.get("max_tokens", 4096),
            models=cfg.get("models", []),
        )
```

- [ ] **Step 3: Add description for `models` field**

In `clio/config/descriptions.py`, add after line 26:

```python
    "ai.providers.{name}.models": "该厂商支持的模型名称列表（如 gemini-2.5-flash），用于任务绑定的下拉选择",
```

- [ ] **Step 4: Write tests for `models` field**

In `clio/tests/test_config.py`, add within `TestLoadConfig`:

```python
    def test_provider_models_list(self, tmp_config):
        cfg = load_config(tmp_config / "config.yaml")
        g = cfg.ai.providers.get("gemini")
        assert g is not None
        assert g.models == ["gemini-2.5-flash", "gemini-2.0-flash"]

    def test_provider_models_defaults_to_empty(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "proxy:\n  enabled: false\n"
            "ai:\n  providers:\n    g:\n      type: gemini\n      api_key: k\n"
            "  tasks:\n    t:\n      provider: g\n      model: m\n",
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert cfg.ai.providers["g"].models == []
```

Also need to update `tmp_config` fixture to include `models` in the test config. Find the `tmp_config` fixture (in conftest.py) and add `models: [gemini-2.5-flash, gemini-2.0-flash]` to the gemini provider.

- [ ] **Step 5: Update `tmp_config` fixture**

In `conftest.py`, find the `tmp_config` fixture. The gemini provider entry currently has:
```yaml
providers:
  gemini:
    type: gemini
    api_key: test_key
```

Change it to:
```yaml
providers:
  gemini:
    type: gemini
    api_key: test_key
    models: [gemini-2.5-flash, gemini-2.0-flash]
```

- [ ] **Step 6: Run tests and commit**

```bash
python -m pytest clio/tests/test_config.py -v --tb=short
git add -A
git commit -m "feat(config): add ProviderConfig.models field for model registry"
```

---

### Task 2: Tag input component (frontend)

**Files:**
- Modify: `clio/ui/static/src/editor-config.js` — add `_renderTagInput` function
- Modify: `clio/ui/static/style.css` — add tag input styles

- [ ] **Step 1: Add `_renderTagInput()` function**

Add to `editor-config.js` (after the `_renderTooltip` function around line 30):

```javascript
export function _renderTagInput(container, values, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'tag-input-wrapper';

  const chips = document.createElement('div');
  chips.className = 'tag-chips';

  function renderChips() {
    chips.innerHTML = '';
    for (const v of values) {
      const chip = document.createElement('span');
      chip.className = 'tag-chip';
      chip.innerHTML = `${escapeHtml(v)} <span class="tag-chip-remove" data-value="${escapeHtml(v)}">×</span>`;
      chip.querySelector('.tag-chip-remove').onclick = () => {
        const idx = values.indexOf(v);
        if (idx >= 0) values.splice(idx, 1);
        renderChips();
        onChange(values);
      };
      chips.appendChild(chip);
    }
  }
  renderChips();

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tag-input';
  input.placeholder = '输入模型名，按回车添加';
  input.onkeydown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const val = input.value.trim();
      if (val && !values.includes(val)) {
        values.push(val);
        renderChips();
        onChange(values);
      }
      input.value = '';
    } else if (e.key === 'Backspace' && !input.value && values.length) {
      values.pop();
      renderChips();
      onChange(values);
    }
  };

  wrapper.appendChild(chips);
  wrapper.appendChild(input);
  container.appendChild(wrapper);
}
```

- [ ] **Step 2: Add CSS for tag input**

Add to `style.css`:

```css
/* Tag input (chip-based model list editor) */
.tag-input-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 6px;
  background: var(--bg-surface, #1e1e1e);
  border: 1px solid var(--border, #333);
  border-radius: var(--radius-sm, 4px);
  min-height: 32px;
  align-items: center;
}
.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: var(--accent, #4a9eff);
  color: #fff;
  font-size: var(--text-xs, 12px);
  padding: 2px 8px;
  border-radius: 12px;
  white-space: nowrap;
}
.tag-chip-remove {
  cursor: pointer;
  font-weight: bold;
  font-size: 14px;
  line-height: 1;
  opacity: 0.7;
}
.tag-chip-remove:hover { opacity: 1; }
.tag-input {
  border: none;
  background: transparent;
  color: var(--text-primary, #e0e0e0);
  font-size: var(--text-sm, 13px);
  outline: none;
  flex: 1;
  min-width: 120px;
}
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(ui): add tag input component for model name editing"
```

---

### Task 3: Provider List UI (Settings → Global tab)

**Files:**
- Modify: `clio/ui/static/src/editor-config.js`

**Architecture note:** In `renderConfig()`, the Global tab currently renders `state.configGlobal` via `_renderConfigForm()`. We intercept the `ai` section specifically: instead of calling `_renderConfigForm(globalData['ai'], 'ai', descs)`, we call a custom `_renderProviderList()` function.

- [ ] **Step 1: Understand the rendering flow in `renderConfig()`**

Current flow for Global tab (around line 258-261):
```javascript
const globalData = state.configGlobal || {};
contentHtml = _renderEnvEditor()
  + `<div class="config-form">${_renderConfigForm(globalData, '', descs)}</div>`;
```

This renders ALL sections of global config with the generic form. We need to:
1. Let `_renderConfigForm()` handle sections OTHER than `ai` normally
2. Replace the `ai` section with `_renderProviderList()`

Change to:
```javascript
contentHtml = _renderEnvEditor()
  + `<div class="config-form">${_renderConfigGlobal(globalData, descs)}</div>`;
```

Where `_renderConfigGlobal()` iterates sections and uses `_renderProviderList()` for `ai`, `_renderConfigForm()` for others.

- [ ] **Step 2: Add `_renderProviderList()` to `editor-config.js`**

```javascript
function _renderProviderList(providers, descs) {
  const providersObj = providers || {};
  const keys = Object.keys(providersObj);
  let html = '<fieldset class="config-fieldset"><legend>AI 模型列表</legend>';

  if (keys.length === 0) {
    html += '<div class="config-empty-state"><p class="muted">还没有注册任何 AI 模型</p><p class="hint">点击下方按钮添加一个 AI 厂商（如 Gemini、DeepSeek、通义千问等），然后在 Project 标签页中为任务绑定模型。</p></div>';
  }

  for (const name of keys) {
    const p = providersObj[name];
    const typeLabel = p.type === 'gemini' ? 'Gemini' : 'OpenAI 兼容';
    const hasModels = p.models && p.models.length > 0;
    const modelTags = hasModels
      ? p.models.map(m => `<span class="tag-chip tag-chip-sm">${escapeHtml(m)}</span>`).join(' ')
      : '<span class="warn">⚠️ 未注册模型</span>';

    html += `<div class="provider-card" data-provider="${escapeHtml(name)}">
      <div class="provider-card-header">
        <span class="provider-card-name">${escapeHtml(name)}</span>
        <span class="provider-card-type">${typeLabel}</span>
        <span class="provider-card-actions">
          <button class="btn-provider-edit" data-provider="${escapeHtml(name)}">编辑</button>
          <button class="btn-provider-delete" data-provider="${escapeHtml(name)}">删除</button>
        </span>
      </div>
      <div class="provider-card-body">
        <div class="provider-card-field"><span class="provider-card-label">类型</span><span>${typeLabel}</span></div>
        <div class="provider-card-field"><span class="provider-card-label">API 密钥</span><span>••••••••••<button class="btn-provider-show-key" data-provider="${escapeHtml(name)}">显示</button></span></div>
        ${p.type !== 'gemini' ? `<div class="provider-card-field"><span class="provider-card-label">接口地址</span><span>${escapeHtml(p.base_url || '(默认)')}</span></div>` : ''}
        <div class="provider-card-field"><span class="provider-card-label">模型</span><span class="provider-card-models">${modelTags}</span></div>
      </div>
    </div>`;
  }

  html += `<div style="margin-top:12px"><button id="btn-add-provider" class="btn-primary">${icon('plus', 14)} 添加 Provider</button></div>`;
  html += '</fieldset>';
  return html;
}
```

- [ ] **Step 3: Add provider modal HTML/JS functions**

```javascript
function _showProviderModal(providersObj, name, onSave) {
  const existing = name ? providersObj[name] : null;
  const isEdit = !!existing;
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center';

  const typeOptions = ['gemini', 'openai'].map(t =>
    `<option value="${t}"${existing?.type === t ? ' selected' : ''}>${t === 'gemini' ? 'Gemini（支持视频分析）' : 'OpenAI 兼容（纯文本，如 DeepSeek）'}</option>`
  ).join('');

  backdrop.innerHTML = `
    <div class="modal" style="background:var(--bg-surface,#1e1e1e);border:1px solid var(--border,#333);border-radius:8px;padding:24px;max-width:520px;width:90%;max-height:80vh;overflow-y:auto">
      <h3 style="margin:0 0 16px">${isEdit ? '编辑 Provider' : '添加 Provider'}</h3>
      <div class="form-group">
        <label class="form-label">名称 <span class="muted">（唯一标识符）</span></label>
        <input id="modal-provider-name" class="form-input" value="${escapeHtml(name || '')}" ${isEdit ? 'readonly' : ''} placeholder="如 my-gemini">
      </div>
      <div class="form-group">
        <label class="form-label">类型</label>
        <select id="modal-provider-type" class="form-input">${typeOptions}</select>
      </div>
      <div class="form-group">
        <label class="form-label">API 密钥</label>
        <div style="display:flex;gap:8px">
          <input id="modal-provider-key" class="form-input" type="password" placeholder="输入 API 密钥" style="flex:1">
          <button id="modal-key-toggle" class="btn-secondary">显示</button>
        </div>
        <span class="hint">密钥将通过 .env 文件存储，不会写入 config.yaml</span>
      </div>
      <div class="form-group" id="modal-base-url-group" style="${existing?.type === 'gemini' && !isEdit ? 'display:none' : ''}">
        <label class="form-label">接口地址</label>
        <input id="modal-provider-base-url" class="form-input" value="${escapeHtml(existing?.base_url || '')}" placeholder="https://api.openai.com/v1">
        <span class="hint">仅 OpenAI 兼容类型需要填写</span>
      </div>
      <div class="form-group">
        <label class="form-label">模型列表 <span class="muted">（按回车添加）</span></label>
        <div id="modal-provider-models"></div>
      </div>
      <div style="display:flex;gap:8px;justify-content:end;margin-top:16px">
        <button id="modal-cancel" class="btn-secondary">取消</button>
        <button id="modal-save" class="btn-primary">${isEdit ? '保存修改' : '添加'}</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  // Tag input for models
  const modelsContainer = backdrop.querySelector('#modal-provider-models');
  const modelsList = existing?.models ? [...existing.models] : [];
  _renderTagInput(modelsContainer, modelsList, () => {});

  // Type toggle → show/hide base URL
  backdrop.querySelector('#modal-provider-type').onchange = (e) => {
    const grp = backdrop.querySelector('#modal-base-url-group');
    grp.style.display = e.target.value === 'gemini' ? 'none' : '';
  };

  // Key visibility toggle
  const keyInput = backdrop.querySelector('#modal-provider-key');
  backdrop.querySelector('#modal-key-toggle').onclick = () => {
    const isPwd = keyInput.type === 'password';
    keyInput.type = isPwd ? 'text' : 'password';
    backdrop.querySelector('#modal-key-toggle').textContent = isPwd ? '隐藏' : '显示';
  };

  // Save
  backdrop.querySelector('#modal-save').onclick = async () => {
    const newName = backdrop.querySelector('#modal-provider-name').value.trim();
    const newType = backdrop.querySelector('#modal-provider-type').value;
    const newKey = backdrop.querySelector('#modal-provider-key').value.trim();
    const newBaseUrl = backdrop.querySelector('#modal-provider-base-url').value.trim();

    if (!newName) { setStatus('请填写 Provider 名称', 'warn'); return; }
    if (isEdit && newName !== name) { setStatus('名称不可修改（如需重命名请删除后重建）', 'warn'); return; }
    if (!isEdit && providersObj[newName]) { setStatus(`Provider "${newName}" 已存在`, 'warn'); return; }

    // Save API key to .env if provided
    if (newKey) {
      const envName = newName.toUpperCase() + '_API_KEY';
      try {
        // Read existing .env, update the specific var, write back
        const existing = await api('GET', '/api/env');
        let envContent = existing.content || '';
        const lines = envContent.split('\n');
        let found = false;
        for (let i = 0; i < lines.length; i++) {
          if (lines[i].startsWith(envName + '=')) {
            lines[i] = `${envName}=${newKey}`;
            found = true;
            break;
          }
        }
        if (!found) lines.push(`${envName}=${newKey}`);
        const envResult = await api('PUT', '/api/env', { content: lines.join('\n') });
        if (!envResult.ok) { setStatus('API 密钥保存失败: ' + (envResult.error || ''), 'err'); return; }
      } catch (e) { setStatus('API 密钥保存失败: ' + e.message, 'err'); return; }
    }

    // Update provider data
    const envName = newName.toUpperCase() + '_API_KEY';
    const providerData = {
      type: newType,
      api_key_env: envName,
      api_key: '',
      base_url: newBaseUrl || '',
      models: modelsList,
    };

    if (isEdit) {
      // Preserve existing api_key_env and other fields if key unchanged
      if (!newKey) {
        delete providerData.api_key_env;
        delete providerData.api_key;
      }
      Object.assign(providersObj[name], providerData);
    } else {
      providersObj[newName] = {
        name: newName,
        type: newType,
        api_key_env: envName,
        api_key: '',
        base_url: newBaseUrl || '',
        models: [...modelsList],
      };
    }

    markDirty();
    backdrop.remove();
    onSave();
  };

  backdrop.querySelector('#modal-cancel').onclick = () => backdrop.remove();
  backdrop.onclick = (e) => { if (e.target === backdrop) backdrop.remove(); };
}
```

- [ ] **Step 4: Modify `renderConfig()` to use custom AI renderer for Global tab**

Replace lines 257-261 in `editor-config.js`:

```javascript
  } else if (active === 'global') {
    const globalData = state.configGlobal || {};
    contentHtml = _renderEnvEditor()
      + `<div class="config-form">${_renderConfigForm(globalData, '', descs)}</div>`;
```

With:

```javascript
  } else if (active === 'global') {
    const globalData = state.configGlobal || {};
    contentHtml = _renderEnvEditor()
      + `<div class="config-form">${_renderConfigGlobal(globalData, descs)}</div>`;
  }
```

And add `_renderConfigGlobal()`:

```javascript
function _renderConfigGlobal(globalData, descs) {
  let html = '';
  for (const [key, val] of Object.entries(globalData)) {
    if (key === 'ai') {
      // Custom renderer for providers (skip generic for ai section)
      continue;
    }
    html += _renderConfigForm({ [key]: val }, '', descs);
  }
  // Add provider list as a dedicated section at the bottom
  html += _renderProviderList(globalData.ai?.providers || {}, descs);
  return html;
}
```

- [ ] **Step 5: Attach event handlers for provider list buttons**

In `renderConfig()`, after rendering the Global tab content (~line 296-297):

```javascript
  if (active === 'global') {
    _attachConfigForm(pane, state.configGlobal || {}, descs);
    _attachEnvEditor();
```

Change to:

```javascript
  if (active === 'global') {
    _attachConfigForm(pane, state.configGlobal || {}, descs);
    _attachEnvEditor();
    _attachProviderListHandlers(pane, state.configGlobal?.ai?.providers || {});
  }
```

Add `_attachProviderListHandlers()`:

```javascript
function _attachProviderListHandlers(pane, providersObj) {
  const reRender = () => renderConfig();

  // Edit buttons
  pane.querySelectorAll('.btn-provider-edit').forEach(btn => {
    btn.onclick = () => {
      const name = btn.dataset.provider;
      _showProviderModal(providersObj, name, reRender);
    };
  });

  // Delete buttons
  pane.querySelectorAll('.btn-provider-delete').forEach(btn => {
    btn.onclick = async () => {
      const name = btn.dataset.provider;
      // Check if any task references this provider
      const tasks = state.configProject?.ai?.tasks || {};
      const refs = Object.entries(tasks)
        .filter(([_, t]) => t.provider === name)
        .map(([k]) => k);
      if (refs.length > 0) {
        if (!confirm(`以下任务正在使用 "${name}"：${refs.join('、')}。确定删除？删除后这些任务将无法运行。`)) return;
      } else {
        if (!confirm(`确定删除 Provider "${name}"？`)) return;
      }
      delete providersObj[name];
      markDirty();
      reRender();
    };
  });

  // Add button
  const addBtn = pane.querySelector('#btn-add-provider');
  if (addBtn) {
    addBtn.onclick = () => _showProviderModal(providersObj, null, reRender);
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(ui): add provider list UI with add/edit/delete in Settings Global tab"
```

---

### Task 4: Task Binding UI (Settings → Project tab)

**Files:**
- Modify: `clio/ui/static/src/editor-config.js`

- [ ] **Step 1: Understand the Project tab rendering flow**

Current flow for Project tab (~line 255-256):
```javascript
const projectData = state.configProject || {};
contentHtml = `<div class="config-form">${_renderConfigForm(projectData, '', descs)}</div>`;
```

We need to intercept the `ai` section similarly to Global tab.

- [ ] **Step 2: Add `_renderTaskBinding()` function**

```javascript
const TASK_LABELS = {
  video_analyze: '视频分析',
  voiceover: '口播文案',
  vlog_plan: 'vlog 剪辑规划',
  refine_text: '文本精修',
};

const TASK_DESCRIPTIONS = {
  video_analyze: '分析视频内容（场景、物体、人物、动作、地点），需多模态模型',
  voiceover: '根据分析结果生成口播文案',
  vlog_plan: '根据所有素材生成剪辑顺序和时间轴',
  refine_text: '对已有文案进行润色和修正（默认跟随视频分析）',
};

function _renderTaskBinding(tasks, providersObj, descs) {
  const taskKeys = ['video_analyze', 'voiceover', 'vlog_plan', 'refine_text'];
  const providerNames = Object.keys(providersObj || {});
  const hasProviders = providerNames.length > 0;
  const geminiProviders = providerNames.filter(n => providersObj[n]?.type === 'gemini');
  const textProviders = providerNames; // all providers for text tasks

  let html = '<fieldset class="config-fieldset"><legend>AI 任务绑定</legend>';

  // Empty state: no providers configured
  if (!hasProviders) {
    html += `<div class="config-empty-state">
      <p class="warn">⚠️ 还没有配置 AI 模型</p>
      <p class="hint">请先在<span style="cursor:pointer;color:var(--accent);text-decoration:underline" id="goto-global-providers">Global 配置 → AI 模型列表</span>中添加 Provider。</p>
    </div>`;
    html += '</fieldset>';
    return html;
  }

  for (const taskKey of taskKeys) {
    const task = tasks[taskKey] || { provider: '', model: '' };
    const isRefine = taskKey === 'refine_text';
    const isVideo = taskKey === 'video_analyze';
    const availableProviders = isVideo ? geminiProviders : textProviders;
    const selectedProvider = task.provider || '';
    const providerModels = providersObj[selectedProvider]?.models || [];

    // refine_text auto-follow logic
    const refineFollow = isRefine && !tasks[taskKey];

    html += `<div class="task-binding-card" data-task="${taskKey}">`;
    html += `<div class="task-binding-header">
      <span class="task-binding-name">${TASK_LABELS[taskKey] || taskKey}</span>
      <span class="muted">(${taskKey})</span>
      ${_renderTooltip(`ai.tasks.{name}`, TASK_DESCRIPTIONS[taskKey] || '')}
    </div>`;

    if (isRefine) {
      html += `<label class="config-field config-bool refine-follow-check">
        <input type="checkbox" class="refine-follow-cb" ${refineFollow ? 'checked' : ''}>
        <span>跟随视频分析（使用 video_analyze 相同的 Provider 和模型）</span>
      </label>`;
    }

    if (!refineFollow) {
      // Provider dropdown
      html += `<div class="task-binding-row"><span class="task-binding-label">Provider</span>
        <select class="task-provider-select" data-task="${taskKey}">
          <option value="">-- 请选择 --</option>
          ${availableProviders.map(n =>
            `<option value="${escapeHtml(n)}" ${selectedProvider === n ? 'selected' : ''}>${escapeHtml(n)} (${providersObj[n]?.type === 'gemini' ? 'Gemini' : 'OpenAI'})</option>`
          ).join('')}
        </select>
        ${availableProviders.length === 0 && isVideo ? '<span class="warn" style="font-size:var(--text-xs)">需要 type=gemini 的 Provider</span>' : ''}
      </div>`;

      // Model dropdown
      const hasProviderModels = providerModels.length > 0;
      html += `<div class="task-binding-row"><span class="task-binding-label">模型</span>`;
      if (hasProviderModels) {
        html += `<select class="task-model-select" data-task="${taskKey}">
          <option value="">-- 请选择 --</option>
          ${providerModels.map(m =>
            `<option value="${escapeHtml(m)}" ${task.model === m ? 'selected' : ''}>${escapeHtml(m)}</option>`
          ).join('')}
        </select>`;
      } else if (selectedProvider) {
        html += `<span class="warn" style="font-size:var(--text-xs)">该 Provider 没有注册可用模型，请先在 Global 配置中<a href="#" class="edit-provider-link" data-provider="${escapeHtml(selectedProvider)}" style="color:var(--accent)">编辑 Provider</a></span>`;
      } else {
        html += `<span class="muted" style="font-size:var(--text-xs)">请先选择 Provider</span>`;
      }
      html += '</div>';
    } else {
      // Following video_analyze: show read-only info
      const va = tasks['video_analyze'];
      if (va) {
        html += `<div class="task-binding-row"><span class="task-binding-label">继承自</span><span class="muted">${escapeHtml(va.provider)} / ${escapeHtml(va.model)}</span></div>`;
      }
    }

    html += '</div>';
  }

  html += '</fieldset>';
  return html;
}
```

- [ ] **Step 3: Modify `renderConfig()` to use custom AI renderer for Project tab**

Replace lines 254-256:
```javascript
  if (active === 'project') {
    const projectData = state.configProject || {};
    contentHtml = `<div class="config-form">${_renderConfigForm(projectData, '', descs)}</div>`;
```

With:
```javascript
  if (active === 'project') {
    const projectData = state.configProject || {};
    contentHtml = `<div class="config-form">${_renderConfigProject(projectData, state.configGlobal, descs)}</div>`;
```

Add `_renderConfigProject()`:
```javascript
function _renderConfigProject(projectData, globalData, descs) {
  let html = '';
  for (const [key, val] of Object.entries(projectData)) {
    if (key === 'ai') {
      continue; // handled by custom renderer
    }
    html += _renderConfigForm({ [key]: val }, '', descs);
  }
  html += _renderTaskBinding(
    projectData.ai?.tasks || {},
    globalData?.ai?.providers || {},
    descs || {},
  );
  return html;
}
```

- [ ] **Step 4: Attach event handlers for task binding**

In `renderConfig()`, after the Project tab handler (~line 298-300):
```javascript
  } else if (active === 'project') {
    _attachConfigForm(pane, state.configProject || {}, descs);
    _attachContextTemplate(pane);
```

Change to:
```javascript
  } else if (active === 'project') {
    _attachConfigForm(pane, state.configProject || {}, descs);
    _attachContextTemplate(pane);
    _attachTaskBindingHandlers(pane, state.configProject);
  }
```

Add `_attachTaskBindingHandlers()`:
```javascript
function _attachTaskBindingHandlers(pane, projectCfg) {
  if (!projectCfg) return;
  if (!projectCfg.ai) projectCfg.ai = {};
  if (!projectCfg.ai.tasks) projectCfg.ai.tasks = {};

  const providers = state.configGlobal?.ai?.providers || {};

  // Provider dropdown change → update model dropdown
  pane.querySelectorAll('.task-provider-select').forEach(sel => {
    sel.onchange = () => {
      const taskKey = sel.dataset.task;
      const provider = sel.value;
      const models = providers[provider]?.models || [];
      // Create/update task entry
      if (!projectCfg.ai.tasks[taskKey]) projectCfg.ai.tasks[taskKey] = { provider: '', model: '' };
      projectCfg.ai.tasks[taskKey].provider = provider;
      projectCfg.ai.tasks[taskKey].model = ''; // Reset model when provider changes
      markDirty();
      renderConfig(); // re-render to update model dropdown
    };
  });

  // Model dropdown change
  pane.querySelectorAll('.task-model-select').forEach(sel => {
    sel.onchange = () => {
      const taskKey = sel.dataset.task;
      projectCfg.ai.tasks[taskKey].model = sel.value;
      markDirty();
    };
  });

  // Refine text follow checkbox
  pane.querySelectorAll('.refine-follow-cb').forEach(cb => {
    cb.onchange = () => {
      if (cb.checked) {
        // Remove refine_text from project config → triggers auto-fallback
        delete projectCfg.ai.tasks.refine_text;
      } else {
        // Create refine_text with independent settings
        projectCfg.ai.tasks.refine_text = { provider: '', model: '' };
      }
      markDirty();
      renderConfig();
    };
  });

  // Cross-tab navigation link
  const gotoBtn = pane.querySelector('#goto-global-providers');
  if (gotoBtn) {
    gotoBtn.onclick = () => {
      state.configTab = 'global';
      state.dirty = false;
      updateSaveBtn();
      renderConfig();
    };
  }

  // Edit provider link in model empty state
  pane.querySelectorAll('.edit-provider-link').forEach(link => {
    link.onclick = (e) => {
      e.preventDefault();
      const pName = link.dataset.provider;
      state.configTab = 'global';
      state.dirty = false;
      updateSaveBtn();
      renderConfig();
      // Auto-open the edit modal for this provider
      setTimeout(() => {
        const editBtn = document.querySelector(`.btn-provider-edit[data-provider="${escapeHtml(pName)}"]`);
        if (editBtn) editBtn.click();
      }, 100);
    };
  });
}
```

- [ ] **Step 5: Update save flow for Project tab**

The existing save flow in `editor.js` (the `save()` function) needs to handle the new structure correctly. Currently it calls `PUT /api/config/project` with `state.configProject`. Since we mutate `state.configProject.ai.tasks` directly, the existing save should work as-is. Verify:

```javascript
// In editor.js save() — this should already work:
const r = await api('PUT', '/api/config/project', state.configProject);
```

No changes needed to the save flow.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(ui): add task binding panel with dropdowns in Settings Project tab"
```

---

### Task 5: CSS styles for provider cards, modals, empty states

**Files:**
- Modify: `clio/ui/static/style.css`

- [ ] **Step 1: Add provider card styles**

```css
/* Provider cards (model registry) */
.provider-card {
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  background: var(--bg-surface, #1e1e1e);
}
.provider-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.provider-card-name {
  font-weight: 600;
  font-size: var(--text-sm, 13px);
}
.provider-card-type {
  font-size: var(--text-xs, 12px);
  color: var(--text-secondary, #999);
  background: var(--bg, #2a2a2a);
  padding: 2px 8px;
  border-radius: 10px;
}
.provider-card-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.provider-card-actions button {
  background: none;
  border: 1px solid var(--border, #555);
  color: var(--text-primary, #e0e0e0);
  padding: 2px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--text-xs, 12px);
}
.provider-card-actions button:hover {
  background: var(--bg-hover, #333);
}
.provider-card-body {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 4px 8px;
  font-size: var(--text-sm, 13px);
}
.provider-card-label {
  color: var(--text-secondary, #999);
}
.provider-card-models {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag-chip-sm {
  font-size: var(--text-xs, 11px);
  padding: 1px 6px;
}

/* Task binding cards */
.task-binding-card {
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  background: var(--bg-surface, #1e1e1e);
}
.task-binding-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: var(--text-sm, 13px);
}
.task-binding-name {
  font-size: var(--text-sm, 13px);
}
.task-binding-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: var(--text-sm, 13px);
}
.task-binding-label {
  min-width: 70px;
  color: var(--text-secondary, #999);
}
.task-binding-row select {
  flex: 1;
  max-width: 300px;
  background: var(--bg, #2a2a2a);
  color: var(--text-primary, #e0e0e0);
  border: 1px solid var(--border, #555);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: var(--text-sm, 13px);
}
.refine-follow-check {
  margin-bottom: 8px;
  font-size: var(--text-sm, 13px);
}

/* Modal styles */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  background: var(--bg-surface, #1e1e1e);
  border: 1px solid var(--border, #333);
  border-radius: 8px;
  padding: 24px;
  max-width: 520px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}
.form-group {
  margin-bottom: 12px;
}
.form-label {
  display: block;
  margin-bottom: 4px;
  font-size: var(--text-sm, 13px);
  font-weight: 500;
}
.form-input {
  width: 100%;
  padding: 6px 10px;
  background: var(--bg, #2a2a2a);
  color: var(--text-primary, #e0e0e0);
  border: 1px solid var(--border, #555);
  border-radius: 4px;
  font-size: var(--text-sm, 13px);
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: var(--accent, #4a9eff);
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "style(ui): add CSS for provider cards, task binding, modals, tag input"
```

---

### Task 6: Integration & full test suite

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest clio/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 970+ passed (existing tests + new tests added).

- [ ] **Step 2: Verify build/lint**

```bash
ruff check .
ruff format . --check
```

- [ ] **Step 3: Manual verification flow**

1. Start server: `python main.py serve --no-browser`
2. Open browser → Settings tab → Global sub-tab
3. Verify: AI section shows provider cards instead of generic form
4. Verify: Add Provider modal works (name, type, API key, base URL, models tag input)
5. Verify: Edit Provider works
6. Verify: Delete Provider with task reference warning
7. Switch to Project sub-tab
8. Verify: AI section shows task binding cards with provider/model dropdowns
9. Verify: video_analyze only shows gemini-type providers
10. Verify: Model dropdown shows models from selected provider
11. Verify: refine_text follow/unfollow checkbox works
12. Verify: Cross-tab navigation link works from Project→Global
13. Verify: Save config → reload → data persists

- [ ] **Step 4: Commit any remaining fixes**

```bash
git add -A
git commit -m "fix(ui): address integration issues in model registry UI"
```

- [ ] **Step 5: Update ROADMAP.md** — mark R-017a through R-017f as done

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "docs: mark R-017 sub-tasks complete in ROADMAP.md"
```

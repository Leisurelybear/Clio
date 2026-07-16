/**
 * Pure helpers for editor save / tab-switch guards.
 */

/**
 * Decide what Ctrl+S / Save should do for the current entity+tab.
 * @returns {{ action: 'texts'|'voiceover'|'plan'|'config'|'noop', configTab?: string, reason?: string }}
 */
export function resolveEditorSaveTarget({ entity, tab, configTab } = {}) {
  if (entity === 'run' || entity === 'logs' || entity === 'tokens') {
    return { action: 'noop', reason: '当前视图不需要保存' };
  }
  if (entity === 'config') {
    const ct = configTab || 'global';
    if (ct === 'global' || ct === 'project') {
      return { action: 'config', configTab: ct };
    }
    return { action: 'noop', reason: '合并视图为只读，无法保存' };
  }
  if (entity === 'plan') {
    return { action: 'plan' };
  }
  // video entity (default)
  if (tab === 'texts') return { action: 'texts' };
  if (tab === 'voiceover') return { action: 'voiceover' };
  return {
    action: 'noop',
    reason: '当前页无可保存内容（请回到「分析结果」或「口播」后再保存）',
  };
}

/** True when switching editor tabs would drop unsaved in-memory edits if user continues. */
export function shouldConfirmDirtyTabSwitch({ dirty, fromTab, toTab } = {}) {
  if (!dirty) return false;
  if (!toTab || toTab === fromTab) return false;
  return true;
}

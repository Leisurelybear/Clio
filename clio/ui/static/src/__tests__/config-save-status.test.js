import { describe, it, expect } from 'vitest';
import { configSaveStatusForTab } from '../editor-plan.js';

describe('configSaveStatusForTab', () => {
  it('says project config changes take effect immediately', () => {
    const result = configSaveStatusForTab('project');

    expect(result.level).toBe('ok');
    expect(result.message).toContain('项目配置');
    expect(result.message).toContain('立即生效');
  });

  it('says global config changes are hot reloaded without restart wording', () => {
    const result = configSaveStatusForTab('global');

    expect(result.level).toBe('ok');
    expect(result.message).toContain('全局配置');
    expect(result.message).toContain('热加载');
    expect(result.message).not.toContain('重启');
  });
});

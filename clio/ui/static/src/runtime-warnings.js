const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);

function isLocalHost(hostname) {
  return LOCAL_HOSTS.has(String(hostname || '').toLowerCase());
}

function buildRuntimeWarnings({ config = {}, hostname = '', hasToken = false } = {}) {
  const warnings = [];
  const debugPrintPrompt = Boolean(config?.ai?.debug_print_prompt);
  if (debugPrintPrompt) {
    warnings.push({
      id: 'debug-prompt',
      level: 'warning',
      text: 'ai.debug_print_prompt=true：AI 调用会把完整 prompt 写入日志/控制台，可能包含行程上下文或临时指令。',
    });
  }

  if (!isLocalHost(hostname)) {
    if (hasToken) {
      warnings.push({
        id: 'lan-host',
        level: 'warning',
        text: `当前通过 ${hostname} 访问 UI，服务可能暴露在局域网内。`,
      });
    } else {
      warnings.push({
        id: 'lan-no-token',
        level: 'danger',
        text: `当前通过 ${hostname} 访问 UI，且浏览器没有 API token。建议启用 token 后再在局域网访问。`,
      });
    }
  }

  return warnings;
}

function renderRuntimeWarnings(container, warnings) {
  if (!container) return;
  container.replaceChildren();
  container.hidden = warnings.length === 0;
  for (const warning of warnings) {
    const item = document.createElement('div');
    item.className = `runtime-warning ${warning.level}`;
    item.dataset.warningId = warning.id;
    item.textContent = warning.text;
    container.appendChild(item);
  }
}

function updateRuntimeWarnings(config) {
  const container = document.getElementById('runtime-warnings');
  const warnings = buildRuntimeWarnings({
    config,
    hostname: window.location.hostname,
    hasToken: Boolean(sessionStorage.getItem('api_token')),
  });
  renderRuntimeWarnings(container, warnings);
}

export { buildRuntimeWarnings, renderRuntimeWarnings, updateRuntimeWarnings };

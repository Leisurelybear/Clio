/** Pure helpers: session log level inference + client-side filter (R-027). */

/** @typedef {'debug'|'info'|'warn'|'error'} LogLevel */

const LEVEL_ORDER = { debug: 0, info: 1, warn: 2, error: 3 };

/**
 * Infer a log level from a free-form session log line.
 * Prefer explicit logging tags, then Chinese/UI heuristics used by Clio prints.
 * @param {string} line
 * @returns {LogLevel}
 */
export function inferLogLevel(line) {
  const s = String(line ?? '');
  if (!s) return 'info';

  // Explicit python logging / structured tags (no leading \b — tag often starts the line)
  if (/\[(ERROR|CRITICAL|FATAL)\]/i.test(s)) return 'error';
  if (/\[WARN(?:ING)?\]/i.test(s)) return 'warn';
  if (/\[DEBUG\]/i.test(s)) return 'debug';
  if (/\[INFO\]/i.test(s)) return 'info';

  // Error heuristics (pipeline / UI Chinese)
  if (
    /Traceback \(most recent call last\)/i.test(s)
    || /\bException\b/.test(s)
    || /\bERROR\b/.test(s)
    || /✗|失败|错误|出错|pipeline failed|HTTP \d{3}/i.test(s)
  ) {
    return 'error';
  }

  // Warning heuristics
  if (
    /⚠|警告|\bWARN(?:ING)?\b/i.test(s)
    || /\[跳过|跳过\]|\[跳过/.test(s)
    || /\bskip(?:ped|ping)?\b/i.test(s)
  ) {
    return 'warn';
  }

  return 'info';
}

/**
 * @param {string} line
 * @param {{ query?: string, level?: string }} [opts]
 *   level: '' | 'all' | LogLevel — empty/all = no level filter
 * @returns {boolean}
 */
export function lineMatchesLogFilter(line, opts = {}) {
  const query = String(opts.query ?? '').trim();
  const level = String(opts.level ?? '').trim().toLowerCase();

  if (level && level !== 'all') {
    if (inferLogLevel(line) !== level) return false;
  }
  if (query) {
    if (!String(line ?? '').toLowerCase().includes(query.toLowerCase())) return false;
  }
  return true;
}

/**
 * @param {string[]} lines
 * @param {{ query?: string, level?: string }} [opts]
 * @returns {string[]}
 */
export function filterLogLines(lines, opts = {}) {
  const arr = Array.isArray(lines) ? lines : [];
  return arr.filter((line) => lineMatchesLogFilter(line, opts));
}

/**
 * CSS class suffix for a level.
 * @param {string} line
 * @returns {string} e.g. "log-level-error"
 */
export function logLineClass(line) {
  return `log-level-${inferLogLevel(line)}`;
}

export { LEVEL_ORDER };

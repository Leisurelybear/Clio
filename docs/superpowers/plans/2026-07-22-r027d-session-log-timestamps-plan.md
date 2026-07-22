# R-027d Session Log Timestamps (slim) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store a capture timestamp on every session log entry and show / filter recent time in the 会话日志 UI (slim R-027d only).

**Architecture:** `session_log` ring buffer holds `{ts: float, text: str}` objects; `GET /api/logs` returns those objects. Frontend normalizes entries, paints muted `HH:MM:SS`, and ANDs optional `sinceMs` with existing keyword/level filters. Disk hourly logging is untouched.

**Tech Stack:** Python 3.11+ / pytest; ES modules + Vitest; stdlib HTTP UI (no build step).

## Global Constraints

- Scope is **slim R-027d only** — no R-027e history files, no from–to pickers, no server-side filter query params.
- API always returns entry objects after Task 1 (no dual string[] format).
- One feature per commit; English commit messages; Chinese UI copy OK.
- Prefer pure helpers in `logs-filter.js`; keep `renderLogs` thin.
- Do not change `_HourlyFileHandler` / Tee disk line format.

---

## File map

| File | Responsibility |
| --- | --- |
| `clio/session_log.py` | Timestamped ring buffer write/read/clear |
| `clio/tests/test_session_log.py` | Backend unit tests |
| `clio/ui/static/src/logs-filter.js` | normalize / format time / filter with sinceMs |
| `clio/ui/static/src/__tests__/logs-filter.test.js` | Vitest for helpers |
| `clio/ui/static/src/editor-config.js` | `renderLogs` DOM + chips + buffer type |
| `clio/ui/static/style.css` | `.log-line-time` muted style |
| `ROADMAP.md` | Mark R-027d done |

No new routes; `_handle_get_logs` stays a thin wrapper around `read`.

---

### Task 1: Timestamped `session_log`

**Files:**
- Modify: `clio/session_log.py`
- Modify: `clio/tests/test_session_log.py`

**Interfaces:**
- Consumes: none (stdlib `time`, `threading`)
- Produces:
  - `write(line: str) -> None` — appends `{"ts": float, "text": str}`
  - `read(offset: int = 0) -> dict[str, Any]` — `{"logs": list[dict], "total": int}`
  - `clear() -> None`

- [ ] **Step 1: Rewrite tests for object entries (expect FAIL on current string buffer)**

Replace body of `clio/tests/test_session_log.py` with:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest

from clio.session_log import _logs, clear, read, write


@pytest.fixture(autouse=True)
def _clear_logs():
    _logs.clear()
    yield
    _logs.clear()


def test_write_adds_entry_with_ts_and_text():
    write("hello")
    assert len(_logs) == 1
    entry = _logs[0]
    assert entry["text"] == "hello"
    assert isinstance(entry["ts"], float)
    assert entry["ts"] > 0


def test_write_adds_multiple_entries():
    write("a")
    write("b")
    write("c")
    assert [e["text"] for e in _logs] == ["a", "b", "c"]
    assert _logs[0]["ts"] <= _logs[1]["ts"] <= _logs[2]["ts"]


def test_read_returns_all_objects():
    write("x")
    write("y")
    result = read()
    assert result["total"] == 2
    assert result["logs"][0]["text"] == "x"
    assert result["logs"][1]["text"] == "y"
    assert isinstance(result["logs"][0]["ts"], float)


def test_read_empty():
    result = read()
    assert result == {"logs": [], "total": 0}


def test_read_with_offset():
    write("a")
    write("b")
    write("c")
    result = read(offset=1)
    assert result["total"] == 3
    assert [e["text"] for e in result["logs"]] == ["b", "c"]


def test_read_with_offset_beyond_length():
    write("a")
    result = read(offset=10)
    assert result == {"logs": [], "total": 1}


def test_write_enforces_max_limit():
    with patch("clio.session_log._MAX", 5):
        for i in range(10):
            write(str(i))
    assert [e["text"] for e in _logs] == ["5", "6", "7", "8", "9"]


def test_write_does_not_remove_below_limit():
    with patch("clio.session_log._MAX", 5):
        for i in range(5):
            write(str(i))
    assert [e["text"] for e in _logs] == ["0", "1", "2", "3", "4"]


def test_clear_empties_logs():
    write("a")
    write("b")
    assert len(read()["logs"]) == 2
    clear()
    assert read() == {"logs": [], "total": 0}


def test_read_returns_copy_not_reference():
    write("a")
    result = read()
    result["logs"].append({"ts": 0.0, "text": "bogus"})
    assert len(_logs) == 1
    assert _logs[0]["text"] == "a"


def test_write_uses_time_time_for_ts():
    with patch("clio.session_log.time.time", return_value=1721606400.5):
        write("clocked")
    assert _logs[0]["ts"] == 1721606400.5
    assert _logs[0]["text"] == "clocked"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest clio/tests/test_session_log.py -v`

Expected: FAIL (e.g. `TypeError` / assert on string vs dict, or `clear` not imported if still using `_logs.clear` only — tests import `clear`).

- [ ] **Step 3: Implement `session_log.py`**

Replace `clio/session_log.py` with:

```python
from __future__ import annotations

import threading
import time
from typing import Any

_logs: list[dict[str, Any]] = []
_lock = threading.Lock()
_MAX = 10000


def write(line: str) -> None:
    entry = {"ts": time.time(), "text": line}
    with _lock:
        _logs.append(entry)
        if len(_logs) > _MAX:
            del _logs[: len(_logs) - _MAX]


def read(offset: int = 0) -> dict[str, Any]:
    with _lock:
        return {"logs": list(_logs[offset:]), "total": len(_logs)}


def clear() -> None:
    with _lock:
        _logs.clear()
```

Note: `clio/log.py` Tee already calls `session_log.write(message.rstrip())` with a string — no Tee change required.

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest clio/tests/test_session_log.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add clio/session_log.py clio/tests/test_session_log.py
git commit -m "$(cat <<'EOF'
feat(session_log): store timestamped log entries

Session ring buffer holds {ts, text} so the UI can show write time
and filter by recent windows (R-027d).
EOF
)"
```

---

### Task 2: Pure filter helpers (normalize, time, sinceMs)

**Files:**
- Modify: `clio/ui/static/src/logs-filter.js`
- Modify: `clio/ui/static/src/__tests__/logs-filter.test.js`

**Interfaces:**
- Consumes: existing `inferLogLevel(line: string)`
- Produces:
  - `normalizeLogEntry(item: unknown) -> { ts: number|null, text: string }`
  - `formatLogTime(ts: number|null|undefined) -> string`  // local HH:MM:SS or ""
  - `entryMatchesLogFilter(entry, opts?: { query?, level?, sinceMs? }) -> boolean`
  - `filterLogEntries(entries, opts?) -> Array<{ts,text}>`
  - Keep: `lineMatchesLogFilter`, `filterLogLines` (normalize first; same opts + optional sinceMs)

- [ ] **Step 1: Add failing Vitest cases**

Append to `clio/ui/static/src/__tests__/logs-filter.test.js` (update imports at top):

```javascript
import {
  inferLogLevel,
  lineMatchesLogFilter,
  filterLogLines,
  logLineClass,
  normalizeLogEntry,
  formatLogTime,
  entryMatchesLogFilter,
  filterLogEntries,
} from '../logs-filter.js';
```

Add describe blocks (keep existing tests):

```javascript
describe('normalizeLogEntry', () => {
  it('passes through object entries', () => {
    expect(normalizeLogEntry({ ts: 1.5, text: 'hi' })).toEqual({ ts: 1.5, text: 'hi' });
  });

  it('wraps plain strings with null ts', () => {
    expect(normalizeLogEntry('raw')).toEqual({ ts: null, text: 'raw' });
  });

  it('handles null/undefined', () => {
    expect(normalizeLogEntry(null)).toEqual({ ts: null, text: '' });
  });
});

describe('formatLogTime', () => {
  it('returns empty for invalid ts', () => {
    expect(formatLogTime(null)).toBe('');
    expect(formatLogTime(undefined)).toBe('');
    expect(formatLogTime(NaN)).toBe('');
  });

  it('formats local HH:MM:SS for a fixed epoch', () => {
    // 2024-07-22 00:00:00 UTC — assert shape only (timezone-dependent wall clock)
    const s = formatLogTime(1721606400);
    expect(s).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe('entryMatchesLogFilter sinceMs', () => {
  const now = 1_000_000_000_000; // ms
  const recent = { ts: (now - 60_000) / 1000, text: '[INFO] recent' };
  const old = { ts: (now - 600_000) / 1000, text: '[INFO] old' };
  const noTs = { ts: null, text: '[INFO] unknown' };

  it('keeps all when sinceMs absent', () => {
    expect(entryMatchesLogFilter(recent, {})).toBe(true);
    expect(entryMatchesLogFilter(old, {})).toBe(true);
  });

  it('keeps only entries within window', () => {
    const opts = { sinceMs: 5 * 60 * 1000, nowMs: now };
    expect(entryMatchesLogFilter(recent, opts)).toBe(true);
    expect(entryMatchesLogFilter(old, opts)).toBe(false);
  });

  it('drops null ts when time filter active', () => {
    expect(entryMatchesLogFilter(noTs, { sinceMs: 60_000, nowMs: now })).toBe(false);
  });

  it('ANDs with level and query', () => {
    const err = { ts: (now - 10_000) / 1000, text: '[ERROR] compress failed' };
    expect(entryMatchesLogFilter(err, {
      sinceMs: 60_000, nowMs: now, level: 'error', query: 'compress',
    })).toBe(true);
    expect(entryMatchesLogFilter(err, {
      sinceMs: 60_000, nowMs: now, level: 'error', query: 'plan',
    })).toBe(false);
  });
});

describe('filterLogEntries', () => {
  it('filters list by sinceMs', () => {
    const now = 2_000_000_000_000;
    const entries = [
      { ts: (now - 10_000) / 1000, text: 'a' },
      { ts: (now - 999_999_000) / 1000, text: 'b' },
    ];
    expect(filterLogEntries(entries, { sinceMs: 60_000, nowMs: now }).map((e) => e.text)).toEqual(['a']);
  });
});

describe('lineMatchesLogFilter with sinceMs on strings', () => {
  it('still filters plain strings by level/query', () => {
    expect(lineMatchesLogFilter('[ERROR] x', { level: 'error' })).toBe(true);
  });
});
```

**Note on testability:** `entryMatchesLogFilter` accepts optional `nowMs` so tests are deterministic. Production UI omits `nowMs` and uses `Date.now()`.

- [ ] **Step 2: Run Vitest — expect FAIL**

Run: `cd clio/ui/static && npm test -- --run src/__tests__/logs-filter.test.js`

Expected: FAIL — `normalizeLogEntry` not exported / not a function.

- [ ] **Step 3: Implement helpers in `logs-filter.js`**

Replace / extend `clio/ui/static/src/logs-filter.js` so the full file is:

```javascript
/** Pure helpers: session log level inference + client-side filter (R-027 / R-027d). */

/** @typedef {'debug'|'info'|'warn'|'error'} LogLevel */
/** @typedef {{ ts: number|null, text: string }} LogEntry */

const LEVEL_ORDER = { debug: 0, info: 1, warn: 2, error: 3 };

/**
 * @param {string} line
 * @returns {LogLevel}
 */
export function inferLogLevel(line) {
  const s = String(line ?? '');
  if (!s) return 'info';

  if (/\[(ERROR|CRITICAL|FATAL)\]/i.test(s)) return 'error';
  if (/\[WARN(?:ING)?\]/i.test(s)) return 'warn';
  if (/\[DEBUG\]/i.test(s)) return 'debug';
  if (/\[INFO\]/i.test(s)) return 'info';

  if (
    /Traceback \(most recent call last\)/i.test(s)
    || /\bException\b/.test(s)
    || /\bERROR\b/.test(s)
    || /✗|失败|错误|出错|pipeline failed|HTTP \d{3}/i.test(s)
  ) {
    return 'error';
  }

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
 * @param {unknown} item
 * @returns {LogEntry}
 */
export function normalizeLogEntry(item) {
  if (item != null && typeof item === 'object' && !Array.isArray(item)) {
    const o = /** @type {Record<string, unknown>} */ (item);
    const tsRaw = o.ts;
    let ts = null;
    if (typeof tsRaw === 'number' && Number.isFinite(tsRaw)) ts = tsRaw;
    else if (typeof tsRaw === 'string' && tsRaw.trim() !== '' && Number.isFinite(Number(tsRaw))) {
      ts = Number(tsRaw);
    }
    return { ts, text: String(o.text ?? '') };
  }
  if (item == null) return { ts: null, text: '' };
  return { ts: null, text: String(item) };
}

/**
 * Local wall-clock HH:MM:SS.
 * @param {number|null|undefined} ts epoch seconds
 * @returns {string}
 */
export function formatLogTime(ts) {
  if (ts == null || typeof ts !== 'number' || !Number.isFinite(ts)) return '';
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * @param {LogEntry|string} entryOrLine
 * @param {{ query?: string, level?: string, sinceMs?: number, nowMs?: number }} [opts]
 * @returns {boolean}
 */
export function entryMatchesLogFilter(entryOrLine, opts = {}) {
  const entry = normalizeLogEntry(entryOrLine);
  const query = String(opts.query ?? '').trim();
  const level = String(opts.level ?? '').trim().toLowerCase();
  const sinceMs = opts.sinceMs;
  const nowMs = typeof opts.nowMs === 'number' ? opts.nowMs : Date.now();

  if (sinceMs != null && sinceMs > 0) {
    if (entry.ts == null || !Number.isFinite(entry.ts)) return false;
    if (nowMs - entry.ts * 1000 > sinceMs) return false;
  }

  if (level && level !== 'all') {
    if (inferLogLevel(entry.text) !== level) return false;
  }
  if (query) {
    if (!entry.text.toLowerCase().includes(query.toLowerCase())) return false;
  }
  return true;
}

/**
 * @param {string} line
 * @param {{ query?: string, level?: string, sinceMs?: number, nowMs?: number }} [opts]
 * @returns {boolean}
 */
export function lineMatchesLogFilter(line, opts = {}) {
  return entryMatchesLogFilter(line, opts);
}

/**
 * @param {Array<LogEntry|string>} entries
 * @param {{ query?: string, level?: string, sinceMs?: number, nowMs?: number }} [opts]
 * @returns {LogEntry[]}
 */
export function filterLogEntries(entries, opts = {}) {
  const arr = Array.isArray(entries) ? entries : [];
  return arr
    .map(normalizeLogEntry)
    .filter((e) => entryMatchesLogFilter(e, opts));
}

/**
 * @param {string[]} lines
 * @param {{ query?: string, level?: string, sinceMs?: number, nowMs?: number }} [opts]
 * @returns {string[]}
 */
export function filterLogLines(lines, opts = {}) {
  return filterLogEntries(lines, opts).map((e) => e.text);
}

/**
 * @param {string|LogEntry} lineOrEntry
 * @returns {string}
 */
export function logLineClass(lineOrEntry) {
  const text = typeof lineOrEntry === 'object' && lineOrEntry != null
    ? String(/** @type {LogEntry} */ (lineOrEntry).text ?? '')
    : String(lineOrEntry ?? '');
  return `log-level-${inferLogLevel(text)}`;
}

export { LEVEL_ORDER };
```

- [ ] **Step 4: Run Vitest — expect PASS**

Run: `cd clio/ui/static && npm test -- --run src/__tests__/logs-filter.test.js`

Expected: all PASS. Existing level/query cases still green via `lineMatchesLogFilter` → normalize.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/logs-filter.js clio/ui/static/src/__tests__/logs-filter.test.js
git commit -m "$(cat <<'EOF'
feat(ui): log entry normalize, time format, and sinceMs filter

Pure helpers for R-027d timestamps and recent-window chips.
EOF
)"
```

---

### Task 3: UI timestamps + recent-time chips

**Files:**
- Modify: `clio/ui/static/src/editor-config.js` (logs section ~1316–1477)
- Modify: `clio/ui/static/style.css` (near `.log-line` ~1046)

**Interfaces:**
- Consumes: `normalizeLogEntry`, `formatLogTime`, `filterLogEntries`, `entryMatchesLogFilter`, `inferLogLevel`, `logLineClass` from `logs-filter.js`
- Produces: updated `renderLogs()` behavior only (no new exports required)

- [ ] **Step 1: Update imports in `editor-config.js`**

Change the logs-filter import to:

```javascript
import {
  filterLogEntries,
  entryMatchesLogFilter,
  inferLogLevel,
  logLineClass,
  normalizeLogEntry,
  formatLogTime,
} from './logs-filter.js';
```

- [ ] **Step 2: Extend module state and helpers**

Replace the logs state block (from `let _logsTimer` through `_syncLogsLevelChips`) with:

```javascript
let _logsTimer = null;
let _logsOffset = 0;
let _logsAutoScroll = true;
/** @type {Array<{ts: number|null, text: string}>} */
let _logsBuffer = [];
let _logsFilterQuery = '';
/** @type {''|'all'|'info'|'warn'|'error'} */
let _logsFilterLevel = 'all';
/** 0 = all; else window in ms */
let _logsFilterSinceMs = 0;

const _LEVEL_LABELS = {
  debug: '调试',
  info: '信息',
  warn: '警告',
  error: '错误',
};

const _SINCE_CHIPS = [
  { ms: 0, label: '全部' },
  { ms: 5 * 60 * 1000, label: '5分钟' },
  { ms: 15 * 60 * 1000, label: '15分钟' },
  { ms: 60 * 60 * 1000, label: '60分钟' },
];

function _logsFilterOpts() {
  return {
    query: _logsFilterQuery,
    level: _logsFilterLevel,
    sinceMs: _logsFilterSinceMs || undefined,
  };
}

function _appendLogLineEl(view, entryOrLine) {
  const entry = normalizeLogEntry(entryOrLine);
  const level = inferLogLevel(entry.text);
  const d = document.createElement('div');
  d.className = `log-line ${logLineClass(entry)}`;
  d.dataset.level = level;
  const badge = document.createElement('span');
  badge.className = 'log-level-badge';
  badge.textContent = _LEVEL_LABELS[level] || '信息';
  const timeEl = document.createElement('span');
  timeEl.className = 'log-line-time';
  const clock = formatLogTime(entry.ts);
  timeEl.textContent = clock || '--:--:--';
  if (entry.ts != null) {
    timeEl.title = new Date(entry.ts * 1000).toLocaleString();
  }
  const text = document.createElement('span');
  text.className = 'log-line-text';
  text.textContent = entry.text;
  d.appendChild(badge);
  d.appendChild(timeEl);
  d.appendChild(text);
  view.appendChild(d);
}

function _paintLogsView(view) {
  if (!view) return;
  const visible = filterLogEntries(_logsBuffer, _logsFilterOpts());
  view.innerHTML = '';
  for (const entry of visible) {
    _appendLogLineEl(view, entry);
  }
  const empty = $('logs-empty-hint');
  if (empty) {
    const filteredOut = _logsBuffer.length > 0 && visible.length === 0;
    empty.hidden = !filteredOut;
  }
  const countEl = $('logs-match-count');
  if (countEl) {
    countEl.textContent = _logsBuffer.length
      ? `显示 ${visible.length} / ${_logsBuffer.length}`
      : '';
  }
  if (_logsAutoScroll) view.scrollTop = view.scrollHeight;
}

function _syncLogsLevelChips() {
  document.querySelectorAll('[data-log-level]').forEach((btn) => {
    const on = (btn.dataset.logLevel || '') === _logsFilterLevel;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

function _syncLogsSinceChips() {
  document.querySelectorAll('[data-log-since]').forEach((btn) => {
    const ms = Number(btn.dataset.logSince || 0);
    const on = ms === _logsFilterSinceMs;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}
```

- [ ] **Step 3: Update `renderLogs` toolbar HTML + wire chips**

In `renderLogs`, keep timer/buffer reset; expand `pane.innerHTML` toolbar:

```javascript
export function renderLogs() {
  const pane = $('tab-logs');
  _logsOffset = 0;
  _logsBuffer = [];
  if (_logsTimer) { clearInterval(_logsTimer); _logsTimer = null; }
  const sinceChipsHtml = _SINCE_CHIPS.map((c) =>
    `<button type="button" class="logs-chip" data-log-since="${c.ms}">${c.label}</button>`
  ).join('');
  pane.innerHTML = `
    <div class="logs-toolbar">
      <span class="logs-toolbar-title">会话日志</span>
      <input type="search" id="logs-filter-query" class="logs-filter-input"
        placeholder="过滤关键字…" autocomplete="off"
        value="${escapeHtml(_logsFilterQuery)}"
        aria-label="日志关键字过滤">
      <div class="logs-level-chips" role="group" aria-label="日志等级">
        <button type="button" class="logs-chip" data-log-level="all">全部</button>
        <button type="button" class="logs-chip" data-log-level="info">信息</button>
        <button type="button" class="logs-chip" data-log-level="warn">警告</button>
        <button type="button" class="logs-chip" data-log-level="error">错误</button>
      </div>
      <div class="logs-since-chips" role="group" aria-label="时间范围">
        ${sinceChipsHtml}
      </div>
      <span id="logs-match-count" class="logs-match-count muted"></span>
      <label class="logs-autoscroll-label">
        <input type="checkbox" id="logs-autoscroll" ${_logsAutoScroll ? 'checked' : ''}> 自动滚动
      </label>
      <button type="button" class="btn-secondary" id="btn-logs-clear">清空</button>
    </div>
    <p id="logs-empty-hint" class="logs-empty-hint muted" hidden>没有匹配当前过滤条件的日志</p>
    <div id="logs-view" class="logs-view" role="log" aria-live="polite"></div>
  `;
  const view = $('logs-view');
  const cb = $('logs-autoscroll');
  if (cb) cb.onchange = () => { _logsAutoScroll = cb.checked; };
  const queryInput = $('logs-filter-query');
  if (queryInput) {
    queryInput.oninput = () => {
      _logsFilterQuery = queryInput.value || '';
      _paintLogsView(view);
    };
  }
  pane.querySelectorAll('[data-log-level]').forEach((btn) => {
    btn.onclick = () => {
      _logsFilterLevel = btn.dataset.logLevel || 'all';
      _syncLogsLevelChips();
      _paintLogsView(view);
    };
  });
  pane.querySelectorAll('[data-log-since]').forEach((btn) => {
    btn.onclick = () => {
      _logsFilterSinceMs = Number(btn.dataset.logSince || 0);
      _syncLogsSinceChips();
      _paintLogsView(view);
    };
  });
  _syncLogsLevelChips();
  _syncLogsSinceChips();

  $('btn-logs-clear').onclick = async () => {
    try {
      await api('POST', '/api/logs/clear', {});
      _logsBuffer = [];
      _logsOffset = 0;
      _paintLogsView(view);
    } catch { /* ignore */ }
  };

  const ingest = (lines) => {
    if (!Array.isArray(lines) || !lines.length) return;
    for (const raw of lines) {
      const entry = normalizeLogEntry(raw);
      _logsBuffer.push(entry);
      if (entryMatchesLogFilter(entry, _logsFilterOpts())) {
        _appendLogLineEl(view, entry);
      }
    }
    const empty = $('logs-empty-hint');
    if (empty) {
      const visible = filterLogEntries(_logsBuffer, _logsFilterOpts());
      empty.hidden = !(_logsBuffer.length > 0 && visible.length === 0);
    }
    const countEl = $('logs-match-count');
    if (countEl) {
      const visible = filterLogEntries(_logsBuffer, _logsFilterOpts());
      countEl.textContent = `显示 ${visible.length} / ${_logsBuffer.length}`;
    }
    if (_logsAutoScroll) view.scrollTop = view.scrollHeight;
  };

  _logsTimer = setInterval(async () => {
    try {
      const r = await api('GET', `/api/logs?offset=${_logsOffset}`);
      if (!r || !r.logs) return;
      ingest(r.logs);
      _logsOffset = r.total;
    } catch { /* ignore */ }
  }, 2000);

  (async () => {
    try {
      const r = await api('GET', '/api/logs?offset=0');
      if (r && r.logs) {
        _logsBuffer = r.logs.map(normalizeLogEntry);
        _logsOffset = r.total;
        _paintLogsView(view);
      }
    } catch { /* ignore */ }
  })();
}
```

- [ ] **Step 4: CSS for time column**

After `.log-line-text` rule in `style.css`, add:

```css
.log-line-time {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  opacity: 0.85;
  min-width: 4.5em;
}
.logs-since-chips { display: flex; gap: 4px; flex-wrap: wrap; }
```

- [ ] **Step 5: Run unit tests**

Run:

```bash
python -m pytest clio/tests/test_session_log.py -q
cd clio/ui/static && npm test -- --run src/__tests__/logs-filter.test.js
```

Expected: all PASS.

Manual smoke (optional if serve available): open 会话日志, run any action that prints, confirm clock +「5分钟」chip.

- [ ] **Step 6: Commit**

```bash
git add clio/ui/static/src/editor-config.js clio/ui/static/style.css
git commit -m "$(cat <<'EOF'
feat(ui): show session log timestamps and recent-time chips

Row clock HH:MM:SS plus 5/15/60 minute filters ANDed with keyword/level (R-027d).
EOF
)"
```

---

### Task 4: ROADMAP + memory touch

**Files:**
- Modify: `ROADMAP.md` (Remaining Open Items + R-027 section)
- Optionally update auto-memory `project-state.md` open list (agent memory path)

- [ ] **Step 1: Update ROADMAP open table**

In `## Remaining Open Items (2026-07-21)` remove or mark done:

| Before | After |
| --- | --- |
| `\| R-027d \| Session logs: **timestamps + time-range filter** \| Small \| Medium \|` | Move to Recently completed |

Add under Recently completed (2026-07-22):

```markdown
### Recently completed (2026-07-22)

| ID | Item | Notes |
| --- | --- | --- |
| R-027d | Session log timestamps + recent chips (slim) | Structured `{ts,text}`; UI HH:MM:SS; 5/15/60 min; no R-027e |
```

In R-027 phases table set:

```markdown
| D | R-027d | **Done** (2026-07-22) | Show timestamps + recent 5/15/60 min chips (slim; no from–to) |
```

Update R-027 status blurb:

```markdown
**Status:** **R-027a/b/d Done** (2026-07-22). **R-027e open** (historical files). R-027c server `?q=` still deferred.
```

- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "$(cat <<'EOF'
docs: mark R-027d session log timestamps done

Slim scope: write-time entries + UI recent chips; R-027e remains open.
EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| `{ts, text}` ring buffer + write-time | Task 1 |
| `GET /api/logs` returns objects | Task 1 (read shape; handler unchanged) |
| normalize + format HH:MM:SS + sinceMs AND | Task 2 |
| Row badge + time + text; chips 全部/5/15/60 | Task 3 |
| Persist filter across clear/re-open | Task 3 (`_logsFilterSinceMs` module scope) |
| pytest + vitest | Tasks 1–2 |
| No disk format / no R-027e | Global Constraints + no tasks for files API |
| ROADMAP mark done | Task 4 |

## Self-review notes

- No TBD/placeholder steps.
- `nowMs` injected for deterministic tests; production omits it.
- `filterLogLines` still returns `string[]` for any legacy caller; UI uses `filterLogEntries`.
- Tee / `log.py` needs no edit (passes string into `write`).

# R-027d Session Log Timestamps — Design (slim)

Date: 2026-07-22  
Status: approved for planning  
Scope: **slim R-027d only** — capture write-time on session log entries and show / filter by recent time in the 会话日志 UI.

## Goal

Make the in-memory session log buffer useful for “when did that fail?” without building a full log browser.

1. Every line written via `session_log.write` stores a **capture timestamp**.
2. UI rows show a muted `HH:MM:SS` clock next to the existing level badge.
3. Optional **recent-time chips** (全部 / 5 / 15 / 60 分钟) combine with existing keyword + level filters (AND).

## Non-goals

- **R-027e** historical files under `logs/YYYY-MM-DD-HH.log` (deferred; disk logging format unchanged)
- Custom from–to datetime pickers
- Server-side `?q=` / level / time filter (R-027c still deferred)
- Changing `_HourlyFileHandler` / Tee disk line format
- Timezone picker; multi-project session buckets
- Export / pause / step chips (nice-to-have under ROADMAP R-027, unscheduled)

## Background

| Piece | Today |
| --- | --- |
| `clio/session_log.py` | Ring buffer `list[str]`, max 10k; `GET /api/logs?offset=` |
| `clio/log.py` Tee | `session_log.write(message.rstrip())` with **no** ts |
| Disk | Already `YYYY-MM-DD HH:MM:SS [LEVEL] …` hourly files — out of scope |
| UI | `editor-config.js` `renderLogs` + pure `logs-filter.js` (query + level chips) |

Roadmap previously sketched full d (structured buffer + time range) + e (load history). Product decision (2026-07-22): **lean d only** — reliable timestamps beat a large log-history feature for this personal tool.

## Approach

**Minimal structural change:** session entries become `{ts, text}` objects end-to-end for the live session API and UI buffer. Disk logging stays as-is.

```text
print / logger
    → _TeeWriter
        → session_log.write(text)  →  [{ts, text}, …]  → GET /api/logs
        → HourlyFileHandler (unchanged)
UI: poll offset → buffer entries → filter (query ∧ level ∧ sinceMs) → paint
```

## Data model

### Session entry

```python
{"ts": float, "text": str}  # ts = Unix epoch seconds (time.time())
```

- `ts`: float for sub-second ordering; UI formats local `HH:MM:SS`.
- `text`: same as today’s raw line content (no forced clock prefix in the string).

### `session_log` API

| Function | Behavior |
| --- | --- |
| `write(line: str)` | Append `{"ts": time.time(), "text": line}` (caller already rstrip’s in Tee). Empty / falsy text: still store if Tee sends non-empty after rstrip (unchanged policy: Tee only writes non-empty lines). |
| `read(offset: int = 0)` | `{"logs": list[_logs[offset:]], "total": len(_logs)}` where each item is a dict. |
| `clear()` | Empty buffer (unchanged). |
| Ring `_MAX` | 10000 (unchanged). |

**No dual format:** API always returns objects after this change. Frontend may still `normalizeLogEntry` if a string slips through (defensive only).

### `GET /api/logs`

Response shape:

```json
{
  "logs": [
    { "ts": 1721606400.12, "text": "=== AI 分析素材 ===" }
  ],
  "total": 42
}
```

Handlers stay thin wrappers around `read` / `clear`. No new query params for time (client filters).

## Frontend

### Pure helpers (`logs-filter.js`)

| Helper | Role |
| --- | --- |
| `normalizeLogEntry(item)` | `{ ts, text }` from object or string (`ts: null` if unknown) |
| `formatLogTime(ts)` | Local `HH:MM:SS`; invalid/null → `""` or omit column |
| `entryMatchesLogFilter(entry, opts)` | AND of: level on `text`, substring `query` on `text`, optional `sinceMs` vs `Date.now() - ts*1000` |
| `filterLogEntries(entries, opts)` | Filter list |
| Existing | `inferLogLevel`, `logLineClass` continue to operate on **text** (or accept entry and use `.text`) |

`sinceMs` semantics:

- Missing / `0` / `'all'`: no time filter.
- `5 * 60 * 1000` etc.: keep entries with `ts != null` and `now - ts*1000 <= sinceMs`.
- Entries with `ts == null`: **drop** when a time filter is active (cannot prove recency).

Backward-compatible aliases: keep `lineMatchesLogFilter` / `filterLogLines` working for plain strings (tests + any residual callers) by normalizing first.

### `renderLogs` (`editor-config.js`)

- Buffer: `Array<{ts, text}>` instead of `string[]`.
- Row DOM: level badge · muted time span · text (same escape/`textContent` style as today).
- Toolbar: existing query + level chips + **time chips** `全部 | 5分钟 | 15分钟 | 60分钟` (default 全部).
- Persist `_logsFilterSinceMs` (or chip key) across clear / re-open like query/level.
- Poll / ingest: treat each `r.logs[]` item as entry; update match count from filtered entries.
- Clear: server clear + empty buffer; **keep** filters.

## Testing

### pytest (`test_session_log.py`)

- `write` produces dict with `ts` (number) and `text`
- `read` returns objects; offset / max ring / clear / copy-not-reference still hold
- Optional: two writes have non-decreasing `ts`

### vitest (`logs-filter.test.js`)

- `normalizeLogEntry` object + string paths
- `formatLogTime` smoke
- Time filter: recent kept, old dropped; null ts dropped when since active
- Existing level/query tests still pass (via string or entry)

## Commit plan

1. `feat(session_log): store timestamped log entries` — backend + pytest  
2. `feat(ui): session log timestamps and recent-time filter` — helpers, UI, vitest  
3. `docs: mark R-027d done` — ROADMAP checkbox + short note (may fold into commit 2 if preferred)

One feature per commit; no push unless asked.

## Acceptance

- [ ] New session lines show local `HH:MM:SS` in the logs panel  
- [ ] Chip「最近 5 分钟」hides older lines; stacks with 错误 + keyword  
- [ ] Clear empties lines; filter chips remain  
- [ ] `pytest` session_log + `vitest` logs-filter green  
- [ ] No change to disk `logs/*.log` format or R-027e APIs  

## Out of scope follow-ups (not this design)

| ID | Note |
| --- | --- |
| R-027e | List/load hourly files when user wants post-restart triage |
| R-027c | Server filter only if client buffer becomes a real problem |
| Open logs folder | If reveal API exists, one-button open `logs_dir` is a tiny UX win without e |

## Related

- ROADMAP § R-027  
- `clio/session_log.py`, `clio/log.py`, `clio/ui/server.py` `_handle_get_logs`  
- `clio/ui/static/src/logs-filter.js`, `editor-config.js` `renderLogs`  

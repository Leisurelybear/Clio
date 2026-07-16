# Project Iteration Review — 2026-07-16

## Scope

Maintenance pass on `main` after `feat/project-video-manager` landed. Roadmap high-priority backlog was empty except:

| ID | Item | Decision |
| --- | --- | --- |
| R-024 | GoPro GPMF telemetry | Deferred (Large / Low) |
| A-006 | Frontend circular dynamic imports | Deferred — runtime risk low today (calls only after module eval) |

Focus: real bugs + UX friction, one small module per commit, Chinese dialogue / English commits.

## Method

1. Roadmap + memory + recent commit audit
2. Parallel read-only review agents (frontend UX + residual bugs)
3. Manual verification of cancel propagation (already solid)
4. Implement → test → per-module commits → this document

## Verification after fixes

| Check | Result |
| --- | --- |
| `python -m pytest clio/tests/ -q` | **1164 passed**, 1 skipped |
| `npm test -- --run` | **138 passed** (10 files) |
| Branch | `main`, 9 commits ahead of pre-session HEAD |

## Findings fixed this session

| Commit | ID | Severity | Summary |
| --- | --- | --- | --- |
| `9592ddd` | BUG-A | P1 | Auto-open last project reused **current** `project_dir`. API now returns `{name, project_dir}`; frontend uses last project's dir. |
| *(same commit as BUG-A sidebar touch)* | BUG-B | P1 | Selection checkbox `data-file` escaped with `escapeHtml` (filenames with `"` no longer break DOM). |
| `6c85f6d` | UX-A/B/F | P1 | Run panel: mount `#run-preview` + `collectRunOptions`; always show overwrite; selection mode with 0 checked videos disables Run. |
| `0ebcaea` | UX-F | P1 | Select-all skips offline videos; offline checkboxes disabled. |
| `2cc5f60` | BUG-D | P2 | Stale `.progress.json` demotion uses atomic tmp+replace. |
| `a6d3f8f` | BUG-C | P2 | Rerun poll handles `cancelled` (overlay no longer stuck 120s). |
| `b34244b` | UX-C | P0/P1 | Settings tab / provider jump confirms before clearing dirty. |
| `96c9be2` | UX-D | P1 | Video manager add success/failure toast; DnD filters non-video paths. |
| `c536987` | UX-E | P1 | Project create/open Chinese copy + busy guards against double-submit. |
| `1791970` | UX-E | P1 | Jianying export button disabled while exporting. |

## Intentional non-fixes

| Item | Why skipped |
| --- | --- |
| R-024 GoPro GPMF | Large feature, low priority |
| A-006 circular imports | Low runtime risk; static `editor`↔`editor-config` cycle only bites on top-level use |
| Offline relink browse modal | Valuable (P2) but larger UX redesign; leave for next pass |
| Restore `lastEntity` / `lastVideo` on open | Useful P2; not in the approved ship list for this session's primary bugs |
| Split `editor-config.js` (1645 lines) | Architecture, not user-facing |

## Residual backlog (next iteration candidates)

| ID | Item | Effort | Priority |
| --- | --- | --- | --- |
| R-024 | GoPro GPMF telemetry as highlight signal | Large | Low |
| A-006 | Break static `editor`↔`editor-config` cycle when next touching those modules | Medium | Low |
| UX-next-1 | ~~Relink offline video via browse modal~~ — done (type + browse) | — | — |
| UX-next-2 | Restore `lastEntity` / `lastVideo` after project open | S | Medium |
| UX-next-3 | Texts/voiceover empty states → “去运行 / 重跑” CTAs | S | Low |
| UX-next-4 | Toast `aria-live` + longer sticky error status | S | Low |

### Follow-up same day: offline relink modal

- New `sidebar-relink.js` + `#modal-relink`: paste/type path **or** toggle in-modal FS browse (dirs + video files)
- Offline row click opens the modal; ⋮ menu still works
- Escape closes only the topmost modal

## Files touched

- `clio/ui/routes/projects.py`, `clio/ui/routes/run.py`
- `clio/ui/static/src/{main,runner,sidebar-data,sidebar-rerun,sidebar-video-manage,editor-config,editor-plan,state}.js`
- `clio/ui/static/src/__tests__/runner.test.js`
- `clio/tests/test_routes_projects.py`
- `ROADMAP.md`, this document

## How to verify manually

1. **Last project**: open project B, close UI, reopen without URL params → loads B (not A’s dir).
2. **Run preview**: open ▶ Run → toggle steps → “运行预览” totals update; check “覆盖现有输出” without multi-select.
3. **Selection guard**: 选择视频 with nothing checked → Run button disabled “请先勾选视频”.
4. **Offline**: select-all does not include offline rows.
5. **Settings**: edit project field → switch to Global → confirm dialog appears.
6. **Video manager**: add videos → toast; drop a `.txt` → ignored warning.
7. **Project modal**: create/open buttons show “创建中…/打开中…” and stay disabled mid-request.

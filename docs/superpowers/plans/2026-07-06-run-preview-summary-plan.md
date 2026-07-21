# Run Preview Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only run preview that shows selected inputs, per-step run/skip counts, and warnings before the user starts the pipeline.

**Architecture:** Put preview computation in a focused backend service (`clio/ui/services/run_preview.py`) and expose it through `POST /api/run/preview`. Keep `/api/run/start` unchanged. Add a small frontend renderer in `runner.js` that refreshes the summary when run options change and immediately before starting.

**Tech Stack:** Python 3.11+ stdlib, pytest, stdlib `http.server` route dispatch, existing ES module frontend, Vitest for pure frontend rendering tests.

---

## File Structure

- Create `clio/ui/services/run_preview.py`
  - Owns all preview computation and returns plain JSON-serializable dictionaries.
  - Does not write files or start background work.
- Modify `clio/ui/routes/run.py`
  - Add `handle_post_run_preview()` and validation for preview request bodies.
- Modify `clio/ui/server.py`
  - Import and route `POST /api/run/preview`.
  - Add route auth policy metadata.
- Modify `clio/ui/static/src/runner.js`
  - Add preview fetch, render helper, and run-start refresh.
  - Export pure renderer for Vitest.
- Add or modify tests:
  - `clio/tests/test_run_preview.py`
  - `clio/tests/test_routes_run.py`
  - `clio/tests/test_server.py`
  - `clio/ui/static/src/__tests__/runner.test.js`
- Modify `ROADMAP.md`
  - Mark only CR-008 pre-run summary as complete after implementation passes.

---

## Task 1: Backend Preview Service

**Files:**
- Create: `clio/ui/services/run_preview.py`
- Test: `clio/tests/test_run_preview.py`

- [ ] **Step 1: Write failing backend service tests**

Create `clio/tests/test_run_preview.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from clio.config.models import (
    AnalyzeConfig,
    AppConfig,
    GlobalConfig,
    GlobalPathsConfig,
    NamingConfig,
    ProjectConfig,
    ProjectPathsConfig,
    ScriptConfig,
    ProjectWhisperConfig,
)
from clio.ui.services.run_preview import build_run_preview


def _config(input_dir: Path, output_dir: Path) -> AppConfig:
    return AppConfig(
        global_cfg=GlobalConfig(paths=GlobalPathsConfig(), naming=NamingConfig(index_width=3)),
        project_cfg=ProjectConfig(
            paths=ProjectPathsConfig(input_dir=input_dir, output_dir=output_dir, recursive=False),
            analyze=AnalyzeConfig(compressed_subdir="compressed", texts_subdir="texts", skip_existing=True),
            script=ScriptConfig(scripts_subdir="scripts"),
            whisper=ProjectWhisperConfig(transcripts_subdir="transcripts"),
        ),
    )


def test_preview_compress_counts_existing_output_as_skip(tmp_path: Path) -> None:
    input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (output_dir / "compressed").mkdir(parents=True)
    (input_dir / "GL010684.mp4").write_bytes(b"video")
    (output_dir / "compressed" / "001_GL010684.mp4").write_bytes(b"compressed")
    cfg = _config(input_dir, output_dir)

    preview = build_run_preview(cfg, input_dir, output_dir, steps=["compress"], files=None, overwrite=False)

    step = preview["steps"][0]
    assert step["key"] == "compress"
    assert step["total"] == 1
    assert step["will_run"] == 0
    assert step["will_skip"] == 1


def test_preview_overwrite_turns_skip_into_run(tmp_path: Path) -> None:
    input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (output_dir / "compressed").mkdir(parents=True)
    (input_dir / "GL010684.mp4").write_bytes(b"video")
    (output_dir / "compressed" / "001_GL010684.mp4").write_bytes(b"compressed")
    cfg = _config(input_dir, output_dir)

    preview = build_run_preview(cfg, input_dir, output_dir, steps=["compress"], files=None, overwrite=True)

    step = preview["steps"][0]
    assert step["will_run"] == 1
    assert step["will_skip"] == 0


def test_preview_selected_voiceover_matches_generated_analysis_title_by_identity(tmp_path: Path) -> None:
    input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    texts_dir = output_dir / "texts"
    scripts_dir = output_dir / "scripts"
    texts_dir.mkdir(parents=True)
    scripts_dir.mkdir()
    analysis = {
        "index": 2,
        "source_file": "GL010684.mp4",
        "compressed_file": "002_GL010684.mp4",
        "media_identity": {
            "original_stem": "GL010684",
            "compressed_stem": "002_GL010684",
        },
    }
    (texts_dir / "002_AI_generated_title.json").write_text(json.dumps(analysis), encoding="utf-8")
    cfg = _config(input_dir, output_dir)

    preview = build_run_preview(
        cfg,
        input_dir,
        output_dir,
        steps=["voiceover"],
        files=["002_GL010684.mp4"],
        overwrite=False,
    )

    step = preview["steps"][0]
    assert step["total"] == 1
    assert step["will_run"] == 1
    assert step["warnings"] == []


def test_preview_voiceover_warns_when_selected_video_has_no_analysis_json(tmp_path: Path) -> None:
    input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    cfg = _config(input_dir, output_dir)

    preview = build_run_preview(
        cfg,
        input_dir,
        output_dir,
        steps=["voiceover"],
        files=["001_GL010684.mp4"],
        overwrite=False,
    )

    step = preview["steps"][0]
    assert step["total"] == 0
    assert step["will_run"] == 0
    assert step["warnings"] == ["No analysis JSON matched the selected videos."]
    assert "voiceover has no matching input artifacts." in preview["warnings"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest clio/tests/test_run_preview.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'clio.ui.services.run_preview'`.

- [ ] **Step 3: Implement `run_preview.py`**

Create `clio/ui/services/run_preview.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clio._constants import VIDEO_EXTS
from clio.config import AppConfig
from clio.tasks._helpers import _matches_selected_artifact, _matches_selected_stem, _selected_stems
from clio.ui.services.file_service import _find_texts_dirs
from clio.utils import find_videos

VALID_RUN_STEPS = {"compress", "analyze", "voiceover", "transcribe", "plan", "label"}


def _step_result(key: str, total: int, will_run: int, will_skip: int, warnings: list[str] | None = None) -> dict:
    return {
        "key": key,
        "label": key,
        "total": total,
        "will_run": will_run,
        "will_skip": will_skip,
        "warnings": warnings or [],
    }


def _video_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def _compressed_files(config: AppConfig) -> list[Path]:
    return _video_files(config.compressed_dir)


def _selected_filter(paths: list[Path], files: list[str] | None) -> list[Path]:
    if not files:
        return paths
    selected = _selected_stems(files)
    return [path for path in paths if _matches_selected_stem(path, selected)]


def _selected_artifacts(paths: list[Path], files: list[str] | None) -> list[Path]:
    if not files:
        return paths
    selected = _selected_stems(files)
    return [path for path in paths if _matches_selected_artifact(path, selected)]


def _existing_compressed_for_original(config: AppConfig, original: Path) -> bool:
    for compressed in _compressed_files(config):
        if original.stem.lower() in compressed.stem.lower():
            return True
    return False


def _analysis_jsons(config: AppConfig, output_dir: Path) -> list[Path]:
    files: list[Path] = []
    for texts_dir in _find_texts_dirs(output_dir):
        files.extend(sorted(path for path in texts_dir.iterdir() if path.suffix == ".json"))
    return files


def _script_exists(config: AppConfig, analysis_path: Path) -> bool:
    script_dir = config.scripts_dir
    if not script_dir.is_dir():
        return False
    prefix = analysis_path.stem.split("_", 1)[0]
    return any(script_dir.glob(f"{prefix}_*.json"))


def _transcript_exists(config: AppConfig, original: Path) -> bool:
    transcript_dir = config.transcripts_dir
    if not transcript_dir.is_dir():
        return False
    return any(transcript_dir.glob(f"*{original.stem}*_transcript.json"))


def _compress_preview(config: AppConfig, files: list[str] | None, overwrite: bool) -> dict:
    originals = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    originals = _selected_filter(originals, files)
    skip = 0 if overwrite else sum(1 for path in originals if _existing_compressed_for_original(config, path))
    return _step_result("compress", len(originals), len(originals) - skip, skip)


def _analyze_preview(config: AppConfig, output_dir: Path, files: list[str] | None, overwrite: bool) -> dict:
    compressed = _selected_filter(_compressed_files(config), files)
    existing = _selected_artifacts(_analysis_jsons(config, output_dir), files)
    existing_count = min(len(compressed), len(existing)) if not overwrite else 0
    warnings = [] if compressed else ["No compressed videos matched the run selection."]
    return _step_result("analyze", len(compressed), len(compressed) - existing_count, existing_count, warnings)


def _voiceover_preview(config: AppConfig, output_dir: Path, files: list[str] | None, overwrite: bool) -> dict:
    analyses = _selected_artifacts(_analysis_jsons(config, output_dir), files)
    skip = 0 if overwrite else sum(1 for path in analyses if _script_exists(config, path))
    warnings = [] if analyses else ["No analysis JSON matched the selected videos."]
    return _step_result("voiceover", len(analyses), len(analyses) - skip, skip, warnings)


def _transcribe_preview(config: AppConfig, files: list[str] | None, overwrite: bool) -> dict:
    originals = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    originals = _selected_filter(originals, files)
    skip = 0 if overwrite else sum(1 for path in originals if _transcript_exists(config, path))
    return _step_result("transcribe", len(originals), len(originals) - skip, skip)


def _plan_preview(config: AppConfig, day_label: str, overwrite: bool) -> dict:
    exists = (config.plans_dir / f"{day_label}_plan.json").is_file()
    skip = 1 if exists and not overwrite else 0
    return _step_result("plan", 1, 1 - skip, skip)


def _label_preview(config: AppConfig, files: list[str] | None, overwrite: bool) -> dict:
    compressed = _selected_filter(_compressed_files(config), files)
    warnings = [] if compressed else ["No compressed videos matched the run selection."]
    return _step_result("label", len(compressed), len(compressed), 0, warnings)


def build_run_preview(
    config: AppConfig,
    project_input: Path,
    project_output: Path,
    *,
    steps: list[str] | None,
    files: list[str] | None,
    overwrite: bool,
    day_label: str = "day1",
) -> dict[str, Any]:
    selected_steps = steps or ["compress", "analyze", "voiceover", "transcribe", "plan", "label"]
    unknown = [step for step in selected_steps if step not in VALID_RUN_STEPS]
    if unknown:
        raise ValueError(f"unknown run step(s): {', '.join(unknown)}")

    step_results: list[dict] = []
    for step in selected_steps:
        if step == "compress":
            step_results.append(_compress_preview(config, files, overwrite))
        elif step == "analyze":
            step_results.append(_analyze_preview(config, project_output, files, overwrite))
        elif step == "voiceover":
            step_results.append(_voiceover_preview(config, project_output, files, overwrite))
        elif step == "transcribe":
            step_results.append(_transcribe_preview(config, files, overwrite))
        elif step == "plan":
            step_results.append(_plan_preview(config, day_label, overwrite))
        elif step == "label":
            step_results.append(_label_preview(config, files, overwrite))

    warnings: list[str] = []
    for step in step_results:
        if step["key"] == "voiceover" and step["total"] == 0:
            warnings.append("voiceover has no matching input artifacts.")
        warnings.extend(step["warnings"])

    selected_files = files or []
    return {
        "ok": True,
        "selection": {
            "mode": "selected" if selected_files else "all",
            "count": len(selected_files),
            "files": selected_files,
        },
        "steps": step_results,
        "warnings": list(dict.fromkeys(warnings)),
    }
```

- [ ] **Step 4: Run backend service tests to verify GREEN**

Run:

```bash
python -m pytest clio/tests/test_run_preview.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add clio/ui/services/run_preview.py clio/tests/test_run_preview.py
git commit -m "feat(ui): add run preview service"
```

---

## Task 2: Route and Server Integration

**Files:**
- Modify: `clio/ui/routes/run.py`
- Modify: `clio/ui/server.py`
- Test: `clio/tests/test_routes_run.py`
- Test: `clio/tests/test_server.py`

- [ ] **Step 1: Write failing route tests**

Append to `clio/tests/test_routes_run.py` imports:

```python
from clio.ui.routes.run import handle_post_run_preview
```

Add tests:

```python
class TestHandlePostRunPreview:
    def test_preview_returns_summary(self, tmp_path: Path, _handler, monkeypatch):
        handler = _handler
        proj_input = tmp_path / "input"
        proj_out = tmp_path / "output"
        proj_input.mkdir()
        proj_out.mkdir()
        cfg = MagicMock()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._get_config.return_value = cfg
        monkeypatch.setattr(
            "clio.ui.routes.run.build_run_preview",
            lambda *args, **kwargs: {"ok": True, "steps": [], "warnings": []},
        )

        handle_post_run_preview(handler, {}, {"steps": ["compress"], "overwrite": True})

        handler._send_json.assert_called_once_with({"ok": True, "steps": [], "warnings": []})

    def test_preview_rejects_non_list_files(self, tmp_path: Path, _handler):
        handler = _handler
        handler._resolve_project_input.return_value = tmp_path

        handle_post_run_preview(handler, {}, {"files": "not-a-list"})

        handler._send_json.assert_called_once_with({"ok": False, "error": "files must be a list of video names"}, 400)

    def test_preview_rejects_unknown_step(self, tmp_path: Path, _handler, monkeypatch):
        handler = _handler
        handler._resolve_project_input.return_value = tmp_path
        handler._get_project_output.return_value = tmp_path / "output"
        handler._get_config.return_value = MagicMock()

        handle_post_run_preview(handler, {}, {"steps": ["unknown"]})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][1] == 400
```

Modify `clio/tests/test_server.py`:

```python
@patch("clio.ui.server.handle_post_run_preview")
def test_post_run_preview(self, mock_fn, handler_cls):
    handler = self._post_handler(handler_cls, {}, "/api/run/preview")
    handler.do_POST()
    mock_fn.assert_called_once()
```

Add `("POST", "/api/run/preview", True)` to `TestRouteAuthPolicy.test_known_route_auth_policy_matrix`.

- [ ] **Step 2: Run route tests to verify RED**

Run:

```bash
python -m pytest clio/tests/test_routes_run.py::TestHandlePostRunPreview clio/tests/test_server.py::TestDoPOST::test_post_run_preview -q
```

Expected: FAIL because `handle_post_run_preview` is not defined or server does not route it.

- [ ] **Step 3: Implement route handler**

Modify `clio/ui/routes/run.py`:

```python
from clio.ui.services.run_preview import build_run_preview
```

Add before `handle_post_run_start()`:

```python
def handle_post_run_preview(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/run/preview."""
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    proj_out = handler._get_project_output(proj_input)
    files_list = obj.get("files")
    if files_list is not None and not isinstance(files_list, list):
        return handler._send_json({"ok": False, "error": "files must be a list of video names"}, 400)
    steps = obj.get("steps")
    if steps is not None and not isinstance(steps, list):
        return handler._send_json({"ok": False, "error": "steps must be a list of step names"}, 400)
    try:
        preview = build_run_preview(
            cfg,
            proj_input,
            proj_out,
            steps=steps,
            files=files_list,
            overwrite=bool(obj.get("overwrite", False)),
            day_label=obj.get("day_label", "day1"),
        )
    except ValueError as exc:
        return handler._send_json({"ok": False, "error": str(exc)}, 400)
    handler._send_json(preview)
```

- [ ] **Step 4: Wire server dispatch**

Modify `clio/ui/server.py`:

- Add import from `clio.ui.routes.run`:

```python
handle_post_run_preview,
```

- Add route policy:

```python
RoutePolicy("POST", "/api/run/preview"),
```

- Add in `do_POST()` before `/api/run/start` or after it:

```python
if path == "/api/run/preview":
    return handle_post_run_preview(self, qs, obj)
```

- [ ] **Step 5: Run route/server tests to verify GREEN**

Run:

```bash
python -m pytest clio/tests/test_routes_run.py clio/tests/test_server.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add clio/ui/routes/run.py clio/ui/server.py clio/tests/test_routes_run.py clio/tests/test_server.py
git commit -m "feat(ui): expose run preview endpoint"
```

---

## Task 3: Frontend Preview Rendering and Fetch

**Files:**
- Modify: `clio/ui/static/src/runner.js`
- Test: `clio/ui/static/src/__tests__/runner.test.js`

- [ ] **Step 1: Write failing frontend renderer tests**

Create `clio/ui/static/src/__tests__/runner.test.js`:

```javascript
import { describe, it, expect } from 'vitest';
import { renderRunPreviewHtml } from '../runner.js';

describe('renderRunPreviewHtml', () => {
  it('renders run and skip counts', () => {
    const html = renderRunPreviewHtml({
      ok: true,
      selection: { mode: 'selected', count: 1, files: ['001_GL010684.mp4'] },
      steps: [
        { key: 'compress', label: 'compress', total: 1, will_run: 0, will_skip: 1, warnings: [] },
      ],
      warnings: [],
    });

    expect(html).toContain('compress');
    expect(html).toContain('0');
    expect(html).toContain('1');
    expect(html).toContain('001_GL010684.mp4');
  });

  it('escapes warnings and filenames', () => {
    const html = renderRunPreviewHtml({
      ok: true,
      selection: { mode: 'selected', count: 1, files: ['<script>.mp4'] },
      steps: [
        { key: 'voiceover', label: 'voiceover', total: 0, will_run: 0, will_skip: 0, warnings: ['<b>bad</b>'] },
      ],
      warnings: ['<img src=x>'],
    });

    expect(html).toContain('&lt;script&gt;.mp4');
    expect(html).toContain('&lt;b&gt;bad&lt;/b&gt;');
    expect(html).toContain('&lt;img src=x&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<b>bad</b>');
  });
});
```

- [ ] **Step 2: Run frontend renderer tests to verify RED**

Run:

```bash
npm test -- --run clio/ui/static/src/__tests__/runner.test.js
```

Expected: FAIL because `renderRunPreviewHtml` is not exported.

If local Node is below 18 and Vite fails before running tests, record the environment failure and continue with backend verification. CI uses Node 22.

- [ ] **Step 3: Add renderer and preview container**

Modify `clio/ui/static/src/runner.js`:

- Add after `updateRunFilesBadge()`:

```javascript
function renderRunPreviewHtml(summary) {
  if (!summary || !summary.ok) return '<p class="muted">运行前摘要不可用</p>';
  const files = summary.selection?.files || [];
  const fileText = files.length
    ? files.map(f => `<code>${escapeHtml(f)}</code>`).join(' ')
    : '全部匹配文件';
  const rows = (summary.steps || []).map(step => {
    const warnings = (step.warnings || []).map(w => `<div class="run-preview-warning">${escapeHtml(w)}</div>`).join('');
    return `
      <div class="run-preview-row">
        <span class="run-preview-step">${escapeHtml(step.label || step.key)}</span>
        <span>${step.total ?? 0}</span>
        <span>${step.will_run ?? 0}</span>
        <span>${step.will_skip ?? 0}</span>
        <span>${warnings}</span>
      </div>
    `;
  }).join('');
  const warnings = (summary.warnings || []).map(w => `<li>${escapeHtml(w)}</li>`).join('');
  return `
    <div class="run-preview">
      <h4>运行前摘要</h4>
      <p class="hint">范围: ${escapeHtml(summary.selection?.mode || 'all')} (${summary.selection?.count || 0}) ${fileText}</p>
      <div class="run-preview-table">
        <div class="run-preview-row run-preview-head">
          <span>步骤</span><span>候选</span><span>将运行</span><span>跳过</span><span>提示</span>
        </div>
        ${rows}
      </div>
      ${warnings ? `<ul class="run-preview-warnings">${warnings}</ul>` : ''}
    </div>
  `;
}
```

- In `renderRun()` add a preview container before `run-progress`:

```html
<div id="run-preview" style="margin-top:12px"></div>
```

- [ ] **Step 4: Add preview fetch helper**

Modify `clio/ui/static/src/runner.js`:

```javascript
function collectRunOptions() {
  const checked = [...document.querySelectorAll('.run-step-cb:checked')].map(cb => cb.dataset.step);
  const body = {
    day_label: ($('run-day')?.value.trim() || state.currentDay),
    steps: checked,
    use_transcripts: $('run-use-transcripts')?.checked ?? true,
  };
  if (state.selectionMode && state.selectedFiles.length > 0) {
    body.files = state.selectedFiles;
  }
  const overwriteCb = $('run-overwrite');
  if (overwriteCb && overwriteCb.checked) {
    body.overwrite = true;
  }
  return body;
}

async function refreshRunPreview() {
  const container = $('run-preview');
  if (!container) return null;
  const body = collectRunOptions();
  if (!body.steps.length) {
    container.innerHTML = '<p class="muted">请选择至少一个步骤以查看运行前摘要</p>';
    return null;
  }
  try {
    const summary = await api('POST', '/api/run/preview', body);
    container.innerHTML = renderRunPreviewHtml(summary);
    return summary;
  } catch (e) {
    container.innerHTML = `<p class="warn">运行前摘要加载失败: ${escapeHtml(e.message)}</p>`;
    return null;
  }
}
```

- Replace duplicated body construction in `startRun()` with:

```javascript
const body = collectRunOptions();
```

Then append context override as before.

- [ ] **Step 5: Wire refresh triggers**

In `renderRun()`:

- After checkbox persistence handlers, call `refreshRunPreview();`.
- In each `.run-step-cb` change handler, after `togglePlanSubOptions();`, call `refreshRunPreview();`.
- In `run-use-transcripts`, `run-day`, and `run-overwrite` change/input handlers, call `refreshRunPreview();`.
- At the start of `startRun()` after validating checked steps, call:

```javascript
await refreshRunPreview();
```

- [ ] **Step 6: Export renderer**

Update export block:

```javascript
export {
  renderRun,
  startRun,
  _stopRunPoll,
  updateRunFilesBadge,
  renderRunPreviewHtml,
};
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
npm test -- --run clio/ui/static/src/__tests__/runner.test.js
```

Expected with Node 18+: tests pass.

If local Node fails with Vite's `node:fs/promises` export error, document that frontend tests could not run locally due to Node version.

- [ ] **Step 8: Commit Task 3**

```bash
git add clio/ui/static/src/runner.js clio/ui/static/src/__tests__/runner.test.js
git commit -m "feat(ui): show run preview summary"
```

---

## Task 4: Roadmap and Full Verification

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: Update ROADMAP CR-008**

Change the CR-008 section from:

```markdown
- [ ] CR-008: UX/observability follow-ups.
  - Add pre-run summary showing selected videos, resolved artifact count per step, expected skips, and warnings.
```

to:

```markdown
- [~] CR-008: UX/observability follow-ups.
  - [x] Add pre-run summary showing selected videos, resolved artifact count per step, expected skips, and warnings.
```

Keep provider/model test connection and why-skipped panel open.

- [ ] **Step 2: Run targeted backend tests**

Run:

```bash
python -m pytest clio/tests/test_run_preview.py clio/tests/test_routes_run.py clio/tests/test_server.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run compile check**

Run:

```bash
python -m compileall -q clio main.py
```

Expected: exit code 0.

- [ ] **Step 4: Run full backend suite**

Run:

```bash
python -m pytest clio/tests/ -q
```

Expected: all tests pass.

- [ ] **Step 5: Run frontend tests if Node supports current Vite**

Run:

```bash
npm test -- --run
```

Expected on Node 18+: tests pass.

If local Node fails before tests execute, report exact Node/Vite error and note backend verification status.

- [ ] **Step 6: Check diff**

Run:

```bash
git diff --stat
git status --short
```

Expected: only CR-008 files are modified; no unrelated files are staged.

- [ ] **Step 7: Commit Task 4**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark run preview summary complete"
```

---

## Implementation Notes

- Do not modify `/api/run/start` behavior except sharing request-body helper logic on the frontend.
- Keep `POST /api/run/preview` read-only. It must not instantiate `ProgressTracker`, start threads, write `.progress.json`, or mutate `.processing.json`.
- Keep warnings informational. The Run button remains usable unless the existing start endpoint rejects the request.
- When matching selected artifacts, prefer `_matches_selected_artifact()` so generated AI title filenames still match selected compressed video names.
- Avoid adding a broad artifact index service in this iteration; that is CR-003.

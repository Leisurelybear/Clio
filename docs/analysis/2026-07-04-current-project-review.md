# Current Project Review - 2026-07-04

## Scope

This review covers the current `vlog-video-analysis` repository state: Python pipeline, AI provider layer, V2 config split, local Web UI, tests, CI, and docs. It is based on static code inspection plus local verification commands.

The working tree already had unrelated local changes before this review. They were not modified.

## Verification Snapshot

| Check | Result | Notes |
|---|---:|---|
| `python -m pytest clio/tests/ -q` | PASS | 972 passed in 25.48s. Local interpreter was Python 3.10.6, while the project targets 3.11+. |
| `ruff check clio main.py` | PASS | Core project paths pass. |
| `ruff check .` | FAIL | Failures are from untracked `.opencode/skills/**` files, not from `clio/`. |
| `npm test -- --run` | FAIL locally | Local Node is v16.14.0. Vite/Vitest needs newer Node; CI uses Node 22. |

## Executive Summary

The project is in good shape for a personal, local AI preprocessing pipeline. The Python test suite is broad, recent refactors are documented, and many historical issues have been fixed: Gemini File API cleanup, config split, provider registry UI, processing state, token accounting, and safer filesystem browsing.

The remaining high-value work is concentrated in a few cross-cutting boundaries:

- UI API security is only partial when the server is exposed beyond localhost.
- Selected-video execution uses inconsistent identifiers across pipeline stages.
- Cancellation is not propagated through all long-running operations.
- Long-video split staging ignores `splits_subdir` and can pollute `compressed/`.
- Recursive input projects are supported by CLI but not fully by the UI.
- Config validation and docs/examples lag behind the current architecture.

## Confirmed Issues

### P0 - Read APIs Are Only Partially Protected in Token Mode

`clio/ui/server.py` protects only a small GET allowlist via `_sensitive` (`/api/env`, config layer endpoints, `/api/video`, `/api/fs/dirs`) while many read endpoints remain unauthenticated: `/api/videos`, `/api/texts`, `/api/voiceover`, `/api/plan`, `/api/plans`, `/api/transcripts`, `/api/logs`, `/api/token-usage`, `/api/project`, and `/api/projects`.

Relevant code:

- `clio/ui/server.py:255` defines the protected GET set.
- `clio/ui/server.py:274` onward dispatches multiple unprotected read APIs.
- `clio/ui/services/project_service.py:253` accepts an `input_dir` query parameter and returns it if it is any existing directory.

Impact:

- In `--host 0.0.0.0` mode, token generation gives a false sense of complete protection.
- Project metadata, logs, AI outputs, token usage, and sidecar content may be readable without a token.
- `input_dir` can widen the readable target area if a directory contains recognizable project/output structure.

Recommendation:

- When `_api_token` is non-empty, require auth for all `/api/*` routes except a deliberate small public set, preferably none.
- Restrict `input_dir` query resolution to registered projects or explicitly allowed roots.
- Add a route-level auth matrix test for every GET/PUT/POST endpoint.

### P0 - Selected-Video Runs Filter Later Stages by the Wrong Identifier

The UI sends selected video filenames as `body.files` from `state.selectedFiles`, but downstream stages filter artifact filenames directly by stem.

Relevant code:

- `clio/ui/static/src/runner.js:180` sends selected video filenames.
- `clio/ui/routes/run.py:103` accepts `files`.
- `clio/pipeline.py:119` forwards `files` to all steps.
- `clio/tasks/scripts.py:90`, `clio/tasks/label.py:35`, and `clio/tasks/refine.py:58` compare selected video stems to `texts/*.json` or `scripts/*.json` stems.

Impact:

- Selected run of `voiceover`, `label`, or `refine` can process zero files because analysis JSON names contain AI-generated titles, not compressed video stems.
- Existing tests use matching artificial names like `002_B`, so they do not cover the real UI filename shape.

Recommendation:

- Normalize filtering around `media_identity.compressed_stem`, `media_identity.original_stem`, or index.
- Add a shared helper such as `matches_selected_artifact(json_path, selected_files)`.
- Add tests using realistic names: `002_GL010684.mp4` selected, `002_街头风景.json` artifact.

### P0 - Cancellation Is Still Incomplete for Long Operations

Several public functions accept `cancel_event`, but not every long-running operation receives it.

Relevant code:

- `clio/analyze.py:187` calls `provider.analyze_video(...)` without passing `cancel_event`, even though `GeminiProvider.analyze_video()` supports it.
- `clio/analyze.py:227` and `clio/analyze.py:288` call text-generation APIs without an in-flight cancellation path.
- `clio/tasks/label.py:81` calls `run_ffmpeg(...)` without `cancel_event`.
- `clio/split.py:9` has no `cancel_event` parameter and calls `run_ffmpeg(...)` internally.

Impact:

- Cancel can stop between items, but not reliably during upload, Gemini processing wait, text generation, split, or label burn-in.
- The UI may show cancellation while external work continues consuming time, quota, or CPU.

Recommendation:

- Pass `cancel_event` from `clio/analyze.py` into `provider.analyze_video`.
- Add optional cancellation support to text provider calls where practical.
- Add `cancel_event` to `split_video()` and pass it to `run_ffmpeg`.
- Pass `cancel_event` to label `run_ffmpeg`.
- Add tests asserting provider/ffmpeg calls receive the exact event object.

### P1 - Split Staging Ignores `splits_subdir` and Pollutes `compressed/`

`ProjectCompressConfig.splits_subdir` exists and is documented, but `run_compress_all()` currently stages split source segments directly inside `compressed/`.

Relevant code:

- `docs/project.example.yaml:37` documents `splits_subdir`.
- `clio/config/models.py:155` defines `splits_subdir`.
- `clio/tasks/compress.py:120` calls `split_video(..., config.compressed_dir, ...)`.
- `clio/split.py:49` writes segment files like `<stem>_seg01.mp4`.
- `clio/ui/routes/videos.py:134` lists every video file in `compressed/`.

Impact:

- Raw intermediate split files can show up in the compressed video list.
- Re-runs can split again before skip logic reuses compressed outputs.
- Step detection may treat intermediate files as successful compression output.

Recommendation:

- Stage split files under `output/<splits_subdir>/` or `output/compressed/<splits_subdir>/`.
- Filter UI compressed lists to indexed outputs only, or explicitly exclude split staging files.
- Skip splitting when `.vindex` plus compressed segments are valid.
- Add cleanup of successful intermediate split files if they are not needed.

### P1 - UI Original View Does Not Honor Recursive Input

The CLI video discovery supports recursive input scanning, but UI original browsing does not.

Relevant code:

- `clio/utils.py:178` supports `find_videos(..., recursive=True)`.
- `docs/project.example.yaml:16` documents `paths.recursive`.
- `clio/ui/routes/videos.py:224` lists originals with `proj_input.iterdir()`.
- `clio/ui/routes/videos.py:281` serves original video as `proj_input / actual_fname`.

Impact:

- Projects using nested camera/day folders work in CLI but are incomplete in UI.
- Original source playback can fail for recursive projects.

Recommendation:

- Use `find_videos(proj_input, recursive=cfg.paths.recursive)` in UI routes.
- Represent original files with a safe relative path or an opaque media id, not only basename.
- Update `/api/video` to resolve recursive originals safely.

### P1 - Config Validation Is Too Thin for User-Editable Settings

`_validate_config()` currently checks proxy URL and task provider existence, but many user-editable numeric and enum-like fields are not validated.

Relevant code:

- `clio/config/validators.py:8` only validates proxy and task provider names.
- `clio/tasks/analyze.py:292` uses `ThreadPoolExecutor(max_workers=max_workers)`, which fails if `max_workers <= 0`.
- `clio/config/models.py` exposes many numeric fields: `max_workers`, `target_size_mb`, `max_width`, `split_max_min`, `index_width`, `max_tokens`, `requests_per_minute`, `provider_ttl_min`.

Impact:

- UI edits can produce configs that load but fail later at runtime.
- Bad values fail far from the editing action, making the error harder to understand.

Recommendation:

- Validate numeric ranges at config save/load time.
- Validate provider `type` against supported types.
- Validate `video_analyze` provider is `type=gemini`.
- Warn when a task model is not in its provider `models` list.

### P1 - `.env` Writes Are Not Atomic

Config and artifact writes mostly use atomic helpers, but `/api/env` writes directly.

Relevant code:

- `clio/ui/routes/env_routes.py:41` uses `env_path.write_text(...)`.
- `clio/ui/services/file_service.py:50` already provides `_save_atomic(...)`.

Impact:

- A crash or interrupted write can leave `.env` truncated.
- API keys are high-value local state; they deserve the safest write path.

Recommendation:

- Use `_save_atomic()` for `.env`.
- Consider one backup file for the first overwrite.
- Add a test matching the existing config atomic-write behavior.

### P2 - Example Config and Docs Drift

Observed drift:

- `config.example.yaml` lists DeepSeek models `deepseek-v4-flash` / `deepseek-v4-pro`, while `docs/project.example.yaml` binds `deepseek-chat`.
- README badge still says `860+` tests, while the suite now has 972 tests.
- `ServerConfig.api_token` exists, but `config.example.yaml` has no `server:` example.
- The docs mention Python 3.11+, but local tests also passed on Python 3.10.6; the supported version policy should be explicit.

Impact:

- The model registry UI can show a default task model that is not present in the provider model list.
- Users do not see how to persist an API token in config.
- Test count and support matrix become unreliable documentation.

Recommendation:

- Align example model lists and task bindings.
- Update README badges/counts.
- Add a `server.api_token` commented example.
- State whether Python 3.10 is unsupported despite passing locally.

### P2 - `debug_print_prompt` Defaults to Printing Full Prompts

`GlobalAIConfig.debug_print_prompt` defaults to `True`, and prompt text is printed in full.

Relevant code:

- `clio/config/models.py:103` defaults `debug_print_prompt=True`.
- `clio/analyze.py:148` prints the full prompt.
- `config.example.yaml:46` documents debug printing as default-on.

Impact:

- Logs can contain full trip context, user feedback, transcript excerpts, and other private project content.
- This compounds the partial GET auth issue for `/api/logs`.

Recommendation:

- Default to `false` in examples and possibly in code.
- Keep an explicit debug toggle for development.
- Redact or summarize prompt logs by default.

## Design Risks and Maintainability Concerns

### Artifact Identity Is Still Fragmented

The project has `media_identity`, `.vmeta`, and `.vindex`, but many routes and tasks still fall back to filename stems and index prefixes. This is the root cause behind selected-run filtering, recursive original lookup gaps, split sidecar matching complexity, and older index-based fallbacks.

Recommended direction:

- Treat `media_identity` as the canonical cross-step contract.
- Build a small artifact index service per project: original -> compressed segments -> texts -> scripts -> transcript -> plan usage.
- Use that service in `videos.py`, selected-run filtering, rerun, label, cut, and export.

### UI Route Authorization Should Be Policy-Driven

The route dispatcher currently embeds auth decisions manually. As the API grows, this is easy to miss.

Recommended direction:

- Define route metadata: method, path, handler, auth policy, content type.
- Default `/api/*` to auth-required when token mode is enabled.
- Add tests that iterate route metadata instead of manually checking only a few endpoints.

### Config Auto-Upgrade Trades Safety for Comment Loss

The loader auto-injects dataclass defaults into YAML and rewrites files with PyYAML. This is useful, but it strips comments and formatting.

Recommended direction:

- Keep auto-upgrade for critical schema migrations only.
- Move non-critical default injection to an explicit `migrate-config` command or UI prompt.
- If comment preservation matters, evaluate `ruamel.yaml`.

### Frontend DOM Rendering Relies Heavily on Template Strings

The UI uses `innerHTML` heavily. Many values are escaped, but this pattern is brittle and easy to regress, especially for data attributes and file names.

Recommended direction:

- Prefer DOM creation plus `textContent` for user/file/provider values.
- Add focused XSS regression tests around filenames, provider names, model names, project names, logs, and AI-generated titles.
- Add a lightweight lint/review rule for raw interpolation inside `innerHTML`.

## Optimization Opportunities

### Performance

- Cache `/api/videos` sidecar scans; it currently reads many JSON files on every refresh.
- Avoid repeated `ffprobe` calls in list rendering where `.vmeta` already has duration.
- Skip split staging when valid compressed segments already exist.
- Add a bounded AI work queue instead of independent ad hoc thread pools per step.
- Add optional thumbnail generation/cache for video list previews.

### Reliability

- Add stale artifact detection for texts/scripts/transcripts when source identity changes.
- Add structured schema validation for AI outputs beyond default field insertion.
- Add resumable run manifests that record exact selected files, prompts, model versions, and provider ids.
- Add retry classification for malformed 200 responses from OpenAI-compatible providers.

### Developer Experience

- Add a local `npm`/Node version check in setup scripts.
- Exclude generated/untracked assistant skill directories from repository-wide lint commands, or document `ruff check clio main.py`.
- Add a `python main.py doctor` command that combines env, ffmpeg, API key, config, model, and write-permission checks.
- Add a test fixture that uses realistic artifact names from the actual pipeline, not simplified `001_A` names.

### UX

- Show a pre-run summary: selected videos, resolved artifact count per step, expected skips, and warnings.
- Add a model/provider "test connection" button.
- Show cancellation state per running subprocess/API call.
- Add a "why skipped" panel using `.processing.json`.
- Add visible warnings when `debug_print_prompt=true` or LAN host mode is active.

## Iteration Roadmap

### Phase 1 - Safety and Correctness

1. Require auth for all `/api/*` routes in token mode.
2. Restrict `input_dir` query resolution to registry/allowed roots.
3. Fix selected-video filtering through canonical media identity.
4. Pass `cancel_event` through Gemini analyze, split, and label.
5. Make `.env` writes atomic.

### Phase 2 - Split and Recursive Media Cleanup

1. Move split staging out of `compressed/` using `splits_subdir`.
2. Filter compressed UI lists to valid indexed outputs.
3. Make UI original view recursive-aware.
4. Rebuild route/file resolution around artifact identity.

### Phase 3 - Config Hardening

1. Add numeric and enum validation.
2. Validate task/provider capability compatibility.
3. Align example model lists and project defaults.
4. Add `server.api_token` example and LAN-mode docs.

### Phase 4 - Observability and UX

1. Default prompt debug logging off.
2. Add run preflight summaries.
3. Add provider test buttons and model availability checks.
4. Improve `.processing.json` display and skip diagnostics.

### Phase 5 - Product Features

1. Storyboard view: plan sequence + clips + voiceover in one timeline.
2. Clip quality scoring: shaky/dark/duplicate/audio-confidence indicators.
3. Smart material search by location, mood, object, action, or transcript keyword.
4. Multi-day trip timeline with map/location grouping.
5. Export presets for JianYing/CapCut variants, EDL, CSV, and subtitle formats.

## New Feature Ideas

- **AI shot clustering**: group visually similar clips and detect duplicates before analysis.
- **Auto highlight extraction**: propose best 3-8 seconds from each clip using timeline + transcript confidence.
- **B-roll matcher**: match voiceover phrases to visual candidate clips.
- **Trip map view**: infer and manually correct locations, then group clips by route.
- **Person/scene tags**: reusable tags for people, food, transport, landmark, hotel, airport, street, nature.
- **Cost estimator**: estimate Gemini/OpenAI cost before a run based on video count, duration, prompt size, and model.
- **Prompt versioning**: store prompt hash/version on each generated artifact for reproducibility.
- **Review queue**: flag low-confidence AI outputs for manual review before planning.
- **Subtitle export**: generate `.srt` / `.ass` from transcript and voiceover.
- **One-click archive**: package source metadata, generated JSON, plans, token stats, and logs for a completed trip.

## Suggested Tests to Add

- Auth tests for every GET route with `_api_token` set.
- Selected-run tests using realistic compressed filenames and AI-generated analysis JSON names.
- Cancellation propagation assertions for Gemini analyze, split, label, and text steps.
- Split staging tests asserting raw split files do not appear in `/api/videos`.
- Recursive UI tests for nested original files.
- Config validation tests for invalid `max_workers`, `max_width`, `target_size_mb`, provider `type`, and task/provider mismatch.
- Atomic `.env` write tests.
- Frontend XSS tests for filenames, provider names, model names, AI titles, logs, and project names.

## Positive Notes

- The Python test suite is broad and currently green.
- Core linting for `clio` and `main.py` passes.
- The V2 config split is a strong architectural improvement.
- `.vmeta` / `.vindex` and `media_identity` are the right direction for stable media mapping.
- Gemini File API cleanup is already implemented.
- Rate limiting no longer sleeps under the lock in the normal provider path.
- Local filesystem browsing is restricted to home/drives, which is a major improvement over earlier unrestricted browsing.


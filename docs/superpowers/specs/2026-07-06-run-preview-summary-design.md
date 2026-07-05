# Run Preview Summary

## 1. Problem

The Run panel can start selected pipeline steps, but it does not tell the user what will happen before the run starts. This creates avoidable confusion:

- selected videos may not map to later artifacts such as analysis JSON or voiceover JSON;
- skip behavior depends on `analyze.skip_existing` and the run `overwrite` flag;
- users cannot see whether a step will process zero files until after they start the run;
- warnings are only discovered through logs or the processing-state table after the fact.

CR-008 covers several observability follow-ups. This spec scopes the first iteration to a **pre-run summary** only. Provider/model connection tests and a full "why skipped" panel remain separate iterations.

## 2. Goals

- Show a run preview before starting the pipeline.
- Reuse the same project, selected-file, step, and overwrite inputs as `POST /api/run/start`.
- Report counts per selected step: total candidates, will run, will skip, and warnings.
- Warn when a selected step is likely to do no useful work, especially when downstream artifacts are missing.
- Keep the preview read-only: no files are created, modified, or deleted.
- Add backend tests for the preview decisions.

## 3. Non-Goals

- Do not implement provider/model connectivity testing.
- Do not redesign `.processing.json` or add persistent skip-reason storage in this iteration.
- Do not guarantee byte-for-byte identical behavior with every task implementation branch; the preview is a conservative estimate for user visibility.
- Do not block runs when warnings exist. The user may still run intentionally.

## 4. Backend API

Add `POST /api/run/preview`.

Request body mirrors `/api/run/start` where relevant:

```json
{
  "day_label": "day1",
  "steps": ["compress", "analyze", "voiceover", "plan"],
  "files": ["001_GL010684.mp4"],
  "overwrite": false,
  "use_transcripts": true
}
```

Response:

```json
{
  "ok": true,
  "selection": {
    "mode": "selected",
    "count": 1,
    "files": ["001_GL010684.mp4"]
  },
  "steps": [
    {
      "key": "compress",
      "label": "compress",
      "total": 1,
      "will_run": 0,
      "will_skip": 1,
      "warnings": []
    },
    {
      "key": "voiceover",
      "label": "voiceover",
      "total": 0,
      "will_run": 0,
      "will_skip": 0,
      "warnings": ["No analysis JSON matched the selected videos."]
    }
  ],
  "warnings": ["voiceover has no matching input artifacts."]
}
```

Auth policy: same as `/api/run/start`, because it reveals project file names.

## 5. Preview Logic

Create a small backend helper module, tentatively `clio/ui/services/run_preview.py`, to keep route code thin and testable.

Inputs:

- `AppConfig`
- project input directory
- project output directory
- selected `steps`
- optional selected `files`
- `overwrite`

Step estimates:

- `compress`: candidates are original videos from `config.paths.input_dir`, respecting `config.paths.recursive`. If `files` is present, match selected stems using existing selection helpers. Skip when a corresponding compressed output exists and `overwrite` is false.
- `analyze`: candidates are compressed videos in `config.compressed_dir`, filtered by selection helpers. Skip when an analysis JSON matching the artifact identity exists and `overwrite` is false.
- `voiceover`: candidates are analysis JSON files in texts directories, filtered using `_matches_selected_artifact`. Skip when a voiceover JSON exists and `overwrite` is false.
- `transcribe`: candidates are original videos, filtered by selection helpers. Skip when a transcript JSON exists and `overwrite` is false.
- `plan`: project-level step. Total is `1`; skip when the day plan exists and `overwrite` is false.
- `label`: candidates are analysis JSON or compressed videos depending on existing task behavior. Use a conservative compressed-video estimate; warn when no compressed videos exist.

Warnings:

- selected files list is empty after filtering;
- a selected downstream step has no matching inputs;
- a step depends on earlier artifacts that are missing and that earlier step is not selected;
- unknown step names should return HTTP 400, matching run-start validation expectations.

## 6. Frontend UX

Add a compact preview block under the Run controls:

- refresh automatically when selected steps, selected files, or overwrite changes;
- also refresh immediately before `POST /api/run/start`;
- show a small table: Step, Will run, Skip, Warnings;
- show selected-file count using the existing selection badge;
- if preview fetch fails, show a non-blocking warning and keep the Run button usable.

The first implementation can render through a small pure function such as `renderRunPreview(summary)`, which can be unit-tested independently.

## 7. Testing

Backend:

- no selected files: preview counts all available originals/compressed artifacts;
- selected file with generated analysis JSON title still matches by identity;
- `overwrite=true` converts existing-output skips into will-run counts;
- downstream missing-artifact warning for `voiceover` with selected videos but no texts JSON;
- unknown step returns 400;
- route requires auth according to the centralized route policy.

Frontend:

- rendering summary table escapes file names and warning text;
- warning-only preview does not disable the run button;
- overwrite or step checkbox changes trigger preview refresh through the event handler.

## 8. Rollout

- Implement in one feature commit after this spec is approved.
- Keep existing `/api/run/start` unchanged.
- Update `ROADMAP.md` CR-008 after implementation, marking only the pre-run summary sub-item complete.

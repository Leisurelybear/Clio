---
name: vlog-artifact-identity-fixes
description: Use when fixing Clio original/compressed/split video matching, sidecar JSON lookup, media_identity, .vmeta/.vindex, selected-file runs, plan resolution, cut/export mapping, or video list navigation.
---

# Vlog Artifact Identity Fixes

## Core Contract

Prefer canonical identity over filenames:

1. `media_identity` in generated JSON
2. `.vmeta` and `.vindex`
3. compressed/original stems
4. index prefixes as legacy fallback

Generated JSON filenames can contain AI titles and are not reliable identifiers.

## Files To Inspect First

- `clio/identity.py`
- `clio/vmeta.py`
- `clio/ui/services/file_service.py`
- `clio/ui/routes/videos.py`
- `clio/tasks/_helpers.py`
- `clio/export/jianying.py`
- `clio/tasks/cut.py`

## Workflow

1. Build a realistic failing case with an original such as `GL010684.MP4`, compressed files like `001_GL010684_seg01.mp4`, and AI JSON with a non-stem title.
2. Verify whether `.vmeta`, `.vindex`, or `media_identity` should be the source of truth for the code path.
3. Reuse existing lookup helpers before adding new matching logic.
4. Preserve split segment offsets and duration behavior.
5. Keep compressed and original UI views symmetric when adding navigation or matching metadata.
6. Run focused media identity and route tests.

## Verification

```bash
python -m pytest clio/tests/test_identity.py clio/tests/test_vmeta.py clio/tests/test_file_service.py clio/tests/test_routes_videos.py -q
```

Run export/cut tests too if plan or JianYing mapping changes:

```bash
python -m pytest clio/tests/test_export.py clio/tests/test_tasks_cut.py -q
```

## Common Mistakes

- Matching by generated text/script filename.
- Treating one original file as one UI row when split compressed segments exist.
- Ignoring case differences in original extensions.
- Recomputing offsets when `.vmeta` already has exact split info.

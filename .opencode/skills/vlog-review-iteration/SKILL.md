---
name: vlog-review-iteration
description: Use when continuing remediation from a Clio review document, ROADMAP bug table, audit finding, or optimization item and turning one finding into a verified fix.
---

# Vlog Review Iteration

## Workflow

1. Read the target review/ROADMAP item and identify one independent finding.
2. Verify the finding against current code before editing; many older review items are already fixed.
3. If the finding is real, prefer a focused failing test or a direct observable reproduction.
4. Implement the narrowest fix in the owning module.
5. Update only the relevant tracking doc (`ROADMAP.md` or the review table) when status changes.
6. Run targeted tests first, then full regression when the touched code is shared.
7. Commit one logical fix with an English Conventional Commit message.
8. Do not push without explicit user confirmation.

## Suggested Test Selection

- Route/auth changes: `clio/tests/test_server.py` plus route-specific tests.
- Config changes: `test_config_v2.py`, `test_routes_config.py`, `test_config_cache.py`.
- Media matching: `test_identity.py`, `test_vmeta.py`, `test_file_service.py`, `test_routes_videos.py`.
- Pipeline/run changes: `test_pipeline.py`, `test_routes_run.py`, `test_progress.py`.
- Frontend-only changes: `node --check` for touched modules; Vitest requires Node 18+.

## Common Mistakes

- Implementing stale review advice without checking current code.
- Batching unrelated review findings in one commit.
- Updating ROADMAP status without verification.
- Letting pre-commit formatting stat noise look like a real unstaged diff; check `git diff --stat`.

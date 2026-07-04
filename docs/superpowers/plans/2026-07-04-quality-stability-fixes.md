# Quality and Stability Fixes - 2026-07-04

## Context

This plan tracks small, isolated fixes applied after syncing `main` to the latest remote state on 2026-07-04.

The goals are:

- Improve cancellation reliability.
- Reduce partial-run inconsistencies.
- Harden local UI safety boundaries.
- Keep each fix small enough to review and commit independently.

## Fix Log

- [x] Propagate cancellation into Gemini video analysis.
- [x] Propagate cancellation into label ffmpeg runs.
- [x] Propagate cancellation into split ffmpeg runs.
- [x] Harden selected-video filtering across artifact-producing steps.
- [x] Make `.env` writes atomic.
- [x] Expand token-mode auth coverage for read APIs.

## Verification

Each fix should run the narrowest relevant pytest module first. Run the full suite after a batch of related fixes.

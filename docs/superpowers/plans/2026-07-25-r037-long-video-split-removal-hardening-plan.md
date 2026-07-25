# R-037 Long-video split-removal hardening plan

**Date:** 2026-07-25  
**Status:** Completed

## Scope

Harden the logical analyze-window implementation introduced when physical video splitting was removed. Preserve read-only compatibility for legacy split projects while ensuring canonical whole-file media always uses the unified path.

## Tasks

1. Treat valid `.vmeta` and `.vindex` sidecars as authoritative when deciding whether a compressed file is a legacy segment.
2. Derive non-split original identity from sidecar source paths so natural `_partNN`, `_ptNN`, and `_chunkNN` filenames remain intact.
3. Apply `analyze.max_analyze_duration_min` to every whole source clip before any Gemini window calls.
4. Replace silent analyze-window truncation with a fail-closed window-count guard.
5. Probe stream-copy window outputs and re-encode when duration drift exceeds tolerance.
6. Suppress legacy segment artifacts when a canonical whole-file artifact exists for the same original during analysis and compressed-video listing.
7. Propagate cancellation as cancellation instead of converting it into an AI failure.
8. Deduplicate overlap timeline rows using normalized text similarity rather than exact equality only.
9. Add focused regression tests, then run Python and frontend test suites.

## Acceptance

- A new whole file named `holiday_part01.mp4` is not treated as a legacy segment.
- Its `MediaIdentity.original_stem` remains `holiday_part01`.
- A positive whole-clip duration cap prevents all Gemini calls when exceeded.
- Every returned analyze-window set covers the full requested duration or raises before analysis starts.
- Temporary window slices stay within the configured duration tolerance.
- Hybrid directories do not analyze or list both canonical whole files and their legacy segments by default.
- User cancellation leaves progress/state cancelled and never raises an “AI analysis failed” summary.
- Paraphrased duplicate overlap events collapse while distinct nearby events remain.

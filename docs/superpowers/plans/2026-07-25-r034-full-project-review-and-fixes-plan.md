# R-034 Full Project Review and Fixes Plan

**Date:** 2026-07-25  
**Status:** Complete  
**Scope:** Production Python and frontend JavaScript, configuration and persistence boundaries, media pipeline behavior, Web UI routes, and test/CI coverage.

## Goal

Perform a fresh full-project logic review against the current `main` branch, document verified findings, fix actionable defects without broad unrelated refactors, and add regression coverage for each behavior change.

## Review Method

1. Establish a clean baseline from git history, configuration examples, maintenance guidance, existing review findings, and current test/tool configuration.
2. Run Python and frontend tests plus Ruff and mypy to identify observable failures and suspicious type boundaries.
3. Review backend domains in dependency order: config and identity, AI providers, pipeline tasks, plan/cut/export, then UI server routes and services.
4. Review frontend state, request, editor, runner, preview, and persistence flows, focusing on backend/frontend contract mismatches and stale async state.
5. Verify findings against production call paths and existing tests; exclude speculative issues and previously fixed findings.
6. Write `docs/analysis/2026-07-25-full-project-review-and-fixes.md` with severity, impact, evidence, resolution, and residual risks.
7. Implement focused fixes and behavioral regression tests, then run targeted and full validation.

## Constraints

- Preserve the two-layer global/project configuration contract.
- Preserve selected-file, cancellation, overwrite, and progress semantics across CLI and UI entry points.
- Reuse artifact identity and path-sandbox helpers instead of adding parallel matching logic.
- Do not change public behavior solely to satisfy mypy unless the runtime contract is demonstrably incorrect.
- Do not fix unrelated style or architectural debt during defect patches.

## Completion Criteria

- Every documented high or medium finding is either fixed, explicitly deferred with rationale, or proven non-actionable.
- Every code fix has a regression test at the narrowest useful level.
- Ruff, pytest, and Vitest pass; mypy results are recorded and newly introduced errors are not accepted.
- `ROADMAP.md` and the final review document reflect the delivered state.

# R-038 Remove dead physical-split writer plan

**Date:** 2026-07-26  
**Status:** Completed

## Scope

Delete the unused physical video split writer after logical analyze windows became the only production long-video path. Keep legacy split artifact reading in identity, UI, cut, plan, transcript, and export flows.

## Tasks

1. Remove `clio/split.py` and its writer-only unit tests.
2. Remove `split_max_min`, `splits_subdir`, and `reencode_split` from active project and compatibility config models.
3. Stop auto-injecting the deprecated keys into project YAML while continuing to ignore existing values safely.
4. Remove deprecated controls and examples from user-facing configuration surfaces.
5. Keep V1-to-V2 ownership routing for old keys so legacy global configs migrate without failure.
6. Update AGENTS and directory documentation to describe legacy split support as read-only artifact compatibility only.
7. Run configuration, compression, UI, Python, and frontend regression suites.

## Acceptance

- No production module can create `_segNN` video files or split manifests.
- Existing project YAML files containing deprecated split keys still load successfully.
- New and auto-upgraded project YAML files do not receive deprecated split keys.
- The Web UI and example configuration do not show physical split controls.
- Legacy split artifacts remain readable through the existing identity gates.

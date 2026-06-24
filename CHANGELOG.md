# Changelog

## 2026-06-24

### Fixed
- Transcribe: extract `_extract_orig_stem` helper, remove dead `_resolve_original_video`, fix state key for missing-original case, wire `progress_callback` to `_extract_audio` in rerun (7fc9b18)
- Transcribe: move `error_count` outside tracker guard so errors are always counted (5eabf52)
- Transcribe: from original video, CUDA fallback, centralized model download UX (428e275)

### Added
- Unit tests for files/overwrite params across all pipeline steps (fa5fee1)
- Fix review: label.py shadow, plan.py overwrite gate, type validation and tests (95b539f)

## 2026-06-22

### Added
- R-014 token usage tracking: `TokenUsage`, `AIResponse`, `FileTokenUsageStore`, Gemini/OpenAI provider usage extraction, UI Tokens panel, CLI `tokens` subcommand (01317f0–e875159)
- R-018 multi-video selection + step execution: sidebar checkboxes, `files`/`overwrite` params, pipeline filtering (3ace4f4–5b0a9c0)
- Config auto-upgrade: inject missing dataclass defaults on load (b4bd05b)
- Split reencode option for frame-accurate cuts (cd1da63)
- AI debug print prompt option (92a6d9e)
- Refine panel with context textarea and AI trigger button (089dc6a)

### Fixed
- Provider cache TOCTOU race + Gemini close leak (45e09e3)
- Transcribe thread-safe os.environ save/restore (9ef45e2)
- Config propagate max_tokens to ProviderConfig (dc3ad72)
- Various code review fixes (6efbcc3, 7017ff6, badb621, bdcc678)
- ffprobe integrity check for skip_existing (6c3c231)
- ETA fix: elapsed_total moved to finally block (94f4501)
- Restore missing analyze header in config.example.yaml (d799f21)

## 2026-06-20

### Added
- Whisper model UI download: POST /api/whisper/install with progress, download button in transcript tab (326fe46, e361f7d)
- Project remove + empty state UI (12c314e, 360b91a)
- Quick-launch serve scripts (fcbccf5)
- ENV_FIREWORKS_API_KEY support

### Fixed
- UI event binding order for empty state (aa720d8, c1584df)
- Lint + UT after empty-state changes (fe45f53)

## 2026-06-19

### Fixed
- Setup scripts: idempotency, input dir check, CUDA disk space (3a5eaed)
- Modal event binding before init early return (aa720d8)
- All event handlers before try block for empty state (c1584df)

## 2026-06-18

### Added
- R-012 preview progress bar: two-row layout, play/pause toggle, segment blocks with tooltip (298a729–5029ba1)
- UI layout overhaul: resizable panels, dark OLED theme (7f5c0d6)

### Fixed
- ProcessingState recorded after generating plan (a29a53c)
- max_tokens + temperature in OpenAI API calls (3660fea)
- compress MIN_VALID_SIZE 256→50KB (78a0b69)
- transcribe find_videos for recursive scanning (6d23de3)
- Trip context cache key includes file mtime (cdcc873)
- TRANSCRIPT_CONTEXT English→Chinese (3ce9ef3)
- Atomic writes for scripts/refine output (123c84f)
- Split clean up partial segments + atomic manifest (097a6ff)
- Stale existing files cleanup on source_file mismatch (eb93573)
- Structured validation for AI responses (129de90)
- Closure late-binding trap in progress callback (d410c4e)

## 2026-06-17

### Fixed
- 10 commits covering usability and code quality issues from comprehensive analysis (a29a53c–d410c4e):
  - Plan state recording, atomic writes, max_tokens validation
  - Closure trap fix, transcript Chinese, prompts validation

## 2026-06-16

### Fixed
- Second code review: 5 S0 + 5 S1 + 1 S2 items all fixed:
  - runner.js prog undefined (S0-1)
  - analyze.py transcript bound to source_stem (S0-2)
  - split.py missing manifest (S0-3)
  - Pipeline recovery atomic writes (S0-4)
  - /api/cut project query parameter (S1-1)
  - transcript UI _segNN stripping (S1-2)
  - _extract_audio ffmpeg parameter (S1-3)
  - Whisper batch gated by max_analyze_duration (S1-4)
  - AI provider cache composite key (S1-5)
  - Whisper model cache key device/compute_type (S2-3)

### Added
- Comprehensive code review: 6 Critical + 12 Important + 36 Minor, fixed 6+12+5

## Earlier

See git log for full history. Key milestones:
- Initial scaffold (commit 1)
- ffmpeg compress with comma escaping fix (commit 2)
- Whisper ASR full integration (commits ~98–112)
- Security fixes: _is_safe_basename, non-retryable 4xx (commits 113–118)
- UI fixes: video ref, state capture, btn guard (commits 119–122)
- Provider cache + test isolation (commits 130–131)
- CI fixes for ctranslate2 mock, Linux case, lint (commits 133–136)
- 27 new tests for whisper, processing_state, CLI (commit 137)

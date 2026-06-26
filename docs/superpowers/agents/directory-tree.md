# Full Directory Tree

> Extracted from AGENTS.md §3. Reference document — load on demand when exploring codebase structure.

```
vlog-video-analysis/
├── main.py                    # CLI entry, all subcommands registered here
├── vlog_tool/
│   ├── config/                # Config package: loader, models, parsers, validators, enums, descriptions
│   ├── shutdown.py            # beforeStop hook: atexit + SIGTERM → kill ffmpeg + close provider connections + flush IO
│   ├── pipeline.py            # High-level pipeline functions (run_analyze_all, etc.)
│   ├── analyze.py             # AI interaction (analyze_video, generate_voiceover, plan_daily_vlog, refine_*)
│   ├── compress.py            # ffmpeg wrapper
│   ├── prompts.py             # All prompt templates (constants)
│   ├── transcribe.py          # Whisper ASR transcription core
│   ├── whisper_cli.py         # whisper install/check CLI
│   ├── utils.py               # ffmpeg path discovery, file IO, mask_if_looks_like_key, extract_json
│   ├── log.py                 # Logging: hourly rotating files + _TeeWriter + timed/format_size/format_duration
│   │                           #     + sys.excepthook turns uncaught exceptions into a single ERROR log
│   ├── progress.py            # Progress tracker: read/write/ETA/atomic write
│   ├── split.py               # Long video splitter: keyframe-aware splitting
│   ├── vmeta.py               # .vmeta/.vindex sidecar metadata: read/write/stale detection
│   ├── cut.py                 # Segment cutting: ffmpeg wrapper + time parsing
│   ├── ratelimit.py           # Rate limiter: interval-based throttling with acquire()
│   ├── session_log.py         # Session-level log tracking
│   ├── processing_state.py    # Per-file pipeline state matrix
│   ├── _constants.py          # Global constants: VIDEO_EXTS, etc.
│   ├── tasks/                 # Pipeline steps (split from pipeline.py)
│   │   ├── transcribe.py        # Pipeline task: run_transcribe_all
│   │   └── ...
│   ├── ui/                    # Local Web UI (visual editing of AI output; stdlib http.server, zero new deps)
│   │   ├── server.py            #   UIHandler (BaseHTTPRequestHandler) + make_handler + run
│   │   ├── README.md            #   UI usage documentation
│   │   ├── routes/              #   Route handlers
│   │   │   ├── refine.py           #   POST /api/refine (AI refine trigger)
│   │   │   ├── transcripts.py   #   Transcript GET/PUT API
│   │   │   └── whisper_routes.py#   Whisper check API
│   │   └── static/              #   Frontend, no build step, ES modules
│   │       ├── index.html
│   │       ├── style.css
│   │       └── src/
│   │           ├── main.js
│   │           ├── layout.js        #   Draggable panels, collapse, persistence
│   │           ├── sidebar.js
│   │           ├── runner.js
│   │           ├── editor.js
│   │           ├── viewer.js
│   │           ├── api.js
│   │           ├── state.js
│   │           └── utils.js
│   └── ai/
│       ├── base.py            # TaskName enum, Provider Protocol
│       ├── factory.py         # Look up provider by name
│       ├── gemini.py          # Multimodal: File API upload + poll PROCESSING (wrapped with_retry)
│       └── openai_compat.py   # OpenAI compatible: DeepSeek / OpenAI / Tongyi Qianwen (通义) / Moonshot (Kimi) (wrapped with_retry)
│   ├── export/                # Export formats: JianYing draft builder + FORMAT_REGISTRY dispatch
├── templates/
│   ├── vlog_template.md       # Voice-over style template (user-customizable)
│   └── trip_context.md        # Trip background & AI rules (auto-injected into all prompts)
├── config.example.yaml        # Config template committed to git
├── .env.example               # Env variable template committed to git
├── config.yaml / .env         # User's local real config, gitignored
├── requirements.txt           # Loose dev dependencies
├── requirements-locked.txt    # Reproducible build with pinned versions
├── .github/workflows/test.yml # GitHub Actions CI (pushes + PRs)
├── vlog_tool/tests/           # Unit tests (pytest, 864 cases)
│   ├── conftest.py            #   Shared fixtures
│   ├── test_ai.py             #   12 tests - factory dispatch / TaskName / provider instantiation
│   ├── test_ai_gemini.py      #   30 tests - Gemini client / retry / upload / wait
│   ├── test_ai_openai_compat.py#  18 tests - OpenAI compat / retry / close
│   ├── test_analyze.py        #   10 tests - _resolve_original file matching
│   ├── test_analyze_funcs.py  #    9 tests - _wrap_with_context / plan filtering
│   ├── test_compress.py       #    7 tests - compress_video bitrate / params / cancel
│   ├── test_config.py         #   41 tests - config loading/merging/validation
│   ├── test_config_cache.py   #   28 tests - ConfigCache LRU / mtime invalidation / thread-safe
│   ├── test_config_descriptions.py # 5 tests - config description helpers
│   ├── test_cut.py            #   26 tests - time parsing / filename generation / cutting / offset
│   ├── test_export.py         #   19 tests - JianYing draft builder / materials / tracks
│   ├── test_export_routes.py  #    4 tests - export API route
│   ├── test_file_service.py   #   61 tests - safe basename / atomic save / segment matching
│   ├── test_fs.py             #   12 tests - path traversal / permission errors / drive listing
│   ├── test_helpers.py        #   23 tests - _next_index / _write_csv / _rewrite_text_file
│   ├── test_log.py            #   24 tests - TeeWriter / format_size / format_duration / setup_logging
│   ├── test_main.py           #    7 tests - CLI subcommand dispatch
│   ├── test_pipeline.py       #    6 tests - cancel_event + files/overwrite propagation
│   ├── test_plan.py           #    2 tests - plan prompt transcript injection
│   ├── test_processing_state.py#   8 tests - mark / reset / persistence / corruption recovery
│   ├── test_processing_state_routes.py# 1 test - processing state API route
│   ├── test_progress.py       #   15 tests - ProgressTracker read/write/ETA/atomic write
│   ├── test_project_service.py#   22 tests - output dir / registry / step detection
│   ├── test_ratelimit.py      #   12 tests - RateLimiter interval/logging
│   ├── test_refine_routes.py  #   24 tests - refine API route / busy lock / error handling
│   ├── test_reindex.py        #    9 tests - video index rebuild / grouping / fallback
│   ├── test_routes_config.py  #   11 tests - config GET/PUT/INIT routes
│   ├── test_routes_env.py     #    8 tests - env variable API routes
│   ├── test_routes_plan.py    #    8 tests - plan GET/PUT/cut routes
│   ├── test_routes_projects.py#   11 tests - project CRUD routes
│   ├── test_routes_run.py     #    9 tests - run start/status/rerun/cancel routes
│   ├── test_routes_texts.py   #   10 tests - texts/voiceover GET/PUT routes
│   ├── test_routes_transcripts.py# 30 tests - transcript/whisper API routes
│   ├── test_routes_videos.py  #   16 tests - videos GET routes
│   ├── test_server.py         #   52 tests - HTTP dispatch / _send_json / _send_static / routing
│   ├── test_session_log.py    #    9 tests - session log write/read/clear/Max limit
│   ├── test_shutdown.py       #   16 tests - process registration / before_stop / signal hooks
│   ├── test_split.py          #    8 tests - split_video segment calculation
│   ├── test_static_files.py   #    5 tests - static file serving / path traversal
│   ├── test_tasks_analyze.py  #    9 tests - run_analyze_all + files/overwrite
│   ├── test_tasks_compress.py #    5 tests - run_compress_all + files_filter
│   ├── test_tasks_cut.py      #   16 tests - run_cut_all / offset / cancel
│   ├── test_tasks_label.py    #    8 tests - run_label_videos + files/overwrite
│   ├── test_tasks_refine.py   #   21 tests - run_refine_texts/scripts/fix_mode + files_filter
│   ├── test_tasks_scripts.py  #   10 tests - run_generate_scripts + files/overwrite
│   ├── test_tasks_transcribe.py#  12 tests - run_transcribe_all + files_filter
│   ├── test_token_routes.py   #    2 tests - token usage API route
│   ├── test_token_usage.py    #   15 tests - _merge_stats / FileTokenUsageStore / record / get_stats
│   ├── test_transcribe.py     #   20 tests - transcribe toggle / device / model / CUDA fallback
│   ├── test_utils.py          #   47 tests - extract_json / mask_key / sanitize / find_videos / with_retry / resolve_binary
│   ├── test_utils_expanded.py #   27 tests - run_subprocess / discover_ffmpeg / atomic_io / run_ffmpeg / get_duration
│   ├── test_vmeta.py          #   13 tests - VideoMeta/VideoIndex read/write/stale/is_split
│   └── test_whisper_cli.py    #    6 tests - whisper check/install status
```

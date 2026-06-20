# Vlog Editing Helper

Pre-processing pipeline for travel vlog editing: compress footage → generate
summary and timeline → voiceover script → daily vlog edit plan.

Final touch-ups (effects, lipsync, subtitles) are done in **剪映 (CapCut/JianYing)**
or any editor of your choice.

[简体中文](README.md)

---

## Features

| Step | Feature | Command |
|------|---------|---------|
| 1 | Compress long videos (strip audio, control size) for AI analysis | `compress` |
| 2 | AI video analysis (summary + timeline), provider-pluggable | `analyze` |
| 3 | Sequential naming + text files + CSV summary | done automatically by `analyze` |
| 4 | Voiceover script generation using a template | `scripts` |
| 5 | Recommended clip order for a single-day vlog | `plan --day day1` |
| 6 | Burn the index number onto the video for editing reference | `label` |
| 7 | Offline ASR speech transcription | `transcribe` |
| — | One-shot full pipeline | `run --day day1` |
| — | Web UI visual editor | `serve` |
| — | Environment check | `check` |

---

## Visual Editor UI

The `serve` subcommand starts a local web server, default `http://127.0.0.1:8765/`:

| Pipeline runner view | Vlog plan editor view |
|:---:|:---:|
| ![pipeline](docs/screenshots/pipeline.png) | ![plan](docs/screenshots/plan.png) |

Zero external dependencies: pure stdlib `http.server`. See `vlog_tool/ui/README.md` for details.

---

## Quick Start

### 1. Bootstrap

```bash
# Windows
.\setup.ps1

# Linux / macOS
./setup.sh
```

Creates a virtualenv, installs deps, installs ffmpeg, copies `.env.example` → `.env`.

### 2. Fill in API key

Edit `.env`:

```env
GEMINI_API_KEY=your_Gemini_API_Key
```

### 3. Prepare config

```bash
cp config.example.yaml config.yaml
# Then edit paths.input_dir, proxy.url etc.
```

### 4. Run analysis

```bash
python main.py analyze -i "E:/Videos/Yunnan"
# or the full pipeline:
python main.py run -i "E:/Videos/Yunnan" --day day1
```

Re-running skips existing outputs. Add `--force` to regenerate.

### 5. View logs

All output goes to both console and `logs/` (rotated hourly). Tail the latest:

```bash
# Windows (PowerShell)
Get-Content (Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) -Tail 50

# Linux / macOS
ls -t logs/*.log | head -1 | xargs tail -50
```

> Full CLI reference (all subcommands, flags, configuration) → [docs/cli-reference.md](docs/cli-reference.md).

---

## FAQ

### ffmpeg not found

Run `.\setup.ps1` or set paths manually in `config.yaml`.

### socksio package not installed

```bash
python -m pip install -r requirements.txt
```

### File is not in an ACTIVE state

The tool polls automatically for Google's video processing; if it fails, retry later.

### ConnectTimeout / network errors

Check your proxy settings in `config.yaml`.

### Re-analyze a single video

Delete the corresponding `.json`/`.txt` from `output/texts/`, or set `analyze.skip_existing: false`.

---

## Development

This is a personal vlogger tool. Issues and PRs welcome.

- Developer docs (project structure, design decisions, conventions): [AGENTS.md](AGENTS.md)
- Roadmap / feature tracking: [ROADMAP.md](ROADMAP.md)
- Full CLI reference: [docs/cli-reference.md](docs/cli-reference.md)
- Run tests: `python -m pytest vlog_tool/tests/ -v`

---

> **Bilingual maintenance note**: The Chinese README is the authoritative source for user-facing docs.
> Developer docs (AGENTS.md, ROADMAP.md, docs/cli-reference.md) are maintained in **English only**.
> This English README is a lightweight translation; for full details on developer topics refer to the English docs above.
> AI translation is recommended for ad-hoc English versions rather than manual parallel maintenance.

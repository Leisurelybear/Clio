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
| 2 | AI video analysis (summary + timeline), provider-pluggable | `analyze -i <folder>` |
| 3 | Sequential naming + text files + CSV summary | done automatically by `analyze` |
| 4 | Voiceover script generation using a template | `scripts` |
| 5 | Recommended clip order for a single-day vlog | `plan --day day1` |
| 6 | Burn the index number onto the video for editing reference | `label` |
| — | One-shot full pipeline | `run --day day1` |

---

## Quick Start

### 1. Bootstrap the environment

```powershell
cd G:\Coding_Project\IdeaProjects\vlog-video-analysis
.\setup.ps1
```

The script will:

- Create a `.venv` virtual environment and install dependencies
- Install ffmpeg via winget (if missing)
- Copy `.env.example` to `.env`
- Copy `config.example.yaml` to `config.yaml`

### 2. Fill in your API key

Edit `.env` in the project root:

```env
GEMINI_API_KEY=your_Gemini_API_Key
```

> You may also set system environment variables, or put the key directly in
> `config.yaml` under `ai.providers` (not recommended for committing).

### 3. Prepare `config.yaml`

```powershell
Copy-Item config.example.yaml config.yaml
# Then edit paths.input_dir / proxy.url etc. for your machine
```

### 4. Point at your footage folder

**Core usage: input is a folder; the tool analyzes every video in it.**

```powershell
# Specify a footage folder (defaults to output/云南/ if folder name is 云南)
python main.py analyze -i "E:/Videos/Yunnan"

# Custom output directory
python main.py run -i "E:/Videos/Yunnan" -o "./output/yunnan_v1" --day day1
```

You can also set a default `paths.input_dir` in `config.yaml` and skip `-i`.

### 5. Configure AI providers and models

Each step can be wired to a different provider/model (`config.yaml` → `ai`):

```yaml
ai:
  providers:
    gemini:
      type: gemini
      api_key_env: GEMINI_API_KEY
    openai:
      type: openai
      api_key_env: OPENAI_API_KEY
      base_url: https://api.openai.com/v1
    deepseek:
      type: openai              # OpenAI-compatible
      api_key_env: DEEPSEEK_API_KEY
      base_url: https://api.deepseek.com/v1

  tasks:
    video_analyze:              # requires a video-capable provider, e.g. gemini
      provider: gemini
      model: gemini-2.5-flash
    voiceover:                  # text only
      provider: deepseek
      model: deepseek-chat
    vlog_plan:                  # text only
      provider: openai
      model: gpt-4o-mini
```

| Task | Description | Supported providers |
|------|-------------|---------------------|
| `video_analyze` | Watch the video, output a timeline | `gemini` |
| `voiceover` | Generate a voiceover script | `gemini` / `openai` / any OpenAI-compatible |
| `vlog_plan` | Recommend the edit order | same as above |
| `refine_text` | Review and correct existing analyses/voiceovers (`refine` cmd) | same as above (text-only) |

> `refine_text` falls back to `video_analyze`'s provider. It is shared by
> the texts and scripts review (both are text-only). Override under
> `ai.tasks.refine_text` to use a cheaper model.

### 6. Other settings

Edit `config.yaml`:

```yaml
paths:
  input_dir: "E:/Videos/Yunnan"
  output_dir: "./output"
  recursive: false              # true to scan subfolders

proxy:
  enabled: true
  url: "socks5://192.168.6.1:1080"
```

### 6.5 Give the AI a "trip context / spec" preamble

AI models sometimes misidentify locations (e.g. mistaking Paris's CDG RER
for Bangkok's Suvarnabhumi). Add `ai.context` or `ai.context_file` to
`config.yaml`; its content is prepended to every AI prompt:

```yaml
ai:
  context: "All footage was shot in Paris, France in July 2024. Do not confuse it with other cities."
  # or, for longer text, use a file:
  # context_file: ./templates/trip_context.md
```

A sample is provided at `templates/trip_context.md`. At minimum, document:

- Trip dates and locations
- Naming conventions (Chinese titles vs. foreign-language originals)
- Known confusion cases (airports, metros, etc.)
- Output language and style

### 7. Verify the environment

```powershell
.\.venv\Scripts\Activate.ps1
python main.py check
```

Wait until every line shows `[OK]`.

### 8. Run

```powershell
# Analyze a folder (most common)
python main.py analyze -i "E:/Videos/Yunnan"

# One-shot full pipeline
python main.py run -i "E:/Videos/Yunnan" --day day1

# Or run steps individually
python main.py analyze          # compress + AI analysis
python main.py scripts          # voiceover scripts
python main.py plan --day day1  # daily vlog plan
python main.py label            # burn index labels
```

> Re-running **automatically skips already-generated outputs** (controlled by
> `skip_existing` in `config.yaml`), so you can resume from where it stopped.
> To force a full re-run, pass `--force`:
> ```powershell
> python main.py analyze --force
> ```

### 9. Inspect run logs

Every CLI run writes its `print()` output and errors to **both** the console
and the `logs/` directory. Files are rotated by hour, named
`logs/YYYY-MM-DD-HH.log` (e.g. `logs/2026-06-06-14.log`). Long runs that
cross an hour boundary get a new file automatically — no restart needed.

```powershell
# tail the most recent run's log
Get-Content (Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) -Tail 50
```

Override the directory via `paths.logs_dir` in `config.yaml`. The `logs/`
folder is gitignored.

---

## Output Layout

```
output/
├── compressed/          # compressed videos (audio stripped, for AI)
├── texts/
│   ├── 001_Lijiang.txt    # human-readable: summary + timeline
│   └── 001_Lijiang.json   # machine-readable, used by later steps
├── scripts/
│   ├── 001_Lijiang_voiceover.md   # voiceover script (drop into 剪映)
│   └── 001_Lijiang_voiceover.json
├── labeled/             # preview videos with index burned in
├── plans/
│   ├── day1_plan.md     # recommended order and timeline
│   └── day1_plan.json
└── summary.csv          # one-row-per-clip overview
```

---

## Typical Workflow

```
raw footage (input_dir)
    │
    ▼ compress + analyze
compressed videos + texts/CSV
    │
    ├──► scripts ──► voiceover script (one per clip)
    │
    ├──► plan ────► daily vlog edit plan (which clips, in what order)
    │
    └──► label ───► preview videos with index labels
    │
    ▼
User in 剪映: follow the plan → add effects → paste the voiceover
```

---

## Configuration Reference

### Compression (`compress`)

| Key | Default | Description |
|-----|---------|-------------|
| `target_size_mb` | 5 | target size in MB; bitrate is computed from duration |
| `max_width` | 640 | max width |
| `fps` | 15 | output frame rate |
| `remove_audio` | true | strip audio |

### AI parameters (`gemini`)

| Key | Default | Description |
|-----|---------|-------------|
| `model` | gemini-2.5-flash | analysis / script model |
| `poll_interval_sec` | 5 | polling interval while Gemini processes uploads |

### Voiceover template

Edit `templates/vlog_template.md` to tweak voiceover style (first-person,
target word count, structure, etc.).

---

## Command Reference

Full reference for every subcommand. Short forms shown for the common cases.

### Global flags

| Flag | Applies to | Description |
|------|------------|-------------|
| `-c, --config <file>` | all | config file (default `config.yaml`) |
| `-i, --input <path>` | most | footage folder / single json / json dir (overrides config.yaml) |
| `-o, --output <path>` | most | output dir (default `output/<footage-folder-name>`) |
| `--force` | all | ignore existing outputs and rerun (overrides `analyze.skip_existing`) |

### `check` — environment check

Verifies the virtualenv, ffmpeg / ffprobe, the footage folder, and the API
key for every AI task. Makes no network calls.

```powershell
python main.py check
python main.py check -i "E:/Videos/Yunnan"     # also verify the footage folder
```

Prints `[OK] xxx` / `[FAIL] xxx` plus the number of video files found.

### `compress` — compress only

Runs ffmpeg to produce 640p / ~5 MB / audio-stripped mp4s.
**Does not** call any AI. Useful when you want to batch-compress and
cherry-pick manually.

```powershell
python main.py compress -i "E:/Videos/Yunnan"
```

Writes to `output/<folder>/compressed/`, named `<index>_<original-stem>.mp4`
(e.g. `001_GL010683.mp4`). Existing files are skipped when
`analyze.skip_existing: true`.

### `analyze` — compress + AI analysis (most common)

Compresses (if needed) and then sends each compressed clip to the
`ai.tasks.video_analyze` provider (default: Gemini) for content analysis.

```powershell
python main.py analyze -i "E:/Videos/Yunnan"
python main.py analyze --force     # rerun everything, ignoring skip_existing
```

Output triple:
- `output/<folder>/texts/<index>_<title>.json` — structured (machine-readable)
- `output/<folder>/texts/<index>_<title>.txt`  — human-readable, with timeline
- `output/<folder>/summary.csv` — one row per clip

> Re-runs **skip** existing `.json` / `.txt` (when
> `analyze.skip_existing: true`). Add `--force` to redo everything.

### `scripts` — voiceover generation

For every `texts/` file, calls the `ai.tasks.voiceover` provider (default:
DeepSeek) with `templates/vlog_template.md` to draft a voiceover.

```powershell
python main.py scripts
```

Writes `output/<folder>/scripts/<index>_<title>_voiceover.{json,md}`.
The `.md` is ready to paste into 剪映.

### `plan` — daily vlog editing plan

Sends every `texts/` summary to the `ai.tasks.vlog_plan` provider, which
picks a narratively coherent subset and orders them.

```powershell
python main.py plan --day day1
python main.py plan --day "Day2_Loire_Valley"
```

`--day` shows up in the filename and the vlog title. Output:
`output/<folder>/plans/<day>_plan.{json,md}`.

### `label` — burn index numbers onto clips

Burns the index (`001`, `002`, ...) onto the top-left of each compressed
clip, so you can match the plan to footage inside 剪映.

```powershell
python main.py label
```

Writes to `output/<folder>/labeled/<index>_<title>_labeled.mp4`.

### `run` — one-shot full pipeline

Runs `analyze` → `scripts` → `plan` → `label` in sequence. Any step can
also be run on its own.

```powershell
python main.py run -i "E:/Videos/Yunnan" --day day1
```

### `refine` — review and correct existing outputs

`refine` runs in two modes:

#### 1. Review mode (default)

The AI reads `ai.context` / `ai.context_file` and fixes obvious errors
on its own (misidentified locations, naming inconsistencies, etc.).

```powershell
# default: review every texts/ and scripts/ file
python main.py refine

# texts only
python main.py refine --target texts

# a single file
python main.py refine -i output/Franch/texts/001_CDG_RER.json

# every json in a folder
python main.py refine -i output/Franch/texts/
```

#### 2. Targeted-fix mode (`--fix`)

You supply an explicit instruction; the AI changes **only** the fields
you mention and leaves everything else untouched. Must be paired with
`-i` to point at a single file (no directory mode — too easy to misuse).

```powershell
# fix a misidentified location
python main.py refine -i output/Franch/texts/001_CDG_RER.json `
    --fix "Change location from 'Bangkok Suvarnabhumi' to 'Paris CDG'"

# correct a specific line in a voiceover
python main.py refine -i output/Franch/scripts/001_CDG_RER_voiceover.json `
    --fix "In voiceover, replace 'Bangkok morning' with 'Paris morning'"
```

The `_changelog` field's first entry reads "applied user instruction
on XXX" for audit purposes. Both modes call the `video_analyze`
provider (default gemini) for `texts/` and the `voiceover` provider
(default deepseek) for `scripts/`; results overwrite the original file.

---

## FAQ

### `ffmpeg not found`

1. Run `.\setup.ps1` to install it
2. Or install manually and set the path in `config.yaml`:
   ```yaml
   paths:
     ffmpeg: "C:/path/to/ffmpeg.exe"
     ffprobe: "C:/path/to/ffprobe.exe"
   ```

### `socksio package is not installed`

Make sure dependencies are installed in the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### `File is not in an ACTIVE state`

The video has been uploaded but Google hasn't finished processing it. The tool
polls automatically; if it still fails, retry later.

### `ConnectTimeout` / network errors

Confirm your proxy works and `proxy.url` in `config.yaml` is correct.

### pip install fails (system Python permissions)

**Always use the project virtual environment**; never use a global `pip`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Re-analyze a single video

Delete the corresponding `.txt` and `.json` from `output/texts/`, or set
`analyze.skip_existing` to `false`.

---

## Project Structure

```
vlog-video-analysis/
├── config.example.yaml  # config template (committed)
├── config.yaml          # actual config (gitignored, copy from example)
├── .env                 # API keys (gitignored)
├── setup.ps1            # one-shot environment setup
├── main.py              # CLI entry point
├── templates/
│   └── vlog_template.md # voiceover style template
└── vlog_tool/
    ├── ai/              # provider abstraction (gemini / openai-compatible)
    ├── compress.py
    ├── analyze.py
    ├── pipeline.py
    └── prompts.py
```

---

## Requirements

- Python 3.11+
- ffmpeg / ffprobe
- Gemini API key
- SOCKS5 proxy (required in mainland China)

---

## Roadmap

- [ ] Auto-group multi-day vlogs by folder/date
- [ ] Export to 剪映 draft format
- [ ] Web UI for timeline preview
- [ ] Local Whisper transcription for clips with live commentary

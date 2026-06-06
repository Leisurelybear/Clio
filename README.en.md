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
| `refine_text` | Review and correct existing analyses (`refine` command) | same as above (text-only) |
| `refine_script` | Review and correct existing voiceovers (`refine` command) | same as above (text-only) |

> `refine_text` falls back to `video_analyze`'s provider, `refine_script` to
> `voiceover`. Override under `ai.tasks` to use a cheaper text model
> (typical: switch both to deepseek).

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

```powershell
python main.py check
python main.py analyze -i "E:/Videos/Yunnan"     # analyze a folder
python main.py run -i "E:/Videos/Yunnan" --day day1
python main.py -c other.yaml analyze              # use a different config
```

### 9. Fix existing outputs (refine)

If some AI analysis or voiceover is wrong (e.g. mistaking Paris CDG for
Bangkok Suvarnabhumi), first write your trip context into `ai.context` /
`ai.context_file`, then run:

```powershell
# default: review all of texts/ and scripts/
python main.py refine

# only texts
python main.py refine --target texts

# refine a single file
python main.py refine -i output/Franch/texts/001_CDG_RER.json

# refine every json in a folder
python main.py refine -i output/Franch/texts/
```

The `video_analyze` provider (usually gemini) reviews texts, and the
`voiceover` provider (usually deepseek) reviews scripts. Results overwrite
the original files; the AI appends a `_changelog` field explaining changes.

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

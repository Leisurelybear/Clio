# 🎬 Vlog Editing Helper — AI Preprocessing Pipeline

> 🧠 **Raw footage → Compress → AI understands → Voiceover scripts → Edit plan → CapCut final cut**
>
> Feed your GoPro/phone 4K footage to AI, get summaries, timelines, voiceover scripts, and edit plans — then finish with effects and lip-sync in **CapCut (JianYing)**.

[![CI](https://github.com/Leisurelybear/vlog-editing-helper/actions/workflows/test.yml/badge.svg)](https://github.com/Leisurelybear/vlog-editing-helper/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/Leisurelybear/vlog-editing-helper/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/Leisurelybear/vlog-editing-helper)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![tests](https://img.shields.io/badge/tests-600%2B-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** · [简体中文](README.md)

---

## ✨ Features

| | Feature | AI | Description |
|---|---------|----|-------------|
| 🗜️ | **Smart Compression** | | 4K→640p·strip audio·auto-split·~5MB |
| 🤖 | **AI Video Understanding** | ✅ Gemini | Watches footage→title/location/timeline |
| ✍️ | **AI Voiceover** | ✅ DeepSeek | Writes narration from template |
| 📋 | **AI Edit Planning** | ✅ DeepSeek | Arranges segment order/duration |
| 🧠 | **AI ASR Transcription** | ✅ Whisper | faster-whisper offline + CUDA |
| 🔧 | **AI Refine** | ✅ DeepSeek | Trip context review·`--fix` targeted fix |
| 🏷️ | **Label Burn-in** | | Index watermark for CapCut reference |
| ✂️ | **Precision Cutting** | | Plan-based cutting·fast/re-encode |
| 🌐 | **Web UI Editor** | | Zero deps·browser editing+pipeline |
| 🚀 | **One-shot Pipeline** | ✅ | `run --day day1` skips existing |

---

## 🖥️ Screenshots

**Pure Python stdlib** (`http.server`). No Node.js / npm / build step.

<div align="center">
  <img src="docs/screenshots/pipeline.png" alt="Pipeline runner" width="80%">
  <br><sub>🏃 Pipeline runner — step-by-step or full run·live progress·ETA</sub>
  <br><br>
  <img src="docs/screenshots/analysis.png" alt="AI analysis editor" width="80%">
  <br><sub>🤖 AI analysis editor — summary·timeline·manual tweaks</sub>
  <br><br>
  <img src="docs/screenshots/voiceover.png" alt="Voiceover editor" width="80%">
  <br><sub>✍️ Voiceover script editor — AI-generated·edit·save</sub>
  <br><br>
  <img src="docs/screenshots/plan.png" alt="Edit plan editor" width="80%">
  <br><sub>📋 Edit plan — theme·segment order·preview playback</sub>
  <br><br>
  <img src="docs/screenshots/new_project.png" alt="Project management" width="80%">
  <br><sub>📁 Project management — create/switch/delete·visual config</sub>
</div>

Launch: `python main.py serve` → open `http://127.0.0.1:8765`

---

## 🧩 Pipeline

```mermaid
graph LR
    A[📹 4K Raw] --> B{🗜️ Split & Compress}
    B --> C[🤖 Gemini Analysis]
    C --> D[✍️ DeepSeek Voiceover]
    C --> E[🧠 Whisper ASR]
    D --> F[🤖 DeepSeek Plan]
    E --> F
    F --> G[✂️ Cut Clips]
    F --> H[🏷️ Burn Labels]
    G & H --> I[🎬 CapCut Final Cut]

    style C fill:#e1f5fe,stroke:#01579b
    style D fill:#f3e5f5,stroke:#7b1fa2
    style E fill:#fff3e0,stroke:#e65100
    style F fill:#e8f5e9,stroke:#1b5e20
```

> 💡 Each step runs independently (`analyze`/`scripts`/`plan`/`transcribe`/`refine`/`cut`/`label`),
> supports single-file processing, `--force` to regenerate, auto-skips existing.

---

## 🚀 Quick Start

```bash
# 1️⃣ One-click setup (venv + ffmpeg + deps)
.\setup.ps1                    # Windows
./setup.sh                     # Linux / macOS

# 2️⃣ Edit .env with your API keys
GEMINI_API_KEY=your_Gemini_API_Key
DEEPSEEK_API_KEY=your_DeepSeek_API_Key

# 3️⃣ Run it
python main.py run -i "E:/Videos/🇫🇷ParisTrip" --day day1   # Full pipeline
python main.py serve                                         # Web UI
python main.py check                                         # Environment check
```

Each AI task can use a different provider/model (`config.yaml` → `ai.tasks`): Gemini / DeepSeek / OpenAI / Tongyi Qianwen / Kimi. Trip context auto-injected from `templates/trip_context.md`.

---

## 📚 Docs

| Doc | Description |
|-----|-------------|
| [docs/cli-reference.md](docs/cli-reference.md) | 📖 Full CLI reference |
| [vlog_tool/ui/README.md](vlog_tool/ui/README.md) | 🖥️ Web UI guide |
| [AGENTS.md](AGENTS.md) | 🧑‍💻 Project structure / conventions / gotchas |
| [ROADMAP.md](ROADMAP.md) | 🗺️ Feature tracking & roadmap |
| [FAQ →](https://github.com/Leisurelybear/vlog-editing-helper/issues) | ❓ ffmpeg / network / re-analyze etc. |

---

## 🤝 Contributing

Personal vlogger tool — [Issues](https://github.com/Leisurelybear/vlog-editing-helper/issues) and PRs welcome.

```bash
.venv\Scripts\activate         # Windows
source .venv/bin/activate      # Linux/Mac
ruff format . && ruff check . && python -m pytest -v
```

---

## 🚀 Future Vision

🧠 Local AI inference · 🖼️ AI thumbnails · 🌍 Multi-language voiceover · 🎵 AI music · 🤝 Collaboration · 📊 Edit scoring · 🏪 Plugins

[→ Share your ideas](https://github.com/Leisurelybear/vlog-editing-helper/issues)

---

<p align="center">
  <b>🗜️ → 🤖 → ✍️ → 🧠 → 📋 → 🔧 → ✂️ → 🎬</b>
  <br>
  <sub>AI-powered vlog creation · From raw footage to final cut, faster</sub>
</p>

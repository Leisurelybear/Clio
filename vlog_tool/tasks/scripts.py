"""Script generation task — generate voiceover scripts from analysis."""

from __future__ import annotations

import json
import time
from pathlib import Path

from vlog_tool.analyze import generate_voiceover
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import _eta_line


def run_generate_scripts(
    config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None
) -> None:
    config.scripts_dir.mkdir(parents=True, exist_ok=True)
    template = config.script.template_file.read_text(encoding="utf-8") if config.script.template_file.exists() else ""

    if single_file:
        files = [single_file]
    else:
        files = sorted(config.texts_dir.glob("*.json"))
    if tracker:
        tracker.update(phase="voiceover", total=len(files), message=f"生成口播文案（{len(files)} 条）...")
    with timed(f"run_generate_scripts（{len(files)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, json_file in enumerate(files, start=1):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data["index"] = data.get("index", json_file.stem[:3])
            out = config.scripts_dir / f"{json_file.stem}_voiceover.json"
            if config.analyze.skip_existing and out.exists():
                print(f"[跳过] {out.name}")
                if tracker:
                    tracker.next(message=f"跳过 {json_file.stem}")
                continue

            print(_eta_line("口播", i, len(files), json_file.stem, completed, elapsed_total))
            if tracker:
                tracker.next(message=f"生成口播 {json_file.stem}")
            t0 = time.monotonic()
            script = generate_voiceover(data, template, config)
            elapsed_total += time.monotonic() - t0
            completed += 1
            out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

            md_out = config.scripts_dir / f"{json_file.stem}_voiceover.md"
            md_out.write_text(
                f"# {script.get('title', json_file.stem)} 口播\n\n"
                f"{script.get('voiceover', '')}\n\n"
                f"**剪辑建议**: {script.get('edit_tip', '')}\n",
                encoding="utf-8",
            )
            print(f"  -> {md_out.name}")

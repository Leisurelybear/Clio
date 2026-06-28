"""Script generation task — generate voiceover scripts from analysis."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from vlog_tool.ai.token_usage import FileTokenUsageStore
from vlog_tool.analyze import generate_voiceover
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.schema import add_schema_version
from vlog_tool.tasks._helpers import _eta_line
from vlog_tool.utils import write_json_atomic, write_text_atomic


def run_generate_scripts(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> None:
    config.scripts_dir.mkdir(parents=True, exist_ok=True)
    token_store = FileTokenUsageStore(str(config.paths.output_dir))
    state = ProcessingState(config.paths.output_dir)
    template = config.script.template_file.read_text(encoding="utf-8") if config.script.template_file.exists() else ""

    if single_file:
        input_files = [single_file]
    else:
        input_files = sorted(config.texts_dir.glob("*.json"))
    if files is not None:
        allowed = {Path(f).stem.lower() for f in files}
        input_files = [f for f in input_files if f.stem.lower() in allowed]
    if tracker:
        tracker.update(phase="voiceover", total=len(input_files), message=f"生成口播文案（{len(input_files)} 条）...")
    with timed(f"run_generate_scripts（{len(input_files)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, json_file in enumerate(input_files, start=1):
            if cancel_event and cancel_event.is_set():
                print("[取消] voiceover 步骤被用户终止")
                break
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data["index"] = data.get("index", json_file.stem[:3])
            orig_stem = Path(data.get("source_file") or json_file.stem).stem
            out = config.scripts_dir / f"{json_file.stem}_voiceover.json"
            if not overwrite and config.analyze.skip_existing and out.exists():
                print(f"[跳过] {out.name}")
                state.mark(orig_stem, "voiceover", "skipped")
                if tracker:
                    tracker.next(message=f"跳过 {json_file.stem}")
                    tracker.log(f"跳过 {json_file.stem}（已存在）")
                continue

            print(_eta_line("口播", i, len(input_files), json_file.stem, completed, elapsed_total))
            if tracker:
                tracker.next(message=f"生成口播 {json_file.stem}")
            t0 = time.monotonic()
            script = generate_voiceover(data, template, config, token_store=token_store, cancel_event=cancel_event)
            elapsed_total += time.monotonic() - t0
            completed += 1
            add_schema_version(script)
            write_json_atomic(out, script)
            state.mark(orig_stem, "voiceover", "done")
            if tracker:
                tracker.log(f"口播 {orig_stem} ✓")

            md_out = config.scripts_dir / f"{json_file.stem}_voiceover.md"
            md_content = (
                f"# {script.get('title', json_file.stem)} 口播\n\n"
                f"{script.get('voiceover', '')}\n\n"
                f"**剪辑建议**: {script.get('edit_tip', '')}\n"
            )
            write_text_atomic(md_out, md_content)
            print(f"  -> {md_out.name}")

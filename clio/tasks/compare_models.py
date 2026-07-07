from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clio.ai.base import TaskName
from clio.analyze import analyze_video
from clio.config import AppConfig
from clio.config.models import ProjectConfig, TaskConfig
from clio.utils import sanitize_name, write_json_atomic, write_text_atomic


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_model_specs(raw_specs: list[str], config: AppConfig) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    for raw in raw_specs:
        for part in raw.split(","):
            text = part.strip()
            if not text:
                continue
            if ":" in text:
                provider, model = text.split(":", 1)
            elif "/" in text:
                provider, model = text.split("/", 1)
            else:
                provider_cfg = config.ai.providers.get(text)
                if provider_cfg is None:
                    raise ValueError(f"未知 provider: {text}")
                if not provider_cfg.models:
                    raise ValueError(f"provider '{text}' 未配置 models，请使用 provider:model 显式指定模型")
                provider, model = text, provider_cfg.models[0]
            provider = provider.strip()
            model = model.strip()
            if not provider or not model:
                raise ValueError(f"模型格式无效: {text}，应为 provider:model")
            if provider not in config.ai.providers:
                raise ValueError(f"未知 provider: {provider}")
            specs.append(ModelSpec(provider=provider, model=model))
    if len(specs) < 2:
        raise ValueError("至少需要指定两个模型用于对比")
    return specs


def _config_for_model(config: AppConfig, spec: ModelSpec) -> AppConfig:
    cfg = copy.deepcopy(config)
    if cfg.project_cfg is None:
        cfg.project_cfg = ProjectConfig()
    cfg.project_cfg.ai.tasks[TaskName.VIDEO_ANALYZE.value] = TaskConfig(provider=spec.provider, model=spec.model)
    return cfg


def _summarize_result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": data.get("title", ""),
        "location": data.get("location", ""),
        "summary": data.get("summary", ""),
        "mood": data.get("mood", ""),
        "suggested_use": data.get("suggested_use", ""),
        "confidence": data.get("_confidence", 0.0),
        "timeline_count": len(data.get("timeline", []) or []),
        "highlights_count": len(data.get("highlights", []) or []),
    }


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_report(video_path: Path, results: list[dict[str, Any]]) -> str:
    lines = [
        f"# Model Compare: {video_path.name}",
        "",
        "| Model | Status | Title | Location | Confidence | Timeline | Highlights |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for item in results:
        if item["ok"]:
            s = item["summary"]
            lines.append(
                "| "
                + " | ".join(
                    [
                        item["model"],
                        "ok",
                        _md_cell(s["title"]),
                        _md_cell(s["location"]),
                        _md_cell(s["confidence"]),
                        _md_cell(s["timeline_count"]),
                        _md_cell(s["highlights_count"]),
                    ]
                )
                + " |"
            )
        else:
            lines.append(f"| {item['model']} | error | {_md_cell(item['error'])} |  |  |  |  |")

    lines.extend(["", "## Summaries", ""])
    for item in results:
        lines.append(f"### {item['model']}")
        if item["ok"]:
            summary = item["summary"]
            lines.append(f"- Title: {summary['title']}")
            lines.append(f"- Location: {summary['location']}")
            lines.append(f"- Mood: {summary['mood']}")
            lines.append(f"- Suggested use: {summary['suggested_use']}")
            lines.append(f"- Summary: {summary['summary']}")
        else:
            lines.append(f"- Error: {item['error']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_compare_models(
    config: AppConfig,
    video_path: Path,
    raw_specs: list[str],
    *,
    output_dir: Path | None = None,
    context_override: str | None = None,
) -> int:
    if not video_path.is_file():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    specs = parse_model_specs(raw_specs, config)
    out_dir = output_dir or config.paths.output_dir / "model_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for spec in specs:
        print(f"\n=== Compare {spec.label} ===")
        try:
            data = analyze_video(
                str(video_path),
                _config_for_model(config, spec),
                context_override=context_override,
            )
            results.append(
                {
                    "model": spec.label,
                    "ok": True,
                    "summary": _summarize_result(data),
                    "result": data,
                }
            )
        except Exception as e:
            results.append({"model": spec.label, "ok": False, "error": str(e)})
            print(f"  [错误] {spec.label}: {e}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    stem = sanitize_name(video_path.stem, max_len=80)
    payload = {
        "video": str(video_path),
        "models": [spec.label for spec in specs],
        "results": results,
    }
    json_path = out_dir / f"{stem}_{timestamp}.json"
    md_path = out_dir / f"{stem}_{timestamp}.md"
    write_json_atomic(json_path, payload)
    write_text_atomic(md_path, _render_report(video_path, results))
    print(f"\n对比 JSON: {json_path}")
    print(f"对比报告: {md_path}")
    return 0 if any(item["ok"] for item in results) else 1

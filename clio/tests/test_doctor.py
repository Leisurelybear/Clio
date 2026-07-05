from __future__ import annotations

from pathlib import Path

from clio.config.models import (
    AppConfig,
    GlobalAIConfig,
    GlobalConfig,
    GlobalPathsConfig,
    ProjectAIConfig,
    ProjectConfig,
    ProjectPathsConfig,
    ProviderConfig,
    TaskConfig,
)
from clio.doctor import (
    DoctorItem,
    collect_doctor_checks,
    doctor_exit_code,
    parse_node_major,
)


def _config(tmp_path: Path, *, provider: ProviderConfig | None = None) -> AppConfig:
    provider = provider or ProviderConfig(
        name="gemini",
        type="gemini",
        api_key_env="GEMINI_API_KEY",
    )
    input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    return AppConfig(
        global_cfg=GlobalConfig(
            paths=GlobalPathsConfig(ffmpeg="", ffprobe=""),
            ai=GlobalAIConfig(providers={provider.name: provider}),
        ),
        project_cfg=ProjectConfig(
            paths=ProjectPathsConfig(input_dir=input_dir, output_dir=output_dir),
            ai=ProjectAIConfig(tasks={"video_analyze": TaskConfig(provider=provider.name, model="m")}),
        ),
    )


def test_doctor_exit_code_fails_on_failures() -> None:
    assert doctor_exit_code([DoctorItem("x", "FAIL", "broken")]) == 1


def test_doctor_exit_code_ignores_warnings() -> None:
    assert doctor_exit_code([DoctorItem("x", "WARN", "heads up")]) == 0


def test_parse_node_major() -> None:
    assert parse_node_major("v22.4.1") == 22
    assert parse_node_major("16.14.0") == 16
    assert parse_node_major("not node") is None


def test_collect_checks_reports_missing_task_provider_key(tmp_path: Path) -> None:
    config = _config(tmp_path)
    items = collect_doctor_checks(
        config,
        discover_binary=lambda name: f"/usr/bin/{name}",
        environ={},
        node_version_getter=lambda: "v22.0.0",
    )

    provider_item = next(item for item in items if item.name == "AI provider: gemini")
    assert provider_item.status == "FAIL"
    assert "GEMINI_API_KEY" in provider_item.detail


def test_collect_checks_accepts_env_provider_key(tmp_path: Path) -> None:
    config = _config(tmp_path)
    items = collect_doctor_checks(
        config,
        discover_binary=lambda name: f"/usr/bin/{name}",
        environ={"GEMINI_API_KEY": "secret"},
        node_version_getter=lambda: "v22.0.0",
    )

    provider_item = next(item for item in items if item.name == "AI provider: gemini")
    assert provider_item.status == "OK"


def test_collect_checks_warns_for_old_node(tmp_path: Path) -> None:
    config = _config(tmp_path, provider=ProviderConfig(name="gemini", type="gemini", api_key="secret"))
    items = collect_doctor_checks(
        config,
        discover_binary=lambda name: f"/usr/bin/{name}",
        environ={},
        node_version_getter=lambda: "v16.14.0",
    )

    node_item = next(item for item in items if item.name == "Node.js")
    assert node_item.status == "WARN"
    assert "18+" in node_item.detail

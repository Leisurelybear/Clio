#!/usr/bin/env python3
"""Vlog 剪辑辅助工具 CLI"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vlog_tool.config import apply_run_paths, load_config
from vlog_tool.pipeline import (
    run_analyze_all,
    run_compress_all,
    run_full_pipeline,
    run_generate_scripts,
    run_label_videos,
    run_plan_vlog,
)
from vlog_tool.utils import discover_ffmpeg_bin, find_videos

PLACEHOLDER_KEYS = {"your_api_key_here", "YOUR_API_KEY", ""}


def _add_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-i", "--input",
        type=Path,
        help="素材文件夹（覆盖 config.yaml 中的 input_dir）",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="输出文件夹（默认 output/<素材文件夹名>）",
    )


def _prepare_config(config_path: Path, args: argparse.Namespace):
    config = load_config(config_path)
    if getattr(args, "input", None) or getattr(args, "output", None):
        config = apply_run_paths(config, args.input, args.output)
    return config


def run_check(config_path: Path, input_dir: Path | None = None) -> int:
    config = load_config(config_path)
    if input_dir:
        config = apply_run_paths(config, input_dir=input_dir, output_dir=None, output_by_input_name=False)

    ok = True

    def status(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "OK" if passed else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
        if not passed:
            ok = False

    print("环境检查:")
    status(
        "虚拟环境",
        Path(sys.executable).parent.name.lower() == "scripts" or ".venv" in sys.executable,
        sys.executable,
    )

    ffmpeg = config.paths.ffmpeg or discover_ffmpeg_bin("ffmpeg")
    ffprobe = config.paths.ffprobe or discover_ffmpeg_bin("ffprobe")
    status("ffmpeg", bool(ffmpeg), ffmpeg or "未找到，运行 setup.ps1")
    status("ffprobe", bool(ffprobe), ffprobe or "未找到")

    check_dir = input_dir or config.paths.input_dir
    status("素材目录", check_dir.is_dir(), str(check_dir))
    if check_dir.is_dir():
        videos = find_videos(check_dir, recursive=config.paths.recursive)
        print(f"       发现 {len(videos)} 个视频文件")

    print("\nAI 任务配置:")
    for task_name, task_cfg in config.ai.tasks.items():
        provider = config.ai.providers.get(task_cfg.provider)
        key_ok = provider and provider.api_key not in PLACEHOLDER_KEYS
        detail = f"{task_cfg.provider}/{task_cfg.model}"
        if provider and not key_ok:
            detail += f" (需设置 {provider.api_key_env})"
        status(f"  {task_name}", bool(provider) and key_ok, detail)

    status(
        "代理",
        not config.proxy.enabled or bool(config.proxy.url),
        config.proxy.url if config.proxy.enabled else "未启用",
    )

    print(f"\n默认输入: {config.paths.input_dir}")
    print(f"默认输出: {config.paths.output_dir}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vlog 剪辑辅助工具：文件夹输入 → 压缩 → AI 分析 → 口播 → 规划",
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径（默认 config.yaml）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已存在的输出，强制重新生成（覆盖 config.yaml 的 skip_existing）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_compress = sub.add_parser("compress", help="仅压缩素材文件夹中的视频")
    _add_io_args(p_compress)

    p_analyze = sub.add_parser("analyze", help="压缩 + AI 分析，输出文本和 CSV")
    _add_io_args(p_analyze)

    p_scripts = sub.add_parser("scripts", help="根据分析结果生成口播文案")
    _add_io_args(p_scripts)

    p_label = sub.add_parser("label", help="在压缩视频上烧录序号标注")
    _add_io_args(p_label)

    p_check = sub.add_parser("check", help="检查环境配置是否就绪")
    p_check.add_argument("-i", "--input", type=Path, help="检查指定素材文件夹")

    p_plan = sub.add_parser("plan", help="生成单日 vlog 剪辑规划")
    _add_io_args(p_plan)
    p_plan.add_argument("--day", default="day1", help="日 vlog 标签")

    p_run = sub.add_parser("run", help="一键执行完整流程")
    _add_io_args(p_run)
    p_run.add_argument("--day", default="day1", help="日 vlog 标签")

    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    if args.command == "check":
        return run_check(config_path, getattr(args, "input", None))

    config = _prepare_config(config_path, args)
    if args.force:
        config.analyze.skip_existing = False

    try:
        if args.command == "compress":
            run_compress_all(config)
        elif args.command == "analyze":
            run_analyze_all(config)
        elif args.command == "scripts":
            run_generate_scripts(config)
        elif args.command == "label":
            run_label_videos(config)
        elif args.command == "plan":
            run_plan_vlog(config, args.day)
        elif args.command == "run":
            run_full_pipeline(config, args.day)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

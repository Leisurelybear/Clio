#!/usr/bin/env python3
"""Vlog 剪辑辅助工具 CLI"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from vlog_tool.config import apply_run_paths, load_config
from vlog_tool.log import setup_logging
from vlog_tool.shutdown import before_stop, install_hooks
from vlog_tool.ui import run as run_ui
from vlog_tool.ui.services.file_service import _migrate_project_configs
from vlog_tool.utils import discover_ffmpeg_bin, find_videos

PLACEHOLDER_KEYS = {"your_api_key_here", "YOUR_API_KEY", ""}


def _add_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help="素材文件夹（覆盖 config.yaml 中的 input_dir）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出文件夹（默认 output/<素材文件夹名>）",
    )


def _prepare_config(config_path: Path, args: argparse.Namespace):
    raw_input = getattr(args, "input", None)
    project_dir = raw_input if (raw_input and raw_input.is_dir()) else Path.cwd()
    config = load_config(config_path, project_dir=project_dir)
    input_override = getattr(args, "input", None)
    output_override = getattr(args, "output", None)
    if input_override or output_override:
        config = apply_run_paths(config, input_override, output_override)
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
    venv_ok = sys.prefix != sys.base_prefix or ".venv" in sys.executable
    status(
        "虚拟环境",
        venv_ok,
        sys.executable + (" (建议使用 .venv 虚拟环境)" if not venv_ok else ""),
    )

    setup_script = "setup.ps1" if os.name == "nt" else "setup.sh"
    ffmpeg = config.paths.ffmpeg or discover_ffmpeg_bin("ffmpeg")
    ffprobe = config.paths.ffprobe or discover_ffmpeg_bin("ffprobe")
    status("ffmpeg", bool(ffmpeg), ffmpeg or f"未找到，运行 {setup_script}")
    status("ffprobe", bool(ffprobe), ffprobe or "未找到")

    check_dir = input_dir or config.paths.input_dir
    if check_dir.is_dir():
        videos = find_videos(check_dir, recursive=config.paths.recursive)
        print(f"  [OK] 素材目录 ({len(videos)} 个视频) - {check_dir}")
    else:
        print("  [WARN] 素材目录未设置，使用 -i/--input 指定目录")
        print(f"         config.yaml 默认: {check_dir}")

    print("\nAI 任务配置:")
    for task_name, task_cfg in config.ai.tasks.items():
        provider = config.ai.providers.get(task_cfg.provider)
        key_ok = provider and provider.api_key not in PLACEHOLDER_KEYS
        detail = f"{task_cfg.provider}/{task_cfg.model}"
        if provider and not key_ok:
            env_name = provider.api_key_env or "<未设置 api_key_env>"
            detail += f" (需设置 {env_name}，或在 api_key 字段填入 key)"
        status(f"  {task_name}", bool(provider) and key_ok, detail)

    status(
        "代理",
        not config.proxy.enabled or bool(config.proxy.url),
        config.proxy.url if config.proxy.enabled else "未启用",
    )

    if not check_dir.is_dir():
        print()
        print("用法: python main.py <命令> -i <素材目录>")
        example_path = "G:\\素材\\巴黎行" if os.name == "nt" else "/path/to/videos"
        print(f"      例如: python main.py run -i {example_path}")
    print(f"\ndone (exit code: {0 if ok else 1})")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vlog 剪辑辅助工具：文件夹输入 → 压缩 → AI 分析 → 口播 → 规划",
    )
    parser.add_argument(
        "-c",
        "--config",
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
    p_plan.add_argument("--no-transcripts", action="store_true", help="不注入语音转录信息到 prompt")

    p_run = sub.add_parser("run", help="一键执行完整流程")
    _add_io_args(p_run)
    p_run.add_argument("--day", default="day1", help="日 vlog 标签")

    p_cut = sub.add_parser("cut", help="根据规划从视频中裁剪片段")
    p_cut.add_argument("--day", default="day1", help="日 vlog 标签（默认 day1）")
    p_cut.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="输出目录（默认 output/cuts/<day>/）",
    )
    p_cut.add_argument(
        "--reencode",
        action="store_true",
        help="重新编码（默认 -c copy 快剪；启用则用 libx264 精确剪）",
    )
    p_cut.add_argument(
        "--source",
        choices=["compressed", "original"],
        default="compressed",
        help="视频来源（compressed: 从压缩版裁剪 / original: 从原片裁剪）",
    )

    p_refine = sub.add_parser("refine", help="用 AI + trip 上下文 审阅并修正已有分析/口播")
    p_refine.add_argument(
        "--target",
        "-t",
        choices=["texts", "scripts", "all"],
        default="all",
        help="要 refine 的目标（默认 all）",
    )
    p_refine.add_argument(
        "-i",
        "--input",
        type=Path,
        help="指定单个 .json 文件或目录；省略则处理整个 texts/ 或 scripts/",
    )
    p_refine.add_argument(
        "--fix",
        "-f",
        type=str,
        default="",
        help=(
            "指定具体修改意见（必须配合 -i 单文件使用）。例: --fix '把 location 从曼谷素万那普机场改成巴黎戴高乐机场'"
        ),
    )
    p_refine.add_argument(
        "--context",
        "-C",
        type=str,
        default="",
        help="临时上下文说明，附加到 ai.context 之后（仅本次 refine 生效）",
    )

    p_migrate = sub.add_parser("migrate-config", help="扫描已有项目的 project.yaml，补充缺失的 provider 配置字段")
    p_migrate.add_argument("--projects-root", type=Path, default=None, help="项目根目录（扫描子目录中的 project.yaml）")

    p_serve = sub.add_parser("serve", help="启动本地 web UI（浏览器里可视化编辑 AI 输出）")
    p_serve.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1，不暴露到局域网）")
    p_serve.add_argument("--port", type=int, default=8765, help="端口（默认 8765）")
    p_serve.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")

    p_transcribe = sub.add_parser("transcribe", help="Whisper ASR 语音转录（需先安装 faster-whisper）")
    _add_io_args(p_transcribe)
    p_transcribe.add_argument("--force", action="store_true", help="忽略已有转录，重新生成")

    p_whisper = sub.add_parser("whisper", help="Whisper 环境管理（安装/检测）")
    whisper_sub = p_whisper.add_subparsers(dest="whisper_command", required=True)
    whisper_sub.add_parser("install", help="安装 faster-whisper 依赖并预下载模型")
    whisper_sub.add_parser("check", help="检测 faster-whisper / CUDA 状态")

    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    base_config = load_config(config_path)
    setup_logging(base_config.paths.logs_dir)
    install_hooks()

    if args.command == "check":
        return run_check(config_path, getattr(args, "input", None))

    elif args.command == "transcribe":
        from vlog_tool.tasks.transcribe import run_transcribe_all

        config = load_config(config_path)
        if getattr(args, "input", None):
            config = apply_run_paths(config, input_dir=args.input)
        config.analyze.skip_existing = not getattr(args, "force", False)
        run_transcribe_all(config)
        return 0

    elif args.command == "whisper":
        from vlog_tool.whisper_cli import run_whisper_check, run_whisper_install

        if args.whisper_command == "install":
            return run_whisper_install(config_path)
        elif args.whisper_command == "check":
            return run_whisper_check(config_path)

    # ── Single-file detection ────────────────────────────────────────
    # If -i points to a single file for compress/analyze/scripts,
    # don't let _prepare_config set it as input_dir (refine already handles -i correctly)
    single_file: Path | None = None
    if args.command in ("compress", "analyze", "scripts"):
        raw_input = getattr(args, "input", None)
        if raw_input is not None and raw_input.is_file():
            single_file = raw_input
            args.input = None  # null out so _prepare_config doesn't use it

    config = _prepare_config(config_path, args)
    if args.force:
        config.analyze.skip_existing = False

    context_override = (getattr(args, "context", "") or "").strip() or None

    try:
        if args.command == "compress":
            from vlog_tool.pipeline import run_compress_all

            run_compress_all(config, single_file=single_file)
        elif args.command == "analyze":
            from vlog_tool.pipeline import run_analyze_all

            run_analyze_all(config, single_file=single_file)
        elif args.command == "scripts":
            from vlog_tool.pipeline import run_generate_scripts

            run_generate_scripts(config, single_file=single_file)
        elif args.command == "label":
            from vlog_tool.pipeline import run_label_videos

            run_label_videos(config)
        elif args.command == "plan":
            from vlog_tool.pipeline import run_plan_vlog

            config.plan.use_transcripts = not getattr(args, "no_transcripts", False)
            run_plan_vlog(config, args.day)
        elif args.command == "run":
            from vlog_tool.pipeline import run_full_pipeline

            run_full_pipeline(config, args.day)
        elif args.command == "refine":
            from vlog_tool.pipeline import run_refine_scripts, run_refine_texts

            if not config.ai.context and not context_override:
                print(
                    "警告: config.yaml 里没有配置 ai.context 或 ai.context_file，"
                    "refine 效果有限（AI 不知道你的行程背景和规范）。",
                    file=sys.stderr,
                )
            fix = (getattr(args, "fix", "") or "").strip() or None
            target_path = getattr(args, "input", None)
            if fix and (target_path is None or target_path.is_dir()):
                print("错误: --fix 必须配合 -i 指定单个 .json 文件", file=sys.stderr)
                return 1
            try:
                if args.target in ("texts", "all"):
                    run_refine_texts(config, target_path, fix=fix, context_override=context_override)
                if args.target in ("scripts", "all"):
                    if args.target == "all" and target_path is not None:
                        scripts_path = None
                    else:
                        scripts_path = target_path
                    run_refine_scripts(config, scripts_path, fix=fix, context_override=context_override)
            except ValueError as e:
                print(f"错误: {e}", file=sys.stderr)
                return 1
        elif args.command == "cut":
            from vlog_tool.pipeline import run_cut_all

            run_cut_all(
                config,
                day_label=args.day,
                output_dir=args.out_dir,
                reencode=args.reencode,
                source=args.source,
            )
        elif args.command == "migrate-config":
            root = args.projects_root or config.paths.input_dir.parent
            updated, errors = _migrate_project_configs(root)
            print(f"已更新 {updated} 个 project.yaml")
            if errors:
                print("错误:")
                for e in errors:
                    print(f"  - {e}")
            return 0
        elif args.command == "serve":
            return run_ui(
                config,
                config_path=config_path,
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
            )
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    finally:
        before_stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

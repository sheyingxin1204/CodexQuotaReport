from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .config import AppConfig, load_config, save_config
from .export import write_report_files
from .report import build_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quota-check",
        description="Check all local Codex accounts and show remaining quotas.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--desktop", action="store_true", help="open the native desktop client (default)")
    mode.add_argument("--cli", action="store_true", help="print a console report and export files")
    parser.add_argument("--refresh", action="store_true", help="force a status refresh before reading")
    parser.add_argument("--no-refresh", action="store_true", help="skip status refresh")
    parser.add_argument("--output-dir", help="directory for exported report files")
    parser.add_argument("--format", default="csv,xlsx,json", help="export formats for --cli")
    parser.add_argument("--config", help="path to a config JSON file")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _apply_overrides(config: AppConfig, args: argparse.Namespace) -> None:
    if args.refresh:
        config.refresh_on_start = True
    if args.no_refresh:
        config.refresh_on_start = False
    if args.output_dir:
        config.output_dir = str(Path(args.output_dir).resolve())


def _print_report(config: AppConfig, args: argparse.Namespace) -> int:
    def progress(message: str) -> None:
        print(f"[progress] {message}", file=sys.stderr)

    refresh = config.refresh_on_start
    result = build_report(config, refresh=refresh, on_progress=progress)

    headers = ["邮箱", "套餐", "快捷方式", "主额度", "5小时", "更新时间", "状态"]
    widths = [34, 8, 10, 10, 10, 16, 9]
    print(" ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("-" * sum(widths) + "-" * (len(widths) - 1))
    for snapshot in result.snapshots:
        alias = next(
            (c.alias for c in result.candidates if c.code_home == snapshot.code_home),
            None,
        )
        weekly = (
            f"{snapshot.weekly.remaining_percent:g}%"
            if snapshot.weekly and snapshot.weekly.remaining_percent is not None
            else "-"
        )
        five_hour = (
            f"{snapshot.five_hour.remaining_percent:g}%"
            if snapshot.five_hour and snapshot.five_hour.remaining_percent is not None
            else "-"
        )
        updated = (
            snapshot.snapshot_at_utc.astimezone().strftime("%Y-%m-%d %H:%M")
            if snapshot.snapshot_at_utc
            else "-"
        )
        row = [
            (snapshot.email or "未登录")[:34],
            (snapshot.plan_type or "-")[:8],
            (alias or snapshot.label)[:10],
            weekly[:10],
            five_hour[:10],
            updated[:16],
            snapshot.status[:9],
        ]
        print(" ".join(value.ljust(width) for value, width in zip(row, widths)))

    formats = [fmt.strip() for fmt in args.format.split(",") if fmt.strip()]
    written = write_report_files(result, config, formats)
    print()
    for path in written:
        print(f"导出: {path}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = load_config(Path(args.config) if args.config else None)
    _apply_overrides(config, args)

    if args.cli:
        return _print_report(config, args)

    from .desktop import run_desktop

    return run_desktop(config)

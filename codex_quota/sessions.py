from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .config import AppConfig
from .models import AccountSnapshot, RateLimit, iso_to_datetime, remaining_percent


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_tail_lines(path: Path, max_lines: int = 2000) -> list[str]:
    """Read the last max_lines non-degenerate lines without loading a huge file."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []

    buffer = bytearray()
    chunk_size = 64 * 1024
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        while position > 0 and buffer.count(b"\n") < max_lines * 2:
            read = min(chunk_size, position)
            position -= read
            handle.seek(position)
            buffer = handle.read(read) + buffer
            if position == 0:
                break

    try:
        text = buffer.decode("utf-8", errors="replace")
    except Exception:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-max_lines:]


def iter_recent_session_files(code_home: Path, max_files: int = 30) -> list[Path]:
    sessions_root = code_home / "sessions"
    if not sessions_root.is_dir():
        return []
    try:
        files = list(sessions_root.rglob("*.jsonl"))
    except OSError:
        return []
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files[:max_files]


def parse_limit_object(obj: Any, source: str) -> Optional[RateLimit]:
    if not isinstance(obj, dict):
        return None
    window = _as_int(obj.get("window_minutes"))
    used = _as_float(obj.get("used_percent"))
    remaining = _as_float(obj.get("remaining_percent") or obj.get("remaining"))
    resets = _as_int(obj.get("resets_at") or obj.get("reset_at"))
    if window is None and used is None and remaining is None and resets is None:
        return None
    if remaining is None:
        remaining = remaining_percent(used)
    return RateLimit(
        window_minutes=window,
        used_percent=used,
        remaining_percent=remaining,
        resets_at_unix=resets,
        source=source,
        raw=obj,
    )


def find_latest_rate_limit_event(
    code_home: Path, config: AppConfig
) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    for file_path in iter_recent_session_files(code_home, config.max_session_files):
        for line in reversed(read_tail_lines(file_path, config.tail_lines)):
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            rate_limits = payload.get("rate_limits")
            if not isinstance(rate_limits, dict):
                continue
            if not any(
                parse_limit_object(rate_limits.get(name), str(name)) is not None
                for name in ("primary", "secondary", "individual_limit")
            ):
                continue
            return item, file_path
    return None, None


def build_snapshot_from_event(
    code_home: Path,
    label: str,
    discovered_from: str,
    event: Optional[dict[str, Any]],
    source_path: Optional[Path],
    auth_info: dict[str, Any],
) -> AccountSnapshot:
    if event is None:
        return AccountSnapshot(
            code_home=code_home,
            label=label,
            discovered_from=discovered_from,
            status="no_data",
            email=auth_info.get("email"),
            plan_type=auth_info.get("plan_type"),
            auth_mode=auth_info.get("auth_mode"),
            source_path=source_path,
            error="No token_count rate-limit event found in sessions.",
        )

    payload = event.get("payload") or {}
    rate_limits = payload.get("rate_limits") or {}
    limits: list[RateLimit] = []
    for name in ("primary", "secondary", "individual_limit"):
        parsed = parse_limit_object(rate_limits.get(name), str(name))
        if parsed is not None:
            limits.append(parsed)

    limits.sort(key=lambda item: item.window_minutes if item.window_minutes is not None else -1, reverse=True)
    weekly = limits[0] if limits else None
    five_hour = next(
        (item for item in limits if item.window_minutes == 300 and weekly is not None and weekly.window_minutes != 300),
        None,
    )
    other_limits = [
        item for item in limits if item is not weekly and item is not five_hour
    ]

    info = payload.get("info") or {}
    total_usage = info.get("total_token_usage") or {}
    last_usage = info.get("last_token_usage") or {}
    snapshot_at = iso_to_datetime(event.get("timestamp"))

    return AccountSnapshot(
        code_home=code_home,
        label=label,
        discovered_from=discovered_from,
        status="ok",
        email=auth_info.get("email"),
        plan_type=rate_limits.get("plan_type") or auth_info.get("plan_type"),
        auth_mode=auth_info.get("auth_mode"),
        weekly=weekly,
        five_hour=five_hour,
        other_limits=other_limits,
        snapshot_at_utc=snapshot_at,
        source_path=source_path,
        total_tokens=_as_int(total_usage.get("total_tokens")),
        last_tokens=_as_int(last_usage.get("total_tokens")),
        credits=rate_limits.get("credits"),
        raw={"event": event},
    )


def load_account_snapshot(
    code_home: Path,
    label: str,
    discovered_from: str,
    auth_info: dict[str, Any],
    config: AppConfig,
) -> AccountSnapshot:
    event, source_path = find_latest_rate_limit_event(code_home, config)
    return build_snapshot_from_event(
        code_home,
        label,
        discovered_from,
        event,
        source_path,
        auth_info,
    )

from __future__ import annotations

import json
import re
from datetime import datetime
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


def _as_unix(value: Any) -> Optional[int]:
    parsed = _as_int(value)
    if parsed is not None:
        return parsed
    if value is None:
        return None
    moment = iso_to_datetime(value)
    if moment is None:
        return None
    try:
        return int(moment.timestamp())
    except (OverflowError, OSError, ValueError):
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
    files.sort(key=_file_sort_time, reverse=True)
    return files[:max_files]


def _file_sort_time(path: Path) -> float:
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%dT%H-%M-%S").timestamp()
        except ValueError:
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _event_sort_time(item: dict[str, Any], path: Path) -> float:
    moment = iso_to_datetime(item.get("timestamp"))
    if moment is not None:
        try:
            return moment.timestamp()
        except (OverflowError, OSError, ValueError):
            pass
    return _file_sort_time(path)


def _file_may_contain_newer(path: Path, latest_time: float) -> bool:
    """Only inspect older files when they were modified after the latest event."""
    if _file_sort_time(path) > latest_time:
        return True
    try:
        return path.stat().st_mtime > latest_time + 1.0
    except OSError:
        return False


def parse_limit_object(obj: Any, source: str) -> Optional[RateLimit]:
    if not isinstance(obj, dict):
        return None
    window = _as_int(obj.get("window_minutes"))
    used = _as_float(obj.get("used_percent"))
    remaining_value = obj.get("remaining_percent")
    if remaining_value is None:
        remaining_value = obj.get("remaining")
    remaining = _as_float(remaining_value)
    resets_value = obj.get("resets_at")
    if resets_value is None:
        resets_value = obj.get("reset_at")
    resets = _as_unix(resets_value)
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
    latest: Optional[tuple[float, dict[str, Any], Path]] = None
    files = iter_recent_session_files(code_home, config.max_session_files)
    for index, file_path in enumerate(files):
        if (
            latest is not None
            and index > 0
            and not _file_may_contain_newer(file_path, latest[0])
        ):
            break
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
            candidate = (_event_sort_time(item, file_path), item, file_path)
            if latest is None or candidate[0] > latest[0]:
                latest = candidate
            break
    if latest is None:
        return None, None
    return latest[1], latest[2]


def find_usage_limit_error(
    code_home: Path, config: AppConfig
) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    latest: Optional[tuple[float, dict[str, Any], Path]] = None
    files = iter_recent_session_files(code_home, config.max_session_files)
    for index, file_path in enumerate(files):
        if (
            latest is not None
            and index > 0
            and not _file_may_contain_newer(file_path, latest[0])
        ):
            break
        for line in reversed(read_tail_lines(file_path, config.tail_lines)):
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(item, dict) or item.get("type") != "event_msg":
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict) or payload.get("type") not in (
                "task_complete",
                "error",
            ):
                continue
            error = (
                payload.get("error")
                if payload.get("type") == "task_complete"
                else payload
            )
            if not isinstance(error, dict):
                continue
            codex_info = str(error.get("codex_error_info") or "")
            message = str(error.get("message") or "")
            if "usage_limit" in codex_info.lower() or "usage limit" in message.lower():
                candidate = (_event_sort_time(item, file_path), item, file_path)
                if latest is None or candidate[0] > latest[0]:
                    latest = candidate
                break
    if latest is None:
        return None, None
    return latest[1], latest[2]


def _extract_error_reset_unix(item: dict[str, Any]) -> Optional[int]:
    payload = item.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    error = payload.get("error") if payload.get("type") == "task_complete" else payload
    if not isinstance(error, dict):
        return None
    for key in ("resets_at", "reset_at", "resets_at_unix"):
        value = _as_unix(error.get(key))
        if value is not None:
            return value
    message = str(error.get("message") or "")
    match = re.search(
        r"(?:try again|reset(?:s|ting)?|available)\s+(?:at\s+)?"
        r"([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\s+"
        r"(\d{1,2}:\d{2})\s*(AM|PM)",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        moment = datetime.strptime(
            f"{match.group(1)} {match.group(2)}, {match.group(3)} "
            f"{match.group(4)} {match.group(5).upper()}",
            "%b %d, %Y %I:%M %p",
        )
        moment = moment.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return int(moment.timestamp())
    except (ValueError, OverflowError, OSError):
        return None


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
            account_id=auth_info.get("account_id"),
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
        account_id=auth_info.get("account_id"),
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
    snapshot = build_snapshot_from_event(
        code_home,
        label,
        discovered_from,
        event,
        source_path,
        auth_info,
    )
    usage_error, usage_path = find_usage_limit_error(code_home, config)
    if usage_error is not None:
        error_at = iso_to_datetime(usage_error.get("timestamp"))
        should_mark_exhausted = event is None
        if not should_mark_exhausted and error_at is not None:
            should_mark_exhausted = (
                snapshot.snapshot_at_utc is None
                or error_at > snapshot.snapshot_at_utc
            )
        if should_mark_exhausted:
            snapshot.status = "ok"
            snapshot.error = None
            existing = snapshot.weekly
            reset_at = _extract_error_reset_unix(usage_error)
            if reset_at is None and existing is not None:
                reset_at = existing.resets_at_unix
            snapshot.weekly = RateLimit(
                window_minutes=existing.window_minutes if existing else None,
                used_percent=100.0,
                resets_at_unix=reset_at,
                source="session_error",
            )
            snapshot.refresh_message = "usage limit reached (0% remaining)"
            if error_at is not None:
                snapshot.snapshot_at_utc = error_at
            snapshot.source_path = usage_path or snapshot.source_path
    return snapshot

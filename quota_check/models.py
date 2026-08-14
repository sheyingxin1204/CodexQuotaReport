from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import APP_NAME


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def remaining_percent(used_percent: Optional[float]) -> Optional[float]:
    if used_percent is None:
        return None
    return round(clamp(100.0 - float(used_percent)), 2)


def iso_to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromtimestamp(float(text))
        except (ValueError, TypeError, OSError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def utc_now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class RateLimit:
    window_minutes: Optional[int] = None
    used_percent: Optional[float] = None
    remaining_percent: Optional[float] = None
    resets_at_unix: Optional[int] = None
    source: str = "primary"
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.used_percent is not None and self.remaining_percent is None:
            try:
                self.remaining_percent = remaining_percent(float(self.used_percent))
            except (TypeError, ValueError):
                self.remaining_percent = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_minutes": self.window_minutes,
            "used_percent": self.used_percent,
            "remaining_percent": self.remaining_percent,
            "resets_at_unix": self.resets_at_unix,
            "source": self.source,
        }


@dataclass
class AccountSnapshot:
    code_home: Path
    label: str
    discovered_from: str = "unknown"
    status: str = "ok"
    email: Optional[str] = None
    plan_type: Optional[str] = None
    auth_mode: Optional[str] = None
    account_id: Optional[str] = None
    weekly: Optional[RateLimit] = None
    five_hour: Optional[RateLimit] = None
    other_limits: list[RateLimit] = field(default_factory=list)
    snapshot_at_utc: Optional[datetime] = None
    source_path: Optional[Path] = None
    error: Optional[str] = None
    refreshed: bool = False
    refresh_message: Optional[str] = None
    total_tokens: Optional[int] = None
    last_tokens: Optional[int] = None
    credits: Optional[dict[str, Any]] = None
    raw: dict[str, Any] = field(default_factory=dict)
    related: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def has_limits(self) -> bool:
        return self.weekly is not None or self.five_hour is not None or bool(self.other_limits)

    def severity(self) -> str:
        if self.status != "ok":
            return self.status
        values = []
        for limit in self.all_limits():
            if limit.remaining_percent is None:
                continue
            values.append(limit.remaining_percent)
        if not values:
            return "no_data"
        worst = min(values)
        if worst <= 10:
            return "critical"
        if worst <= 30:
            return "warning"
        return "ok"

    def all_limits(self) -> list[RateLimit]:
        limits: list[RateLimit] = []
        if self.weekly is not None:
            limits.append(self.weekly)
        if self.five_hour is not None:
            limits.append(self.five_hour)
        limits.extend(self.other_limits)
        return limits

    def to_dict(self) -> dict[str, Any]:
        def fmt(dt: Optional[datetime]) -> Optional[str]:
            if dt is None:
                return None
            return dt.isoformat(timespec="seconds")

        return {
            "code_home": str(self.code_home),
            "label": self.label,
            "discovered_from": self.discovered_from,
            "status": self.status,
            "severity": self.severity(),
            "email": self.email or "",
            "plan_type": self.plan_type or "",
            "auth_mode": self.auth_mode or "",
            "account_id": self.account_id or "",
            "weekly": self.weekly.to_dict() if self.weekly else None,
            "five_hour": self.five_hour.to_dict() if self.five_hour else None,
            "other_limits": [limit.to_dict() for limit in self.other_limits],
            "snapshot_at_utc": fmt(self.snapshot_at_utc),
            "source_path": str(self.source_path) if self.source_path else None,
            "error": self.error,
            "refreshed": self.refreshed,
            "refresh_message": self.refresh_message,
            "total_tokens": self.total_tokens,
            "last_tokens": self.last_tokens,
            "credits": self.credits,
            "related": list(self.related),
            "app_name": APP_NAME,
        }

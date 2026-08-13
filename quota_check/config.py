from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def default_config_dir() -> Path:
    return Path(os.environ.get("QUOTA_CHECK_CONFIG_DIR", str(Path.home() / ".quota_check")))


@dataclass
class AppConfig:
    extra_code_homes: list[str] = field(default_factory=list)
    scan_home: bool = True
    scan_profiles: bool = True
    refresh_on_start: bool = True
    refresh_timeout_seconds: int = 60
    output_dir: str = ""
    max_session_files: int = 30
    tail_lines: int = 2000
    port: int = 0

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(Path.home() / "Desktop")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        allowed = cls()
        for key, value in data.items():
            if not hasattr(allowed, key):
                continue
            current = getattr(allowed, key)
            if isinstance(current, bool):
                setattr(allowed, key, bool(value))
            elif isinstance(current, int):
                try:
                    setattr(allowed, key, int(value))
                except (TypeError, ValueError):
                    pass
            elif isinstance(current, list):
                setattr(allowed, key, [str(item) for item in value])
            else:
                setattr(allowed, key, str(value))
        return allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "extra_code_homes": list(self.extra_code_homes),
            "scan_home": self.scan_home,
            "scan_profiles": self.scan_profiles,
            "refresh_on_start": self.refresh_on_start,
            "refresh_timeout_seconds": self.refresh_timeout_seconds,
            "output_dir": self.output_dir,
            "max_session_files": self.max_session_files,
            "tail_lines": self.tail_lines,
            "port": self.port,
        }


def load_config(path: Path | None = None) -> AppConfig:
    path = path or (default_config_dir() / "config.json")
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    return AppConfig.from_dict(raw)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    path = path or (default_config_dir() / "config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

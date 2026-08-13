from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .config import AppConfig


@dataclass
class CodeHomeCandidate:
    code_home: Path
    label: str
    discovered_from: str
    alias: Optional[str] = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code_home": str(self.code_home),
            "label": self.label,
            "discovered_from": self.discovered_from,
            "alias": self.alias,
        }


def expand_path(text: str) -> Path:
    expanded = os.path.expandvars(text)
    if os.name == "nt":
        home = str(Path.home())
        expanded = expanded.replace("$HOME", home).replace("${HOME}", home)
        expanded = os.path.expandvars(expanded)
    return Path(os.path.expanduser(expanded.strip().strip('"')))


def is_code_home(path: Path) -> bool:
    if not path.is_dir():
        return False
    markers = ("auth.json", "sessions", "config.toml", "history.jsonl")
    return any((path / marker).exists() for marker in markers)


def _dedupe(candidates: Iterable[CodeHomeCandidate]) -> list[CodeHomeCandidate]:
    seen: set[str] = set()
    result: list[CodeHomeCandidate] = []
    for candidate in candidates:
        key = os.path.normcase(str(Path(candidate.code_home).resolve()))
        if key in seen:
            existing = next(item for item in result if os.path.normcase(str(Path(item.code_home).resolve())) == key)
            if candidate.alias and not existing.alias:
                existing.alias = candidate.alias
            if candidate.discovered_from != "home" and existing.discovered_from == "home":
                existing.discovered_from = candidate.discovered_from
            continue
        seen.add(key)
        result.append(candidate)
    return result


def iter_home_candidates(home: Path) -> list[Path]:
    try:
        entries = list(home.iterdir())
    except OSError:
        return []
    result: list[Path] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name.lower()
        if name.startswith(".codex") or "codex" in name:
            if is_code_home(entry):
                result.append(entry)
    return result


def _profile_candidates() -> list[Path]:
    home = Path.home()
    docs = Path.home() / "Documents"
    return [
        docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
        home / ".config" / "powershell" / "Microsoft.PowerShell_profile.ps1",
        home / ".config" / "powershell" / "profile.ps1",
        home / ".bashrc",
        home / ".bash_profile",
        home / ".profile",
        home / ".zshrc",
        home / ".config" / "fish" / "config.fish",
    ]


def scan_profiles() -> dict[str, str]:
    """Return {resolved_path: alias} found in common shell profiles."""
    aliases: dict[str, str] = {}
    home_pattern = re.compile(
        r"(?i)(?:Invoke-CodexHome|CODEX_HOME|codex_home)\s*=\s*[(\"']*"
        r"([A-Za-z0-9_\\/:.${}~ -]+?)[\"')]"
    )
    function_pattern = re.compile(r"(?im)^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?\s*\{")

    for profile in _profile_candidates():
        if not profile.exists():
            continue
        try:
            content = profile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for match in re.finditer(r"(?im)^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\()?\s*\{", content):
            body_start = match.end()
            body_end = content.find("\n}", body_start)
            if body_end < 0:
                body_end = len(content)
            body = content[body_start:body_end]
            home_match = re.search(
                r"(?i)Invoke-CodexHome\s+[\"']([^\"']+)[\"']|CODEX_HOME\s*=\s*[\"']([^\"']+)[\"']",
                body,
            )
            if home_match:
                raw = home_match.group(1) or home_match.group(2)
                aliases[str(expand_path(raw))] = match.group(1)

        for match in re.finditer(
            r"(?im)(?:export\s+|set\s+-[gux]+\s+|setenv\s+)?CODEX_HOME\s*=\s*[\"']([^\"']+)[\"']",
            content,
        ):
            aliases.setdefault(str(expand_path(match.group(1))), "")
    return aliases


def _collect_extra(config: AppConfig) -> list[CodeHomeCandidate]:
    result: list[CodeHomeCandidate] = []
    for raw_path in config.extra_code_homes:
        if not raw_path.strip():
            continue
        path = expand_path(raw_path)
        if is_code_home(path):
            result.append(
                CodeHomeCandidate(path, path.name, "custom", alias=os.environ.get("CODEX_HOME_ALIAS"))
            )
            continue
        if not path.is_dir():
            continue
        for child in sorted(path.iterdir()):
            if child.is_dir() and is_code_home(child):
                result.append(CodeHomeCandidate(child, child.name, "custom"))
    return result


def discover_code_homes(config: AppConfig) -> list[CodeHomeCandidate]:
    candidates: list[CodeHomeCandidate] = []
    home = Path.home()

    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        path = expand_path(env_home)
        if is_code_home(path):
            candidates.append(CodeHomeCandidate(path, path.name, "env"))

    default_home = home / ".codex"
    if is_code_home(default_home):
        candidates.append(CodeHomeCandidate(default_home, "default", "default"))

    for path in (home / ".config" / "codex", home / "Library" / "Application Support" / "codex"):
        if is_code_home(path):
            candidates.append(CodeHomeCandidate(path, path.name, "default"))

    if config.scan_home:
        for path in iter_home_candidates(home):
            candidates.append(CodeHomeCandidate(path, path.name, "home"))

    if config.scan_profiles:
        aliases = scan_profiles()
        for path, alias in aliases.items():
            resolved = expand_path(path)
            if is_code_home(resolved):
                candidates.append(
                    CodeHomeCandidate(resolved, resolved.name, "profile", alias=alias or None)
                )

    candidates.extend(_collect_extra(config))
    return _dedupe(candidates)

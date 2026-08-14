from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import os
import threading
from typing import Any, Callable, Optional

from .auth import read_auth_info
from .config import AppConfig
from .discovery import CodeHomeCandidate, discover_code_homes
from .models import AccountSnapshot
from .refresh import RefreshResult, find_codex_executable, refresh_account
from .sessions import load_account_snapshot


ProgressCallback = Callable[[str], None]


@dataclass
class ReportResult:
    snapshots: list[AccountSnapshot]
    candidates: list[CodeHomeCandidate]
    refresh_results: list[RefreshResult] = field(default_factory=list)
    codex_available: bool = False
    accounts: list[AccountSnapshot] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.refresh_merged()

    def refresh_merged(self) -> None:
        self.accounts = merge_account_snapshots(self.snapshots, self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accounts": [snapshot.to_dict() for snapshot in self.accounts],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "refresh_results": [result.to_dict() for result in self.refresh_results],
            "codex_available": self.codex_available,
        }


def _account_key(snapshot: AccountSnapshot) -> str:
    if snapshot.account_id:
        return "id:" + str(snapshot.account_id).strip().lower()
    if snapshot.email:
        return "mail:" + snapshot.email.strip().lower()
    return "home:" + os.path.normcase(str(snapshot.code_home))


def _alias_map(candidates: list[CodeHomeCandidate]) -> dict[str, str]:
    return {
        os.path.normcase(str(candidate.code_home)): candidate.alias or ""
        for candidate in candidates
    }


def merge_account_snapshots(
    snapshots: list[AccountSnapshot],
    candidates: list[CodeHomeCandidate],
) -> list[AccountSnapshot]:
    aliases = _alias_map(candidates)
    groups: dict[str, list[AccountSnapshot]] = {}
    order: list[str] = []
    for snapshot in snapshots:
        key = _account_key(snapshot)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(snapshot)

    merged: list[AccountSnapshot] = []
    for key in order:
        group = groups[key]
        primary = _pick_primary(group)
        related: list[dict[str, Any]] = []
        for snapshot in group:
            if snapshot is primary:
                continue
            related.append(
                {
                    "label": snapshot.label,
                    "alias": aliases.get(os.path.normcase(str(snapshot.code_home)), ""),
                    "code_home": str(snapshot.code_home),
                    "status": snapshot.status,
                    "error": snapshot.error,
                    "snapshot_at_utc": (
                        snapshot.snapshot_at_utc.isoformat(timespec="seconds")
                        if snapshot.snapshot_at_utc
                        else None
                    ),
                    "weekly_remaining": (
                        snapshot.weekly.remaining_percent if snapshot.weekly else None
                    ),
                    "five_hour_remaining": (
                        snapshot.five_hour.remaining_percent if snapshot.five_hour else None
                    ),
                }
            )
        primary.related = related
        merged.append(primary)
    return merged


def _pick_primary(group: list[AccountSnapshot]) -> AccountSnapshot:
    ranked = sorted(
        group,
        key=lambda item: (
            item.status != "ok",
            not item.has_limits,
            item.label != "default",
        ),
    )
    return ranked[0]


def build_report(
    config: AppConfig,
    refresh: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> ReportResult:
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    candidates = discover_code_homes(config)
    progress(f"发现 {len(candidates)} 个 Codex 账号目录")

    codex_available = find_codex_executable() is not None
    refresh_results: list[RefreshResult] = []
    snapshots: list[AccountSnapshot] = []
    lock = threading.Lock()

    def process_candidate(index: int, candidate: CodeHomeCandidate) -> AccountSnapshot:
        progress(f"[{index}/{len(candidates)}] 正在读取 {candidate.label}")
        auth_info = read_auth_info(candidate.code_home)
        refresh_result: Optional[RefreshResult] = None
        if refresh and codex_available:
            progress(f"[{index}/{len(candidates)}] 正在刷新 {candidate.label} 的状态")
            refresh_result = refresh_account(candidate.code_home, config.refresh_timeout_seconds)
            with lock:
                refresh_results.append(refresh_result)

        snapshot = load_account_snapshot(
            candidate.code_home,
            candidate.label,
            candidate.discovered_from,
            auth_info,
            config,
        )
        if refresh_result is not None:
            snapshot.refreshed = refresh_result.ok
            snapshot.refresh_message = refresh_result.message
            if not refresh_result.ok:
                snapshot.error = (snapshot.error or "") + " | " + refresh_result.message
                snapshot.status = "error"
        return snapshot

    workers = max(1, min(4, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        ordered = executor.map(
            lambda item: process_candidate(item[0], item[1]),
            enumerate(candidates, start=1),
        )
        snapshots = list(ordered)

    return ReportResult(
        snapshots=snapshots,
        candidates=candidates,
        refresh_results=refresh_results,
        codex_available=codex_available,
    )

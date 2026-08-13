from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "accounts": [snapshot.to_dict() for snapshot in self.snapshots],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "refresh_results": [result.to_dict() for result in self.refresh_results],
            "codex_available": self.codex_available,
        }


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

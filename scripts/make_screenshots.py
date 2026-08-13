from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quota_check.discovery import CodeHomeCandidate
from quota_check.models import AccountSnapshot, RateLimit
from quota_check.report import ReportResult
from quota_check.server import QuotaState, _make_handler


MOCK_ACCOUNTS = [
    {
        "label": ".codex_a",
        "alias": "ca",
        "email": "alice@example.com",
        "plan": "plus",
        "weekly": 72,
        "window": 10080,
        "five": 88,
        "tokens": 286_340,
    },
    {
        "label": ".codex_b",
        "alias": "cb",
        "email": "bob@example.com",
        "plan": "plus",
        "weekly": 45,
        "window": 10080,
        "five": 63,
        "tokens": 192_118,
    },
    {
        "label": ".codex_c",
        "alias": "cc",
        "email": "carol@example.com",
        "plan": "pro",
        "weekly": 18,
        "window": 10080,
        "five": 41,
        "tokens": 452_074,
    },
    {
        "label": ".codex_d",
        "alias": "cd",
        "email": "dave@example.com",
        "plan": "free",
        "weekly": 7,
        "window": 43200,
        "five": None,
        "tokens": 17_860,
    },
    {
        "label": ".codex_e",
        "alias": "ce",
        "email": "erin@example.com",
        "plan": "free",
        "weekly": 96,
        "window": 43200,
        "five": None,
        "tokens": 24_531,
    },
    {
        "label": ".codex_f",
        "alias": "cf",
        "email": "frank@example.com",
        "plan": "free",
        "weekly": 100,
        "window": 43200,
        "five": None,
        "tokens": 12_402,
    },
    {
        "label": ".codex_g",
        "alias": "cg",
        "email": "grace@example.com",
        "plan": "free",
        "weekly": 88,
        "window": 10080,
        "five": None,
        "tokens": 31_274,
    },
    {
        "label": ".codex_h",
        "alias": "ch",
        "email": "henry@example.com",
        "plan": "pro",
        "weekly": 34,
        "window": 10080,
        "five": 55,
        "tokens": 391_208,
    },
    {
        "label": ".codex_i",
        "alias": "ci",
        "email": "iris@example.com",
        "plan": "plus",
        "weekly": 81,
        "window": 10080,
        "five": 92,
        "tokens": 243_771,
    },
]


def build_mock_report() -> ReportResult:
    snapshots: list[AccountSnapshot] = []
    candidates: list[CodeHomeCandidate] = []
    for item in MOCK_ACCOUNTS:
        code_home = Path.home() / item["label"]
        weekly = RateLimit(
            window_minutes=item["window"],
            used_percent=round(100 - item["weekly"], 2),
            remaining_percent=item["weekly"],
            resets_at_unix=1_800_000_000,
            source="primary",
        )
        five_hour = None
        if item["five"] is not None:
            five_hour = RateLimit(
                window_minutes=300,
                used_percent=round(100 - item["five"], 2),
                remaining_percent=item["five"],
                resets_at_unix=1_800_000_000,
                source="secondary",
            )
        snapshots.append(
            AccountSnapshot(
                code_home=code_home,
                label=item["label"],
                discovered_from="home",
                status="ok",
                email=item["email"],
                plan_type=item["plan"],
                weekly=weekly,
                five_hour=five_hour,
                total_tokens=item["tokens"],
                snapshot_at_utc=None,
            )
        )
        candidates.append(
            CodeHomeCandidate(code_home, item["label"], "home", alias=item["alias"])
        )
    return ReportResult(snapshots=snapshots, candidates=candidates, codex_available=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--wait", type=int, default=0)
    args = parser.parse_args()

    state = QuotaState(_dummy_config())
    state.report = build_mock_report()
    state.refreshed_at = "2026-08-13T12:00:00+08:00"
    state.codex_path = "C:\\Users\\demo\\AppData\\Roaming\\npm\\codex.cmd"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"mock dashboard: http://127.0.0.1:{args.port}/")
    if args.wait:
        time.sleep(args.wait)
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    server.shutdown()
    server.server_close()


def _dummy_config():
    from quota_check.config import AppConfig

    config = AppConfig()
    config.refresh_on_start = False
    return config


if __name__ == "__main__":
    main()

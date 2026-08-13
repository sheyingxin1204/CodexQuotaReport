from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quota_check.config import AppConfig
from quota_check.sessions import (
    build_snapshot_from_event,
    find_latest_rate_limit_event,
    load_account_snapshot,
    read_tail_lines,
)


def make_event() -> dict:
    return {
        "timestamp": "2026-08-01T12:00:00Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {"total_tokens": 12345},
                "last_token_usage": {"total_tokens": 100},
            },
            "rate_limits": {
                "plan_type": "plus",
                "primary": {
                    "used_percent": 15.0,
                    "window_minutes": 10080,
                    "resets_at": 1785000000,
                },
                "secondary": {
                    "used_percent": 1.0,
                    "window_minutes": 300,
                    "resets_at": 1785090000,
                },
            },
        },
    }


class SessionTests(unittest.TestCase):
    def test_read_tail_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("".join(f"line {i}\n" for i in range(50)), encoding="utf-8")
            self.assertEqual(read_tail_lines(path, 10), [f"line {i}" for i in range(40, 50)])

    def test_find_and_build_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code_home = Path(directory) / ".codex"
            session_dir = code_home / "sessions" / "2026" / "08"
            session_dir.mkdir(parents=True)
            (session_dir / "rollout.jsonl").write_text(
                json.dumps(make_event()) + "\n",
                encoding="utf-8",
            )
            event, source = find_latest_rate_limit_event(code_home, AppConfig())
            self.assertIsNotNone(event)
            snapshot = build_snapshot_from_event(
                code_home,
                "default",
                "default",
                event,
                source,
                {"email": "a@b.c", "plan_type": "free"},
            )
        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.weekly.window_minutes, 10080)
        self.assertEqual(snapshot.weekly.remaining_percent, 85.0)
        self.assertEqual(snapshot.five_hour.window_minutes, 300)
        self.assertEqual(snapshot.plan_type, "plus")
        self.assertEqual(snapshot.total_tokens, 12345)

    def test_no_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code_home = Path(directory) / ".codex"
            (code_home / "sessions").mkdir(parents=True)
            snapshot = load_account_snapshot(
                code_home, "default", "default", {}, AppConfig()
            )
        self.assertEqual(snapshot.status, "no_data")
        self.assertIn("No token_count", snapshot.error or "")


if __name__ == "__main__":
    unittest.main()

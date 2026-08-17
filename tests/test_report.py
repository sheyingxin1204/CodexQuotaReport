from __future__ import annotations

import unittest
from pathlib import Path

from quota_check.discovery import CodeHomeCandidate
from quota_check.models import AccountSnapshot, RateLimit
from quota_check.refresh import RefreshResult, _detect_usage_limit
from quota_check.report import ReportResult, apply_refresh_result, merge_account_snapshots


def make_snapshot(code_home: str, label: str, account_id: str, email: str) -> AccountSnapshot:
    return AccountSnapshot(
        code_home=Path(code_home),
        label=label,
        status="ok",
        account_id=account_id,
        email=email,
    )


class ReportTests(unittest.TestCase):
    def test_merge_by_account_id(self) -> None:
        snapshots = [
            make_snapshot(r"C:\Users\me\.codex", "default", "acc-1", "same@example.com"),
            make_snapshot(r"C:\Users\me\.codex_a", ".codex_a", "acc-1", "same@example.com"),
            make_snapshot(r"C:\Users\me\.codex_b", ".codex_b", "acc-2", "other@example.com"),
        ]
        candidates = [
            CodeHomeCandidate(Path(r"C:\Users\me\.codex"), "default", "default", alias=""),
            CodeHomeCandidate(Path(r"C:\Users\me\.codex_a"), ".codex_a", "home", alias="ca"),
            CodeHomeCandidate(Path(r"C:\Users\me\.codex_b"), ".codex_b", "home", alias="cb"),
        ]
        merged = merge_account_snapshots(snapshots, candidates)
        self.assertEqual(len(merged), 2)
        primary = next(item for item in merged if item.account_id == "acc-1")
        self.assertEqual(len(primary.related), 1)
        self.assertEqual(primary.related[0]["alias"], "ca")

    def test_report_result_uses_merged_accounts(self) -> None:
        snapshots = [
            make_snapshot(r"C:\Users\me\.codex", "default", "acc-1", "same@example.com"),
            make_snapshot(r"C:\Users\me\.codex_a", ".codex_a", "acc-1", "same@example.com"),
        ]
        candidates = [CodeHomeCandidate(Path(r"C:\Users\me\.codex"), "default", "default")]
        result = ReportResult(snapshots=snapshots, candidates=candidates)
        self.assertEqual(len(result.accounts), 1)
        payload = result.to_dict()
        self.assertEqual(len(payload["accounts"]), 1)
        self.assertEqual(len(payload["accounts"][0]["related"]), 1)

    def test_detect_usage_limit(self) -> None:
        self.assertTrue(
            _detect_usage_limit(
                "You've hit your usage limit. Upgrade to Plus to continue using Codex."
            )
        )
        self.assertFalse(_detect_usage_limit("rate limit event refreshed"))

    def test_apply_refresh_result_exhausted(self) -> None:
        snapshot = make_snapshot(r"C:\Users\me\.codex_b", ".codex_b", "acc-2", "used@example.com")
        snapshot.weekly = RateLimit(
            window_minutes=43200,
            used_percent=1.0,
            resets_at_unix=1789097254,
        )
        result = RefreshResult(
            code_home=Path(r"C:\Users\me\.codex_b"),
            ok=True,
            message="usage limit reached (0% remaining)",
            exit_code=1,
            exhausted=True,
        )
        apply_refresh_result(snapshot, result)
        self.assertEqual(snapshot.status, "ok")
        self.assertIsNotNone(snapshot.weekly)
        assert snapshot.weekly is not None
        self.assertEqual(snapshot.weekly.used_percent, 100.0)
        self.assertEqual(snapshot.weekly.remaining_percent, 0.0)
        self.assertEqual(snapshot.weekly.resets_at_unix, 1789097254)

    def test_refresh_result_to_dict_includes_exhausted(self) -> None:
        result = RefreshResult(
            code_home=Path(r"C:\Users\me\.codex_b"),
            ok=True,
            message="usage limit reached (0% remaining)",
            exhausted=True,
        )
        payload = result.to_dict()
        self.assertTrue(payload["exhausted"])


if __name__ == "__main__":
    unittest.main()

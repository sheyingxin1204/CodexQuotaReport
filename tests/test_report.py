from __future__ import annotations

import unittest
from pathlib import Path

from quota_check.discovery import CodeHomeCandidate
from quota_check.models import AccountSnapshot
from quota_check.report import ReportResult, merge_account_snapshots


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


if __name__ == "__main__":
    unittest.main()

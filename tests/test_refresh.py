from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from quota_check.refresh import RefreshResult, refresh_account


class RefreshTests(unittest.TestCase):
    def test_transient_failure_is_retried(self) -> None:
        code_home = Path(r"C:\Users\me\.codex")
        failed = RefreshResult(code_home, False, "timed out")
        succeeded = RefreshResult(code_home, True, "rate limit event refreshed")
        with mock.patch(
            "quota_check.refresh._refresh_account_once",
            side_effect=[failed, succeeded],
        ) as refresh_once, mock.patch("quota_check.refresh.time.sleep") as sleep:
            result = refresh_account(code_home, timeout_seconds=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 2)
        self.assertIn("重试 1 次后", result.message)
        self.assertEqual(refresh_once.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()

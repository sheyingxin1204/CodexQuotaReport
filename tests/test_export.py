from __future__ import annotations

import io
import zipfile
import unittest

from quota_check.export import export_csv_bytes, export_xlsx_bytes, build_rows
from quota_check.models import AccountSnapshot, RateLimit
from quota_check.report import ReportResult
from quota_check.discovery import CodeHomeCandidate


def sample_report() -> ReportResult:
    snapshot = AccountSnapshot(
        code_home=__import__("pathlib").Path("/home/user/.codex_a"),
        label=".codex_a",
        email="user@example.com",
        plan_type="plus",
        weekly=RateLimit(window_minutes=10080, used_percent=15.0, resets_at_unix=1785000000),
        five_hour=RateLimit(window_minutes=300, used_percent=1.0, resets_at_unix=1785090000),
    )
    candidate = CodeHomeCandidate(snapshot.code_home, ".codex_a", "home", alias="ca")
    return ReportResult(snapshots=[snapshot], candidates=[candidate])


class ExportTests(unittest.TestCase):
    def test_csv_headers(self) -> None:
        csv_text = export_csv_bytes(build_rows(sample_report())).decode("utf-8-sig")
        self.assertIn("账号邮箱", csv_text.splitlines()[0])
        self.assertIn("85%", csv_text)

    def test_xlsx_is_valid_zip(self) -> None:
        data = export_xlsx_bytes(build_rows(sample_report()))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("xl/worksheets/sheet1.xml", names)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_quota.auth import decode_jwt_payload, read_auth_info

from tests.helpers import make_jwt


class AuthTests(unittest.TestCase):
    def test_decode_jwt_payload(self) -> None:
        payload = {"email": "user@example.com", "chatgpt_plan_type": "plus"}
        self.assertEqual(decode_jwt_payload(make_jwt(payload)), payload)

    def test_read_auth_info(self) -> None:
        token = make_jwt(
            {
                "https://api.openai.com/profile": {"email": "user@example.com"},
                "https://api.openai.com/auth": {"chatgpt_plan_type": "pro"},
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            code_home = Path(directory) / ".codex"
            code_home.mkdir()
            (code_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": token}}),
                encoding="utf-8",
            )
            info = read_auth_info(code_home)
        self.assertEqual(info["email"], "user@example.com")
        self.assertEqual(info["plan_type"], "pro")
        self.assertEqual(info["auth_mode"], "chatgpt")

    def test_missing_auth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            info = read_auth_info(Path(directory) / ".codex")
        self.assertIsNone(info["email"])
        self.assertFalse(info["api_key"])


if __name__ == "__main__":
    unittest.main()

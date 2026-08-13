from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quota_check.config import AppConfig
from quota_check.discovery import discover_code_homes, is_code_home


class DiscoveryTests(unittest.TestCase):
    def test_is_code_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "auth.json"
            valid.touch()
            self.assertTrue(is_code_home(root))
            empty = root / "empty"
            empty.mkdir()
            self.assertFalse(is_code_home(empty))

    def test_home_scan_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            default = home / ".codex"
            (default / "sessions").mkdir(parents=True)
            extra = home / ".codex_a"
            extra.mkdir()
            (extra / "auth.json").touch()
            noise = home / ".codexskins"
            noise.mkdir()

            config = AppConfig()
            config.scan_home = True
            config.scan_profiles = False

            original_home = Path.home
            try:
                import quota_check.discovery as discovery

                discovery.Path.home = staticmethod(lambda: home)
                candidates = discover_code_homes(config)
            finally:
                discovery.Path.home = original_home

        paths = {str(candidate.code_home) for candidate in candidates}
        self.assertIn(str(default), paths)
        self.assertIn(str(extra), paths)
        self.assertNotIn(str(noise), paths)
        self.assertEqual(len(candidates), len(paths))

    def test_custom_extra_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            custom = home / ".codex_custom"
            custom.mkdir()
            (custom / "auth.json").touch()
            config = AppConfig(extra_code_homes=[str(custom)])
            candidates = discover_code_homes(config)
        self.assertTrue(any(candidate.code_home == custom for candidate in candidates))


if __name__ == "__main__":
    unittest.main()

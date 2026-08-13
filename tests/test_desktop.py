from __future__ import annotations

import threading
import unittest

from quota_check.config import AppConfig
from quota_check.desktop import create_app_server, is_webview_available


class DesktopTests(unittest.TestCase):
    def test_create_app_server(self) -> None:
        config = AppConfig()
        config.port = 0
        config.refresh_on_start = False
        server, state, url = create_app_server(config)
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertFalse(state.refreshing)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        server.shutdown()
        server.server_close()

    def test_webview_availability_is_bool(self) -> None:
        self.assertIsInstance(is_webview_available(), bool)


if __name__ == "__main__":
    unittest.main()

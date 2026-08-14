from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quota_check.config import AppConfig
from quota_check.desktop import create_app_server
from quota_check.models import RateLimit
from quota_check.refresh import RefreshResult


def fake_refresh_account(code_home, timeout_seconds=60):
    return RefreshResult(
        code_home=Path(code_home),
        ok=True,
        message="rate limit event refreshed",
        exit_code=0,
        elapsed_seconds=0.1,
    )


def main() -> None:
    config = AppConfig()
    config.port = 8795
    config.refresh_on_start = False
    config.check_updates = False
    server, state, url = create_app_server(config)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.start_load(refresh=False)
    time.sleep(8)

    home = os.path.expanduser("~/.codex_b")
    with mock.patch("quota_check.server.refresh_account", fake_refresh_account):
        request = urllib.request.Request(
            url + "api/refresh-account",
            data=json.dumps({"code_home": home}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = json.load(urllib.request.urlopen(request))["started"]
        print("started=", started, flush=True)
        assert started, "single refresh should start"
        for _ in range(10):
            time.sleep(1)
            data = json.load(urllib.request.urlopen(url + "api/state"))
            if not data["refreshing_accounts"]:
                break
        data = json.load(urllib.request.urlopen(url + "api/state"))
        assert not data["refreshing_accounts"]
        assert data["account_refresh_results"]
        print("flow ok, accounts=", len(data["report"]["accounts"]), flush=True)
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()

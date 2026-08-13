from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from .config import AppConfig
from .server import QuotaState, _make_handler


def create_app_server(
    config: AppConfig,
) -> tuple[ThreadingHTTPServer, QuotaState, str]:
    state = QuotaState(config)
    server = ThreadingHTTPServer(("127.0.0.1", config.port), _make_handler(state))
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    return server, state, url


def run_desktop(config: AppConfig) -> int:
    server, state, url = create_app_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.start_load()

    try:
        import webview
    except Exception as exc:
        server.shutdown()
        server.server_close()
        print(f"原生窗口组件不可用，请运行: python -m pip install pywebview（原始错误: {exc}）")
        return 1

    window = webview.create_window(
        "codex自检额度",
        url,
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#f4f6fa",
    )
    try:
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


def is_webview_available() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except Exception:
        return False

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

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
    state.start_update_check()

    try:
        import webview
    except Exception as exc:
        server.shutdown()
        server.server_close()
        print(f"原生窗口组件不可用，请运行: python -m pip install pywebview（原始错误: {exc}）")
        return 1

    window = webview.create_window(
        "自检额度",
        url,
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#f4f6fa",
    )
    state.set_notification_handler(
        lambda title, message: _notify(webview, title, message)
    )
    tray = _start_tray(window)

    def on_closing() -> bool:
        if tray is not None:
            window.hide()
            return False
        return True

    window.events.closing += on_closing
    try:
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        if tray is not None:
            tray.stop()
        server.shutdown()
        server.server_close()
    return 0


def is_webview_available() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except Exception:
        return False


def _notify(webview, title: str, message: str) -> None:
    try:
        windows = getattr(webview, "windows", None)
        if windows:
            windows[0].create_notification(title, message)
    except Exception:
        pass


def _start_tray(window):
    try:
        import pystray
        from PIL import Image
    except Exception:
        return None

    icon_path = Path(__file__).resolve().parents[1] / "build" / "icon.ico"
    try:
        image = Image.open(icon_path)
    except Exception:
        image = Image.new("RGBA", (64, 64), (37, 99, 235, 255))

    def show():
        window.show()
        window.restore()

    def quit_app(icon, item):
        icon.stop()
        window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("显示窗口", lambda icon, item: show(), default=True),
        pystray.MenuItem("退出", quit_app),
    )
    tray = pystray.Icon("quota-self-check", image, "自检额度", menu)
    tray.run_detached()
    return tray

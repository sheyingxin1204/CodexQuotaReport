from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import AppConfig, save_config
from .export import export_csv_bytes, export_json_bytes, export_xlsx_bytes, build_rows
from .refresh import find_codex_executable
from .report import ReportResult, build_report


def _web_dir() -> Path:
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / "quota_check" / "web"
    return Path(__file__).resolve().parent / "web"


class QuotaState:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.report: Optional[ReportResult] = None
        self.refreshed_at: Optional[str] = None
        self.refreshing = False
        self.progress_log: list[str] = []
        self.lock = threading.Lock()
        self.codex_path = str(find_codex_executable() or "")

    def set_progress(self, message: str) -> None:
        with self.lock:
            self.progress_log.append(message)
            if len(self.progress_log) > 200:
                self.progress_log = self.progress_log[-200:]

    def start_load(self, refresh: Optional[bool] = None) -> None:
        if refresh is None:
            refresh = self.config.refresh_on_start
        with self.lock:
            if self.refreshing:
                return
            self.refreshing = True
            self.progress_log = []
        thread = threading.Thread(
            target=self._run_load,
            args=(refresh,),
            daemon=True,
            name="quota-check-load",
        )
        thread.start()

    def _run_load(self, refresh: bool) -> None:
        try:
            report = build_report(self.config, refresh=refresh, on_progress=self.set_progress)
            with self.lock:
                self.report = report
                self.refreshed_at = datetime.now().astimezone().isoformat(timespec="seconds")
                self.codex_path = str(find_codex_executable() or "")
        except Exception as exc:  # 发现失败时保留已有界面，不让窗口直接退出
            self.set_progress(f"加载失败: {exc}")
        finally:
            with self.lock:
                self.refreshing = False

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "config": self.config.to_dict(),
                "report": self.report.to_dict() if self.report else None,
                "refreshed_at": self.refreshed_at,
                "refreshing": self.refreshing,
                "progress_log": list(self.progress_log),
                "codex_path": self.codex_path,
                "version": __version__,
            }


def _make_handler(state: QuotaState) -> type[BaseHTTPRequestHandler]:
    web_root = _web_dir()

    class Handler(BaseHTTPRequestHandler):
        server_version = "QuotaSelfCheck/" + __version__

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(
            self,
            body: bytes,
            content_type: str,
            filename: Optional[str] = None,
        ) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if filename:
                safe_name = filename.encode("ascii", "ignore").decode("ascii") or "download"
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{safe_name}"',
                )
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in (
                "application/javascript",
                "application/json",
            ):
                content_type += "; charset=utf-8"
            self._send_bytes(path.read_bytes(), content_type)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/state":
                self._send_json(state.to_dict())
                return
            if path == "/api/export":
                query = parse_qs(parsed.query)
                fmt = (query.get("format") or ["csv"])[0]
                self._handle_export(fmt)
                return
            if path == "/api/open-auth":
                query = parse_qs(parsed.query)
                code_home = (query.get("code_home") or [""])[0]
                ok, error = open_auth_file(code_home)
                self._send_json({"ok": ok, "error": error})
                return
            if path == "/" or path == "":
                self._send_file(web_root / "index.html")
                return
            if path.startswith("/static/"):
                relative = path[len("/static/"):]
                target = (web_root / relative).resolve()
                if not str(target).startswith(str(web_root.resolve())):
                    self.send_error(403)
                    return
                self._send_file(target)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json({"error": "invalid JSON"}, 400)
                return

            if parsed.path == "/api/refresh":
                state.start_load(refresh=True)
                self._send_json({"started": True})
                return
            if parsed.path == "/api/config":
                merged = {**state.config.to_dict(), **payload}
                state.config = AppConfig.from_dict(merged)
                save_config(state.config)
                state.start_load(refresh=False)
                self._send_json(state.config.to_dict())
                return
            self.send_error(404)

        def _handle_export(self, fmt: str) -> None:
            report = state.report
            if report is None:
                self.send_error(409, "report not ready")
                return
            rows = build_rows(report)
            if fmt == "xlsx":
                self._send_bytes(
                    export_xlsx_bytes(rows),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "QuotaSelfCheck.xlsx",
                )
            elif fmt == "json":
                self._send_bytes(
                    export_json_bytes(report),
                    "application/json; charset=utf-8",
                    "QuotaSelfCheck.json",
                )
            else:
                self._send_bytes(
                    export_csv_bytes(rows),
                    "text/csv; charset=utf-8",
                    "QuotaSelfCheck.csv",
                )

    return Handler
def open_auth_file(code_home: str) -> tuple[bool, str]:
    if not code_home:
        return False, "code_home is required"
    path = Path(code_home).expanduser() / "auth.json"
    if not path.is_file():
        return False, f"auth.json not found: {path}"
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        return False, str(exc)
    return True, ""

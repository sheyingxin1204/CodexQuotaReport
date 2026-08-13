from __future__ import annotations

import json
import mimetypes
import os
import importlib.util
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib import request as url_request
from urllib.parse import parse_qs, urlparse

from . import __version__
from .auth import read_auth_info
from .config import AppConfig, save_config
from .export import export_csv_bytes, export_json_bytes, export_xlsx_bytes, build_rows
from .refresh import find_codex_executable, refresh_account
from .report import ReportResult, build_report
from .sessions import load_account_snapshot


UPDATE_REPO = "sheyingxin1204/QuotaSelfCheck"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"


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
        self.refreshing_accounts: set[str] = set()
        self.account_refresh_results: dict[str, dict[str, Any]] = {}
        self.progress_log: list[str] = []
        self.lock = threading.Lock()
        self.notify_handler: Optional[Any] = None
        self.codex_path = str(find_codex_executable() or "")
        self.latest_version: Optional[str] = None
        self.latest_release_url: Optional[str] = None
        self.update_available = False
        self.update_error: Optional[str] = None

    def set_notification_handler(self, handler: Any) -> None:
        self.notify_handler = handler

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
        self._maybe_notify_low_quota()

    def refresh_one(self, code_home: str) -> bool:
        key = os.path.normcase(str(Path(code_home).expanduser()))
        with self.lock:
            if self.refreshing or key in self.refreshing_accounts:
                return False
            if self.report is None:
                return False
            if not any(
                os.path.normcase(str(c.code_home)) == key
                for c in self.report.candidates
            ):
                return False
            self.refreshing_accounts.add(key)
            self.set_progress(f"正在单独刷新 {Path(code_home).name}")
        thread = threading.Thread(
            target=self._run_refresh_one,
            args=(key,),
            daemon=True,
            name="quota-check-refresh-one",
        )
        thread.start()
        return True

    def _run_refresh_one(self, key: str) -> None:
        try:
            with self.lock:
                if self.report is None:
                    return
                candidate = next(
                    (c for c in self.report.candidates if os.path.normcase(str(c.code_home)) == key),
                    None,
                )
            if candidate is None:
                return
            result = refresh_account(candidate.code_home, self.config.refresh_timeout_seconds)
            auth_info = read_auth_info(candidate.code_home)
            snapshot = load_account_snapshot(
                candidate.code_home,
                candidate.label,
                candidate.discovered_from,
                auth_info,
                self.config,
            )
            snapshot.refreshed = result.ok
            snapshot.refresh_message = result.message
            if not result.ok:
                snapshot.error = (snapshot.error or "") + " | " + result.message
                snapshot.status = "error"
            with self.lock:
                if self.report is not None:
                    for index, existing in enumerate(self.report.snapshots):
                        if os.path.normcase(str(existing.code_home)) == key:
                            self.report.snapshots[index] = snapshot
                            break
                self.refreshed_at = datetime.now().astimezone().isoformat(timespec="seconds")
                self.account_refresh_results[key] = result.to_dict()
                self.set_progress(f"{candidate.label} 刷新完成: {result.message}")
        except Exception as exc:
            self.set_progress(f"单账号刷新失败: {exc}")
        finally:
            with self.lock:
                self.refreshing_accounts.discard(key)
        self._maybe_notify_low_quota()

    def start_update_check(self) -> None:
        if not self.config.check_updates:
            return
        thread = threading.Thread(
            target=self._run_update_check,
            daemon=True,
            name="quota-check-update",
        )
        thread.start()

    def _run_update_check(self) -> None:
        try:
            request = url_request.Request(
                UPDATE_API,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "QuotaSelfCheck"},
            )
            with url_request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            tag = str(payload.get("tag_name") or "").lstrip("v")
            html_url = str(payload.get("html_url") or "")
            current = tuple(int(part) for part in __version__.split(".") if part.isdigit())
            latest = tuple(int(part) for part in tag.split(".") if part.isdigit())
            with self.lock:
                self.latest_version = tag or None
                self.latest_release_url = html_url or None
                self.update_available = bool(tag and latest > current)
                self.update_error = None
        except Exception as exc:
            with self.lock:
                self.update_error = str(exc)

    def _maybe_notify_low_quota(self) -> None:
        if not self.config.notify_low_quota or self.notify_handler is None:
            return
        with self.lock:
            report = self.report
        if report is None:
            return
        threshold = float(self.config.low_quota_threshold)
        low: list[str] = []
        for snapshot in report.snapshots:
            values = [
                limit.remaining_percent
                for limit in snapshot.all_limits()
                if limit.remaining_percent is not None
            ]
            if values and min(values) <= threshold:
                low.append(f"{snapshot.label}（{(snapshot.email or '未登录')}）")
        if low:
            title = "自检额度提醒"
            message = "以下账号额度偏低：" + "、".join(low[:3])
            if len(low) > 3:
                message += f" 等 {len(low)} 个"
            self.notify_handler(title, message)

    def diagnostics(self) -> dict[str, Any]:
        with self.lock:
            webview_available = importlib.util.find_spec("webview") is not None
            return {
                "app_version": __version__,
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
                "os_name": os.name,
                "codex_path": self.codex_path,
                "webview_available": webview_available,
                "config": self.config.to_dict(),
                "candidates": [candidate.to_dict() for candidate in self.report.candidates] if self.report else [],
                "accounts": [snapshot.to_dict() for snapshot in self.report.snapshots] if self.report else [],
                "refresh_results": [result.to_dict() for result in self.report.refresh_results] if self.report else [],
                "account_refresh_results": dict(self.account_refresh_results),
                "refreshed_at": self.refreshed_at,
                "update_available": self.update_available,
                "latest_version": self.latest_version,
                "latest_release_url": self.latest_release_url,
                "update_error": self.update_error,
                "progress_log": list(self.progress_log),
            }

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "config": self.config.to_dict(),
                "report": self.report.to_dict() if self.report else None,
                "refreshed_at": self.refreshed_at,
                "refreshing": self.refreshing,
                "progress_log": list(self.progress_log),
                "codex_path": self.codex_path,
                "refreshing_accounts": sorted(self.refreshing_accounts),
                "update_available": self.update_available,
                "latest_version": self.latest_version,
                "latest_release_url": self.latest_release_url,
                "update_error": self.update_error,
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
            if path == "/api/diagnostics":
                self._send_json(state.diagnostics())
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
            if parsed.path == "/api/refresh-account":
                code_home = str(payload.get("code_home") or "")
                started = state.refresh_one(code_home) if code_home else False
                self._send_json({"started": started})
                return
            if parsed.path == "/api/open-output":
                ok, error = open_directory(state.config.output_dir)
                self._send_json({"ok": ok, "error": error})
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


def open_directory(path_text: str) -> tuple[bool, str]:
    path = Path(path_text or "").expanduser()
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, str(exc)
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

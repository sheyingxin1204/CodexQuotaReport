from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class RefreshResult:
    code_home: Path
    ok: bool
    message: str
    exit_code: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    exhausted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_home": str(self.code_home),
            "ok": self.ok,
            "message": self.message,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed_seconds,
            "exhausted": self.exhausted,
        }


def _detect_usage_limit(output: str) -> bool:
    return re.search(
        r"hit your usage limit|usage limit reached|rate limit reached",
        output,
        re.IGNORECASE,
    ) is not None


def find_codex_executable() -> Optional[Path]:
    names = ["codex.cmd", "codex.exe", "codex"]
    if os.name != "nt":
        names = ["codex"]
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            for name in ("codex.cmd", "codex"):
                candidate = Path(appdata) / "npm" / name
                if candidate.exists():
                    return candidate
    return None


def _command_for(exe: Path, args: list[str]) -> list[str]:
    suffix = exe.suffix.lower()
    if os.name == "nt" and suffix in (".cmd", ".ps1"):
        node_command = _node_script_command(exe, args)
        if node_command:
            return node_command
    if os.name == "nt" and suffix == ".cmd":
        comspec = os.environ.get("ComSpec") or "cmd.exe"
        return [comspec, "/d", "/s", "/c", f'"{exe}" {subprocess.list2cmdline(args)}']
    if os.name == "nt" and suffix == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(exe), *args]
    return [str(exe), *args]


def _node_script_command(exe: Path, args: list[str]) -> Optional[list[str]]:
    try:
        text = exe.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"node_modules[\\/]([^\"\r\n]+?\.js)", text, re.IGNORECASE)
    if not match:
        return None
    script = exe.parent / "node_modules" / match.group(1)
    if not script.exists():
        return None
    node = shutil.which("node") or str(exe.parent / "node.exe")
    return [node, str(script), *args]


def latest_session_mtime(code_home: Path) -> float:
    sessions_root = code_home / "sessions"
    if not sessions_root.is_dir():
        return 0.0
    newest = 0.0
    try:
        for path in sessions_root.rglob("*.jsonl"):
            newest = max(newest, path.stat().st_mtime)
    except OSError:
        pass
    return newest


def refresh_account(code_home: Path, timeout_seconds: int = 60) -> RefreshResult:
    exe = find_codex_executable()
    if exe is None:
        return RefreshResult(
            code_home=code_home,
            ok=False,
            message="codex CLI not found on PATH",
        )

    workdir = Path(tempfile.mkdtemp(prefix="quota-check-refresh-"))
    env = os.environ.copy()
    env["CODEX_HOME"] = str(code_home)
    args = ["exec", "--skip-git-repo-check", "--ignore-user-config", "--json", "/status"]
    command = _command_for(exe, args)
    before_mtime = latest_session_mtime(code_home)

    import time

    started = time.monotonic()
    process: Optional[subprocess.Popen[bytes]] = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        assert process.stdout is not None
        output = process.communicate(timeout=timeout_seconds)[0].decode("utf-8", errors="replace")
        exit_code = process.returncode
        elapsed = time.monotonic() - started
    except subprocess.TimeoutExpired:
        if process is not None:
            _kill_process_tree(process)
        elapsed = time.monotonic() - started
        return RefreshResult(
            code_home=code_home,
            ok=False,
            message=f"codex status refresh timed out after {int(elapsed)}s",
            exit_code=None,
            elapsed_seconds=round(elapsed, 2),
        )
    except OSError as exc:
        elapsed = time.monotonic() - started
        return RefreshResult(
            code_home=code_home,
            ok=False,
            message=f"failed to launch codex: {exc}",
            elapsed_seconds=round(elapsed, 2),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    after_mtime = latest_session_mtime(code_home)
    wrote_event = after_mtime > before_mtime
    usage_limit_hit = _detect_usage_limit(output)
    ok = exit_code == 0 or wrote_event or usage_limit_hit
    summary = output.strip().splitlines()
    tail = " | ".join(summary[-3:])[:500] if summary else ""
    if usage_limit_hit:
        message = "usage limit reached (0% remaining)"
    else:
        message = "rate limit event refreshed" if wrote_event else tail or "no new event written"
    return RefreshResult(
        code_home=code_home,
        ok=ok,
        message=message,
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 2),
        exhausted=usage_limit_hit,
    )


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            process.kill()
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass

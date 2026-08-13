from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any, Optional


def _get(obj: Any, *names: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return None


def decode_jwt_payload(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    parts = str(token).split(".")
    if len(parts) < 2:
        return None
    payload_text = parts[1].replace("-", "+").replace("_", "/")
    payload_text += "=" * (-len(payload_text) % 4)
    try:
        raw = base64.b64decode(payload_text, validate=False)
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (binascii.Error, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def read_auth_info(code_home: Path) -> dict[str, Any]:
    auth_path = code_home / "auth.json"
    info: dict[str, Any] = {
        "email": None,
        "plan_type": None,
        "auth_mode": None,
        "account_id": None,
        "api_key": False,
    }
    if not auth_path.exists():
        return info

    data = _load_json(auth_path)
    if not isinstance(data, dict):
        return info
    info["api_key"] = bool(_get(data, "OPENAI_API_KEY"))

    tokens = data.get("tokens")
    if isinstance(tokens, str):
        tokens = {"access_token": tokens}
    if not isinstance(tokens, dict):
        tokens = {}

    for key in ("access_token", "id_token"):
        payload = decode_jwt_payload(tokens.get(key))
        if not payload:
            continue
        profile = _get(payload, "https://api.openai.com/profile")
        auth_section = _get(payload, "https://api.openai.com/auth")
        if not info["email"]:
            info["email"] = _get(profile, "email") or _get(payload, "email")
        if not info["plan_type"]:
            info["plan_type"] = _get(auth_section, "chatgpt_plan_type") or _get(
                payload, "chatgpt_plan_type", "plan_type"
            )
        if not info["account_id"]:
            info["account_id"] = _get(auth_section, "chatgpt_account_id") or _get(
                payload, "chatgpt_account_id"
            )

    info["auth_mode"] = _get(data, "auth_mode")
    if not info["auth_mode"]:
        if _get(data, "OPENAI_API_KEY"):
            info["auth_mode"] = "api_key"
        elif tokens:
            info["auth_mode"] = "chatgpt"
    if not info["email"] and info["auth_mode"] == "api_key":
        info["email"] = "OPENAI API Key"
    return info


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None

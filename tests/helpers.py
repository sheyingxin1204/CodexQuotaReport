from __future__ import annotations

import base64
import json
from typing import Any


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    return ".".join([b64url(json.dumps(header).encode("utf-8")), b64url(json.dumps(payload).encode("utf-8")), "sig"])

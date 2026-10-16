"""Allekirjoitetut linkit. Vain salaisuuden haltija voi tehdä kelvollisen linkin."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{_b64e(raw)}.{_b64e(digest)}"


def verify(token: str, secret: str) -> dict | None:
    if not token or "." not in token or not secret:
        return None
    raw_b64, sig_b64 = token.split(".", 1)
    try:
        raw = _b64d(raw_b64)
        signature = _b64d(sig_b64)
    except Exception:
        return None
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(datetime.now(timezone.utc).timestamp()):
                return None
        except (TypeError, ValueError):
            return None
    return payload


def owner_token(secret: str) -> str:
    return sign({"role": "owner"}, secret)


def vote_token(secret: str, event_id: str, vote: str, days: int = 40) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
    return sign({"e": event_id, "exp": exp, "role": "vote", "v": vote}, secret)


def click_token(secret: str, event_id: str, target: str, days: int = 40) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
    return sign({"e": event_id, "exp": exp, "role": "click", "to": target}, secret)

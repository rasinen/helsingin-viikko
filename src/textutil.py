"""Tekstin siivous."""

from __future__ import annotations

import re
from html import unescape

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def plain(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("fi", "en", "sv"):
            if value.get(key):
                return plain(value[key])
        return ""
    text = _TAG.sub(" ", str(value))
    text = unescape(text).replace("\xa0", " ")
    return _WS.sub(" ", text).strip()


def clip(text: str, limit: int = 200) -> str:
    text = plain(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,;") + "…"


def norm(text: str) -> str:
    text = plain(text).lower().replace("–", "-").replace("—", "-")
    return _WS.sub(" ", text).strip()

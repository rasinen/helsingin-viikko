"""Palautteiden haku ja oppimistilan tallennus välittäjään."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class FeedbackError(RuntimeError):
    pass


def _request(url: str, secret: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {secret}",
        "Accept": "application/json",
        "User-Agent": "HelsinginViikko/1.0",
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:240]
        raise FeedbackError(f"Palautepalvelu vastasi {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise FeedbackError(f"Palautepalveluun ei saatu yhteyttä: {error.reason}") from error


def fetch_bundle(worker_url: str, admin_secret: str) -> dict:
    base = worker_url.rstrip("/")
    payload = _request(f"{base}/admin/bundle", admin_secret)
    payload.setdefault("votes", [])
    payload.setdefault("weights", {})
    payload.setdefault("labels", {})
    payload.setdefault("weeks", {})
    return payload


def save_bundle(worker_url: str, admin_secret: str, bundle: dict) -> dict:
    base = worker_url.rstrip("/")
    return _request(f"{base}/admin/bundle", admin_secret, method="PUT", body=bundle)

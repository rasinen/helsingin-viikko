"""Luo tai päivitä palautteiden tallennuspaikan. Ei tulosta salaisuuksia."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAME = "helsingin-viikko"
API = "https://api.cloudflare.com/client/v4"


def derive_secrets(password: str) -> tuple[str, str]:
    feedback = hmac.new(password.encode(), b"helsingin-viikko-feedback-v1", hashlib.sha256).hexdigest()
    admin = hmac.new(password.encode(), b"helsingin-viikko-admin-v1", hashlib.sha256).hexdigest()
    return feedback, admin


def build_script_body(script: bytes, namespace_id: str) -> tuple[bytes, str]:
    metadata = json.dumps(
        {
            "main_module": "index.js",
            "compatibility_date": "2026-10-01",
            "bindings": [{"type": "kv_namespace", "name": "DATA", "namespace_id": namespace_id}],
        }
    ).encode()
    boundary = "----Helsinki" + uuid.uuid4().hex
    chunks = [
        _part(boundary, "metadata", metadata, "application/json", "metadata.json"),
        _part(boundary, "index.js", script, "application/javascript+module", "index.js"),
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


def _part(boundary: str, name: str, content: bytes, content_type: str, filename: str) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    )
    return header.encode() + content + b"\r\n"


def _redact(text: str) -> str:
    for key in ("CLOUDFLARE_API_TOKEN", "SMTP_PASSWORD", "FEEDBACK_SECRET", "ADMIN_SECRET"):
        value = os.environ.get(key) or ""
        if value:
            text = text.replace(value, "***")
    return text[:400]


def _api(token: str, method: str, path: str, body: dict | None = None, raw: bytes | None = None, headers: dict | None = None) -> dict:
    hdrs = {"Authorization": f"Bearer {token}", "User-Agent": "HelsinginViikko/1.0"}
    payload = raw
    if body is not None:
        payload = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    request = urllib.request.Request(API + path, data=payload, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as error:
        detail = _redact(error.read().decode("utf-8", "replace"))
        raise SystemExit(f"Cloudflare vastasi {error.code}. {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Cloudflareen ei saatu yhteyttä: {error.reason}") from error


def _result(payload: dict):
    if not payload.get("success"):
        errors = payload.get("errors") or []
        message = errors[0].get("message") if errors else "pyyntö epäonnistui"
        raise SystemExit(f"Cloudflare: {_redact(str(message))}")
    return payload.get("result")


def account_id(token: str) -> str:
    chosen = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
    if chosen:
        return chosen
    result = _result(_api(token, "GET", "/accounts?per_page=20")) or []
    if not result:
        raise SystemExit("Cloudflare-tiliä ei löytynyt. Tarkista, että avain on luotu ja tili on valittu.")
    return result[0]["id"]


def workers_subdomain(token: str, account: str) -> str:
    try:
        result = _result(_api(token, "GET", f"/accounts/{account}/workers/subdomain"))
    except SystemExit as error:
        text = str(error).lower()
        if "404" not in text and "10007" not in text and "not found" not in text:
            raise
        result = None
    if isinstance(result, dict) and result.get("subdomain"):
        return result["subdomain"]
    for name in ("rasinen-viikko", "rasinen-helsinki", "lauri-viikko"):
        try:
            created = _result(_api(token, "PUT", f"/accounts/{account}/workers/subdomain", {"subdomain": name}))
        except SystemExit:
            continue
        if isinstance(created, dict) and created.get("subdomain"):
            return created["subdomain"]
        return name
    raise SystemExit("Cloudflareen ei saatu osoitetta. Avaa Cloudflare ja hyväksy ilmainen workers-osoite.")


def kv_id(token: str, account: str) -> str:
    listed = _result(_api(token, "GET", f"/accounts/{account}/storage/kv/namespaces?per_page=100")) or []
    for item in listed:
        if item.get("title") == SCRIPT_NAME:
            return item["id"]
    created = _result(_api(token, "POST", f"/accounts/{account}/storage/kv/namespaces", {"title": SCRIPT_NAME}))
    return created["id"]


def upload_script(token: str, account: str, namespace_id: str) -> None:
    script = (ROOT / "worker" / "src" / "index.js").read_bytes()
    body, boundary = build_script_body(script, namespace_id)
    _api(
        token,
        "PUT",
        f"/accounts/{account}/workers/scripts/{SCRIPT_NAME}",
        raw=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def put_secret(token: str, account: str, name: str, text: str) -> None:
    _api(
        token,
        "PUT",
        f"/accounts/{account}/workers/scripts/{SCRIPT_NAME}/secrets",
        {"name": name, "text": text, "type": "secret_text"},
    )


def enable_subdomain(token: str, account: str) -> None:
    _api(
        token,
        "POST",
        f"/accounts/{account}/workers/scripts/{SCRIPT_NAME}/subdomain",
        {"enabled": True, "previews_enabled": False},
    )


def publish_env(url: str, feedback: str, admin: str) -> None:
    for value in (feedback, admin):
        print(f"::add-mask::{value}")
    path = os.environ.get("GITHUB_ENV")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"WORKER_URL={url}\n")
        handle.write(f"FEEDBACK_SECRET={feedback}\n")
        handle.write(f"ADMIN_SECRET={admin}\n")


def main() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN") or ""
    password = os.environ.get("SMTP_PASSWORD") or ""
    if not token:
        print("Palautteiden tallennusta ei kytketty, koska CLOUDFLARE_API_TOKEN puuttuu.")
        return
    if not password:
        raise SystemExit("Gmail-salaisuus puuttuu, joten palautteiden avainta ei voi tehdä.")
    feedback, admin = derive_secrets(password)
    account = account_id(token)
    subdomain = workers_subdomain(token, account)
    namespace = kv_id(token, account)
    upload_script(token, account, namespace)
    put_secret(token, account, "FEEDBACK_SECRET", feedback)
    put_secret(token, account, "ADMIN_SECRET", admin)
    enable_subdomain(token, account)
    url = f"https://{SCRIPT_NAME}.{subdomain}.workers.dev"
    publish_env(url, feedback, admin)
    print(f"Palautteet käytössä: {url}")


if __name__ == "__main__":
    main()

"""Julkisen sivun tiedostot. Ei pisteitä, ei ääniä, ei salaisuuksia."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

FORBIDDEN_KEYS = {
    "scores",
    "reasons",
    "weights",
    "votes",
    "token",
    "feedback_secret",
    "admin_secret",
    "smtp_password",
    "password",
}


def assert_public_safe(payload) -> None:
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_KEYS:
                    raise RuntimeError(f"Julkiseen dataan päätyi kielletty kenttä: {key}")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for needle in ("smtp_password", "feedback_secret", "admin_secret", "gmail.com"):
        if needle in blob:
            raise RuntimeError("Julkisessa datassa on arkaluonteinen merkkijono")


def write_site(root: Path, public: dict, preview_personal: dict | None = None) -> None:
    site = root / "site"
    web = root / "web"
    data = site / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js", "favicon.svg"):
        source = web / name
        if source.exists():
            shutil.copyfile(source, site / name)
    week_id = public["week"]["start"]
    assert_public_safe(public)
    _write_json(data / f"{week_id}.json", public)
    weeks = []
    index_path = data / "weeks.json"
    if index_path.exists():
        try:
            weeks = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            weeks = []
    weeks = [row for row in weeks if row.get("id") != week_id]
    weeks.append(
        {
            "id": week_id,
            "label": public["week"]["label"],
            "end": public["week"]["end"],
        }
    )
    weeks.sort(key=lambda row: row["id"], reverse=True)
    assert_public_safe(weeks)
    _write_json(index_path, weeks)
    preview_path = site / "personal.preview.json"
    if preview_personal is not None:
        _write_json(preview_path, preview_personal)
    elif preview_path.exists():
        preview_path.unlink()


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

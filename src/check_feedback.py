"""Tarkistaa, että peukku tallentuu ja muuttaa pisteitä. Tyhjentää kokeilun lopuksi."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .deploy_worker import derive_secrets
from .model import learning_active, rebuild_weights, score_event
from .tokens import owner_token, vote_token

WORKER = "https://helsingin-viikko.rasinen-viikko.workers.dev"
DATA = "https://rasinen.github.io/helsingin-viikko/data/2026-10-19.json"


def _json(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None, raw: bytes | None = None) -> tuple[int, str]:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"User-Agent": "HelsinginViikko/1.0"}
    if headers:
        hdrs.update(headers)
    request = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.status, response.read().decode("utf-8")


def main() -> None:
    password = os.environ.get("SMTP_PASSWORD") or ""
    if not password:
        raise SystemExit("Gmail-salaisuus puuttuu, tarkistusta ei voi tehdä.")
    feedback, admin = derive_secrets(password)
    with urllib.request.urlopen(DATA, timeout=40) as response:
        events = json.loads(response.read().decode("utf-8"))["events"]
    music = [event for event in events if any(item.startswith("k:musiikki") for item in event.get("features") or [])]
    other = [
        event
        for event in events
        if event.get("features")
        and not any(item.startswith(("k:musiikki", "k:konsertti", "k:teatteri")) for item in event["features"])
    ]
    if len(music) < 11 or not other:
        raise SystemExit("Tarkistukseen ei löytynyt tarpeeksi erilaisia tapahtumia.")
    liked = music[:10]
    held = music[10]
    plain = other[0]
    owner = owner_token(feedback)
    try:
        token = vote_token(feedback, liked[0]["id"], "up")
        status, page = _json(f"{WORKER}/v?k={urllib.parse.quote(token)}")
        if status != 200 or "Tallenna" not in page or "Kiitos, palaute tallennettiin" in page:
            raise SystemExit("Sähköpostin peukkulinkki ei näytä vahvistusta.")
        status, saved = _json(
            f"{WORKER}/v",
            "POST",
            raw=urllib.parse.urlencode({"k": token}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status != 200 or "Kiitos" not in saved:
            raise SystemExit("Peukun vahvistus ei tallentunut.")
        for event in liked[1:]:
            _json(
                f"{WORKER}/v",
                "POST",
                {"k": owner, "e": event["id"], "vote": "up", "features": event["features"], "label": event["name"][:80]},
                {"Content-Type": "application/json"},
            )
        _status, raw = _json(f"{WORKER}/admin/bundle", headers={"Authorization": f"Bearer {admin}"})
        bundle = json.loads(raw)
        votes = bundle.get("votes") or []
        if len(votes) < 10:
            raise SystemExit(f"Peukkuja tallessa vain {len(votes)}.")
        # Ensimmäinen ääni tuli linkistä ilman piirteitä. Liitetään ne, kuten viikkoajo tekee.
        for vote in votes:
            if vote.get("event_id") == liked[0]["id"] and not vote.get("features"):
                vote["features"] = liked[0]["features"]
        now = datetime.now(timezone.utc)
        before = score_event(held, {}, None)
        after = score_event(held, rebuild_weights(votes, now), None)
        plain_after = score_event(plain, rebuild_weights(votes, now), None)
        if not learning_active(votes) or after <= before or plain_after >= after:
            raise SystemExit(f"Pisteet eivät muuttuneet odotetusti: musiikki {before}->{after}, muu {plain_after}.")
        print(f"Peukku tallentui. Musiikki {before} -> {after}. Muu tapahtuma jäi {plain_after}.")
    finally:
        _json(f"{WORKER}/reset", "POST", {"k": owner}, {"Content-Type": "application/json"})
        _status, raw = _json(f"{WORKER}/admin/bundle", headers={"Authorization": f"Bearer {admin}"})
        left = len(json.loads(raw).get("votes") or [])
        if left:
            raise SystemExit(f"Kokeilu ei tyhjentynyt, ääniä jäljellä {left}.")
        print("Kokeilu tyhjennettiin. Omat peukut alkavat nollasta.")


if __name__ == "__main__":
    main()

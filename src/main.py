"""Komentorivi: python -m src.main [build|send|run] [--dry-run]"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .emailer import send_email
from .pipeline import PipelineError, build_bundle

ROOT = Path(__file__).resolve().parents[1]


def _send() -> None:
    path = ROOT / "private" / "mail.json"
    if not path.exists():
        raise SystemExit("Sähköpostia ei voi lähettää, koska viikkokoostetta ei ole vielä tehty.")
    mail = json.loads(path.read_text(encoding="utf-8"))
    user = os.environ.get("SMTP_USER") or ""
    password = os.environ.get("SMTP_PASSWORD") or ""
    recipient = os.environ.get("EMAIL_TO") or ""
    missing = [
        name
        for name, value in (("SMTP_USER", user), ("SMTP_PASSWORD", password), ("EMAIL_TO", recipient))
        if not value
    ]
    if missing:
        raise SystemExit(
            "Sähköpostia ei lähetetty, koska nämä salaisuudet puuttuvat: "
            + ", ".join(missing)
            + ". Ohje on README-tiedostossa. Salasanaa ei saa kirjoittaa keskusteluun eikä koodiin."
        )
    send_email(mail, user, password, recipient)
    print("Sähköposti lähetetty.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Helsingin viikko")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "build", "send"])
    parser.add_argument("--dry-run", action="store_true", help="Tee sivu ja sähköpostin esikatselu, älä lähetä mitään.")
    args = parser.parse_args(argv)
    try:
        if args.command == "send":
            _send()
            return
        summary = build_bundle(ROOT, dry_run=args.dry_run)
        print(
            f"Viikko {summary['week']['label']}: {summary['event_count']} tapahtumaa. "
            f"Sää: {summary['weather_source'] or 'puuttuu'}."
        )
        for warning in summary["warnings"]:
            print("Huomio:", warning)
        if args.dry_run or args.command == "build":
            print("Esikatselu tehty. Sähköpostia ei lähetetty.")
            return
        _send()
    except PipelineError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()

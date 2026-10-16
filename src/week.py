"""Viikon rajat: aina seuraava maanantai–sunnuntai, Europe/Helsinki."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HELSINKI = ZoneInfo("Europe/Helsinki")

WEEKDAYS_FI = [
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
]
WEEKDAYS_SHORT = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def today_helsinki(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(HELSINKI)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=HELSINKI)
    else:
        now = now.astimezone(HELSINKI)
    return now.date()


def next_week_bounds(today: date) -> tuple[date, date]:
    """Seuraava maanantai ja sitä seuraava sunnuntai.

    Jos tänään on maanantai, otetaan ensi viikon maanantai, ei alkanutta viikkoa.
    """
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    start = today + timedelta(days=days_ahead)
    end = start + timedelta(days=6)
    return start, end


def week_label(start: date, end: date) -> str:
    return f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.')}"


def week_dates(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days

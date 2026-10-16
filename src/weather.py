"""Sääennuste Helsinkiin. Ensisijaisesti Open-Meteo, varalla Norjan meteorologinen laitos."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

from .week import HELSINKI, WEEKDAYS_SHORT

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
MET_NO = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
LAT = 60.1699
LON = 24.9384
USER_AGENT = "HelsinginViikko/1.0 https://github.com/rasinen/helsingin-viikko"

WMO_FI = {
    0: "Selkeää",
    1: "Enimmäkseen selkeää",
    2: "Puolipilvistä",
    3: "Pilvistä",
    45: "Sumua",
    48: "Sumua",
    51: "Heikkoa tihkua",
    53: "Tihkua",
    55: "Tiheää tihkua",
    56: "Jäätävää tihkua",
    57: "Jäätävää tihkua",
    61: "Heikkoa sadetta",
    63: "Sadetta",
    65: "Voimakasta sadetta",
    66: "Jäätävää sadetta",
    67: "Jäätävää sadetta",
    71: "Heikkoa lumisadetta",
    73: "Lumisadetta",
    75: "Runsasta lumisadetta",
    77: "Lumijyväsiä",
    80: "Sadekuuroja",
    81: "Sadekuuroja",
    82: "Voimakkaita sadekuuroja",
    85: "Lumikuuroja",
    86: "Lumikuuroja",
    95: "Ukkosta",
    96: "Ukkosta ja rakeita",
    99: "Ukkosta ja rakeita",
}


def describe_wmo(code: int | None) -> str:
    if code is None:
        return "Sääennuste"
    return WMO_FI.get(int(code), "Vaihtelevaa")


def describe_symbol(code: str | None) -> str:
    text = (code or "").lower()
    order = [
        ("thunder", "Ukkosta"),
        ("heavysnow", "Runsasta lumisadetta"),
        ("snow", "Lumisadetta"),
        ("sleet", "Räntää"),
        ("heavyrain", "Voimakasta sadetta"),
        ("lightrain", "Heikkoa sadetta"),
        ("rain", "Sadetta"),
        ("drizzle", "Tihkua"),
        ("fog", "Sumua"),
        ("clearsky", "Selkeää"),
        ("fair", "Enimmäkseen selkeää"),
        ("partlycloudy", "Puolipilvistä"),
        ("cloudy", "Pilvistä"),
    ]
    for needle, label in order:
        if needle in text:
            return label
    return "Vaihtelevaa"


def _get_json(url: str, timeout: int = 40) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Sääpyyntö epäonnistui ({error.code}): {body[:180]}") from error


def fetch_open_meteo(start, end) -> dict:
    query = urllib.parse.urlencode(
        {
            "latitude": LAT,
            "longitude": LON,
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "precipitation_sum",
                    "wind_speed_10m_max",
                ]
            ),
            "timezone": "Europe/Helsinki",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "wind_speed_unit": "ms",
        }
    )
    payload = _get_json(OPEN_METEO + "?" + query)
    if payload.get("error"):
        raise RuntimeError(payload.get("reason") or "Open-Meteo ei palauttanut ennustetta")
    daily = payload.get("daily") or {}
    days = []
    dates = daily.get("time") or []
    for index, iso in enumerate(dates):
        code = _at(daily.get("weather_code"), index)
        day = datetime.fromisoformat(iso).date()
        days.append(
            {
                "date": iso,
                "weekday": WEEKDAYS_SHORT[day.weekday()],
                "temp_max": _round( _at(daily.get("temperature_2m_max"), index), 0),
                "temp_min": _round(_at(daily.get("temperature_2m_min"), index), 0),
                "precip_prob": _round(_at(daily.get("precipitation_probability_max"), index), 0),
                "precip_mm": _round(_at(daily.get("precipitation_sum"), index), 1),
                "wind": _round(_at(daily.get("wind_speed_10m_max"), index), 1),
                "description": describe_wmo(code),
            }
        )
    if len(days) < 7:
        raise RuntimeError("Open-Meteo palautti vajaan viikon")
    return {"source": "open-meteo", "source_label": "Open-Meteo", "days": days[:7], "summary": summarize(days[:7])}


def fetch_metno(start, end) -> dict:
    url = MET_NO + "?" + urllib.parse.urlencode({"lat": LAT, "lon": LON})
    payload = _get_json(url)
    series = ((payload.get("properties") or {}).get("timeseries")) or []
    buckets = defaultdict(list)
    for row in series:
        moment = datetime.fromisoformat(row["time"].replace("Z", "+00:00")).astimezone(HELSINKI)
        if not (start <= moment.date() <= end):
            continue
        data = row.get("data") or {}
        instant = ((data.get("instant") or {}).get("details")) or {}
        hour = (data.get("next_1_hours") or data.get("next_6_hours") or {})
        details = hour.get("details") or {}
        summary = (hour.get("summary") or {}).get("symbol_code")
        buckets[moment.date().isoformat()].append(
            {
                "hour": moment.hour,
                "temp": instant.get("air_temperature"),
                "wind": instant.get("wind_speed"),
                "prob": details.get("probability_of_precipitation"),
                "mm": details.get("precipitation_amount"),
                "symbol": summary,
            }
        )
    days = []
    cursor = start
    while cursor <= end:
        rows = buckets.get(cursor.isoformat()) or []
        if not rows:
            raise RuntimeError(f"Varasäästä puuttuu päivä {cursor.isoformat()}")
        temps = [row["temp"] for row in rows if isinstance(row["temp"], (int, float))]
        winds = [row["wind"] for row in rows if isinstance(row["wind"], (int, float))]
        probs = [row["prob"] for row in rows if isinstance(row["prob"], (int, float))]
        mms = [row["mm"] for row in rows if isinstance(row["mm"], (int, float))]
        afternoon = [row for row in rows if 12 <= row["hour"] <= 17 and row.get("symbol")] or rows
        afternoon.sort(key=lambda row: (-(row["prob"] or 0), -(row["mm"] or 0), row["hour"]))
        symbol = afternoon[0].get("symbol") if afternoon else None
        mm_sum = sum(mms) if mms else 0
        if probs:
            prob = max(probs)
        else:
            prob = _estimate_prob(symbol, mm_sum)
        days.append(
            {
                "date": cursor.isoformat(),
                "weekday": WEEKDAYS_SHORT[cursor.weekday()],
                "temp_max": _round(max(temps) if temps else None, 0),
                "temp_min": _round(min(temps) if temps else None, 0),
                "precip_prob": _round(prob, 0),
                "precip_mm": _round(mm_sum, 1),
                "wind": _round(max(winds) if winds else None, 1),
                "description": describe_symbol(symbol),
            }
        )
        cursor = cursor.fromordinal(cursor.toordinal() + 1)
    return {
        "source": "met.no",
        "source_label": "Norjan meteorologinen laitos",
        "days": days,
        "summary": summarize(days),
    }


def fetch_weather(start, end) -> tuple[dict, list[str]]:
    warnings = []
    try:
        return fetch_open_meteo(start, end), warnings
    except Exception as error:
        warnings.append(
            "Open-Meteo ei vastannut (" + _short(error) + "). Sää haettiin varalähteestä."
        )
        weather = fetch_metno(start, end)
        weather["summary"] = weather["summary"] + " Ennuste on varalähteestä, koska Open-Meteo ei vastannut."
        return weather, warnings


def _estimate_prob(symbol: str | None, mm: float | None) -> int:
    text = (symbol or "").lower()
    wet = any(word in text for word in ("rain", "snow", "sleet", "thunder", "drizzle"))
    amount = mm or 0
    if wet and amount >= 1:
        return 70
    if wet or amount > 0:
        return 40
    return 10


def summarize(days: list[dict]) -> str:
    if not days:
        return "Sääennustetta ei saatu."
    highs = [day["temp_max"] for day in days if day.get("temp_max") is not None]
    lows = [day["temp_min"] for day in days if day.get("temp_min") is not None]
    wet = max(days, key=lambda day: day.get("precip_prob") or 0)
    wind = max(days, key=lambda day: day.get("wind") or 0)
    parts = []
    if highs and lows:
        parts.append(f"Päivisin noin {min(highs):.0f}–{max(highs):.0f} astetta, öisin {min(lows):.0f}–{max(lows):.0f}.")
    if (wet.get("precip_prob") or 0) >= 40:
        parts.append(
            f"Sateen mahdollisuus on suurin { _weekday_full(wet['date']) } ({int(wet['precip_prob'])} %)."
        )
    else:
        parts.append("Viikko näyttää melko kuivalta.")
    if wind.get("wind") is not None:
        parts.append(f"Tuuli yltyy korkeimmillaan noin {wind['wind']:.0f} metriin sekunnissa.")
    return " ".join(parts)


def _weekday_full(iso: str) -> str:
    names = ["maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina", "sunnuntaina"]
    return names[datetime.fromisoformat(iso).weekday()]


def _at(values, index):
    if not values or index >= len(values):
        return None
    return values[index]


def _round(value, digits):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if digits == 0:
        return int(round(number))
    return round(number, digits)


def _short(error: Exception) -> str:
    text = str(error).replace("\n", " ")
    return text[:160]

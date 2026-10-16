"""Helsingin tapahtumat Linked Events -rajapinnasta."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .textutil import clip, norm, plain
from .week import HELSINKI

API = "https://api.hel.fi/linkedevents/v1/event/"
DIVISION = "ocd-division/country:fi/kunta:helsinki"
USER_AGENT = "HelsinginViikko/1.0 https://github.com/rasinen/helsingin-viikko"
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _request_json(url: str, timeout: int = 60) -> dict:
    last_error = None
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as error:
            last_error = error
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Tapahtumien haku epäonnistui: {last_error}")


def fetch_events(start, end_exclusive) -> list[dict]:
    """Hakee kaikki sivut. end_exclusive on viikon sunnuntaita seuraava päivä."""
    params = {
        "start": start.isoformat(),
        "end": end_exclusive.isoformat(),
        "division": DIVISION,
        "page_size": "100",
        "sort": "start_time",
        "include": "location,keywords",
        "super_event_type": "none,umbrella",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    events = []
    while url:
        payload = _request_json(url)
        events.extend(payload.get("data") or [])
        url = (payload.get("meta") or {}).get("next")
    return events


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HELSINKI)
    return parsed.astimezone(HELSINKI)


def _numbers(value) -> list[float]:
    text = plain(value)
    found = []
    for match in _NUMBER.findall(text):
        try:
            found.append(float(match.replace(",", ".")))
        except ValueError:
            continue
    return found


def price_info(offers) -> tuple[bool, str, str]:
    offers = offers or []
    if not isinstance(offers, list):
        offers = []
    free_flags = []
    amounts = []
    texts = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        if offer.get("is_free") is True:
            free_flags.append(True)
        elif offer.get("is_free") is False:
            free_flags.append(False)
        amounts.extend(_numbers(offer.get("price")))
        texts.append(plain(offer.get("description")).lower())
        texts.append(plain(offer.get("price")).lower())
    blob = " ".join(texts)
    if any(free_flags) and not any(amount > 0 for amount in amounts):
        return True, "Ilmainen", "price:free"
    if any(word in blob for word in ("vapaa pääsy", "ilmainen", "maksuton", "0 €", "0€")) and not any(
        amount > 0 for amount in amounts
    ):
        return True, "Ilmainen", "price:free"
    positive = [amount for amount in amounts if amount > 0]
    if positive:
        highest = max(positive)
        if len(positive) == 1:
            label = _euro(positive[0])
        else:
            label = f"{_euro(min(positive))}–{_euro(highest)}"
        if highest < 15:
            feature = "price:low"
        elif highest <= 40:
            feature = "price:mid"
        else:
            feature = "price:high"
        return False, label, feature
    if any(flag is False for flag in free_flags) or "maksullinen" in blob:
        return False, "Maksullinen", "price:paid"
    return False, "", "price:unknown"


def _euro(amount: float) -> str:
    if abs(amount - round(amount)) < 0.05:
        return f"{int(round(amount))} €"
    return f"{amount:.2f}".replace(".", ",") + " €"


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 23:
        return "evening"
    return "night"


def _keyword_names(raw) -> list[str]:
    names = []
    for keyword in raw or []:
        if isinstance(keyword, dict):
            name = plain(keyword.get("name"))
        else:
            name = plain(keyword)
        if name and name not in names:
            names.append(name)
    return names


def _place(location) -> tuple[str, str, str]:
    if not isinstance(location, dict):
        return "", "", ""
    name = plain(location.get("name"))
    street = plain(location.get("street_address"))
    place_id = str(location.get("id") or "")
    return name, street, place_id


def _event_url(event: dict) -> str:
    info = event.get("info_url")
    if isinstance(info, dict):
        for key in ("fi", "en", "sv"):
            link = (info.get(key) or "").strip()
            if link.startswith("http"):
                return link
    elif isinstance(info, str) and info.startswith("http"):
        return info
    event_id = event.get("id") or ""
    return f"https://tapahtumat.hel.fi/fi/events/{event_id}"


def _features(keywords, place, organiser, price_feature, start: datetime, spanning: bool) -> tuple[list[str], dict]:
    features = []
    labels = {}
    for keyword in keywords:
        key = norm(keyword)
        if len(key) < 2:
            continue
        feature = "k:" + key
        if feature not in features:
            features.append(feature)
            labels[feature] = keyword.strip()
        if sum(1 for item in features if item.startswith("k:")) >= 12:
            break
    if place:
        feature = "p:" + norm(place)
        features.append(feature)
        labels[feature] = place
    if organiser:
        feature = "o:" + norm(organiser)
        features.append(feature)
        labels[feature] = organiser
    features.append(price_feature)
    if spanning:
        features.append("span:multi")
    else:
        features.append(f"wd:{start.weekday()}")
        features.append(f"tod:{_time_of_day(start.hour)}")
    return features, labels


def prepare_event(raw: dict, week_start, week_end, permanent_days: int) -> dict | None:
    """Muuttaa yhden API-tietueen siivotuksi tapahtumaksi tai hylkää sen."""
    name = plain((raw.get("name") or {}).get("fi") if isinstance(raw.get("name"), dict) else raw.get("name"))
    if not name:
        return None
    if raw.get("deleted"):
        return None
    status = raw.get("event_status") or ""
    if "Cancelled" in status:
        return None
    start = _parse_dt(raw.get("start_time"))
    end = _parse_dt(raw.get("end_time"))
    if start is None:
        return None
    if end is None or end < start:
        end = start
    duration_days = (end - start).total_seconds() / 86400.0
    if duration_days > permanent_days:
        return None
    if start.year < 2015:
        return None
    overlaps = end.date() >= week_start and start.date() <= week_end
    if not overlaps:
        return None
    end_date = end.date()
    if end.hour == 0 and end.minute == 0 and end_date > start.date():
        end_date = end_date - timedelta(days=1)
    calendar_days = (end_date - start.date()).days + 1
    spanning = calendar_days >= 2 and duration_days >= 0.75
    if spanning:
        day = None
    elif week_start <= start.date() <= week_end:
        day = start.date().isoformat()
    elif start.date() < week_start <= end.date():
        day = week_start.isoformat()
    else:
        return None
    keywords = _keyword_names(raw.get("keywords"))
    place, address, _place_id = _place(raw.get("location"))
    organiser = plain(raw.get("provider"))
    free, price_label, price_feature = price_info(raw.get("offers"))
    description = plain(raw.get("short_description")) or plain(raw.get("description"))
    features, feature_labels = _features(keywords, place, organiser, price_feature, start, spanning)
    return {
        "id": raw.get("id"),
        "name": name,
        "description": clip(description, 360),
        "summary": clip(description, 200),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "date": day,
        "time_label": start.strftime("%H.%M"),
        "end_time_label": end.strftime("%H.%M") if not spanning else "",
        "place": place,
        "address": address,
        "organiser": organiser,
        "free": free,
        "price_label": price_label,
        "price_feature": price_feature,
        "keywords": keywords[:12],
        "features": features,
        "feature_labels": feature_labels,
        "url": _event_url(raw),
        "spanning": spanning,
        "rescheduled": "Rescheduled" in status,
    }


def clean_events(raw_events: list[dict], week_start, week_end, config: dict | None = None) -> list[dict]:
    config = config or {}
    permanent_days = int(config.get("permanent_days_limit") or 150)
    cleaned = []
    seen_ids = set()
    seen_sig = set()
    for raw in raw_events:
        event = prepare_event(raw, week_start, week_end, permanent_days)
        if not event or not event.get("id"):
            continue
        if event["id"] in seen_ids:
            continue
        signature = (norm(event["name"]), norm(event.get("place") or ""), event["start"][:16])
        if signature in seen_sig:
            continue
        seen_ids.add(event["id"])
        seen_sig.add(signature)
        cleaned.append(event)
    cleaned.sort(key=lambda event: (event.get("start") or "", event["id"]))
    return cleaned

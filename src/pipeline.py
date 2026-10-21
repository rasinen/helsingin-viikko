"""Kokoaa viikon: tapahtumat, sää, oppi, sivu ja sähköposti."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .emailer import build_messages, weekday_title
from .events import clean_events, fetch_events
from .feedback_client import FeedbackError, fetch_bundle, save_bundle
from .model import (
    calibration_ids,
    collapse_votes,
    explicit_count,
    interest_ids,
    learned_summary,
    learning_active,
    rebuild_weights,
    score_event,
    select_recommended,
    topic_strength,
    unique_shows,
)
from .render import write_site
from .weather import fetch_weather
from .week import HELSINKI, next_week_bounds, today_helsinki, week_dates, week_label


class PipelineError(RuntimeError):
    pass


def load_config(root: Path) -> dict:
    return json.loads((root / "config.json").read_text(encoding="utf-8"))


def _catalog(root: Path, events: list[dict]) -> dict:
    catalog = {}
    data_dir = root / "site" / "data"
    if data_dir.exists():
        for path in data_dir.glob("*.json"):
            if path.name == "weeks.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for event in payload.get("events") or []:
                catalog[event.get("id")] = {
                    "features": event.get("features") or [],
                    "name": event.get("name") or "",
                }
    for event in events:
        catalog[event["id"]] = {
            "features": event.get("features") or [],
            "name": event.get("name") or "",
        }
    return catalog


def _enrich(votes: list[dict], catalog: dict) -> bool:
    changed = False
    for vote in votes:
        known = catalog.get(vote.get("event_id") or "")
        if not known:
            continue
        if not vote.get("features") and known.get("features"):
            vote["features"] = list(known["features"])
            changed = True
        if not vote.get("label") and known.get("name"):
            vote["label"] = known["name"]
            changed = True
    return changed


def _labels(events: list[dict], previous: dict | None) -> dict:
    labels = dict(previous or {})
    for event in events:
        labels.update(event.get("feature_labels") or {})
    return labels


def _weather_line(day: dict | None) -> str:
    if not day:
        return ""
    rain = day.get("precip_prob")
    rain_text = f"sade {int(rain)} %" if rain is not None else "sade ei tiedossa"
    return (
        f"{day.get('description') or 'Sää'} · "
        f"{_n(day.get('temp_max'))}° / {_n(day.get('temp_min'))}° · "
        f"{rain_text} · "
        f"tuuli {_n(day.get('wind'))} m/s"
    )


def _n(value) -> str:
    if value is None:
        return "–"
    return str(int(value) if isinstance(value, float) and value.is_integer() else value)


def _pick_for_mail(events: list[dict], config: dict, weights: dict, active: bool, limit: int) -> tuple[list[dict], int]:
    topics = config.get("interested_topics") or []
    pool = [event for event in events if event.get("free")] if config.get("free_only") else list(events)

    def sort_key(event: dict):
        strength = topic_strength(event, topics)
        score = score_event(event, weights, config) if active else 50
        return (-strength, -score, event.get("start") or "", event["id"])

    ranked = unique_shows(sorted(pool, key=sort_key))
    chosen = ranked[: max(0, limit)]
    omitted = max(0, len(ranked) - len(chosen))
    chosen.sort(key=lambda event: (event.get("start") or "", event["id"]))
    return chosen, omitted


def _attach(event: dict, extra: dict | None = None) -> dict:
    copy = dict(event)
    copy.pop("feature_labels", None)
    if extra:
        copy.update(extra)
    return copy


def build_bundle(root: Path, *, dry_run: bool = False, now: datetime | None = None) -> dict:
    config = load_config(root)
    moment = now.astimezone(HELSINKI) if now else datetime.now(HELSINKI)
    start, end = next_week_bounds(today_helsinki(moment))
    warnings = []
    events_failed = False
    weather_failed = False
    events: list[dict] = []
    weather = None

    try:
        raw = fetch_events(start, end + timedelta(days=1))
        events = clean_events(raw, start, end, config)
        if not events:
            raise PipelineError("Tapahtumahaku onnistui, mutta yhtään kelvollista tapahtumaa ei jäänyt.")
    except Exception as error:
        events_failed = True
        warnings.append("Tapahtumia ei saatu: " + str(error).replace("\n", " ")[:240])

    try:
        weather, weather_warnings = fetch_weather(start, end)
        warnings.extend(weather_warnings)
    except Exception as error:
        weather_failed = True
        warnings.append("Sääennustetta ei saatu: " + str(error).replace("\n", " ")[:240])

    if events_failed and weather_failed:
        raise PipelineError(
            "Sekä tapahtumat että sää epäonnistuivat, joten viikkoa ei julkaista.\n"
            + "\n".join(warnings)
        )

    worker_url = os.environ.get("WORKER_URL") or config.get("worker_url") or ""
    admin_secret = os.environ.get("ADMIN_SECRET") or ""
    feedback_secret = os.environ.get("FEEDBACK_SECRET") or ""
    votes: list[dict] = []
    stored_weights: dict = {}
    stored_labels: dict = {}
    stored_weeks: dict = {}
    feedback_failed = False
    bundle_remote = None

    if worker_url and admin_secret and not dry_run:
        try:
            bundle_remote = fetch_bundle(worker_url, admin_secret)
            votes = list(bundle_remote.get("votes") or [])
            stored_weights = dict(bundle_remote.get("weights") or {})
            stored_labels = dict(bundle_remote.get("labels") or {})
            stored_weeks = dict(bundle_remote.get("weeks") or {})
        except FeedbackError as error:
            feedback_failed = True
            warnings.append(
                "Palautteita ei saatu, joten käytössä on viimeksi tallennettu järjestys tai aikajärjestys. "
                + str(error)
            )
    elif dry_run:
        local_votes = root / "private" / "votes.json"
        if local_votes.exists():
            votes = json.loads(local_votes.read_text(encoding="utf-8"))
        else:
            warnings.append("Esikatselu ilman aiempia peukutuksia.")
    else:
        warnings.append("Palautepalvelua ei ole vielä kytketty. Tapahtumat näytetään aikajärjestyksessä.")

    if events:
        changed = _enrich(votes, _catalog(root, events))
    else:
        changed = False

    if feedback_failed and stored_weights:
        weights = stored_weights
        active = explicit_count(votes) >= 10 and bool(weights)
    elif feedback_failed:
        weights = {}
        active = False
    else:
        weights = rebuild_weights(votes, moment) if votes else {}
        active = learning_active(votes)

    labels = _labels(events, stored_labels)
    recommended = select_recommended(events, weights, votes, config) if events and active else []
    recommended_ids = [item["id"] for item in recommended]
    by_id = {event["id"]: event for event in events}
    recommended_events = []
    for item in recommended:
        event = by_id.get(item["id"])
        if not event:
            continue
        recommended_events.append(
            _attach(event, {"score": item["score"], "novel": item["novel"], "reason": item["reason"]})
        )

    scores = {}
    if active:
        for event in events:
            scores[event["id"]] = score_event(event, weights, config)

    summary = learned_summary(weights, labels) if active else {"positive": [], "negative": []}
    explicit, clicks = collapse_votes(votes)
    personal = {
        "week": start.isoformat(),
        "learning_active": active,
        "explicit_count": len(explicit),
        "click_count": len([event_id for event_id in clicks if event_id not in explicit]),
        "scores": scores,
        "reasons": {item["id"]: item["reason"] for item in recommended},
        "novel_ids": [item["id"] for item in recommended if item["novel"]],
        "recommended_ids": recommended_ids,
        "learned": summary,
    }

    if worker_url and admin_secret and not dry_run and not feedback_failed:
        weeks = stored_weeks
        weeks[start.isoformat()] = personal
        week_keys = sorted(weeks)[-12:]
        weeks = {key: weeks[key] for key in week_keys}
        try:
            save_bundle(
                worker_url,
                admin_secret,
                {
                    "votes": votes if changed else None,
                    "weights": weights,
                    "labels": labels,
                    "weeks": weeks,
                },
            )
        except FeedbackError as error:
            warnings.append("Oppimista ei saatu tallennettua palautepalveluun. " + str(error))

    calibration = calibration_ids(events, 20) if events else []
    highlights = interest_ids(events, config, int(config.get("recommendation_count") or 8)) if events else []
    weather_by_date = {day["date"]: day for day in (weather or {}).get("days") or []}
    day_rows = []
    for day in week_dates(start, end):
        iso = day.isoformat()
        ids = [event["id"] for event in events if event.get("date") == iso]
        day_rows.append(
            {
                "date": iso,
                "title": weekday_title(iso),
                "weather_line": _weather_line(weather_by_date.get(iso)),
                "event_ids": ids,
            }
        )
    spanning_ids = [event["id"] for event in events if event.get("spanning")]

    public_events = []
    for event in events:
        public_event = dict(event)
        public_event.pop("feature_labels", None)
        public_events.append(public_event)
    public = {
        "week": {"start": start.isoformat(), "end": end.isoformat(), "label": week_label(start, end)},
        "generated_at": moment.isoformat(),
        "warnings": [warning for warning in warnings if "peukutuksia" not in warning.lower()],
        "weather": weather,
        "events": public_events,
        "days": day_rows,
        "spanning_ids": spanning_ids,
        "calibration_ids": calibration,
        "interest_ids": highlights,
        "preferences": {
            "free_only": bool(config.get("free_only")),
            "interested_topics": list(config.get("interested_topics") or []),
        },
        "worker_url": worker_url,
    }
    # Julkiselle sivulle ei laiteta henkilökohtaista pisteytystä.
    write_site(root, public, preview_personal=personal if dry_run else None)

    mail_days = []
    for row in day_rows:
        day_events = [by_id[event_id] for event_id in row["event_ids"] if event_id in by_id]
        chosen, omitted = _pick_for_mail(
            day_events, config, weights, active, int(config.get("email_per_day") or 18)
        )
        mail_days.append(
            {
                "title": row["title"],
                "weather_line": row["weather_line"],
                "events": [_attach(event) for event in chosen],
                "omitted": omitted,
            }
        )
    span_events = [event for event in events if event.get("spanning")]
    span_chosen, span_omitted = _pick_for_mail(
        span_events, config, weights, active, int(config.get("email_spanning_limit") or 12)
    )
    cal_events = [_attach(by_id[event_id]) for event_id in calibration[:8] if event_id in by_id]
    mail = {
        "week": public["week"],
        "weather": weather,
        "warnings": warnings,
        "learning_active": active,
        "explicit_count": len(explicit),
        "recommended_events": recommended_events,
        "calibration_events": cal_events,
        "spanning_events": [_attach(event) for event in span_chosen],
        "spanning_omitted": span_omitted,
        "day_sections": mail_days,
        "site_url": os.environ.get("SITE_URL") or config.get("site_url") or "",
        "worker_url": worker_url,
        "feedback_secret": feedback_secret,
    }
    private = root / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "mail.json").write_text(json.dumps(mail, ensure_ascii=False), encoding="utf-8")
    if dry_run:
        subject, text, html = build_messages(mail)
        (private / "posti.txt").write_text(text, encoding="utf-8")
        (private / "posti.html").write_text(html, encoding="utf-8")
        (root / "site" / "posti-esikatselu.html").write_text(html, encoding="utf-8")
        (private / "otsikko.txt").write_text(subject + "\n", encoding="utf-8")
    return {
        "week": public["week"],
        "event_count": len(events),
        "warnings": warnings,
        "learning_active": active,
        "explicit_count": len(explicit),
        "weather_source": (weather or {}).get("source"),
        "events_failed": events_failed,
        "weather_failed": weather_failed,
    }

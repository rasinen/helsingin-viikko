"""Sähköpostin kokoaminen ja lähetys Gmailin kautta. Vain Pythonin vakiokirjastot."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from html import escape

from .tokens import click_token, owner_token, vote_token
from .week import WEEKDAYS_FI


def _link(worker_url: str, secret: str, event: dict, vote: str) -> str:
    token = vote_token(secret, event["id"], vote)
    return f"{worker_url.rstrip('/')}/v?k={token}"


def _click(worker_url: str, secret: str, event: dict) -> str:
    if not worker_url or not secret:
        return event["url"]
    token = click_token(secret, event["id"], event["url"])
    return f"{worker_url.rstrip('/')}/c?k={token}"


def _site(site_url: str, secret: str) -> str:
    if site_url and secret:
        token = owner_token(secret)
        join = "&" if "?" in site_url else "?"
        return f"{site_url.rstrip('/')}{join}k={token}"
    return site_url or ""


def build_messages(bundle: dict) -> tuple[str, str, str]:
    """Palauttaa otsikon, tekstiversion ja HTML-version."""
    week = bundle["week"]
    subject = f"Helsingin viikko {week['label']}"
    text = _text(bundle)
    html = _html(bundle)
    return subject, text, html


def send_email(bundle: dict, smtp_user: str, smtp_password: str, email_to: str) -> None:
    subject, text, html = build_messages(bundle)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_user
    message["To"] = email_to
    message["Date"] = formatdate(localtime=True)
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=40) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def _text(bundle: dict) -> str:
    week = bundle["week"]
    lines = [f"Helsingin viikko {week['label']}", ""]
    weather = bundle.get("weather")
    if weather:
        lines.append(weather.get("summary") or "")
        lines.append(f"Lähde: {weather.get('source_label')}")
        lines.append("")
        for day in weather.get("days") or []:
            lines.append(
                f"{day['weekday']} {day['date'][8:10]}.{day['date'][5:7]}.  "
                f"{_num(day.get('temp_max'))}° / {_num(day.get('temp_min'))}°  "
                f"{day.get('description') or ''}  "
                f"sade { _num(day.get('precip_prob')) } %  "
                f"tuuli {_num(day.get('wind'))} m/s"
            )
    else:
        lines.append("Sääennustetta ei saatu tähän viestiin.")
    for warning in bundle.get("warnings") or []:
        lines.append("Huomio: " + warning)
    lines.append("")
    if bundle.get("learning_active"):
        lines.append("Sinulle suositeltua")
        for event in bundle.get("recommended_events") or []:
            lines.extend(_event_lines(event, bundle, recommended=True))
    else:
        lines.append("Auta suodatinta alkuun")
        lines.append(
            "Peukutuksia ei ole vielä kymmentä, joten tapahtumat ovat aikajärjestyksessä. "
            "Alla on monipuolinen näyte — vastaa peukulla, niin seuraava viikko osuu paremmin."
        )
        lines.append("")
        for event in bundle.get("calibration_events") or []:
            lines.extend(_event_lines(event, bundle, recommended=False))
    spanning = bundle.get("spanning_events") or []
    if spanning:
        lines.append("")
        lines.append("Koko viikon kestävät")
        for event in spanning:
            lines.extend(_event_lines(event, bundle, recommended=False))
        extra = bundle.get("spanning_omitted") or 0
        if extra:
            lines.append(f"Lisäksi {extra} muuta koko viikon tapahtumaa verkkosivulla.")
    for day in bundle.get("day_sections") or []:
        lines.append("")
        lines.append(day["title"])
        if day.get("weather_line"):
            lines.append(day["weather_line"])
        if not day.get("events"):
            lines.append("Ei poimittuja tapahtumia.")
        for event in day.get("events") or []:
            lines.extend(_event_lines(event, bundle, recommended=False))
        if day.get("omitted"):
            lines.append(f"Lisäksi {day['omitted']} muuta tapahtumaa tältä päivältä verkkosivulla.")
    lines.append("")
    lines.append("Koko viikko selaimessa: " + (_site(bundle.get("site_url") or "", bundle.get("feedback_secret") or "") or "osoite puuttuu"))
    lines.append("Älä lähetä viestiä eteenpäin: linkit ovat henkilökohtaisia.")
    return "\n".join(lines).strip() + "\n"


def _event_lines(event: dict, bundle: dict, recommended: bool) -> list[str]:
    bits = [f"- {event.get('time_label') or 'koko päivä'}  {event['name']}"]
    place = event.get("place") or "Paikka ei tiedossa"
    price = "Ilmainen" if event.get("free") else (event.get("price_label") or "")
    extra = place if not price else f"{place} · {price}"
    bits.append(f"  {extra}")
    if event.get("summary"):
        bits.append("  " + event["summary"])
    if recommended and event.get("reason"):
        bits.append("  " + event["reason"])
    if event.get("novel"):
        bits.append("  Uutta sinulle")
    bits.append("  " + _click(bundle.get("worker_url") or "", bundle.get("feedback_secret") or "", event))
    secret = bundle.get("feedback_secret") or ""
    worker = bundle.get("worker_url") or ""
    if secret and worker:
        bits.append("  Pidän: " + _link(worker, secret, event, "up"))
        bits.append("  Ei kiinnosta: " + _link(worker, secret, event, "down"))
        bits.append("  Menen tai kävin: " + _link(worker, secret, event, "going"))
    bits.append("")
    return bits


def _html(bundle: dict) -> str:
    week = bundle["week"]
    weather = bundle.get("weather")
    parts = [
        "<!doctype html><html lang='fi'><body style='margin:0;padding:0;background:#f3efe6;'>",
        "<div style='display:none;max-height:0;overflow:hidden;'>Helsingin tulevan viikon sää ja tapahtumat.</div>",
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#f3efe6;'>",
        "<tr><td align='center' style='padding:20px 12px;'>",
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='max-width:640px;background:#fffdf8;border-radius:18px;overflow:hidden;font-family:Georgia,serif;color:#1a1814;'>",
        "<tr><td style='padding:28px 24px 12px;background:#14352c;color:#f6f1e6;'>",
        "<div style='font-family:Arial,sans-serif;letter-spacing:.16em;font-size:12px;text-transform:uppercase;color:#e2a312;'>Helsinki</div>",
        f"<h1 style='margin:8px 0 0;font-size:30px;line-height:1.15;'>Viikko {escape(week['label'])}</h1>",
        "</td></tr>",
        "<tr><td style='padding:20px 24px 8px;font-family:Arial,sans-serif;font-size:16px;line-height:1.5;'>",
    ]
    if weather:
        parts.append(f"<p style='margin:0 0 12px;'>{escape(weather.get('summary') or '')}</p>")
        parts.append("<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>")
        for day in weather.get("days") or []:
            parts.append(
                "<tr>"
                f"<td style='padding:6px 0;border-top:1px solid #efe6d6;font-size:14px;'><strong>{escape(day['weekday'])}</strong></td>"
                f"<td style='padding:6px 8px;border-top:1px solid #efe6d6;font-size:14px;'>{_num(day.get('temp_max'))}° / {_num(day.get('temp_min'))}°</td>"
                f"<td style='padding:6px 0;border-top:1px solid #efe6d6;font-size:14px;'>{escape(day.get('description') or '')}</td>"
                f"<td style='padding:6px 0;border-top:1px solid #efe6d6;font-size:14px;text-align:right;'>sade {_num(day.get('precip_prob'))} %</td>"
                "</tr>"
            )
        parts.append("</table>")
        parts.append(
            f"<p style='color:#6d665c;font-size:12px;'>Sää: {escape(weather.get('source_label') or '')}</p>"
        )
    else:
        parts.append("<p><strong>Sääennuste puuttuu tästä viikosta.</strong> Tapahtumat ovat silti alla.</p>")
    for warning in bundle.get("warnings") or []:
        parts.append(
            f"<p style='background:#fff4d6;border-radius:10px;padding:10px 12px;font-size:14px;'>{escape(warning)}</p>"
        )
    parts.append("</td></tr>")
    if bundle.get("learning_active"):
        parts.append(_section("Sinulle suositeltua", "Järjestys perustuu aiempiin peukutuksiisi. Mitään ei ole piilotettu."))
        for event in bundle.get("recommended_events") or []:
            parts.append(_card(event, bundle, recommended=True))
    else:
        count = bundle.get("explicit_count") or 0
        parts.append(
            _section(
                "Auta suodatinta alkuun",
                f"Selkeitä peukutuksia on {count}/10. Ennen sitä lista on aikajärjestyksessä. "
                "Valitse alta muutama tapahtuma, niin seuraava kirje osuu paremmin.",
            )
        )
        for event in bundle.get("calibration_events") or []:
            parts.append(_card(event, bundle, recommended=False))
    if bundle.get("spanning_events"):
        parts.append(_section("Koko viikon kestävät", "Näyttelyt ja muut monen päivän tapahtumat, ei joka päivän kohdalla uudestaan."))
        for event in bundle["spanning_events"]:
            parts.append(_card(event, bundle, recommended=False))
        if bundle.get("spanning_omitted"):
            parts.append(
                f"<p style='padding:0 24px;font-family:Arial,sans-serif;font-size:14px;color:#6d665c;'>Lisäksi {bundle['spanning_omitted']} muuta koko viikon tapahtumaa verkkosivulla.</p>"
            )
    for day in bundle.get("day_sections") or []:
        parts.append(_section(day["title"], day.get("weather_line") or ""))
        if not day.get("events"):
            parts.append("<p style='padding:0 24px;font-family:Arial,sans-serif;'>Ei poimittuja tapahtumia.</p>")
        for event in day.get("events") or []:
            parts.append(_card(event, bundle, recommended=False))
        if day.get("omitted"):
            parts.append(
                f"<p style='padding:0 24px 8px;font-family:Arial,sans-serif;font-size:14px;color:#6d665c;'>Lisäksi {day['omitted']} muuta tapahtumaa tältä päivältä verkkosivulla.</p>"
            )
    site = _site(bundle.get("site_url") or "", bundle.get("feedback_secret") or "")
    parts.append("<tr><td style='padding:8px 24px 28px;font-family:Arial,sans-serif;'>")
    if site:
        parts.append(
            f"<a href='{escape(site)}' style='display:inline-block;background:#14352c;color:#f6f1e6;text-decoration:none;padding:12px 18px;border-radius:999px;font-weight:bold;'>Avaa viikko selaimessa</a>"
        )
    parts.append(
        "<p style='font-size:12px;color:#6d665c;line-height:1.45;'>Linkki on henkilökohtainen. Älä lähetä viestiä eteenpäin, jos et halua muiden näkevän suosituksiasi tai antavan palautetta puolestasi.</p>"
    )
    parts.append("</td></tr></table></td></tr></table></body></html>")
    return "".join(parts)


def _section(title: str, subtitle: str) -> str:
    sub = f"<div style='color:#6d665c;font-size:14px;margin-top:4px;'>{escape(subtitle)}</div>" if subtitle else ""
    return (
        "<tr><td style='padding:18px 24px 4px;font-family:Arial,sans-serif;'>"
        f"<h2 style='margin:0;font-family:Georgia,serif;font-size:22px;'>{escape(title)}</h2>{sub}</td></tr>"
    )


def _card(event: dict, bundle: dict, recommended: bool) -> str:
    secret = bundle.get("feedback_secret") or ""
    worker = bundle.get("worker_url") or ""
    href = _click(worker, secret, event)
    when = event.get("time_label") or "Koko viikko"
    if event.get("end_time_label") and not event.get("spanning"):
        when += "–" + event["end_time_label"]
    place = event.get("place") or "Paikka ei tiedossa"
    if event.get("address"):
        place += ", " + event["address"]
    badges = []
    if event.get("free"):
        badges.append("Ilmainen")
    elif event.get("price_label"):
        badges.append(event["price_label"])
    if event.get("novel"):
        badges.append("Uutta sinulle")
    if event.get("rescheduled"):
        badges.append("Aikataulu muuttunut")
    badge_html = ""
    if badges:
        badge_html = "<div style='font-family:Arial,sans-serif;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#0f6e56;margin-bottom:4px;'>" + escape(" · ".join(badges)) + "</div>"
    reason = ""
    if recommended and event.get("reason"):
        reason = f"<div style='margin-top:8px;background:#f6f1e4;border-radius:8px;padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'>{escape(event['reason'])}</div>"
    actions = ""
    if secret and worker:
        actions = (
            "<div style='margin-top:10px;font-family:Arial,sans-serif;font-size:14px;'>"
            f"<a href='{escape(_link(worker, secret, event, 'up'))}' style='margin-right:12px;color:#14352c;'>Pidän</a>"
            f"<a href='{escape(_link(worker, secret, event, 'down'))}' style='margin-right:12px;color:#14352c;'>Ei kiinnosta</a>"
            f"<a href='{escape(_link(worker, secret, event, 'going'))}' style='color:#14352c;'>Menen tai kävin</a>"
            "</div>"
        )
    summary = f"<div style='font-family:Arial,sans-serif;font-size:14px;line-height:1.45;color:#3c3832;margin-top:6px;'>{escape(event.get('summary') or '')}</div>" if event.get("summary") else ""
    return (
        "<tr><td style='padding:8px 24px;'>"
        "<div style='border:1px solid #efe6d6;border-radius:14px;padding:12px 14px;'>"
        f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#6d665c;'>{escape(when)}</div>"
        f"{badge_html}"
        f"<a href='{escape(href)}' style='color:#1a1814;text-decoration:none;font-size:18px;font-weight:bold;'>{escape(event['name'])}</a>"
        f"<div style='font-family:Arial,sans-serif;font-size:14px;margin-top:4px;'>{escape(place)}</div>"
        f"{summary}{reason}{actions}"
        "</div></td></tr>"
    )


def _num(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def weekday_title(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    index = __import__("datetime").date(int(year), int(month), int(day)).weekday()
    return f"{WEEKDAYS_FI[index].capitalize()} {int(day)}.{int(month)}."

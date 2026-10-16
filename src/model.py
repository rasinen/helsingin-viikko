"""Yksinkertainen oppiva pisteytys.

Paino on piirteen saamien palautteiden summa. Vanha palaute
puoliintuu noin puolessa vuodessa. Pisteet 0–100, 50 on neutraali.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from .textutil import norm

HALF_LIFE_DAYS = 182.5
COLD_START_MIN = 10
STRENGTH = {"up": 1.0, "down": -1.0, "going": 2.5, "click": 0.25}
EXPLICIT = {"up", "down", "going"}

GENERIC_KEYWORDS = {
    "osallistuminen",
    "tapahtumat",
    "kulttuuritapahtumat",
    "hyvinvointi",
    "helsinki",
    "suomi",
    "ruotsi",
    "englanti",
    "keskustelu",
}

ELATIVE = {
    "musiikki": "musiikista",
    "konsertti": "konserteista",
    "konsertit": "konserteista",
    "keikka": "keikoista",
    "teatteri": "teatterista",
    "teatteritaide": "teatterista",
    "tanssi": "tanssista",
    "näytelmä": "näytelmistä",
    "esitys": "esityksistä",
    "elokuva": "elokuvista",
    "elokuvat": "elokuvista",
    "ruoka": "ruoasta",
    "ruokakulttuuri": "ruoasta",
    "markkinat": "markkinoista",
    "festivaali": "festivaaleista",
    "näyttely": "näyttelyistä",
    "taide": "taiteesta",
    "kuvataide": "kuvataiteesta",
    "kirjallisuus": "kirjallisuudesta",
}

TOD_PHRASE = {
    "morning": "aamutapahtumista",
    "afternoon": "päiväohjelmasta",
    "evening": "iltatapahtumista",
    "night": "yötapahtumista",
}
PRICE_PHRASE = {
    "free": "ilmaisista tapahtumista",
    "paid": "maksullisista tapahtumista",
    "low": "edullisista tapahtumista",
    "mid": "keskihintaisista tapahtumista",
    "high": "kalliimmista tapahtumista",
}
WEEKDAY_PHRASE = [
    "maanantaista",
    "tiistaista",
    "keskiviikosta",
    "torstaista",
    "perjantaista",
    "lauantaista",
    "sunnuntaista",
]


def decay_factor(age_days: float) -> float:
    if age_days < 0:
        age_days = 0.0
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def _parse_ts(ts, now: datetime) -> float:
    if not ts:
        return 0.0
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def collapse_votes(votes: list[dict]) -> tuple[dict, dict]:
    """Viimeisin selkeä palaute korvaa aiemman. Klikkaus ei kumoa peukkua."""
    explicit: dict[str, dict] = {}
    clicks: dict[str, dict] = {}
    ordered = sorted(votes or [], key=lambda v: str(v.get("ts") or ""))
    for vote in ordered:
        event_id = vote.get("event_id")
        kind = vote.get("vote")
        if not event_id or kind not in STRENGTH:
            continue
        if kind == "click":
            clicks[event_id] = vote
        elif kind in EXPLICIT:
            explicit[event_id] = vote
    return explicit, clicks


def explicit_count(votes: list[dict]) -> int:
    explicit, _clicks = collapse_votes(votes)
    return len(explicit)


def learning_active(votes: list[dict]) -> bool:
    return explicit_count(votes) >= COLD_START_MIN


def rebuild_weights(votes: list[dict], now: datetime) -> dict[str, float]:
    explicit, clicks = collapse_votes(votes)
    weights: dict[str, float] = {}

    def add(vote: dict) -> None:
        strength = STRENGTH[vote["vote"]] * decay_factor(_parse_ts(vote.get("ts"), now))
        for feature in vote.get("features") or []:
            weights[feature] = weights.get(feature, 0.0) + strength

    for vote in explicit.values():
        add(vote)
    for event_id, vote in clicks.items():
        if event_id in explicit:
            continue
        add(vote)
    return weights


def normalize_score(raw: float) -> int:
    value = 100.0 / (1.0 + math.exp(-raw / 2.5))
    return int(max(0, min(100, round(value))))


def topic_matches(features: list[str], topics: list[str]) -> int:
    labels = [feature[2:] for feature in features or [] if feature.startswith("k:")]
    found = 0
    for topic in topics or []:
        needle = norm(topic)
        if len(needle) < 3:
            continue
        if any(needle in label or label in needle for label in labels if len(label) >= 3):
            found += 1
    return found


def prior_bonus(features: list[str], config: dict | None) -> float:
    if not config:
        return 0.0
    bonus = 0.0
    bonus += 0.45 * topic_matches(features, config.get("interested_topics") or [])
    bonus -= 1.2 * topic_matches(features, config.get("excluded_topics") or [])
    if config.get("free_only") and "price:free" in (features or []):
        bonus += 0.4
    return bonus


def score_raw(features: list[str], weights: dict[str, float], config: dict | None = None) -> float:
    total = prior_bonus(features, config)
    for feature in set(features or []):
        total += (weights or {}).get(feature, 0.0)
    return total


def score_event(event: dict, weights: dict[str, float], config: dict | None = None) -> int:
    return normalize_score(score_raw(event.get("features") or [], weights, config))


def seen_keywords(votes: list[dict]) -> set[str]:
    explicit, _clicks = collapse_votes(votes)
    seen = set()
    for vote in explicit.values():
        for feature in vote.get("features") or []:
            if feature.startswith("k:") and feature[2:] not in GENERIC_KEYWORDS:
                seen.add(feature)
    return seen


def is_novel(event: dict, seen: set[str]) -> bool:
    keywords = [
        feature
        for feature in event.get("features") or []
        if feature.startswith("k:") and feature[2:] not in GENERIC_KEYWORDS
    ]
    if not keywords:
        return False
    return all(feature not in seen for feature in keywords)


def _phrase(feature: str, labels: dict | None) -> str:
    labels = labels or {}
    if feature.startswith("k:"):
        name = (labels.get(feature) or feature[2:]).strip()
        key = norm(name)
        if key in ELATIVE:
            return ELATIVE[key]
        return f"aiheesta {name}"
    if feature.startswith("p:"):
        name = labels.get(feature) or feature[2:]
        return f"paikasta {name}"
    if feature.startswith("o:"):
        name = labels.get(feature) or feature[2:]
        return f"järjestäjästä {name}"
    if feature.startswith("tod:"):
        return TOD_PHRASE.get(feature[4:], "tästä ajankohdasta")
    if feature.startswith("price:"):
        return PRICE_PHRASE.get(feature[6:], "hintaluokasta")
    if feature.startswith("wd:"):
        try:
            return WEEKDAY_PHRASE[int(feature[3:])]
        except (ValueError, IndexError):
            return "tästä viikonpäivästä"
    return feature


def explain(event: dict, weights: dict[str, float], labels: dict | None = None) -> str:
    if event.get("novel"):
        return "Uutta sinulle — tämän aihepiirin tapahtumia et ole vielä arvioinut."
    ranked = []
    for feature in event.get("features") or []:
        weight = (weights or {}).get(feature, 0.0)
        if weight <= 0.2:
            continue
        if feature.startswith("k:") and feature[2:] in GENERIC_KEYWORDS:
            continue
        ranked.append((weight, _phrase(feature, labels or event.get("feature_labels"))))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    phrases = []
    for _weight, phrase in ranked:
        if phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) == 2:
            break
    if not phrases:
        return "Nousi esiin, koska se muistuttaa tapahtumia, joista olet pitänyt."
    if len(phrases) == 1:
        return f"Suositeltu, koska olet pitänyt {phrases[0]}."
    return f"Suositeltu, koska olet pitänyt {phrases[0]} ja {phrases[1]}."


def select_recommended(
    events: list[dict],
    weights: dict[str, float],
    votes: list[dict],
    config: dict | None = None,
) -> list[dict]:
    """Palauttaa suositellut. Muita tapahtumia ei poisteta mistään."""
    config = config or {}
    if not learning_active(votes):
        return []
    count = max(1, int(config.get("recommendation_count") or 8))
    ratio = config.get("novelty_ratio")
    ratio = 0.2 if ratio is None else float(ratio)
    novel_slots = int(round(count * ratio))
    seen = seen_keywords(votes)
    decorated = []
    for event in events:
        decorated.append(
            {
                "id": event["id"],
                "score": score_event(event, weights, config),
                "novel": is_novel(event, seen),
                "event": event,
            }
        )
    decorated.sort(key=lambda item: (-item["score"], item["id"]))
    regulars = [item for item in decorated if not item["novel"]]
    novels = [item for item in decorated if item["novel"]]
    picked = regulars[: max(0, count - novel_slots)] + novels[:novel_slots]
    allowed_novel = {item["id"] for item in novels[:novel_slots]}
    used = {item["id"] for item in picked}
    if len(picked) < count:
        for item in decorated:
            if item["id"] in used:
                continue
            picked.append(item)
            used.add(item["id"])
            if len(picked) >= count:
                break
    output = []
    for item in sorted(picked, key=lambda row: (-row["score"], row["id"])):
        novel = item["id"] in allowed_novel
        event = dict(item["event"])
        event["novel"] = novel
        output.append(
            {
                "id": item["id"],
                "score": item["score"],
                "novel": novel,
                "reason": explain(event, weights, event.get("feature_labels")),
            }
        )
    return output


def topic_strength(event: dict, topics: list[str] | None) -> float:
    """Miten hyvin tapahtuma osuu valittuihin aiheisiin. Ei piilota mitään."""
    labels = [norm(keyword) for keyword in event.get("keywords") or []]
    score = 0.0
    for topic in topics or []:
        needle = norm(topic)
        if len(needle) < 3:
            continue
        best = 0.0
        for label in labels:
            if not label:
                continue
            if label == needle:
                best = max(best, 4.0)
            elif label.startswith(needle + " ") or label.endswith(" " + needle) or f" {needle} " in f" {label} ":
                best = max(best, 3.0)
            elif needle in label and len(label) <= len(needle) + 8:
                best = max(best, 2.0)
            elif needle in label or (len(label) >= 4 and label in needle):
                best = max(best, 1.0)
        score += best
    blob = " ".join(labels + [norm(event.get("place") or ""), norm(event.get("name") or "")])
    if any(word in blob for word in ("leikkipuisto", "leikkiminen", "vauva", "palvelukeskus")):
        score -= 2.0
    return score


def interest_ids(events: list[dict], config: dict, limit: int = 8) -> list[str]:
    topics = config.get("interested_topics") or []
    ranked = sorted(
        events,
        key=lambda event: (-topic_strength(event, topics), event.get("start") or "", event["id"]),
    )
    return [event["id"] for event in ranked if topic_strength(event, topics) > 0][:limit]


def calibration_ids(events: list[dict], limit: int = 20) -> list[str]:
    pool = [event for event in events if not event.get("spanning")] or list(events)
    picked = []
    used_keywords: dict[str, int] = {}
    used_places = set()
    while len(picked) < limit and pool:
        best = None
        best_key = None
        for event in pool:
            keywords = [
                norm(keyword)
                for keyword in event.get("keywords") or []
                if norm(keyword) and norm(keyword) not in GENERIC_KEYWORDS
            ]
            primary = keywords[0] if keywords else ""
            place = norm(event.get("place") or "")
            penalty = used_keywords.get(primary, 0) * 3 + (1 if place and place in used_places else 0)
            if not primary:
                penalty += 2
            key = (penalty, event.get("start") or "", event["id"])
            if best_key is None or key < best_key:
                best_key = key
                best = event
        picked.append(best)
        pool.remove(best)
        keywords = [
            norm(keyword)
            for keyword in best.get("keywords") or []
            if norm(keyword) and norm(keyword) not in GENERIC_KEYWORDS
        ]
        if keywords:
            used_keywords[keywords[0]] = used_keywords.get(keywords[0], 0) + 1
        if best.get("place"):
            used_places.add(norm(best["place"]))
    return [event["id"] for event in picked]


def learned_summary(weights: dict[str, float], labels: dict | None = None, limit: int = 8) -> dict:
    labels = labels or {}
    rows = []
    for feature, weight in (weights or {}).items():
        if abs(weight) < 0.2:
            continue
        if feature.startswith("k:") and feature[2:] in GENERIC_KEYWORDS:
            continue
        rows.append(
            {
                "feature": feature,
                "label": _phrase(feature, labels),
                "weight": round(weight, 2),
            }
        )
    positive = sorted((row for row in rows if row["weight"] > 0), key=lambda row: -row["weight"])[:limit]
    negative = sorted((row for row in rows if row["weight"] < 0), key=lambda row: row["weight"])[:limit]
    return {"positive": positive, "negative": negative}


def sort_events(events: list[dict], weights: dict[str, float], votes: list[dict], config: dict | None = None) -> list[dict]:
    """Kylmäkäynnistyksessä aikajärjestys. Muuten pisteet, aikatasaus tasatilanteessa."""
    if not learning_active(votes):
        return sorted(events, key=lambda event: (event.get("start") or "", event.get("id") or ""))
    config = config or {}
    return sorted(
        events,
        key=lambda event: (
            -score_event(event, weights, config),
            event.get("start") or "",
            event.get("id") or "",
        ),
    )

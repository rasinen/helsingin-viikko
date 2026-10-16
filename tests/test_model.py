import unittest
from datetime import datetime, timedelta, timezone

from src.model import (
    explain,
    explicit_count,
    learning_active,
    normalize_score,
    rebuild_weights,
    score_event,
    select_recommended,
    sort_events,
)


def event(event_id, features, start="2026-10-19T18:00:00+03:00", keywords=None):
    labels = {}
    for feature in features:
        if feature.startswith("k:"):
            labels[feature] = feature[2:]
        if feature.startswith("p:"):
            labels[feature] = feature[2:].title()
    return {
        "id": event_id,
        "name": event_id,
        "start": start,
        "features": features,
        "feature_labels": labels,
        "keywords": keywords or [feature[2:] for feature in features if feature.startswith("k:")],
        "place": "",
        "spanning": False,
    }


def vote(event_id, kind, features, when):
    return {"event_id": event_id, "vote": kind, "features": features, "ts": when.isoformat()}


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    def test_thumbs_change_similar_events(self):
        music = event("m", ["k:musiikki", "p:tavastia"])
        bingo = event("b", ["k:bingo"])
        when = self.now
        up = [vote(f"old{i}", "up", ["k:musiikki", "p:tavastia"], when) for i in range(10)]
        weights = rebuild_weights(up, self.now)
        self.assertGreater(score_event(music, weights), score_event(bingo, weights))
        down = [vote(f"old{i}", "down", ["k:musiikki"], when) for i in range(10)]
        weights_down = rebuild_weights(down, self.now)
        self.assertLess(score_event(music, weights_down), normalize_score(0))
        self.assertGreater(score_event(music, weights), score_event(music, weights_down))

    def test_going_weighs_more_than_click(self):
        sample = event("x", ["k:elokuva"])
        going = rebuild_weights([vote("a", "going", ["k:elokuva"], self.now)], self.now)
        click = rebuild_weights([vote("b", "click", ["k:elokuva"], self.now)], self.now)
        self.assertGreater(going["k:elokuva"], click["k:elokuva"] * 5)

    def test_latest_explicit_replaces_and_click_does_not_override(self):
        votes = [
            vote("a", "up", ["k:teatteri"], self.now - timedelta(days=1)),
            vote("a", "down", ["k:teatteri"], self.now),
            vote("a", "click", ["k:teatteri"], self.now),
        ]
        weights = rebuild_weights(votes, self.now)
        self.assertLess(weights["k:teatteri"], 0)
        self.assertEqual(explicit_count(votes), 1)

    def test_decay_half_life(self):
        fresh = vote("a", "up", ["k:musiikki"], self.now)
        old = vote("b", "up", ["k:teatteri"], self.now - timedelta(days=182.5))
        weights = rebuild_weights([fresh, old], self.now)
        self.assertAlmostEqual(weights["k:musiikki"] / weights["k:teatteri"], 2, delta=0.08)

    def test_cold_start_orders_by_time_and_does_not_claim_learning(self):
        votes = [vote(f"v{i}", "up", ["k:musiikki"], self.now) for i in range(9)]
        self.assertFalse(learning_active(votes))
        later = event("later", ["k:bingo"], start="2026-10-21T10:00:00+03:00")
        sooner = event("sooner", ["k:musiikki"], start="2026-10-19T10:00:00+03:00")
        ordered = sort_events([later, sooner], rebuild_weights(votes, self.now), votes)
        self.assertEqual([item["id"] for item in ordered], ["sooner", "later"])
        self.assertEqual(select_recommended([later, sooner], {}, votes, {}), [])

    def test_learning_starts_at_ten_and_hides_nothing(self):
        votes = [vote(f"v{i}", "up", ["k:musiikki"], self.now) for i in range(10)]
        self.assertTrue(learning_active(votes))
        events = [
            event("low", ["k:bingo"], start="2026-10-19T09:00:00+03:00"),
            event("high", ["k:musiikki"], start="2026-10-20T09:00:00+03:00"),
        ]
        ordered = sort_events(events, rebuild_weights(votes, self.now), votes)
        self.assertEqual([item["id"] for item in ordered], ["high", "low"])
        self.assertEqual(len(ordered), 2)

    def test_novelty_slots_are_reserved(self):
        votes = [vote(f"v{i}", "up", ["k:musiikki"], self.now) for i in range(10)]
        weights = rebuild_weights(votes, self.now)
        events = [event(f"m{i}", ["k:musiikki"]) for i in range(8)]
        events += [event("c1", ["k:keramiikka"]), event("c2", ["k:keramiikka"])]
        picked = select_recommended(events, weights, votes, {"recommendation_count": 8, "novelty_ratio": 0.2})
        ids = [item["id"] for item in picked]
        self.assertEqual(len(ids), 8)
        self.assertIn("c1", ids)
        self.assertIn("c2", ids)
        novels = [item["id"] for item in picked if item["novel"]]
        self.assertEqual(sorted(novels), ["c1", "c2"])
        self.assertIn("Uutta sinulle", explain({"features": ["k:keramiikka"], "novel": True}, weights))

    def test_reason_mentions_liked_features(self):
        weights = {"k:musiikki": 2.0, "p:tavastia": 1.4}
        event_row = event("m", ["k:musiikki", "p:tavastia"])
        text = explain(event_row, weights, event_row["feature_labels"])
        self.assertIn("musiikista", text)
        self.assertIn("Tavastia", text)


if __name__ == "__main__":
    unittest.main()

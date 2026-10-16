import unittest
from datetime import date, datetime

from src.events import clean_events, prepare_event, price_info
from src.render import assert_public_safe
from src.tokens import owner_token, sign, verify
from src.week import next_week_bounds, week_label


class WeekTests(unittest.TestCase):
    def test_next_week_from_thursday_sunday_and_monday(self):
        self.assertEqual(next_week_bounds(date(2026, 10, 15)), (date(2026, 10, 19), date(2026, 10, 25)))
        self.assertEqual(next_week_bounds(date(2026, 10, 18)), (date(2026, 10, 19), date(2026, 10, 25)))
        self.assertEqual(next_week_bounds(date(2026, 10, 19)), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(week_label(date(2026, 10, 19), date(2026, 10, 25)), "19.10.–25.10.")


class EventTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2026, 10, 19)
        self.end = date(2026, 10, 25)

    def raw(self, **overrides):
        event = {
            "id": "helsinki:1",
            "name": {"fi": "Illan konsertti"},
            "start_time": "2026-10-19T16:00:00Z",
            "end_time": "2026-10-19T18:00:00Z",
            "offers": [{"is_free": True, "price": None, "description": {"fi": "Vapaa pääsy"}}],
            "keywords": [{"name": {"fi": "musiikki"}}, {"name": {"fi": "konsertit"}}],
            "location": {
                "name": {"fi": "Tavastia"},
                "street_address": {"fi": "Urho Kekkosen katu 4-6"},
            },
            "provider": {"fi": "Tavastia-klubi"},
            "info_url": {"fi": "https://example.com/konsertti"},
            "event_status": "EventScheduled",
        }
        event.update(overrides)
        return event

    def test_price_and_clean_event(self):
        self.assertEqual(price_info([{"is_free": False, "price": {"fi": "12 €"}}])[2], "price:low")
        cleaned = prepare_event(self.raw(), self.start, self.end, 150)
        self.assertTrue(cleaned["free"])
        self.assertEqual(cleaned["place"], "Tavastia")
        self.assertIn("k:musiikki", cleaned["features"])
        self.assertFalse(cleaned["spanning"])
        self.assertEqual(cleaned["date"], "2026-10-19")
        self.assertEqual(cleaned["summary"].endswith("…") or len(cleaned["summary"]) <= 200, True)

    def test_drops_bad_rows_and_duplicates_and_keeps_spanning_apart(self):
        long = self.raw(
            id="museum:1",
            name={"fi": "Näyttely"},
            start_time="2026-10-01T07:00:00Z",
            end_time="2026-10-31T16:00:00Z",
        )
        permanent = self.raw(
            id="museum:forever",
            name={"fi": "Pysyvä näyttely"},
            start_time="2001-01-01T07:00:00Z",
            end_time="2050-12-31T16:00:00Z",
        )
        nameless = self.raw(id="x:1", name={"fi": ""})
        cancelled = self.raw(id="x:2", event_status="EventCancelled")
        duplicate = self.raw(id="helsinki:1b")
        cleaned = clean_events(
            [self.raw(), duplicate, long, permanent, nameless, cancelled],
            self.start,
            self.end,
            {"permanent_days_limit": 150},
        )
        ids = [event["id"] for event in cleaned]
        self.assertIn("helsinki:1", ids)
        self.assertNotIn("helsinki:1b", ids)
        self.assertNotIn("museum:forever", ids)
        self.assertNotIn("x:1", ids)
        self.assertNotIn("x:2", ids)
        spanning = next(event for event in cleaned if event["id"] == "museum:1")
        self.assertTrue(spanning["spanning"])
        self.assertIsNone(spanning["date"])


class TokenTests(unittest.TestCase):
    def test_roundtrip_and_reject_tamper(self):
        secret = "testi-salaisuus"
        token = owner_token(secret)
        self.assertEqual(verify(token, secret)["role"], "owner")
        self.assertIsNone(verify(token, "vaara"))
        self.assertIsNone(verify(token + "x", secret))
        other = sign({"role": "owner", "exp": 10}, secret)
        self.assertIsNone(verify(other, secret))


class PrivacyTests(unittest.TestCase):
    def test_public_payload_rejects_personal_fields(self):
        assert_public_safe({"events": [{"id": "a", "features": ["k:musiikki"]}]})
        with self.assertRaises(RuntimeError):
            assert_public_safe({"scores": {}})
        with self.assertRaises(RuntimeError):
            assert_public_safe({"note": "lauri@gmail.com"})


if __name__ == "__main__":
    unittest.main()

import json
from datetime import date

from django.test import Client, TestCase

from races.models import Race, RaceCorrectionSuggestion


class RaceCorrectionSuggestionsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.race = Race.objects.create(
            name="Mosfellsbær 10k",
            description="Road race",
            race_type="10k",
            date=date(2025, 5, 1),
            location="Mosfellsbær",
            distance_km=10.0,
            surface_type="road",
            discipline="running",
            organizer="Tímataka",
        )

    def test_create_correction_suggestion(self):
        response = self.client.post(
            f"/api/races/{self.race.id}/correction-suggestions",
            data=json.dumps({
                "suggested_surface_type": "trail",
                "suggested_race_type": "trail",
                "comment": "Þetta er í raun utanvegahlaup.",
                "submitter_name": "Testari",
                "submitter_email": "test@example.com",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["race_id"], self.race.id)
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["suggested_surface_type"], "trail")
        self.assertEqual(payload["suggested_race_type"], "trail")

        suggestion = RaceCorrectionSuggestion.objects.get(id=payload["id"])
        self.assertEqual(suggestion.current_surface_type, "road")
        self.assertEqual(suggestion.current_race_type, "10k")
        self.assertEqual(suggestion.comment, "Þetta er í raun utanvegahlaup.")

    def test_create_correction_suggestion_without_distance(self):
        response = self.client.post(
            f"/api/races/{self.race.id}/correction-suggestions",
            data=json.dumps({
                "suggested_discipline": "biking",
                "comment": "Þetta er hjólreiðaviðburður.",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        suggestion = RaceCorrectionSuggestion.objects.get()
        self.assertIsNone(suggestion.suggested_distance_km)
        self.assertEqual(suggestion.suggested_discipline, "biking")

    def test_rejects_noop_correction_suggestion(self):
        response = self.client.post(
            f"/api/races/{self.race.id}/correction-suggestions",
            data=json.dumps({
                "suggested_surface_type": "road",
                "suggested_distance_km": 10.0,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RaceCorrectionSuggestion.objects.count(), 0)
        self.assertIn("must differ", response.json()["detail"])

    def test_accepts_suggestion_for_race_with_invalid_current_distance(self):
        self.race.distance_km = 0.0
        self.race.save(update_fields=["distance_km"])

        response = self.client.post(
            f"/api/races/{self.race.id}/correction-suggestions",
            data=json.dumps({
                "suggested_distance_km": 2,
                "comment": "Rétt vegalengd er 2 km.",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        suggestion = RaceCorrectionSuggestion.objects.get()
        self.assertEqual(suggestion.current_distance_km, 0.0)
        self.assertEqual(suggestion.suggested_distance_km, 2.0)

    def test_apply_suggestion_updates_race_and_marks_done(self):
        suggestion = RaceCorrectionSuggestion.objects.create(
            race=self.race,
            current_surface_type=self.race.surface_type,
            current_distance_km=self.race.distance_km,
            current_discipline=self.race.discipline,
            current_race_type=self.race.race_type,
            suggested_surface_type="trail",
            suggested_distance_km=12.5,
            suggested_discipline="biking",
            suggested_race_type="other",
            comment="Manual correction",
        )

        suggestion.apply_to_race()

        self.race.refresh_from_db()
        suggestion.refresh_from_db()
        self.assertEqual(self.race.surface_type, "trail")
        self.assertEqual(self.race.distance_km, 12.5)
        self.assertEqual(self.race.discipline, "biking")
        self.assertEqual(self.race.race_type, "other")
        self.assertEqual(suggestion.status, "applied")
        self.assertIsNotNone(suggestion.reviewed_at)

    def test_reject_suggestion_marks_rejected(self):
        suggestion = RaceCorrectionSuggestion.objects.create(
            race=self.race,
            current_surface_type=self.race.surface_type,
            current_distance_km=self.race.distance_km,
            current_discipline=self.race.discipline,
            current_race_type=self.race.race_type,
            suggested_discipline="biking",
            comment="Not actually biking",
        )

        suggestion.reject()

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, "rejected")
        self.assertIsNotNone(suggestion.reviewed_at)

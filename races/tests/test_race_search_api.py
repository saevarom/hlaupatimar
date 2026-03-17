from datetime import date, timedelta

from django.test import Client, TestCase

from races.models import Race, Result, Runner


class RaceSearchApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_search_races_includes_speed_index(self):
        race_ids = []
        for race_number in range(5):
            race = Race.objects.create(
                name=f"Vorhlaup 10k {race_number + 1}",
                description="Road 10k race",
                race_type="10k",
                date=date(2025, 5, 1) + timedelta(days=race_number),
                location="Reykjavik",
                distance_km=10.0,
                surface_type="road",
                organizer="Tímataka",
            )
            race_ids.append(race.id)

            for finisher in range(5):
                runner = Runner.objects.create(
                    name=f"Runner {race_number}-{finisher}",
                    birth_year=1990 + finisher,
                    gender="M",
                )
                Result.objects.create(
                    race=race,
                    runner=runner,
                    participant_name=runner.name,
                    finish_time=timedelta(minutes=40 + race_number + finisher),
                    status="finished",
                )

        response = self.client.get("/api/races/search", {"q": "Vorhlaup", "limit": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 5)
        self.assertEqual({item["id"] for item in payload}, set(race_ids))
        self.assertTrue(all(item["speed_index"] is not None for item in payload))


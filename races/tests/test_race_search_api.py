from datetime import date, timedelta

from django.test import Client, TestCase

from races.models import Race, Result, Runner


class RaceSearchApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _create_race_with_results(
        self,
        *,
        name: str,
        race_type: str,
        race_date: date,
        distance_km: float,
        surface_type: str,
        winner_minutes: int,
    ):
        race = Race.objects.create(
            name=name,
            description=f"{surface_type.title()} {race_type} race",
            race_type=race_type,
            date=race_date,
            location="Reykjavik",
            distance_km=distance_km,
            surface_type=surface_type,
            organizer="Tímataka",
        )

        for finisher in range(5):
            runner = Runner.objects.create(
                name=f"{name} Runner {finisher}",
                birth_year=1990 + finisher,
                gender="M",
            )
            Result.objects.create(
                race=race,
                runner=runner,
                participant_name=runner.name,
                finish_time=timedelta(minutes=winner_minutes + finisher),
                status="finished",
            )

        return race

    def test_search_races_includes_speed_index(self):
        race_ids = []
        for race_number in range(5):
            race = self._create_race_with_results(
                name=f"Vorhlaup 10k {race_number + 1}",
                race_type="10k",
                race_date=date(2025, 5, 1) + timedelta(days=race_number),
                distance_km=10.0,
                surface_type="road",
                winner_minutes=40 + race_number,
            )
            race_ids.append(race.id)

        response = self.client.get("/api/races/search", {"q": "Vorhlaup", "limit": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 5)
        self.assertEqual({item["id"] for item in payload}, set(race_ids))
        self.assertTrue(all(item["speed_index"] is not None for item in payload))

    def test_search_races_supports_sorting_and_filters(self):
        fastest = self._create_race_with_results(
            name="Vorhlaup 10k Fastest",
            race_type="10k",
            race_date=date(2025, 5, 1),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=36,
        )
        middle = self._create_race_with_results(
            name="Vorhlaup 10k Middle",
            race_type="10k",
            race_date=date(2025, 5, 2),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=40,
        )
        self._create_race_with_results(
            name="Vorhlaup 10k Slowest",
            race_type="10k",
            race_date=date(2025, 5, 3),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=44,
        )
        self._create_race_with_results(
            name="Vorhlaup 10k Fourth",
            race_type="10k",
            race_date=date(2025, 5, 4),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=41,
        )
        self._create_race_with_results(
            name="Vorhlaup 10k Fifth",
            race_type="10k",
            race_date=date(2025, 5, 5),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=43,
        )
        Race.objects.create(
            name="Vorhlaup Trail",
            description="Trail race",
            race_type="trail",
            date=date(2025, 5, 6),
            location="Reykjavik",
            distance_km=12.0,
            surface_type="trail",
            organizer="Tímataka",
        )

        response = self.client.get(
            "/api/races/search",
            {
                "q": "Vorhlaup",
                "race_type": "10k",
                "surface_type": "road",
                "require_speed_index": "true",
                "order_by": "winning_fastest",
                "limit": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(all(item["race_type"] == "10k" for item in payload))
        self.assertTrue(all(item["surface_type"] == "road" for item in payload))
        self.assertTrue(all(item["speed_index"] is not None for item in payload))
        self.assertEqual(payload[0]["id"], fastest.id)
        self.assertEqual(payload[1]["id"], middle.id)

    def test_browse_races_supports_speed_filter_and_winning_time_sort(self):
        fastest = self._create_race_with_results(
            name="Browse 10k Fastest",
            race_type="10k",
            race_date=date(2025, 6, 1),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=35,
        )
        self._create_race_with_results(
            name="Browse 10k Slower",
            race_type="10k",
            race_date=date(2025, 6, 2),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=42,
        )
        self._create_race_with_results(
            name="Browse 10k Third",
            race_type="10k",
            race_date=date(2025, 6, 3),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=39,
        )
        self._create_race_with_results(
            name="Browse 10k Fourth",
            race_type="10k",
            race_date=date(2025, 6, 4),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=41,
        )
        self._create_race_with_results(
            name="Browse 10k Fifth",
            race_type="10k",
            race_date=date(2025, 6, 5),
            distance_km=10.0,
            surface_type="road",
            winner_minutes=43,
        )
        Race.objects.create(
            name="Browse Trail",
            description="Trail race",
            race_type="trail",
            date=date(2025, 6, 6),
            location="Reykjavik",
            distance_km=18.0,
            surface_type="trail",
            organizer="Tímataka",
        )

        response = self.client.get(
            "/api/races/browse",
            {
                "q": "Browse",
                "require_speed_index": "true",
                "order_by": "winning_fastest",
                "limit": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 5)
        self.assertEqual(payload["items"][0]["id"], fastest.id)
        self.assertTrue(all(item["speed_index"] is not None for item in payload["items"]))

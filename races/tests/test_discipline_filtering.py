from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase

from races.api import _build_race_speed_data
from races.models import DisciplineKeyword, Event, Race, Result, Runner


class DisciplineFilteringTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _create_result(self, race: Race, runner: Runner, minutes: int) -> Result:
        return Result.objects.create(
            race=race,
            runner=runner,
            participant_name=runner.name,
            finish_time=timedelta(minutes=minutes),
            status="finished",
        )

    def test_keyword_model_classifies_events_and_races(self):
        DisciplineKeyword.objects.update_or_create(
            normalized_snippet="criterium",
            defaults={"snippet": "criterium", "discipline": "biking", "priority": 1},
        )

        biking_event = Event.objects.create(
            name="Canon criterium mótaröðin",
            date=date(2025, 6, 1),
            url="https://timataka.net/canon-criterium/",
        )
        biking_race = Race.objects.create(
            event=biking_event,
            name="Canon criterium mótaröðin - Criterium-A",
            description="",
            race_type="other",
            date=biking_event.date,
            location="Reykjavik",
            distance_km=35.0,
            organizer="Tímataka",
        )

        self.assertEqual(biking_event.discipline, "biking")
        self.assertEqual(biking_race.discipline, "biking")

    def test_public_managers_and_endpoints_only_return_running_content(self):
        running_event = Event.objects.create(
            name="Vorhlaup Reykjavíkur",
            date=date(2025, 5, 1),
            url="https://timataka.net/vorhlaup/",
        )
        biking_event = Event.objects.create(
            name="Canon criterium mótaröðin",
            date=date(2025, 5, 2),
            url="https://timataka.net/canon-criterium/",
        )

        running_race = Race.objects.create(
            event=running_event,
            name="Vorhlaup Reykjavíkur 10k",
            description="Road race",
            race_type="10k",
            date=running_event.date,
            location="Reykjavik",
            distance_km=10.0,
            surface_type="road",
            organizer="Tímataka",
        )
        biking_race = Race.objects.create(
            event=biking_event,
            name="Canon criterium mótaröðin - Criterium-A",
            description="Bike race",
            race_type="other",
            date=biking_event.date,
            location="Reykjavik",
            distance_km=35.0,
            organizer="Tímataka",
        )

        runner = Runner.objects.create(name="Tester", birth_year=1990, gender="M")
        self._create_result(running_race, runner, 41)
        self._create_result(biking_race, runner, 55)

        self.assertEqual(list(Race.public.values_list("id", flat=True)), [running_race.id])
        self.assertEqual(list(Event.public.values_list("id", flat=True)), [running_event.id])

        search_response = self.client.get("/api/races/search", {"q": "mótaröðin", "limit": 10})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json(), [])

        latest_response = self.client.get("/api/races/events/latest", {"limit": 10})
        self.assertEqual(latest_response.status_code, 200)
        latest_payload = latest_response.json()
        self.assertEqual([item["id"] for item in latest_payload], [running_event.id])
        self.assertTrue(all(item["discipline"] == "running" for item in latest_payload))

    def test_runner_endpoints_only_count_running_races(self):
        running_event = Event.objects.create(
            name="Vetrarhlaup",
            date=date(2025, 1, 10),
            url="https://timataka.net/vetrarhlaup/",
        )
        biking_event = Event.objects.create(
            name="BMX mót",
            date=date(2025, 2, 10),
            url="https://timataka.net/bmx-mot/",
        )
        running_race = Race.objects.create(
            event=running_event,
            name="Vetrarhlaup 5k",
            description="Running race",
            race_type="5k",
            date=running_event.date,
            location="Reykjavik",
            distance_km=5.0,
            surface_type="road",
            organizer="Tímataka",
        )
        biking_race = Race.objects.create(
            event=biking_event,
            name="BMX mót",
            description="Bike race",
            race_type="other",
            date=biking_event.date,
            location="Reykjavik",
            distance_km=2.0,
            organizer="Bike Club",
        )

        runner = Runner.objects.create(name="History Runner", birth_year=1988, gender="F")
        self._create_result(running_race, runner, 24)
        self._create_result(biking_race, runner, 18)

        search_response = self.client.get("/api/races/runners/search", {"q": "History"})
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.json()
        self.assertEqual(len(search_payload), 1)
        self.assertEqual(search_payload[0]["total_races"], 1)

        detail_response = self.client.get(f"/api/races/runners/{runner.id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["total_races"], 1)
        self.assertEqual(len(detail_payload["race_history"]), 1)
        self.assertEqual(detail_payload["race_history"][0]["discipline"], "running")

    def test_speed_index_cohorts_ignore_other_disciplines(self):
        DisciplineKeyword.objects.update_or_create(
            normalized_snippet="bike",
            defaults={"snippet": "bike", "discipline": "biking", "priority": 1},
        )

        running_races = []
        for race_number in range(5):
            race = Race.objects.create(
                name=f"Vorhlaup 10k {race_number + 1}",
                description="Road race",
                race_type="10k",
                date=date(2025, 5, 1) + timedelta(days=race_number),
                location="Reykjavik",
                distance_km=10.0,
                surface_type="road",
                organizer="Tímataka",
            )
            running_races.append(race)

            for finisher in range(5):
                runner = Runner.objects.create(
                    name=f"Running Runner {race_number}-{finisher}",
                    birth_year=1980 + race_number * 10 + finisher,
                    gender="M",
                )
                self._create_result(race, runner, 40 + race_number + finisher)

        for race_number in range(5):
            race = Race.objects.create(
                name=f"Bike 10k {race_number + 1}",
                description="Bike road race",
                race_type="10k",
                date=date(2025, 6, 1) + timedelta(days=race_number),
                location="Reykjavik",
                distance_km=10.0,
                surface_type="road",
                organizer="Bike Club",
            )

            for finisher in range(5):
                runner = Runner.objects.create(
                    name=f"Bike Runner {race_number}-{finisher}",
                    birth_year=1930 + race_number * 10 + finisher,
                    gender="M",
                )
                self._create_result(race, runner, 30 + race_number + finisher)

        speed_data = _build_race_speed_data([running_races[0]])
        self.assertIn(running_races[0].id, speed_data)
        self.assertEqual(speed_data[running_races[0].id]["cohort_race_count"], 5)

    def test_backfill_disciplines_command_updates_races_and_events(self):
        DisciplineKeyword.objects.update_or_create(
            normalized_snippet="criterium",
            defaults={"snippet": "criterium", "discipline": "biking", "priority": 1},
        )

        running_event = Event.objects.create(
            name="Vorhlaup Reykjavíkur",
            date=date(2025, 5, 1),
            url="https://timataka.net/vorhlaup/",
        )
        biking_event = Event.objects.create(
            name="Canon criterium mótaröðin",
            date=date(2025, 5, 2),
            url="https://timataka.net/canon-criterium/",
        )
        running_race = Race.objects.create(
            event=running_event,
            name="Vorhlaup Reykjavíkur 10k",
            description="Road race",
            race_type="10k",
            date=running_event.date,
            location="Reykjavik",
            distance_km=10.0,
            surface_type="road",
            organizer="Tímataka",
        )
        biking_race = Race.objects.create(
            event=biking_event,
            name="Canon criterium mótaröðin - Criterium-A",
            description="Bike race",
            race_type="other",
            date=biking_event.date,
            location="Reykjavik",
            distance_km=35.0,
            organizer="Bike Club",
        )

        Race.objects.filter(id__in=[running_race.id, biking_race.id]).update(discipline='unknown')
        Event.objects.filter(id__in=[running_event.id, biking_event.id]).update(discipline='unknown')

        call_command('backfill_disciplines', stdout=StringIO())

        running_race.refresh_from_db()
        biking_race.refresh_from_db()
        running_event.refresh_from_db()
        biking_event.refresh_from_db()

        self.assertEqual(running_race.discipline, 'running')
        self.assertEqual(biking_race.discipline, 'biking')
        self.assertEqual(running_event.discipline, 'running')
        self.assertEqual(biking_event.discipline, 'biking')

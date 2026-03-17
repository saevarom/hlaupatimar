from datetime import date

from django.test import TestCase

from races.management.commands.timataka_process_results import Command
from races.models import Event, Race
from races.services import ScrapingService


class TimatakaProcessResultsCommandTests(TestCase):
    def setUp(self):
        self.command = Command()
        self.command.verbosity = 0
        self.command.overwrite = False
        self.command.include_server_errors = False
        self.command.service = ScrapingService()

    def _create_race(self, *, name: str, race_date: date, has_server_error: bool = False, results_url: str = ""):
        event = Event.objects.create(
            name=f"{name} Event",
            date=race_date,
            url=f"https://timataka.net/{name.lower().replace(' ', '-')}/",
        )
        return Race.objects.create(
            event=event,
            name=name,
            description="",
            race_type="other",
            date=race_date,
            location="Reykjavik",
            distance_km=10.0,
            organizer="Tímataka",
            results_url=results_url,
            has_server_error=has_server_error,
        )

    def test_get_races_to_process_prioritizes_recent_pending_races(self):
        oldest = self._create_race(name="Oldest", race_date=date(2024, 1, 1))
        middle = self._create_race(name="Middle", race_date=date(2025, 6, 1))
        newest = self._create_race(name="Newest", race_date=date(2026, 3, 12))
        self._create_race(
            name="Skipped Server Error",
            race_date=date(2026, 3, 13),
            has_server_error=True,
        )

        races = self.command._get_races_to_process({"limit": 2})

        self.assertEqual(list(races.values_list("id", flat=True)), [newest.id, middle.id])
        self.assertNotIn(oldest.id, list(races.values_list("id", flat=True)))

    def test_build_results_url_normalizes_start_list_urls(self):
        race = self._create_race(
            name="Powerade",
            race_date=date(2026, 3, 12),
            results_url="https://timataka.net/vetrarhlaup-2026-03-12/raslisti/?race=1&cat=overall",
        )

        self.assertEqual(
            self.command._build_results_url(race),
            "https://timataka.net/vetrarhlaup-2026-03-12/urslit/?race=1&cat=overall",
        )


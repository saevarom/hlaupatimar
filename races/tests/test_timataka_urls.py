from django.test import SimpleTestCase

from races.scraper import TimatakaScraper
from races.services import ScrapingService


class TimatakaUrlNormalizationTests(SimpleTestCase):
    def test_scraper_normalizes_start_list_urls_to_results_pages(self):
        scraper = TimatakaScraper()

        self.assertEqual(
            scraper.normalize_results_page_url(
                "https://timataka.net/vetrarhlaup-2026-03-12/raslisti/?race=1",
                ensure_overall=True,
            ),
            "https://timataka.net/vetrarhlaup-2026-03-12/urslit/?race=1&cat=overall",
        )

    def test_service_normalizes_direct_event_urls_before_saving(self):
        service = ScrapingService()

        self.assertEqual(
            service._normalize_event_url(
                "https://timataka.net/vetrarhlaup-2026-03-12/raslisti/?race=1&cat=m"
            ),
            "https://timataka.net/vetrarhlaup-2026-03-12/urslit/?race=1&cat=overall",
        )

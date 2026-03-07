import re
from collections import defaultdict

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from races.models import Race


class Command(BaseCommand):
    help = "Audit race name/distance inference mismatches and likely fallback artifacts."

    KM_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:km|k)\b", re.IGNORECASE)

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="timataka.net",
            help="Race source to audit (default: timataka.net).",
        )
        parser.add_argument(
            "--event-ids",
            nargs="+",
            type=int,
            help="Optional list of event IDs to restrict the audit.",
        )
        parser.add_argument(
            "--tolerance",
            type=float,
            default=0.25,
            help="Distance tolerance in km for mismatch checks (default: 0.25).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=25,
            help="Max rows to print per section (default: 25).",
        )

    def _parse_distance_from_text(self, text: str) -> float | None:
        normalized = (text or "").lower()
        km_match = self.KM_PATTERN.search(normalized)
        if km_match:
            try:
                return float(km_match.group(1).replace(",", "."))
            except ValueError:
                return None

        if "half marathon" in normalized or "half-marathon" in normalized or "hálf mara" in normalized:
            return 21.1
        if ("marathon" in normalized or "maraþon" in normalized) and ("half" not in normalized and "hálf" not in normalized):
            return 42.2
        return None

    def _has_explicit_km(self, text: str) -> bool:
        return bool(self.KM_PATTERN.search((text or "").lower()))

    def handle(self, *args, **options):
        source = (options.get("source") or "timataka.net").strip()
        event_ids = options.get("event_ids") or []
        tolerance = float(options.get("tolerance") or 0.25)
        top = int(options.get("top") or 25)

        queryset = Race.objects.filter(source=source).only(
            "id",
            "event_id",
            "name",
            "distance_km",
            "race_type",
            "cached_html",
            "results_url",
        )
        if event_ids:
            queryset = queryset.filter(event_id__in=event_ids)

        races = list(queryset)

        explicit_name_mismatch = []
        result_heading_mismatch = []
        ultra_fallback_candidates = []
        grouped_ultra_fallback = defaultdict(list)

        for race in races:
            stored_distance = float(race.distance_km or 0.0)
            name_distance = self._parse_distance_from_text(race.name)

            if (
                name_distance is not None
                and stored_distance > 0
                and abs(name_distance - stored_distance) > tolerance
            ):
                explicit_name_mismatch.append(
                    (
                        race.id,
                        race.event_id,
                        race.name,
                        stored_distance,
                        name_distance,
                        race.race_type,
                    )
                )

            heading = ""
            if race.cached_html:
                soup = BeautifulSoup(race.cached_html, "lxml")
                h2 = soup.select_one("div.ibox-title h2")
                if h2:
                    heading = " ".join(h2.get_text(" ", strip=True).split())

            if heading:
                heading_distance = self._parse_distance_from_text(heading)
                if (
                    heading_distance is not None
                    and stored_distance > 0
                    and abs(heading_distance - stored_distance) > tolerance
                ):
                    result_heading_mismatch.append(
                        (
                            race.id,
                            race.event_id,
                            race.name,
                            stored_distance,
                            heading,
                            heading_distance,
                            race.race_type,
                        )
                    )

                heading_lower = heading.lower()
                if (
                    heading_distance is None
                    and not self._has_explicit_km(heading)
                    and "ultra" in heading_lower
                    and stored_distance in (50.0, 55.0)
                ):
                    row = (
                        race.id,
                        race.event_id,
                        race.name,
                        stored_distance,
                        heading,
                        race.race_type,
                    )
                    ultra_fallback_candidates.append(row)
                    grouped_ultra_fallback[race.event_id].append(row)

        self.stdout.write(self.style.SUCCESS("Race inference audit summary"))
        self.stdout.write(f"source={source}")
        self.stdout.write(f"races_scanned={len(races)}")
        self.stdout.write(f"explicit_name_mismatch_count={len(explicit_name_mismatch)}")
        self.stdout.write(f"result_heading_mismatch_count={len(result_heading_mismatch)}")
        self.stdout.write(f"ultra_fallback_candidate_count={len(ultra_fallback_candidates)}")
        self.stdout.write(f"ultra_fallback_event_count={len(grouped_ultra_fallback)}")

        self.stdout.write("\nTop explicit name mismatches")
        for row in explicit_name_mismatch[:top]:
            self.stdout.write(str(row))

        self.stdout.write("\nTop result heading mismatches")
        for row in result_heading_mismatch[:top]:
            self.stdout.write(str(row))

        self.stdout.write("\nTop ultra fallback candidates")
        for row in ultra_fallback_candidates[:top]:
            self.stdout.write(str(row))

        self.stdout.write("\nUltra fallback grouped by event")
        event_rows = sorted(
            grouped_ultra_fallback.items(),
            key=lambda item: (-len(item[1]), item[0] or 0),
        )
        for event_id, rows in event_rows[:top]:
            self.stdout.write(f"event_id={event_id} count={len(rows)}")
            for row in rows[:top]:
                self.stdout.write(f"  {row}")

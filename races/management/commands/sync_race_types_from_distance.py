from django.core.management.base import BaseCommand
from django.utils import timezone

from races.models import Race


DISTANCE_RACE_TYPES = {'5k', '10k', 'half_marathon', 'marathon', 'ultra'}


class Command(BaseCommand):
    help = (
        "Sync race_type from distance_km using tightened boundaries. "
        "Updates races currently in distance-based types (or 'other')."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving changes.',
        )
        parser.add_argument(
            '--race-ids',
            nargs='+',
            type=int,
            help='Specific race IDs to process (space-separated).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of races processed.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        race_ids = options.get('race_ids')
        limit = options.get('limit')

        queryset = Race.objects.all().order_by('id')
        if race_ids:
            queryset = queryset.filter(id__in=race_ids)
        if limit:
            queryset = queryset[:limit]

        processed = 0
        updated = 0
        skipped_non_distance = 0

        for race in queryset:
            processed += 1
            current = (race.race_type or 'other').strip().lower()
            if current not in DISTANCE_RACE_TYPES and current != 'other':
                skipped_non_distance += 1
                continue

            expected = Race.infer_race_type_from_distance(
                race.distance_km,
                current_race_type='other',
            )

            if current == expected:
                continue

            updated += 1
            if dry_run:
                self.stdout.write(
                    f"Would update race {race.id}: "
                    f"{current} -> {expected} (distance={float(race.distance_km or 0.0):g}) | {race.name}"
                )
                continue

            Race.objects.filter(id=race.id).update(
                race_type=expected,
                updated_at=timezone.now(),
            )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: processed={processed}, updated={updated}, "
                f"skipped_non_distance={skipped_non_distance}"
            )
        )

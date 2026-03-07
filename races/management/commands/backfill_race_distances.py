from django.core.management.base import BaseCommand

from races.models import Race, RaceDistanceKeyword


class Command(BaseCommand):
    help = "Backfill race distance/type using dictionary snippet rules."

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
        parser.add_argument(
            '--no-race-type-sync',
            action='store_true',
            help='Only update distance_km from rules, do not adjust race_type by distance.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        race_ids = options.get('race_ids')
        limit = options.get('limit')
        no_race_type_sync = options.get('no_race_type_sync', False)

        active_rules = RaceDistanceKeyword.get_active_rules()
        if not active_rules:
            self.stdout.write(
                self.style.WARNING("No active RaceDistanceKeyword rules found. Nothing to apply.")
            )
            return

        queryset = Race.objects.all().order_by('id')
        if race_ids:
            queryset = queryset.filter(id__in=race_ids)
        if limit:
            queryset = queryset[:limit]

        processed = 0
        matched = 0
        updated = 0

        for race in queryset:
            processed += 1
            inferred_distance = Race.infer_distance_from_rules(
                name=race.name,
                description=race.description,
                location=race.location,
                distance_rules=active_rules,
            )
            if inferred_distance is None:
                continue

            matched += 1
            new_race_type = race.race_type
            if not no_race_type_sync:
                new_race_type = Race.infer_race_type_from_distance(
                    inferred_distance,
                    current_race_type=race.race_type,
                )

            distance_changed = abs(float(race.distance_km or 0.0) - float(inferred_distance)) > 1e-6
            type_changed = new_race_type != race.race_type
            if not distance_changed and not type_changed:
                continue

            updated += 1
            if dry_run:
                self.stdout.write(
                    f"Would update race {race.id}: "
                    f"distance {race.distance_km:g} -> {inferred_distance:g}, "
                    f"type {race.race_type} -> {new_race_type} | {race.name}"
                )
            else:
                race.distance_km = inferred_distance
                race.race_type = new_race_type
                race.save(update_fields=['distance_km', 'race_type', 'updated_at'])

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: processed={processed}, matched={matched}, updated={updated}, "
                f"rules={len(active_rules)}, race_type_sync={not no_race_type_sync}"
            )
        )

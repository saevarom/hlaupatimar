from django.core.management.base import BaseCommand

from races.models import Race, RaceSurfaceKeyword


class Command(BaseCommand):
    help = "Backfill or recompute race surface types (road/trail/mixed/unknown)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving changes.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recompute for all races, not just surface_type=unknown.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of races processed.',
        )
        parser.add_argument(
            '--race-ids',
            nargs='+',
            type=int,
            help='Specific race IDs to process (space-separated).',
        )
        parser.add_argument(
            '--dictionary-only',
            action='store_true',
            help='Only apply dictionary snippet rules and skip heuristic fallback.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        limit = options.get('limit')
        race_ids = options.get('race_ids')
        dictionary_only = options.get('dictionary_only', False)
        active_rules = RaceSurfaceKeyword.get_active_rules()

        if dictionary_only and not active_rules:
            self.stdout.write(
                self.style.WARNING(
                    "No active RaceSurfaceKeyword rules found. Nothing to apply in --dictionary-only mode."
                )
            )
            return

        queryset = Race.objects.all().order_by('id')
        if race_ids:
            queryset = queryset.filter(id__in=race_ids)
        if not force:
            queryset = queryset.filter(surface_type='unknown')
        if limit:
            queryset = queryset[:limit]

        processed = 0
        updated = 0
        matched = 0

        for race in queryset:
            processed += 1
            if dictionary_only:
                inferred = Race.infer_surface_type_from_rules(
                    name=race.name,
                    description=race.description,
                    location=race.location,
                    surface_rules=active_rules,
                )
                if not inferred:
                    continue
                matched += 1
            else:
                inferred = Race.infer_surface_type(
                    race_type=race.race_type,
                    name=race.name,
                    description=race.description,
                    location=race.location,
                    elevation_gain_m=race.elevation_gain_m,
                    distance_km=race.distance_km,
                    surface_rules=active_rules,
                )

            if inferred != race.surface_type:
                updated += 1
                if dry_run:
                    self.stdout.write(
                        f"Would update race {race.id}: {race.surface_type} -> {inferred} | {race.name}"
                    )
                else:
                    race.surface_type = inferred
                    race.save(update_fields=['surface_type', 'updated_at'])

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: processed={processed}, updated={updated}, "
                f"matched={matched}, rules={len(active_rules)}, "
                f"force={force}, dictionary_only={dictionary_only}"
            )
        )

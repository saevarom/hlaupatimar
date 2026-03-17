from django.core.management.base import BaseCommand
from django.utils import timezone

from races.models import DisciplineKeyword, Event, Race


class Command(BaseCommand):
    help = "Backfill or recompute race and event disciplines."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving changes.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recompute for all rows, not just discipline=unknown.',
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
            '--event-ids',
            nargs='+',
            type=int,
            help='Specific event IDs to process (space-separated).',
        )
        parser.add_argument(
            '--dictionary-only',
            action='store_true',
            help='Only apply DisciplineKeyword rules and event rollup from child races.',
        )
        parser.add_argument(
            '--no-event-sync',
            action='store_true',
            help='Only backfill race disciplines and skip event discipline updates.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        limit = options.get('limit')
        race_ids = options.get('race_ids')
        event_ids = options.get('event_ids')
        dictionary_only = options.get('dictionary_only', False)
        no_event_sync = options.get('no_event_sync', False)
        active_rules = DisciplineKeyword.get_active_rules()
        now = timezone.now()

        if dictionary_only and not active_rules:
            self.stdout.write(
                self.style.WARNING(
                    "No active DisciplineKeyword rules found. Nothing to apply in --dictionary-only mode."
                )
            )
            return

        race_queryset = Race.objects.select_related('event').order_by('id')
        if race_ids:
            race_queryset = race_queryset.filter(id__in=race_ids)
        if not force:
            race_queryset = race_queryset.filter(discipline='unknown')
        if limit:
            race_queryset = race_queryset[:limit]

        processed_races = 0
        updated_races = 0
        matched_races = 0
        impacted_event_ids: set[int] = set(event_ids or [])

        for race in race_queryset:
            processed_races += 1
            if race.event_id:
                impacted_event_ids.add(int(race.event_id))

            matched_rule = Race.infer_discipline_from_rules(
                name=race.name,
                description=race.description,
                location=race.location,
                organizer=race.organizer,
                event_name=race.event.name if race.event_id and race.event else '',
                source_url=race.source_url,
                results_url=race.results_url,
                discipline_rules=active_rules,
            )
            if matched_rule:
                matched_races += 1

            if dictionary_only:
                inferred = matched_rule
                if not inferred:
                    continue
            else:
                inferred = Race.infer_discipline(
                    race_type=race.race_type,
                    name=race.name,
                    description=race.description,
                    location=race.location,
                    organizer=race.organizer,
                    event_name=race.event.name if race.event_id and race.event else '',
                    source_url=race.source_url,
                    results_url=race.results_url,
                    current_discipline=race.discipline,
                    fallback_discipline=race.event.discipline if race.event_id and race.event else 'unknown',
                    discipline_rules=active_rules,
                )

            if inferred == race.discipline:
                continue

            updated_races += 1
            if dry_run:
                self.stdout.write(
                    f"Would update race {race.id}: {race.discipline} -> {inferred} | {race.name}"
                )
                continue

            Race.objects.filter(id=race.id).update(
                discipline=inferred,
                updated_at=now,
            )

        processed_events = 0
        updated_events = 0
        matched_events = 0
        rolled_up_events = 0

        if not no_event_sync:
            event_queryset = Event.objects.order_by('id')
            if event_ids:
                event_queryset = event_queryset.filter(id__in=event_ids)
            elif impacted_event_ids:
                event_queryset = event_queryset.filter(id__in=impacted_event_ids)
            elif not force:
                event_queryset = event_queryset.filter(discipline='unknown')

            for event in event_queryset:
                processed_events += 1
                race_disciplines = list(
                    Race.objects.filter(event_id=event.id)
                    .exclude(discipline='unknown')
                    .values_list('discipline', flat=True)
                )
                rolled_up = Event.infer_discipline_from_race_disciplines(race_disciplines)
                if rolled_up:
                    rolled_up_events += 1
                    inferred = rolled_up
                else:
                    matched_rule = Event.infer_discipline_from_rules(
                        name=event.name,
                        url=event.url,
                        discipline_rules=active_rules,
                    )
                    if matched_rule:
                        matched_events += 1

                    if dictionary_only:
                        inferred = matched_rule
                        if not inferred:
                            continue
                    else:
                        inferred = Event.infer_discipline(
                            name=event.name,
                            url=event.url,
                            current_discipline=event.discipline,
                            discipline_rules=active_rules,
                        )

                if inferred == event.discipline:
                    continue

                updated_events += 1
                if dry_run:
                    self.stdout.write(
                        f"Would update event {event.id}: {event.discipline} -> {inferred} | {event.name}"
                    )
                    continue

                Event.objects.filter(id=event.id).update(
                    discipline=inferred,
                    updated_at=now,
                )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: races_processed={processed_races}, races_updated={updated_races}, "
                f"race_rule_matches={matched_races}, events_processed={processed_events}, "
                f"events_updated={updated_events}, event_rule_matches={matched_events}, "
                f"event_rollups={rolled_up_events}, rules={len(active_rules)}, "
                f"force={force}, dictionary_only={dictionary_only}, event_sync={not no_event_sync}"
            )
        )

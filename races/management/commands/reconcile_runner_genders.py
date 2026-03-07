import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from races.corsa_scraper import CorsaScraper
from races.models import Race, Result, Runner, RunnerAlias


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _to_gender_code(raw_gender: str) -> str:
    normalized = str(raw_gender or "").strip().lower()
    if normalized == "male":
        return "M"
    if normalized == "female":
        return "F"
    return ""


class Command(BaseCommand):
    help = (
        "Reconcile Runner.gender from explicit corsa participant genders found in cached race HTML. "
        "Uses per-runner vote totals and only updates when confidence threshold is met."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without saving changes.",
        )
        parser.add_argument(
            "--runner-ids",
            nargs="+",
            type=int,
            help="Specific runner IDs to reconcile.",
        )
        parser.add_argument(
            "--runner-stable-ids",
            nargs="+",
            type=str,
            help="Specific runner stable IDs to reconcile.",
        )
        parser.add_argument(
            "--race-ids",
            nargs="+",
            type=int,
            help="Only use these corsa race IDs as evidence.",
        )
        parser.add_argument(
            "--min-votes",
            type=int,
            default=2,
            help="Minimum explicit corsa votes required for changing a runner gender (default: 2).",
        )

    @staticmethod
    def _status_priority(status: str) -> int:
        normalized = str(status or "").lower()
        priorities = {
            "finished": 4,
            "dnf": 3,
            "dns": 2,
            "dq": 1,
        }
        return priorities.get(normalized, 0)

    @staticmethod
    def _expected_stable_id(runner: Runner, resolved_gender: str) -> str | None:
        if not runner.birth_year:
            return None
        return Runner.build_stable_id(runner.name, runner.birth_year, resolved_gender)

    @staticmethod
    def _upsert_alias(
        *,
        alias_stable_id: str | None,
        canonical_runner: Runner,
        reason: str,
        source_runner: Runner | None = None,
        alias_runner_id: int | None = None,
        dry_run: bool = False,
    ) -> None:
        if not alias_stable_id:
            return
        alias_stable_id = alias_stable_id.strip()
        if not alias_stable_id:
            return
        if dry_run:
            return

        existing_by_runner_id = (
            RunnerAlias.objects.filter(alias_runner_id=alias_runner_id).first()
            if alias_runner_id is not None
            else None
        )
        if existing_by_runner_id and existing_by_runner_id.alias_stable_id != alias_stable_id:
            existing_by_runner_id.alias_stable_id = alias_stable_id
            existing_by_runner_id.canonical_runner = canonical_runner
            existing_by_runner_id.source_runner = source_runner
            existing_by_runner_id.reason = reason
            existing_by_runner_id.is_active = True
            existing_by_runner_id.save()
            return

        defaults = {
            "canonical_runner": canonical_runner,
            "source_runner": source_runner,
            "alias_runner_id": alias_runner_id,
            "reason": reason,
            "is_active": True,
        }
        RunnerAlias.objects.update_or_create(
            alias_stable_id=alias_stable_id,
            defaults=defaults,
        )

    def _merge_result_records(self, target_result: Result, source_result: Result, dry_run: bool) -> tuple[bool, int]:
        result_updated = False

        if not target_result.bib_number and source_result.bib_number:
            target_result.bib_number = source_result.bib_number
            result_updated = True
        if not target_result.club and source_result.club:
            target_result.club = source_result.club
            result_updated = True
        if target_result.chip_time is None and source_result.chip_time is not None:
            target_result.chip_time = source_result.chip_time
            result_updated = True
        if target_result.time_behind is None and source_result.time_behind is not None:
            target_result.time_behind = source_result.time_behind
            result_updated = True
        if self._status_priority(source_result.status) > self._status_priority(target_result.status):
            target_result.status = source_result.status
            result_updated = True
        if source_result.finish_time and (
            not target_result.finish_time
            or (
                target_result.status == "finished"
                and source_result.status == "finished"
                and source_result.finish_time < target_result.finish_time
            )
        ):
            target_result.finish_time = source_result.finish_time
            result_updated = True

        splits_created = 0
        if not dry_run:
            for split in source_result.splits.all():
                _, created = target_result.splits.get_or_create(
                    split_name=split.split_name,
                    defaults={
                        "distance_km": split.distance_km,
                        "split_time": split.split_time,
                    },
                )
                if created:
                    splits_created += 1
            if result_updated:
                target_result.save()
        else:
            existing_names = set(target_result.splits.values_list("split_name", flat=True))
            for split in source_result.splits.all():
                if split.split_name not in existing_names:
                    splits_created += 1

        return result_updated, splits_created

    def _merge_runner_into_target(self, source_runner: Runner, target_runner: Runner, dry_run: bool) -> dict:
        stats = {
            "moved_results": 0,
            "merged_results": 0,
            "updated_results": 0,
            "created_splits": 0,
            "deleted_source_runner": 0,
        }
        if source_runner.id == target_runner.id:
            return stats

        source_results = list(
            Result.objects.filter(runner=source_runner)
            .select_related("race")
            .prefetch_related("splits")
        )
        target_results_by_race = {
            result.race_id: result
            for result in Result.objects.filter(runner=target_runner).prefetch_related("splits")
        }

        for source_result in source_results:
            target_result = target_results_by_race.get(source_result.race_id)
            if target_result:
                stats["merged_results"] += 1
                result_updated, splits_created = self._merge_result_records(
                    target_result=target_result,
                    source_result=source_result,
                    dry_run=dry_run,
                )
                stats["created_splits"] += splits_created
                if result_updated:
                    stats["updated_results"] += 1
                if not dry_run:
                    source_result.delete()
                continue

            stats["moved_results"] += 1
            if not dry_run:
                source_result.runner = target_runner
                source_result.save(update_fields=["runner", "updated_at"])

        if not dry_run:
            source_runner.delete()
            stats["deleted_source_runner"] = 1

        return stats

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        race_ids = options.get("race_ids")
        min_votes = max(1, int(options.get("min_votes") or 2))

        target_runner_ids = set(options.get("runner_ids") or [])
        runner_stable_ids = options.get("runner_stable_ids") or []
        if runner_stable_ids:
            matched_ids = list(
                Runner.objects.filter(stable_id__in=runner_stable_ids).values_list("id", flat=True)
            )
            target_runner_ids.update(matched_ids)
            missing = sorted(set(runner_stable_ids) - set(
                Runner.objects.filter(stable_id__in=runner_stable_ids).values_list("stable_id", flat=True)
            ))
            for stable_id in missing:
                self.stdout.write(self.style.WARNING(f"Runner not found for stable_id={stable_id}"))

        race_queryset = Race.objects.filter(source="corsa.is").order_by("id")
        if race_ids:
            race_queryset = race_queryset.filter(id__in=race_ids)
        if target_runner_ids and not race_ids:
            race_queryset = race_queryset.filter(results__runner_id__in=target_runner_ids).distinct()

        scraper = CorsaScraper()
        votes = defaultdict(lambda: {"M": 0, "F": 0})

        processed_races = 0
        skipped_no_cache = 0
        parse_errors = 0
        matched_rows = 0
        unmatched_rows = 0
        ignored_rows = 0

        for race in race_queryset.iterator():
            html_content = race.cached_html or ""
            if not html_content.strip():
                skipped_no_cache += 1
                continue

            processed_races += 1
            try:
                parsed_rows = scraper._extract_results_from_html(
                    html_content,
                    race.results_url or race.source_url,
                )
            except Exception as exc:
                parse_errors += 1
                self.stdout.write(
                    self.style.WARNING(f"Failed parsing race {race.id}: {exc}")
                )
                continue

            race_results = list(
                Result.objects.filter(race=race).select_related("runner")
            )
            by_bib = defaultdict(list)
            by_name = defaultdict(list)
            for race_result in race_results:
                if not race_result.runner_id:
                    continue
                bib_number = (race_result.bib_number or "").strip()
                if bib_number:
                    by_bib[bib_number].append(race_result)
                runner_name_key = _normalize_name(race_result.runner.name)
                if runner_name_key:
                    by_name[runner_name_key].append(race_result)

            for row in parsed_rows:
                gender_code = _to_gender_code(row.get("gender"))
                if not gender_code:
                    ignored_rows += 1
                    continue

                bib_number = str(row.get("bib_number") or "").strip()
                name_key = _normalize_name(str(row.get("name") or ""))

                matched_result = None
                if bib_number and len(by_bib.get(bib_number, [])) == 1:
                    matched_result = by_bib[bib_number][0]
                elif name_key and len(by_name.get(name_key, [])) == 1:
                    matched_result = by_name[name_key][0]
                else:
                    candidates = []
                    if bib_number:
                        candidates.extend(by_bib.get(bib_number, []))
                    if name_key:
                        name_candidates = by_name.get(name_key, [])
                        if candidates:
                            candidate_ids = {candidate.id for candidate in candidates}
                            candidates = [
                                candidate for candidate in name_candidates if candidate.id in candidate_ids
                            ]
                        else:
                            candidates.extend(name_candidates)
                    unique_candidates = {candidate.id: candidate for candidate in candidates}
                    if len(unique_candidates) == 1:
                        matched_result = next(iter(unique_candidates.values()))

                if not matched_result or not matched_result.runner_id:
                    unmatched_rows += 1
                    continue

                runner_id = matched_result.runner_id
                if target_runner_ids and runner_id not in target_runner_ids:
                    continue

                votes[runner_id][gender_code] += 1
                matched_rows += 1

        runners_by_id = Runner.objects.in_bulk(votes.keys())
        considered = 0
        updated = 0
        unchanged = 0
        merged_runners = 0
        moved_results = 0
        merged_results = 0
        updated_results = 0
        created_splits = 0
        deleted_source_runners = 0
        skipped_low_votes = 0
        skipped_tie = 0

        for runner_id, counts in votes.items():
            runner = runners_by_id.get(runner_id)
            if not runner:
                continue
            if not Runner.objects.filter(id=runner.id).exists():
                # Runner may already have been merged/deleted in this run.
                continue

            male_votes = counts["M"]
            female_votes = counts["F"]
            total_votes = male_votes + female_votes
            if total_votes < min_votes:
                skipped_low_votes += 1
                continue
            if male_votes == female_votes:
                skipped_tie += 1
                continue

            considered += 1
            resolved_gender = "M" if male_votes > female_votes else "F"
            expected_stable_id = self._expected_stable_id(runner, resolved_gender)
            needs_gender_update = runner.gender != resolved_gender
            needs_stable_update = runner.stable_id != expected_stable_id
            if not needs_gender_update and not needs_stable_update:
                unchanged += 1
                continue

            conflict_runner = None
            if expected_stable_id:
                conflict_runner = Runner.objects.filter(stable_id=expected_stable_id).exclude(id=runner.id).first()

            if conflict_runner:
                merge_label = (
                    f"runner {runner.id} ({runner.stable_id or '-'}) -> "
                    f"runner {conflict_runner.id} ({conflict_runner.stable_id or '-'})"
                )
                if dry_run:
                    self.stdout.write(
                        f"Would merge {merge_label} after resolving gender to {resolved_gender} "
                        f"(M={male_votes}, F={female_votes})"
                    )
                else:
                    with transaction.atomic():
                        self._upsert_alias(
                            alias_stable_id=runner.stable_id,
                            alias_runner_id=runner.id,
                            source_runner=runner,
                            canonical_runner=conflict_runner,
                            reason="gender_reconcile_merge",
                            dry_run=False,
                        )
                        merge_stats = self._merge_runner_into_target(
                            source_runner=runner,
                            target_runner=conflict_runner,
                            dry_run=False,
                        )
                        if conflict_runner.gender != resolved_gender:
                            conflict_runner.gender = resolved_gender
                            conflict_runner.save()
                    moved_results += merge_stats["moved_results"]
                    merged_results += merge_stats["merged_results"]
                    updated_results += merge_stats["updated_results"]
                    created_splits += merge_stats["created_splits"]
                    deleted_source_runners += merge_stats["deleted_source_runner"]
                    merged_runners += 1
                    updated += 1
                    self.stdout.write(
                        f"Merged {merge_label} and resolved gender={resolved_gender} "
                        f"(M={male_votes}, F={female_votes})"
                    )
                continue

            current_stable = runner.stable_id or "-"
            if dry_run:
                self.stdout.write(
                    f"Would normalize runner {runner.id} ({current_stable}) {runner.name}: "
                    f"gender {runner.gender or '-'} -> {resolved_gender}, "
                    f"stable_id {current_stable} -> {expected_stable_id or '-'} "
                    f"(M={male_votes}, F={female_votes})"
                )
                continue

            old_stable_id = runner.stable_id
            runner.gender = resolved_gender
            runner.save()
            if old_stable_id and old_stable_id != runner.stable_id:
                self._upsert_alias(
                    alias_stable_id=old_stable_id,
                    alias_runner_id=None,
                    source_runner=None,
                    canonical_runner=runner,
                    reason="gender_reconcile_stable_id_change",
                    dry_run=False,
                )
            updated += 1
            self.stdout.write(
                f"Normalized runner {runner.id} {runner.name}: "
                f"gender={runner.gender}, stable_id={runner.stable_id or '-'} "
                f"(M={male_votes}, F={female_votes})"
            )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: races_processed={processed_races}, skipped_no_cache={skipped_no_cache}, "
                f"parse_errors={parse_errors}, matched_rows={matched_rows}, "
                f"unmatched_rows={unmatched_rows}, ignored_rows={ignored_rows}, "
                f"runners_with_votes={len(votes)}, considered={considered}, "
                f"updated={updated}, unchanged={unchanged}, merged_runners={merged_runners}, "
                f"moved_results={moved_results}, merged_results={merged_results}, "
                f"updated_results={updated_results}, created_splits={created_splits}, "
                f"deleted_source_runners={deleted_source_runners}, "
                f"skipped_low_votes={skipped_low_votes}, skipped_tie={skipped_tie}, "
                f"min_votes={min_votes}"
            )
        )

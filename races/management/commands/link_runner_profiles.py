from django.core.management.base import BaseCommand, CommandError

from races.models import Runner, RunnerAlias


class Command(BaseCommand):
    help = "Link a duplicate runner profile to a canonical/default runner profile."

    def add_arguments(self, parser):
        parser.add_argument("--source-id", type=int, help="Source (duplicate) runner numeric ID.")
        parser.add_argument("--source-stable-id", type=str, help="Source (duplicate) runner stable ID.")
        parser.add_argument(
            "--alias-stable-id",
            action="append",
            dest="alias_stable_ids",
            type=str,
            help=(
                "Alias stable ID (for deleted/legacy source profiles). "
                "Can be repeated and/or comma-separated."
            ),
        )
        parser.add_argument("--alias-runner-id", type=int, help="Alias numeric runner ID (for deleted/legacy source profiles).")
        parser.add_argument("--canonical-id", type=int, help="Canonical/default runner numeric ID.")
        parser.add_argument("--canonical-stable-id", type=str, help="Canonical/default runner stable ID.")
        parser.add_argument("--reason", type=str, default="manual_link", help="Reason for linking.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving.",
        )

    @staticmethod
    def _resolve_runner(*, runner_id: int | None, stable_id: str | None, label: str) -> Runner:
        if runner_id is None and not stable_id:
            raise CommandError(f"Provide either --{label}-id or --{label}-stable-id.")

        runner = None
        if runner_id is not None:
            runner = Runner.objects.filter(id=runner_id).first()
        if not runner and stable_id:
            runner = Runner.objects.filter(stable_id=stable_id).first()
        if not runner:
            raise CommandError(f"{label.capitalize()} runner not found.")
        return runner

    @staticmethod
    def _parse_alias_stable_ids(raw_values: list[str] | None) -> list[str]:
        values = raw_values or []
        parsed: list[str] = []
        seen = set()
        for value in values:
            for token in (value or "").split(","):
                stable_id = token.strip()
                if not stable_id or stable_id in seen:
                    continue
                parsed.append(stable_id)
                seen.add(stable_id)
        return parsed

    @staticmethod
    def _upsert_alias(
        *,
        alias_stable_id: str,
        alias_runner_id: int | None,
        source: Runner | None,
        canonical: Runner,
        reason: str,
    ) -> tuple[RunnerAlias, bool]:
        alias_defaults = {
            "alias_runner_id": alias_runner_id,
            "source_runner": source,
            "canonical_runner": canonical,
            "reason": reason,
            "is_active": True,
        }
        existing_by_runner_id = (
            RunnerAlias.objects.filter(alias_runner_id=alias_runner_id).first()
            if alias_runner_id is not None
            else None
        )
        if existing_by_runner_id and existing_by_runner_id.alias_stable_id != alias_stable_id:
            existing_by_runner_id.alias_stable_id = alias_stable_id
            existing_by_runner_id.source_runner = source
            existing_by_runner_id.canonical_runner = canonical
            existing_by_runner_id.reason = reason
            existing_by_runner_id.is_active = True
            existing_by_runner_id.save()
            return existing_by_runner_id, False
        return RunnerAlias.objects.update_or_create(
            alias_stable_id=alias_stable_id,
            defaults=alias_defaults,
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        reason = (options.get("reason") or "manual_link").strip()[:255]

        canonical = self._resolve_runner(
            runner_id=options.get("canonical_id"),
            stable_id=options.get("canonical_stable_id"),
            label="canonical",
        )

        source = None
        source_id = options.get("source_id")
        source_stable_id = options.get("source_stable_id")
        alias_stable_ids = self._parse_alias_stable_ids(options.get("alias_stable_ids"))
        alias_runner_id = options.get("alias_runner_id")

        if source_id is not None or source_stable_id:
            source = self._resolve_runner(
                runner_id=source_id,
                stable_id=source_stable_id,
                label="source",
            )
            if source.id == canonical.id:
                raise CommandError("Source and canonical runner must be different.")
            if not source.stable_id:
                raise CommandError("Source runner has no stable_id, cannot create stable alias mapping.")
            alias_stable_ids = [source.stable_id]
            alias_runner_id = source.id
        elif not alias_stable_ids:
            raise CommandError(
                "Provide source runner (--source-id/--source-stable-id) "
                "or explicit alias (--alias-stable-id, repeatable)."
            )

        if alias_runner_id is not None and len(alias_stable_ids) > 1:
            raise CommandError("--alias-runner-id can only be used with a single --alias-stable-id.")

        for alias_stable_id in alias_stable_ids:
            if alias_stable_id == canonical.stable_id:
                raise CommandError("Alias stable ID cannot be the same as canonical stable ID.")

        created_count = 0
        updated_count = 0
        for index, alias_stable_id in enumerate(alias_stable_ids):
            current_alias_runner_id = alias_runner_id if index == 0 else None
            if dry_run:
                self.stdout.write(
                    f"Would link alias {alias_stable_id} ({current_alias_runner_id or '-'}) -> "
                    f"canonical runner {canonical.id} ({canonical.stable_id or '-'}) "
                    f"reason={reason}"
                )
                continue

            alias, created = self._upsert_alias(
                alias_stable_id=alias_stable_id,
                alias_runner_id=current_alias_runner_id,
                source=source,
                canonical=canonical,
                reason=reason,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{action} link: alias={alias.alias_stable_id} "
                    f"source={source.id if source else (current_alias_runner_id or '-')} -> canonical={canonical.id}"
                )
            )

        if not dry_run and len(alias_stable_ids) > 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Completed linking {len(alias_stable_ids)} aliases "
                    f"(created={created_count}, updated={updated_count}) to canonical={canonical.id}"
                )
            )

from django.core.management.base import BaseCommand, CommandError
from races.models import Runner


class Command(BaseCommand):
    help = 'Show race history for a runner'

    def add_arguments(self, parser):
        parser.add_argument('runner_name', type=str, nargs='?', help='Name of the runner (partial matches allowed)')
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of results to show'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output results as JSON'
        )
        parser.add_argument(
            '--runner-id',
            type=int,
            help='Specify runner by ID instead of name'
        )

    def handle(self, *args, **options):
        try:
            if options['runner_id']:
                # Get runner by ID
                try:
                    runner = Runner.objects.get(id=options['runner_id'])
                except Runner.DoesNotExist:
                    raise CommandError(f"No runner found with ID {options['runner_id']}")
            elif options['runner_name']:
                # Find runners by name
                runners = Runner.objects.filter(
                    name__icontains=options['runner_name']
                ).filter(results__isnull=False).distinct()
                
                if not runners.exists():
                    raise CommandError(f"No runners found with name containing '{options['runner_name']}' who have race results.")
                
                if runners.count() > 1:
                    self.stdout.write(f"Found {runners.count()} runners with name containing '{options['runner_name']}':")
                    for runner in runners:
                        self.stdout.write(f"  ID {runner.id}: {runner} - {runner.results.count()} results")
                    raise CommandError("Multiple runners found. Please use --runner-id to specify which one.")
                
                runner = runners.first()
            else:
                raise CommandError("Please provide either runner_name or --runner-id")

            if options['json']:
                self._output_json(runner, options['limit'])
            else:
                self._output_formatted(runner, options['limit'])

        except Exception as e:
            raise CommandError(f"Error: {e}")

    def _output_json(self, runner, limit):
        """Output race history as JSON"""
        import json
        
        summary = runner.get_race_history_summary()
        if limit:
            summary = summary[:limit]
        
        self.stdout.write(json.dumps(summary, indent=2, default=str))

    def _output_formatted(self, runner, limit):
        """Output race history in a formatted, human-readable way"""
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS(f"RACE HISTORY FOR {runner.name}"))
        if runner.birth_year:
            self.stdout.write(f"Born: {runner.birth_year}")
        if runner.gender:
            self.stdout.write(f"Gender: {runner.get_gender_display()}")
        self.stdout.write(f"Total races: {runner.results.count()}")
        self.stdout.write(self.style.SUCCESS(f"{'='*60}\n"))
        
        # Get race history
        history = runner.get_race_history()
        if limit:
            history = history[:limit]
            self.stdout.write(self.style.WARNING(f"Showing first {limit} results:\n"))
        
        for i, result in enumerate(history, 1):
            race = result.race
            event = race.event
            
            # Race header
            self.stdout.write(self.style.HTTP_INFO(f"{i}. {race.date} - {race.name}"))
            
            if event:
                self.stdout.write(f"   Event: {event.name}")
            self.stdout.write(f"   Distance: {race.distance_km}km")
            self.stdout.write(f"   Location: {race.location}")
            
            # Result details
            self.stdout.write(f"   Finish Time: {self.style.SUCCESS(str(result.finish_time))}")
            self.stdout.write(f"   Status: {result.get_status_display()}")
            
            if result.bib_number:
                self.stdout.write(f"   Bib: {result.bib_number}")
            if result.club:
                self.stdout.write(f"   Club: {result.club}")
            
            # Show splits if available
            splits = result.splits.all()
            if splits:
                self.stdout.write(f"   Splits ({splits.count()}):")
                for split in splits:
                    distance_str = f" ({split.distance_km}km)" if split.distance_km else ""
                    self.stdout.write(f"     - {split.split_name}{distance_str}: {split.split_time}")
            
            self.stdout.write("")  # Empty line between results

from django.core.management.base import BaseCommand
from races.models import Race, Result, Runner, Split


class Command(BaseCommand):
    help = 'Display a summary of races, results, and runners in the database'

    def handle(self, *args, **options):
        # Count totals
        race_count = Race.objects.count()
        result_count = Result.objects.count()
        runner_count = Runner.objects.count()
        split_count = Split.objects.count()
        
        self.stdout.write(self.style.SUCCESS(f'\n=== TIMATAKA DATABASE SUMMARY ==='))
        self.stdout.write(f'Total Races: {race_count}')
        self.stdout.write(f'Total Runners: {runner_count}')
        self.stdout.write(f'Total Results: {result_count}')
        self.stdout.write(f'Total Splits: {split_count}')
        
        # Show races with result counts
        self.stdout.write(f'\n=== RACES ===')
        for race in Race.objects.all().order_by('date'):
            result_count = race.results.count()
            self.stdout.write(f'ID {race.id}: {race.name} ({race.date}) - {result_count} results')
        
        # Show sample runners
        self.stdout.write(f'\n=== SAMPLE RUNNERS ===')
        for runner in Runner.objects.all()[:5]:
            result_count = runner.results.count()
            self.stdout.write(f'{runner.name} ({runner.birth_year}) - {result_count} race(s)')
        
        if runner_count > 5:
            self.stdout.write(f'... and {runner_count - 5} more runners')
        
        # Show races with most participants
        races_with_results = Race.objects.filter(results__isnull=False).distinct()
        if races_with_results.exists():
            self.stdout.write(f'\n=== RACE PARTICIPATION ===')
            for race in races_with_results:
                participant_count = race.results.count()
                avg_splits = race.results.first().splits.count() if race.results.first() else 0
                self.stdout.write(f'{race.name}: {participant_count} participants, {avg_splits} split points')

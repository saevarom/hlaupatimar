#!/usr/bin/env python3
"""
Django management command to manage races with server errors.

This command allows you to:
- List races with server errors
- Clear error flags for specific races
- Mark races as having server errors
- Show statistics about server errors
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from races.models import Race

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage races with server errors (500, 404, etc.)'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # List races with server errors
        list_parser = subparsers.add_parser('list', help='List races with server errors')
        list_parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of races to show'
        )
        
        # Clear error flags
        clear_parser = subparsers.add_parser('clear', help='Clear server error flags')
        clear_parser.add_argument(
            '--race-ids',
            nargs='+',
            type=int,
            help='Specific race IDs to clear (space-separated)'
        )
        clear_parser.add_argument(
            '--all',
            action='store_true',
            help='Clear all server error flags'
        )
        
        # Show statistics
        stats_parser = subparsers.add_parser('stats', help='Show server error statistics')
        
        # Mark races with errors (for testing)
        mark_parser = subparsers.add_parser('mark', help='Mark races as having server errors')
        mark_parser.add_argument(
            '--race-ids',
            nargs='+',
            type=int,
            required=True,
            help='Race IDs to mark with server errors (space-separated)'
        )
        mark_parser.add_argument(
            '--error-code',
            type=int,
            default=500,
            help='Error code to set (default: 500)'
        )

    def handle(self, *args, **options):
        action = options.get('action')
        
        if not action:
            self.stdout.write(
                self.style.ERROR("Please specify an action: list, clear, stats, or mark")
            )
            return
        
        if action == 'list':
            self._list_error_races(options)
        elif action == 'clear':
            self._clear_error_flags(options)
        elif action == 'stats':
            self._show_statistics()
        elif action == 'mark':
            self._mark_error_races(options)
        else:
            self.stdout.write(
                self.style.ERROR(f"Unknown action: {action}")
            )

    def _list_error_races(self, options):
        """List races with server errors"""
        races = Race.objects.filter(has_server_error=True).order_by('-last_error_at')
        
        if options.get('limit'):
            races = races[:options['limit']]
        
        total_count = Race.objects.filter(has_server_error=True).count()
        showing_count = races.count()
        
        self.stdout.write(f"\n=== RACES WITH SERVER ERRORS ===")
        self.stdout.write(f"Showing {showing_count} of {total_count} races with server errors\n")
        
        if not races.exists():
            self.stdout.write(self.style.SUCCESS("No races with server errors found!"))
            return
        
        for race in races:
            error_info = f"Error {race.last_error_code}" if race.last_error_code else "Unknown error"
            error_time = race.last_error_at.strftime('%Y-%m-%d %H:%M') if race.last_error_at else "Unknown"
            
            self.stdout.write(
                f"ID: {race.id:4d} | {race.name:40s} | {error_info:12s} | "
                f"Count: {race.error_count:2d} | Last: {error_time}"
            )
            
            if race.last_error_message and len(race.last_error_message) < 100:
                self.stdout.write(f"      Message: {race.last_error_message}")

    def _clear_error_flags(self, options):
        """Clear server error flags for races"""
        if options.get('all'):
            # Clear all error flags
            count = Race.objects.filter(has_server_error=True).update(
                has_server_error=False,
                last_error_code=None,
                last_error_message='',
                error_count=0,
                last_error_at=None
            )
            self.stdout.write(
                self.style.SUCCESS(f"Cleared server error flags for {count} races")
            )
        elif options.get('race_ids'):
            # Clear specific races
            race_ids = options['race_ids']
            races = Race.objects.filter(id__in=race_ids, has_server_error=True)
            count = races.update(
                has_server_error=False,
                last_error_code=None,
                last_error_message='',
                error_count=0,
                last_error_at=None
            )
            self.stdout.write(
                self.style.SUCCESS(f"Cleared server error flags for {count} races")
            )
            
            # Show which races weren't found
            found_ids = set(races.values_list('id', flat=True))
            not_found = set(race_ids) - found_ids
            if not_found:
                self.stdout.write(
                    self.style.WARNING(f"Race IDs not found with errors: {list(not_found)}")
                )
        else:
            self.stdout.write(
                self.style.ERROR("Please specify --race-ids or --all")
            )

    def _show_statistics(self):
        """Show server error statistics"""
        total_races = Race.objects.count()
        error_races = Race.objects.filter(has_server_error=True).count()
        
        # Error code breakdown
        error_codes = Race.objects.filter(has_server_error=True).values_list(
            'last_error_code', flat=True
        )
        code_counts = {}
        for code in error_codes:
            if code:
                code_counts[code] = code_counts.get(code, 0) + 1
        
        # Recent errors (last 7 days)
        week_ago = timezone.now() - timezone.timedelta(days=7)
        recent_errors = Race.objects.filter(
            has_server_error=True,
            last_error_at__gte=week_ago
        ).count()
        
        self.stdout.write(f"\n=== SERVER ERROR STATISTICS ===")
        self.stdout.write(f"Total races: {total_races}")
        self.stdout.write(f"Races with server errors: {error_races}")
        self.stdout.write(f"Error percentage: {(error_races/total_races*100):.1f}%")
        self.stdout.write(f"Recent errors (7 days): {recent_errors}")
        
        if code_counts:
            self.stdout.write(f"\nError code breakdown:")
            for code, count in sorted(code_counts.items()):
                self.stdout.write(f"  {code}: {count} races")

    def _mark_error_races(self, options):
        """Mark specific races as having server errors"""
        race_ids = options['race_ids']
        error_code = options['error_code']
        
        races = Race.objects.filter(id__in=race_ids)
        found_ids = set(races.values_list('id', flat=True))
        not_found = set(race_ids) - found_ids
        
        if not_found:
            self.stdout.write(
                self.style.WARNING(f"Race IDs not found: {list(not_found)}")
            )
        
        if races.exists():
            count = races.update(
                has_server_error=True,
                last_error_code=error_code,
                last_error_message=f'Manually marked with error code {error_code}',
                error_count=1,
                last_error_at=timezone.now()
            )
            self.stdout.write(
                self.style.SUCCESS(f"Marked {count} races with server error {error_code}")
            )

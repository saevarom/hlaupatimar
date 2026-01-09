#!/usr/bin/env python3
"""
Django management command to show HTML cache statistics.

This command provides information about cached HTML content for Events and Races,
helping to understand cache utilization and identify opportunities for optimization.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Q
from races.models import Event, Race


class Command(BaseCommand):
    help = 'Show HTML cache statistics for Events and Races'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-cache',
            action='store_true',
            help='Clear all cached HTML content'
        )

    def handle(self, *args, **options):
        clear_cache = options.get('clear_cache', False)
        
        if clear_cache:
            self._clear_all_cache()
            return
        
        self.stdout.write("HTML Cache Statistics")
        self.stdout.write("=" * 50)
        
        # Event cache statistics
        self._show_event_cache_stats()
        
        self.stdout.write()
        
        # Race cache statistics
        self._show_race_cache_stats()

    def _show_event_cache_stats(self):
        """Show cache statistics for Events"""
        total_events = Event.objects.count()
        cached_events = Event.objects.exclude(cached_html='').exclude(cached_html__isnull=True).count()
        
        # Calculate total cache size
        cached_html_sizes = Event.objects.exclude(cached_html='').exclude(cached_html__isnull=True).values_list('cached_html', flat=True)
        total_cache_size = sum(len(html) for html in cached_html_sizes)
        
        self.stdout.write("📄 EVENT CACHE STATISTICS")
        self.stdout.write(f"  Total events: {total_events}")
        self.stdout.write(f"  Cached events: {cached_events}")
        self.stdout.write(f"  Cache coverage: {(cached_events/total_events*100):.1f}%" if total_events > 0 else "Cache coverage: 0%")
        self.stdout.write(f"  Total cache size: {self._format_bytes(total_cache_size)}")
        
        if cached_events > 0:
            avg_cache_size = total_cache_size / cached_events
            self.stdout.write(f"  Average cache size: {self._format_bytes(avg_cache_size)}")

    def _show_race_cache_stats(self):
        """Show cache statistics for Races"""
        total_races = Race.objects.count()
        cached_races = Race.objects.exclude(cached_html='').exclude(cached_html__isnull=True).count()
        
        # Calculate total cache size
        cached_html_sizes = Race.objects.exclude(cached_html='').exclude(cached_html__isnull=True).values_list('cached_html', flat=True)
        total_cache_size = sum(len(html) for html in cached_html_sizes)
        
        self.stdout.write("🏃 RACE CACHE STATISTICS")
        self.stdout.write(f"  Total races: {total_races}")
        self.stdout.write(f"  Cached races: {cached_races}")
        self.stdout.write(f"  Cache coverage: {(cached_races/total_races*100):.1f}%" if total_races > 0 else "Cache coverage: 0%")
        self.stdout.write(f"  Total cache size: {self._format_bytes(total_cache_size)}")
        
        if cached_races > 0:
            avg_cache_size = total_cache_size / cached_races
            self.stdout.write(f"  Average cache size: {self._format_bytes(avg_cache_size)}")

    def _clear_all_cache(self):
        """Clear all cached HTML content"""
        self.stdout.write("Clearing all cached HTML content...")
        
        # Clear event cache
        events_updated = Event.objects.exclude(cached_html='').exclude(cached_html__isnull=True).update(
            cached_html='',
            html_fetched_at=None
        )
        
        # Clear race cache
        races_updated = Race.objects.exclude(cached_html='').exclude(cached_html__isnull=True).update(
            cached_html='',
            html_fetched_at=None
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Cache cleared!\n"
                f"  Events cleared: {events_updated}\n"
                f"  Races cleared: {races_updated}"
            )
        )

    def _format_bytes(self, bytes_count):
        """Format byte count in human readable format"""
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.1f} GB"

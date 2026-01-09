"""
Django management command to discover events from corsa.is results page.

This command scrapes the main corsa.is results page to find racing events
and saves them as Event records in the database. Each event can contain
multiple race categories.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from races.services import ScrapingService
from races.corsa_scraper import CorsaScrapingError
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Discover events from corsa.is results page and save them to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', 
            action='store_true', 
            help='Show what would be discovered without saving to database'
        )
        parser.add_argument(
            '--force-refresh', 
            action='store_true', 
            help='Bypass cache and fetch fresh data from corsa.is'
        )
        parser.add_argument(
            '--overwrite', 
            action='store_true', 
            help='Update existing events with new data'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of events to process (useful for testing)'
        )

    def handle(self, *args, **options):
        verbosity = options['verbosity']
        dry_run = options['dry_run']
        force_refresh = options['force_refresh']
        overwrite = options['overwrite']
        limit = options['limit']

        # Configure logging based on verbosity
        if verbosity >= 2:
            logging.basicConfig(level=logging.DEBUG)
        elif verbosity >= 1:
            logging.basicConfig(level=logging.INFO)
        else:
            logging.basicConfig(level=logging.WARNING)

        self.stdout.write(
            self.style.SUCCESS(f"🔍 Discovering events from corsa.is...")
        )
        
        if dry_run:
            self.stdout.write("📋 DRY RUN MODE - No data will be saved")
        if force_refresh:
            self.stdout.write("🔄 FORCE REFRESH - Bypassing cache")
        if overwrite:
            self.stdout.write("✏️ OVERWRITE MODE - Will update existing events")
        if limit:
            self.stdout.write(f"📊 LIMIT: Processing maximum {limit} events")

        try:
            service = ScrapingService()
            
            if dry_run:
                # In dry run mode, just discover and display events
                scraper = service.corsa_scraper
                discovered_events = scraper.discover_events_from_results_page(force_refresh=force_refresh)
                
                if limit:
                    discovered_events = discovered_events[:limit]
                
                self.stdout.write(f"\n📊 Found {len(discovered_events)} events on corsa.is:\n")
                
                for i, event_info in enumerate(discovered_events, 1):
                    self.stdout.write(f"{i:3d}. {event_info['name']} ({event_info['date']})")
                    for race in event_info['races']:
                        self.stdout.write(f"     → {race['name']} ({race['race_type']}, {race.get('distance_km', '?')}km)")
                    
                    if i >= (limit or len(discovered_events)):
                        break
            else:
                # Actually save events to database
                result = service.discover_and_save_corsa_events(
                    overwrite=overwrite,
                    force_refresh=force_refresh,
                    limit=limit
                )
                
                self.stdout.write(f"\n✅ Event discovery completed!")
                self.stdout.write(f"📊 Discovered: {result['discovered']} events")
                self.stdout.write(f"🆕 New events: {result['new']}")
                self.stdout.write(f"🔄 Updated events: {result['updated']}")
                self.stdout.write(f"📋 Existing events: {result['existing']}")
                
                if result['errors'] > 0:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️ Errors: {result['errors']}")
                    )

        except CorsaScrapingError as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Corsa scraping failed: {e}")
            )
            return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Unexpected error: {e}")
            )
            return

        self.stdout.write(
            self.style.SUCCESS("🎉 Corsa event discovery completed successfully!")
        )
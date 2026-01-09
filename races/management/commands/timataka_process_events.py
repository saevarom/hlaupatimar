from django.core.management.base import BaseCommand, CommandError
from races.services import ScrapingService
from races.scraper import TimatakaScrapingError
from races.models import Event
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process Event records and extract individual Race records from their detail pages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--event-ids',
            nargs='+',
            type=int,
            help='Specific event IDs to process (space-separated)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Maximum number of events to process in this run'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing'
        )
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force refresh of cached HTML from web'
        )

    def handle(self, *args, **options):
        event_ids = options.get('event_ids')
        limit = options.get('limit')
        dry_run = options['dry_run']
        force_refresh = options['force_refresh']
        
        self.stdout.write("Starting event processing to extract races...")
        
        try:
            service = ScrapingService()
            
            # Get events that would be processed
            if event_ids:
                events_to_process = Event.objects.filter(id__in=event_ids)
                self.stdout.write(f"Processing specific events: {event_ids}")
            else:
                events_to_process = Event.objects.filter(status='discovered').order_by('date')
                self.stdout.write("Processing all unprocessed events")
                
            if limit:
                events_to_process = events_to_process[:limit]
                self.stdout.write(f"Limited to {limit} events")
            
            total_events = events_to_process.count()
            
            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f"Would process {total_events} events:")
                )
                
                for event in events_to_process:
                    self.stdout.write(f"  - {event.name} ({event.date})")
                    self.stdout.write(f"    URL: {event.url}")
                    self.stdout.write(f"    Status: {event.status}")
                
                return
            
            if total_events == 0:
                self.stdout.write(
                    self.style.WARNING("No events found to process.")
                )
                return
            
            # Actually process events
            result = service.process_events_and_extract_races(
                event_ids=event_ids, 
                limit=limit,
                force_refresh=force_refresh
            )
            
            # Display results
            self.stdout.write(
                self.style.SUCCESS(
                    f"Event processing completed!\n"
                    f"  Events processed: {result['processed']}\n"
                    f"  Races created: {result['races_created']}\n"
                    f"  Errors: {result['errors']}"
                )
            )
            
            if result['errors'] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  {result['errors']} errors occurred during processing. "
                        "Check logs for details."
                    )
                )
            
            # Show some stats
            total_events_in_db = Event.objects.count()
            processed_events = Event.objects.filter(status='processed').count()
            error_events = Event.objects.filter(status='error').count()
            pending_events = Event.objects.filter(status='discovered').count()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nEvent processing statistics:\n"
                    f"  Total events: {total_events_in_db}\n"
                    f"  Processed: {processed_events}\n"
                    f"  Pending: {pending_events}\n"
                    f"  Errors: {error_events}"
                )
            )
                
        except TimatakaScrapingError as e:
            raise CommandError(f"Processing failed: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error during event processing")
            raise CommandError(f"Unexpected error: {str(e)}")

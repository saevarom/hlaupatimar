#!/usr/bin/env python3
"""
Django management command to process Race records and extract Results from their result pages.

This command fetches race result pages and extracts individual runner results,
storing them as Result records with runner information, times, and splits.
"""

import logging
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from races.models import Race, Result
from races.services import ScrapingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process Race records and extract Results from their result pages. HTML content is cached by default for each race results page.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--race-ids',
            nargs='+',
            type=int,
            help='Specific race IDs to process (space-separated)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Maximum number of races to process in this run'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing results for races'
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
        parser.add_argument(
            '--no-cache-html',
            action='store_true',
            help='Skip caching HTML content for race results pages (caching is enabled by default)'
        )
        parser.add_argument(
            '--include-server-errors',
            action='store_true',
            help='Include races that previously had server errors (500, 404, etc.)'
        )

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.dry_run = options.get('dry_run', False)
        self.overwrite = options.get('overwrite', False)
        self.force_refresh = options.get('force_refresh', False)
        self.cache_html = not options.get('no_cache_html', False)  # Cache by default
        self.include_server_errors = options.get('include_server_errors', False)
        self.service = ScrapingService()
        
        if self.verbosity >= 1:
            self.stdout.write("Starting race results processing...")
        
        # Determine which races to process
        races_to_process = self._get_races_to_process(options)
        
        if self.dry_run:
            self._show_dry_run_info(races_to_process)
            return
        
        # Process races
        self._process_races(races_to_process)
        
        if self.verbosity >= 1:
            self._show_final_statistics()

    def _get_races_to_process(self, options):
        """Get the list of races to process based on command options"""
        if options.get('race_ids'):
            if self.verbosity >= 2:
                self.stdout.write(f"Processing specific races: {options['race_ids']}")
            races = Race.objects.filter(id__in=options['race_ids'])
        else:
            if self.verbosity >= 2:
                self.stdout.write("Processing all races without results")
            # Get races that don't have results yet (or all if overwrite is True)
            if self.overwrite:
                races = Race.objects.all()
            else:
                races = Race.objects.filter(results__isnull=True).distinct()
        
        # Filter out races with server errors unless explicitly included
        if not self.include_server_errors and not options.get('race_ids'):
            initial_count = races.count()
            races = races.filter(has_server_error=False)
            filtered_count = races.count()
            error_races_count = initial_count - filtered_count
            
            if error_races_count > 0 and self.verbosity >= 1:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {error_races_count} races with known server errors. "
                        f"Use --include-server-errors to process them anyway."
                    )
                )
        
        # Apply limit if specified
        if options.get('limit'):
            if self.verbosity >= 2:
                self.stdout.write(f"Limited to {options['limit']} races")
            races = races[:options['limit']]
        
        return races

    def _show_dry_run_info(self, races):
        """Show what would be processed in a dry run"""
        self.stdout.write(f"\n=== DRY RUN ===")
        self.stdout.write(f"Would process {races.count()} races:")
        
        for race in races[:10]:  # Show first 10
            result_count = Result.objects.filter(race=race).count()
            results_url = self._build_results_url(race)
            
            self.stdout.write(
                f"  {race.id}: {race.name} "
                f"({result_count} existing results) "
                f"-> {results_url}"
            )
        
        if races.count() > 10:
            self.stdout.write(f"  ... and {races.count() - 10} more races")

    def _process_races(self, races):
        """Process each race to extract results"""
        total_races = races.count()
        processed_count = 0
        success_count = 0
        error_count = 0
        total_results_saved = 0
        
        for race in races:
            processed_count += 1
            
            if self.verbosity >= 2:
                self.stdout.write(
                    f"Processing race {processed_count}/{total_races}: {race.name}"
                )
            
            try:
                # Build the results URL for this race
                results_url = self._build_results_url(race)
                
                if not results_url:
                    if self.verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(f"  Skipping: No results URL could be built")
                        )
                    continue
                
                race_total_saved = 0
                race_total_scraped = 0
                race_total_errors = 0
                
                # Clear existing results once if overwriting
                if self.overwrite:
                    existing_count = Result.objects.filter(race=race).count()
                    if existing_count > 0:
                        Result.objects.filter(race=race).delete()
                        if self.verbosity >= 2:
                            self.stdout.write(f"    Deleted {existing_count} existing results")
                
                # Process both male and female results by modifying the URL parameter
                gender_categories = [
                    ('male', 'cat=m'),
                    ('female', 'cat=f')
                ]
                
                for gender_name, cat_param in gender_categories:
                    # Create gender-specific URL by replacing cat=overall with the gender category
                    if 'cat=overall' in results_url:
                        gender_url = results_url.replace('cat=overall', cat_param)
                    elif 'cat=' not in results_url:
                        # Add gender category if no category exists
                        separator = '&' if '?' in results_url else '?'
                        gender_url = f"{results_url}{separator}{cat_param}"
                    else:
                        # Skip if URL has different category format
                        continue
                    
                    if self.verbosity >= 2:
                        self.stdout.write(f"    Processing {gender_name} results: {gender_url}")
                    
                    # Fetch the results page for this gender (with caching)
                    html_content = self._fetch_results_page(gender_url, race=race)
                    
                    if not html_content:
                        if self.verbosity >= 2:
                            self.stdout.write(
                                self.style.WARNING(f"    Skipping {gender_name}: Could not fetch results page")
                            )
                        continue
                    
                    # Process results for this gender (skip existing check since we already cleared above)
                    result_stats = self.service.scrape_and_save_race_results(
                        html_content, 
                        race.id, 
                        overwrite=False,  # Never overwrite within the gender loop
                        gender=gender_name,
                        skip_existing_check=True  # Skip check since we already handled it above
                    )
                    
                    race_total_saved += result_stats['saved']
                    race_total_scraped += result_stats['scraped'] 
                    race_total_errors += result_stats['errors']
                
                success_count += 1
                total_results_saved += race_total_saved
                
                if self.verbosity >= 2:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ Saved {race_total_saved} results total "
                            f"(scraped: {race_total_scraped}, errors: {race_total_errors})"
                        )
                    )
                
                # Update race with results URL if not set (keep the original overall URL)
                if not race.results_url:
                    race.results_url = results_url
                    race.save()
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing race {race.id} '{race.name}': {str(e)}")
                if self.verbosity >= 1:
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Error processing race '{race.name}': {str(e)}")
                    )
        
        # Show summary
        if self.verbosity >= 1:
            self.stdout.write("\nRace results processing completed!")
            self.stdout.write(f"  Races processed: {success_count}")
            self.stdout.write(f"  Total results saved: {total_results_saved}")
            self.stdout.write(f"  Errors: {error_count}")
            
            if error_count > 0:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  {error_count} errors occurred during processing. Check logs for details.")
                )

    def _build_results_url(self, race):
        """Build the results URL for a race"""
        # Check if race already has a results_url
        if race.results_url:
            # If the results_url ends with /urslit/ but doesn't have race parameters,
            # it might be pointing to a directory rather than actual results
            if (race.results_url.endswith('/urslit/') and 
                'race=' not in race.results_url and 
                'cat=' not in race.results_url):
                # Try to build a proper results URL using the event page
                return self._build_results_url_from_event_page(race)
            return race.results_url
        
        # Try to build URL from event URL
        return self._build_results_url_from_event_page(race)
    
    def _build_results_url_from_event_page(self, race):
        """Build the results URL by analyzing the event page"""
        event_url = race.event.url
        
        if not event_url:
            return None
        
        # Case 1: Event URL already points to results with parameters
        if '/urslit/' in event_url and ('race=' in event_url or 'cat=' in event_url):
            return event_url
        
        # Case 2: Event URL is an event page - we need to scrape it to find race links
        try:
            # Remove /urslit/ from event URL if it's there (might be incorrectly normalized)
            clean_event_url = event_url.replace('/urslit/', '/').rstrip('/')
            if not clean_event_url.endswith('/'):
                clean_event_url += '/'
            
            # Skip if this would create an invalid URL
            if clean_event_url.count('/urslit/') > 0:
                logger.warning(f"Skipping URL building for {event_url} - would create invalid URL")
                return event_url
            
            # Fetch the event page to look for race links
            response = requests.get(clean_event_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Look for race links with parameters
            links = soup.find_all('a', href=True)
            race_links = []
            
            for link in links:
                href = link.get('href', '')
                if 'race=' in href and 'cat=overall' in href:
                    # Found a race link with overall category
                    if href.startswith('/'):
                        # Relative URL - make it absolute
                        full_url = 'https://timataka.net' + href
                    elif href.startswith('?'):
                        # Query parameters only - add to base URL
                        base_url = clean_event_url.rstrip('/')
                        full_url = base_url + '/urslit/' + href
                    elif href.startswith('urslit/'):
                        # Relative path starting with urslit/
                        base_url = clean_event_url.rstrip('/')
                        full_url = base_url + '/' + href
                    elif href.startswith('http'):
                        # Already absolute URL
                        full_url = href
                    else:
                        # Other relative URL - add to base
                        base_url = clean_event_url.rstrip('/')
                        full_url = base_url + '/' + href
                    
                    race_links.append(full_url)
            
            # If we found race links, return the first overall results link
            if race_links:
                return race_links[0]
            
            # No race links found - this might be a simple event page
            # Return the original event URL (which should point to results)
            return event_url
                
        except Exception as e:
            logger.error(f"Error building results URL from event page {event_url}: {str(e)}")
            # Fallback to original URL
            return event_url

    def _fetch_results_page(self, url, race=None):
        """Fetch the HTML content of a results page with caching support"""
        try:
            # Use the appropriate scraper based on race source
            service = ScrapingService()
            scraper = service.get_scraper(race.source if race else 'timataka.net')
            
            if self.cache_html and race:
                html_content = scraper._fetch_html_with_cache(
                    url, 
                    cache_obj=race, 
                    force_refresh=self.force_refresh
                )
            else:
                # Fetch without caching - need to make the request manually
                import requests
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, timeout=30, headers=headers)
                response.raise_for_status()
                html_content = response.text
            return html_content
        except Exception as e:
            logger.error(f"Error fetching results page {url}: {str(e)}")
            return None

    def _show_final_statistics(self):
        """Show final statistics about the processing"""
        total_races = Race.objects.count()
        races_with_results = Race.objects.filter(results__isnull=False).distinct().count()
        total_results = Result.objects.count()
        
        self.stdout.write(f"\nFinal race results statistics:")
        self.stdout.write(f"  Total races: {total_races}")
        self.stdout.write(f"  Races with results: {races_with_results}")
        self.stdout.write(f"  Races without results: {total_races - races_with_results}")
        self.stdout.write(f"  Total results: {total_results}")
        if races_with_results > 0:
            self.stdout.write(f"  Average results per race: {total_results / races_with_results:.1f}")

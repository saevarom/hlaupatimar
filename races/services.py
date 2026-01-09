from typing import List, Dict, Optional
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from django.db import transaction
from .scraper import TimatakaScraper, TimatakaScrapingError
from .corsa_scraper import CorsaScraper, CorsaScrapingError
from .models import Race, Runner, Result, Split, Event

logger = logging.getLogger(__name__)


class ScrapingService:
    """
    Service class for handling race data scraping operations.
    
    This service provides high-level methods for scraping race data
    and integrating it with the database from multiple sources.
    """
    
    def __init__(self):
        self.timataka_scraper = TimatakaScraper()
        self.corsa_scraper = CorsaScraper()
    
    def get_scraper(self, source: str):
        """Get the appropriate scraper for the source"""
        if source == 'corsa.is':
            return self.corsa_scraper
        else:
            return self.timataka_scraper
    
    def scrape_and_save_race_results(self, html_content: str, race_id: int, 
                                   overwrite: bool = False, gender: str = None, 
                                   skip_existing_check: bool = False) -> Dict[str, int]:
        """
        Scrape race results from HTML content and save to database.
        
        Args:
            html_content: Raw HTML content from race results page
            race_id: ID of the race in database
            overwrite: Whether to overwrite existing results
            gender: Gender category for these results ('male', 'female', or None for mixed)
            skip_existing_check: Skip the check for existing results (used for gender-specific processing)
            
        Returns:
            Dict with counts: {'scraped': X, 'saved': Y, 'skipped': Z, 'errors': W}
        """
        result = {
            'scraped': 0,
            'saved': 0,
            'skipped': 0,
            'updated': 0,
            'errors': 0
        }
        
        try:
            # Get the race
            race = Race.objects.get(id=race_id)
            
            # Get the appropriate scraper based on the race source
            scraper = self.get_scraper(race.source)
            
            # Scrape results data using the appropriate scraper
            if race.source == 'corsa.is':
                # For Corsa, extract results from HTML
                results_list = scraper._extract_results_from_html(html_content, race.results_url or race.source_url)
                results_data = {
                    'results_count': len(results_list),
                    'results': results_list
                }
            else:
                # For Timataka, use the existing method
                results_data = scraper.scrape_race_results(html_content, race_id)
            
            result['scraped'] = results_data['results_count']
            
            # Check if results already exist (unless skipping this check)
            if not skip_existing_check:
                existing_results = Result.objects.filter(race=race).count()
                if existing_results > 0 and not overwrite:
                    logger.info(f"Results for race '{race.name}' already exist, skipping")
                    result['skipped'] = result['scraped']
                    return result
            
            # Save results with transaction
            with transaction.atomic():
                if not skip_existing_check and overwrite:
                    # Delete existing results
                    existing_results = Result.objects.filter(race=race).count()
                    if existing_results > 0:
                        Result.objects.filter(race=race).delete()
                        logger.info(f"Deleted {existing_results} existing results for race '{race.name}'")
                
                # Save each result
                for result_data in results_data['results']:
                    try:
                        self._save_result_to_db(result_data, race, gender)
                        result['saved'] += 1
                    except Exception as e:
                        logger.error(f"Error saving result for '{result_data.get('name', 'Unknown')}' (gender={gender}): {str(e)}")
                        result['errors'] += 1
            
            return result
            
        except Race.DoesNotExist:
            raise TimatakaScrapingError(f"Race with ID {race_id} not found")
        except TimatakaScrapingError as e:
            logger.error(f"Scraping failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in results scraping: {str(e)}")
            raise TimatakaScrapingError(f"Service error: {str(e)}")
    
    def _save_result_to_db(self, result_data: Dict, race: Race, gender: str = None) -> Result:
        """Save a single result to database"""
        # Normalize result data based on source
        normalized_data = self._normalize_result_data(result_data, race.source)
        
        # Get or create runner
        runner = self._get_or_create_runner(
            normalized_data['name'], 
            normalized_data.get('year'),
            gender[0].upper() if gender else normalized_data.get('gender', '')
        )
        
        # Create or get result (prevent duplicates for same runner in same race)
        result, result_created = Result.objects.get_or_create(
            race=race,
            runner=runner,
            defaults={
                'bib_number': normalized_data.get('bib_number', ''),
                'club': normalized_data.get('club', ''),
                'finish_time': normalized_data['finish_time'],
                'chip_time': normalized_data.get('chip_time'),
                'time_behind': normalized_data.get('time_behind'),
                'status': normalized_data.get('status', 'finished')
            }
        )
        
        # If result already existed, optionally update fields
        if not result_created:
            # Update fields if they're different (e.g., better bib number)
            updated = False
            if normalized_data.get('bib_number', '') and not result.bib_number:
                result.bib_number = normalized_data.get('bib_number', '')
                updated = True
            if normalized_data.get('club', '') and not result.club:
                result.club = normalized_data.get('club', '')
                updated = True
            if updated:
                result.save()
        
        # Save splits if they exist (only if result was created or no splits exist)
        splits_data = result_data.get('splits', [])
        if splits_data and (result_created or not result.splits.exists()):
            for split_data in splits_data:
                Split.objects.get_or_create(
                    result=result,
                    split_name=split_data['location'],
                    defaults={
                        'split_time': split_data['time']
                    }
                )
        
        return result
    
    def _normalize_result_data(self, result_data: Dict, source: str) -> Dict:
        """
        Normalize result data from different sources to a common format.
        
        Args:
            result_data: Raw result data from scraper
            source: Source website ('timataka.net' or 'corsa.is')
            
        Returns:
            Normalized result data dictionary
        """
        if source == 'corsa.is':
            # Normalize Corsa data format
            # Convert seconds to formatted time string if needed
            finish_time = result_data.get('gun_time_seconds')
            if finish_time and isinstance(finish_time, (int, float)):
                # Convert seconds to HH:MM:SS format
                hours = int(finish_time // 3600)
                minutes = int((finish_time % 3600) // 60)
                seconds = int(finish_time % 60)
                finish_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                finish_time = result_data.get('finish_time', '')
                
            chip_time = result_data.get('net_time_seconds')
            if chip_time and isinstance(chip_time, (int, float)):
                # Convert seconds to HH:MM:SS format  
                hours = int(chip_time // 3600)
                minutes = int((chip_time % 3600) // 60)
                seconds = int(chip_time % 60)
                chip_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                chip_time = result_data.get('chip_time')
            
            # Convert gender to database format (single character)
            raw_gender = result_data.get('gender', '').lower()
            if raw_gender == 'male':
                gender_code = 'M'
            elif raw_gender == 'female':
                gender_code = 'F'
            elif raw_gender == 'nonbinary':
                # Database only supports M/F, so we'll leave this blank for now
                gender_code = ''
            else:
                gender_code = ''
            
            return {
                'name': result_data.get('name', ''),
                'bib_number': result_data.get('bib_number', ''),
                'club': result_data.get('club', ''),
                'finish_time': finish_time,
                'chip_time': chip_time,
                'time_behind': result_data.get('behind_time'),
                'status': result_data.get('status', 'Finished').lower(),
                'gender': gender_code,
                'year': result_data.get('age'),  # Corsa might have age instead of birth year
                'rank': result_data.get('rank_overall', result_data.get('rank', 0)),
            }
        else:
            # Timataka data format (existing format)
            return {
                'name': result_data.get('name', ''),
                'bib_number': result_data.get('bib', ''),
                'club': result_data.get('club', ''),
                'finish_time': result_data.get('finish_time', ''),
                'chip_time': result_data.get('chip_time'),
                'time_behind': result_data.get('time_behind'),
                'status': 'finished',
                'gender': '',  # Timataka handles gender separately
                'year': result_data.get('year'),
                'rank': result_data.get('rank', 0),
            }
    
    def _get_or_create_runner(self, name: str, birth_year: Optional[int], gender: str = '') -> Runner:
        """Get or create a runner by name and birth year"""
        created = False  # Initialize created variable
        
        # Try to find existing runner by name and birth year
        if birth_year:
            runner, created = Runner.objects.get_or_create(
                name=name,
                birth_year=birth_year,
                defaults={'nationality': 'ISL', 'gender': gender}
            )
            # Update gender if not set and we have gender info
            if not created and gender and not runner.gender:
                runner.gender = gender
                runner.save()
        else:
            # Try to find by name only
            existing_runners = Runner.objects.filter(name=name)
            if existing_runners.exists():
                # If multiple runners with same name, prefer one with birth year
                runner_with_year = existing_runners.filter(birth_year__isnull=False).first()
                if runner_with_year:
                    runner = runner_with_year
                else:
                    runner = existing_runners.first()
                
                # Update gender if not set and we have gender info
                if gender and not runner.gender:
                    runner.gender = gender
                    runner.save()
                # created is already False, so no need to set it
            else:
                # Create new runner without birth year
                runner = Runner.objects.create(
                    name=name,
                    birth_year=birth_year,
                    nationality='ISL',
                    gender=gender
                )
                created = True
        
        if created:
            logger.info(f"Created new runner: {runner}")
        
        return runner
    
    def scrape_and_save_races(self, html_content: str, source_url: str = "", 
                              overwrite: bool = False) -> Dict[str, int]:
        """
        Scrape races from HTML content and save to database.
        
        Args:
            html_content: Raw HTML content from Timataka page
            source_url: Original URL for reference
            overwrite: Whether to overwrite existing races
            
        Returns:
            Dict with counts: {'scraped': X, 'saved': Y, 'skipped': Z, 'errors': W}
        """
        result = {
            'scraped': 0,
            'saved': 0,
            'skipped': 0,
            'updated': 0,
            'errors': 0
        }
        
        try:
            # Scrape race data
            races_data = self.scraper.scrape_race_data(html_content, source_url)
            result['scraped'] = len(races_data)
            
            # Save each race to database
            for race_data in races_data:
                try:
                    save_result = self._save_race_to_db(race_data, overwrite)
                    if save_result == 'saved':
                        result['saved'] += 1
                    elif save_result == 'skipped':
                        result['skipped'] += 1
                    elif save_result == 'updated':
                        result['updated'] += 1
                        
                except Exception as e:
                    logger.error(f"Error saving race '{race_data.get('name', 'Unknown')}': {str(e)}")
                    result['errors'] += 1
            
            return result
            
        except TimatakaScrapingError as e:
            logger.error(f"Scraping failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in scraping service: {str(e)}")
            raise TimatakaScrapingError(f"Service error: {str(e)}")
    
    def scrape_races_only(self, html_content: str, source_url: str = "") -> List[Dict]:
        """
        Scrape races from HTML content without saving to database.
        
        Args:
            html_content: Raw HTML content from Timataka page
            source_url: Original URL for reference
            
        Returns:
            List of race dictionaries
        """
        return self.scraper.scrape_race_data(html_content, source_url)
    
    def _save_race_to_db(self, race_data: Dict, overwrite: bool = False) -> str:
        """
        Save a single race to database.
        
        Args:
            race_data: Race data dictionary
            overwrite: Whether to overwrite existing races
            
        Returns:
            String indicating result: 'saved', 'skipped', or 'updated'
        """
        # Remove fields that don't belong in the Race model
        race_data_for_db = race_data.copy()
        race_data_for_db.pop('start_time', None)
        
        # Check if race already exists
        existing_race = Race.objects.filter(
            name=race_data_for_db['name'],
            date=race_data_for_db['date']
        ).first()
        
        if existing_race:
            if overwrite:
                # Update existing race
                for field, value in race_data_for_db.items():
                    setattr(existing_race, field, value)
                existing_race.save()
                logger.info(f"Updated existing race: {existing_race.name}")
                return 'updated'
            else:
                logger.info(f"Race '{race_data_for_db['name']}' already exists, skipping")
                return 'skipped'
        else:
            # Create new race
            race = Race.objects.create(**race_data_for_db)
            logger.info(f"Created new race: {race.name}")
            return 'saved'
    
    def discover_and_save_events(self, overwrite: bool = False, force_refresh: bool = False, cache_html: bool = False, limit: int = None) -> Dict[str, int]:
        """
        Discover events from timataka.net homepage and save new ones to database.
        
        Args:
            overwrite: Whether to update existing events
            force_refresh: If True, bypass cache and fetch HTML from web
            cache_html: If True, also fetch and cache HTML content for each event page
            limit: If specified, limit the number of events to process
            
        Returns:
            Dict with counts: {'discovered': X, 'new': Y, 'existing': Z, 'errors': W}
        """
        result = {
            'discovered': 0,
            'new': 0,
            'existing': 0,
            'updated': 0,
            'errors': 0
        }
        
        try:
            # Discover events from homepage (with caching support)
            discovered_events = self.scraper.discover_races_from_homepage(force_refresh=force_refresh)
            
            # Apply limit if specified
            if limit and len(discovered_events) > limit:
                logger.info(f"Limiting processing to {limit} out of {len(discovered_events)} discovered events")
                discovered_events = discovered_events[:limit]
            
            result['discovered'] = len(discovered_events)
            
            logger.info(f"Processing {len(discovered_events)} events from timataka.net")
            
            # Process each discovered event
            for event_info in discovered_events:
                try:
                    # Check if event already exists (by URL)
                    existing_event = Event.objects.filter(url=event_info['url']).first()
                    
                    if existing_event:
                        # Check if we should update the date
                        # Convert new date to date object if needed
                        new_date = event_info['date'].date() if hasattr(event_info['date'], 'date') else event_info['date']
                        
                        should_update = False
                        update_reason = ""
                        
                        # Update if dates are different and the new date is not a mid-month default (15th)
                        if (existing_event.date != new_date and 
                              new_date and 
                              new_date.day != 15):  # 15th suggests mid-month default
                            should_update = True
                            update_reason = "more specific date"
                        # Also update if existing date is mid-month (15th) and new date is different
                        elif (existing_event.date.day == 15 and 
                              existing_event.date != new_date and 
                              new_date):
                            should_update = True
                            update_reason = "replacing mid-month default"
                        
                        if should_update:
                            old_date = existing_event.date
                            existing_event.date = new_date
                            existing_event.save()
                            result['updated'] += 1
                            logger.info(f"Updated date for event '{event_info['name']}' ({update_reason}): {old_date} -> {existing_event.date}")
                        else:
                            result['existing'] += 1
                            logger.debug(f"Event already exists with current date: {event_info['name']} ({existing_event.date})")
                        
                        # Cache HTML for existing events if requested and not already cached
                        if cache_html and not existing_event.cached_html:
                            try:
                                logger.info(f"Caching HTML for existing event: {existing_event.name}")
                                html_content = self.scraper._fetch_html_with_cache(existing_event.url, existing_event)
                                logger.info(f"Cached {len(html_content)} characters for existing event: {existing_event.name}")
                            except Exception as e:
                                logger.warning(f"Failed to cache HTML for existing event {existing_event.name}: {str(e)}")
                        
                        continue
                    
                    # Create new event record
                    with transaction.atomic():
                        event = self._create_event_from_discovery(event_info, cache_html=cache_html)
                        result['new'] += 1
                        logger.info(f"Saved new event: {event.name} ({event.date})")
                        
                except Exception as e:
                    logger.error(f"Error processing discovered event '{event_info.get('name', 'Unknown')}': {str(e)}")
                    result['errors'] += 1
            
            return result
            
        except TimatakaScrapingError as e:
            logger.error(f"Event discovery failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in event discovery: {str(e)}")
            raise TimatakaScrapingError(f"Service error: {str(e)}")
    
    def _create_event_from_discovery(self, event_info: Dict, cache_html: bool = False) -> Event:
        """Create an Event object from discovered event information"""
        # Extract basic information
        name = event_info['name']
        event_date = event_info['date']
        url = event_info['url']
        
        # Normalize the URL to ensure it points to results if it's a simple event page
        normalized_url = self._normalize_event_url(url)
        
        # Convert date to date object if needed
        if event_date is None:
            # If no date was extracted, use a placeholder far in the future
            event_date = datetime(2099, 12, 31).date()
        elif hasattr(event_date, 'date'):
            event_date = event_date.date()
        
        # Create and save the event
        event = Event.objects.create(
            name=name,
            date=event_date,
            url=normalized_url,
            status='discovered',
        )
        
        # Optionally cache the HTML content of the event page
        if cache_html:
            try:
                logger.info(f"Fetching and caching HTML for event: {name}")
                html_content = self.scraper._fetch_html_with_cache(normalized_url, event)
                logger.info(f"Cached {len(html_content)} characters for event: {name}")
            except Exception as e:
                logger.warning(f"Failed to cache HTML for event {name}: {str(e)}")
        
        return event
    
    def _normalize_event_url(self, url: str) -> str:
        """
        Normalize event URLs to ensure they point to the correct page type.
        
        For complex event pages that contain race links (like tindahlaup2025),
        keep them as event pages since they contain navigation to specific race results.
        
        For simple event pages that don't contain race links (like gamlarshlaup2013), 
        append /urslit/ to make them results URLs.
        
        For URLs that are already results URLs (contain /urslit/ or have race parameters),
        leave them as-is.
        
        Args:
            url: Original event URL
            
        Returns:
            Normalized URL that points to the appropriate page
        """
        # If URL already contains /urslit/ or has race parameters, don't modify it
        if '/urslit/' in url or 'race=' in url:
            return url
        
        # If URL ends with /urslit (without trailing slash), add trailing slash
        if url.endswith('/urslit'):
            return f"{url}/"
        
        # Check if this is a complex event page by looking for race links
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'lxml')
                
                # Look for race links with parameters
                links = soup.find_all('a', href=True)
                has_race_links = any('race=' in link.get('href', '') for link in links)
                
                if has_race_links:
                    # This is a complex event page with race links - keep as event page
                    return url
        except Exception:
            # If we can't check the page, fall back to simple normalization
            pass
        
        # For simple event pages, append /urslit/ to make them results URLs
        if url.endswith('/'):
            return f"{url}urslit/"
        else:
            return f"{url}/urslit/"

    def discover_and_save_corsa_events(self, overwrite: bool = False, force_refresh: bool = False, limit: int = None) -> Dict[str, int]:
        """
        Discover events from corsa.is results page and save them to database.
        
        Args:
            overwrite: Whether to update existing events
            force_refresh: If True, bypass cache and fetch HTML from web
            limit: If specified, limit the number of events to process
            
        Returns:
            Dict with counts: {'discovered': X, 'new': Y, 'existing': Z, 'errors': W}
        """
        result = {
            'discovered': 0,
            'new': 0,
            'existing': 0,
            'updated': 0,
            'errors': 0
        }
        
        try:
            # Discover events from corsa.is results page
            discovered_events = self.corsa_scraper.discover_events_from_results_page(force_refresh=force_refresh)
            
            # Apply limit if specified
            if limit and len(discovered_events) > limit:
                logger.info(f"Limiting processing to {limit} out of {len(discovered_events)} discovered events")
                discovered_events = discovered_events[:limit]
            
            result['discovered'] = len(discovered_events)
            
            logger.info(f"Processing {len(discovered_events)} events from corsa.is")
            
            # Process each discovered event and its races
            for event_info in discovered_events:
                try:
                    # For Corsa events, we process them differently since each event has multiple race URLs
                    # We create one Event record and multiple Race records for each race category
                    
                    # Check if event already exists (by name and year, since URLs are different for races)
                    existing_event = Event.objects.filter(
                        name=event_info['name'],
                        source='corsa.is'
                    ).first()
                    
                    if existing_event and not overwrite:
                        result['existing'] += 1
                        logger.debug(f"Event already exists: {event_info['name']}")
                        continue
                    
                    # Create or update event record
                    with transaction.atomic():
                        if existing_event:
                            # Update existing event
                            existing_event.date = event_info['date']
                            existing_event.status = 'discovered'  # Reset status to allow reprocessing
                            existing_event.save()
                            event = existing_event
                            result['updated'] += 1
                            logger.info(f"Updated event: {event.name}")
                        else:
                            # Create new event record
                            event = self._create_corsa_event_from_discovery(event_info)
                            result['new'] += 1
                            logger.info(f"Created new event: {event.name} ({event.date})")
                        
                        # Create/update race records for each race category in this event
                        for race_info in event_info['races']:
                            try:
                                self._create_or_update_corsa_race(event, race_info, overwrite)
                            except Exception as e:
                                logger.error(f"Error creating race '{race_info['name']}' for event '{event.name}': {str(e)}")
                                result['errors'] += 1
                                
                except Exception as e:
                    logger.error(f"Error processing discovered event '{event_info.get('name', 'Unknown')}': {str(e)}")
                    result['errors'] += 1
            
            return result
            
        except CorsaScrapingError as e:
            logger.error(f"Corsa event discovery failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Corsa event discovery: {str(e)}")
            raise CorsaScrapingError(f"Service error: {str(e)}")
    
    def _create_corsa_event_from_discovery(self, event_info: Dict) -> Event:
        """Create a Corsa Event object from discovered event information"""
        name = event_info['name']
        event_date = event_info['date']
        
        # For Corsa events, we use the first race URL as the primary URL
        # or create a placeholder URL
        primary_url = event_info['races'][0]['url'] if event_info['races'] else f"https://www.corsa.is/{name.lower().replace(' ', '-')}"
        
        # Create and save the event
        event = Event.objects.create(
            name=name,
            date=event_date,
            url=primary_url,
            source='corsa.is',
            status='discovered',
        )
        
        return event
    
    def _create_or_update_corsa_race(self, event: Event, race_info: Dict, overwrite: bool = False):
        """Create or update a Race record from Corsa race information"""
        # Check if race already exists
        existing_race = Race.objects.filter(
            event=event,
            name=race_info['name'],
            source='corsa.is'
        ).first()
        
        if existing_race and not overwrite:
            logger.debug(f"Race already exists: {race_info['name']}")
            return existing_race
        
        # Extract location from event name (rough estimate)
        location = "Reykjavik"  # Default location
        if 'reykjavik' in event.name.lower():
            location = "Reykjavik"
        elif 'laugavegur' in event.name.lower():
            location = "Laugavegur"
        
        race_data = {
            'event': event,
            'name': race_info['name'],
            'race_type': race_info['race_type'],
            'date': event.date,
            'location': location,
            'distance_km': race_info.get('distance_km') or 1.0,  # Ensure we have a valid distance
            'results_url': race_info['url'],
            'source_url': race_info['url'],
            'source': 'corsa.is',
        }
        
        if existing_race:
            # Update existing race
            for key, value in race_data.items():
                if key != 'event':  # Don't update the event field
                    setattr(existing_race, key, value)
            existing_race.save()
            logger.info(f"Updated race: {race_info['name']}")
            return existing_race
        else:
            # Create new race
            race = Race.objects.create(**race_data)
            logger.info(f"Created race: {race_info['name']} ({race.race_type})")
            return race

    def process_events_and_extract_races(self, event_ids: List[int] = None, limit: int = None, force_refresh: bool = False) -> Dict[str, int]:
        """
        Process Event records and extract individual Race records from their detail pages.
        
        Args:
            event_ids: List of specific event IDs to process. If None, processes unprocessed events.
            limit: Maximum number of events to process in this run
            force_refresh: If True, bypass cache and fetch HTML from web
            
        Returns:
            Dict with counts: {'processed': X, 'races_created': Y, 'errors': Z}
        """
        result = {
            'processed': 0,
            'races_created': 0,
            'errors': 0
        }
        
        try:
            # Get events to process
            if event_ids:
                events = Event.objects.filter(id__in=event_ids)
            else:
                # Process events that haven't been processed yet
                events = Event.objects.filter(status='discovered').order_by('date')
                
            if limit:
                events = events[:limit]
            
            logger.info(f"Processing {events.count()} events to extract races")
            
            for event in events:
                try:
                    logger.info(f"Processing event: {event.name} ({event.url})")
                    
                    # Update event status to indicate processing has started
                    event.status = 'processing'
                    event.last_processed = datetime.now()
                    event.save()
                    
                    races_created_count = 0
                    
                    # Handle different sources differently
                    if event.source == 'corsa.is':
                        # For Corsa events, races are already created during discovery
                        # Just verify races exist and mark as processed
                        existing_races = Race.objects.filter(event=event).count()
                        if existing_races > 0:
                            logger.info(f"Corsa event already has {existing_races} races from discovery phase")
                            races_created_count = existing_races
                        else:
                            logger.warning(f"Corsa event has no races - may need to re-run corsa_discover_events")
                    else:
                        # For Timataka events, extract races from event URL
                        scraper = self.get_scraper(event.source)
                        
                        # Scrape races from the event URL (with caching support)
                        races_data = scraper.scrape_races_from_event_url(event.url, event_obj=event, force_refresh=force_refresh)
                        
                        # Create Race objects for each race found
                        with transaction.atomic():
                            for race_data in races_data:
                                try:
                                    race = self._create_race_from_event_data(race_data, event)
                                    races_created_count += 1
                                    logger.debug(f"Created race: {race.name}")
                                except Exception as e:
                                    logger.error(f"Error creating race from data {race_data}: {str(e)}")
                                    result['errors'] += 1
                    
                    # Update event status to processed
                    event.status = 'processed'
                    event.save()
                    
                    result['processed'] += 1
                    result['races_created'] += races_created_count
                    logger.info(f"Successfully processed event '{event.name}': {races_created_count} races created")
                    
                except Exception as e:
                    # Mark event as error and continue with next event
                    event.status = 'error'
                    event.processing_error = str(e)
                    event.save()
                    result['errors'] += 1
                    logger.error(f"Error processing event '{event.name}': {str(e)}")
                    
            return result
            
        except Exception as e:
            logger.error(f"Unexpected error in event processing: {str(e)}")
            raise TimatakaScrapingError(f"Service error: {str(e)}")
    
    def _create_race_from_event_data(self, race_data: Dict, event: Event) -> Race:
        """Create a Race object from scraped race data and link it to an Event"""
        # Extract race information from the scraped data
        name = race_data.get('name', 'Unknown Race')
        race_type = race_data.get('race_type', 'other')
        date = race_data.get('date')
        location = race_data.get('location', event.name)  # Fallback to event name
        distance_km = race_data.get('distance_km', 0.0)
        elevation_gain_m = race_data.get('elevation_gain_m', 0)
        organizer = race_data.get('organizer', 'Tímataka')
        
        # Convert date if needed
        if date and hasattr(date, 'date'):
            date = date.date()
        elif not date:
            # Use event date as fallback
            date = event.date
        
        # Create and save the race
        race = Race.objects.create(
            event=event,
            name=name,
            description=race_data.get('description', f"Race from event: {event.name}"),
            race_type=race_type,
            date=date,
            location=location,
            distance_km=distance_km,
            elevation_gain_m=elevation_gain_m,
            organizer=organizer,
            currency=race_data.get('currency', 'ISK'),
            source_url=race_data.get('source_url', event.url),  # Use scraped source URL if available
            results_url=race_data.get('results_url', ''),  # Set the results URL from scraped data
        )
        
        return race
    
    def _create_race_from_discovery(self, race_info: Dict) -> Race:
        """Create a Race object from discovered race information"""
        # Extract basic information
        name = race_info['name']
        race_date = race_info['date']
        source_url = race_info['url']
        
        # Set default values for required fields
        race_type = 'other'  # Default, will be updated when race page is scraped
        location = 'Iceland'  # Default location
        distance_km = 0.0  # Default, will be updated when race page is scraped
        
        # Try to extract some information from the name
        if race_date is None:
            # If no date was extracted, use a placeholder far in the future
            race_date = datetime(2099, 12, 31).date()
        elif hasattr(race_date, 'date'):
            race_date = race_date.date()
        
        # Create and save the race
        race = Race.objects.create(
            name=name,
            description=f"Race discovered from timataka.net - {name}",
            race_type=race_type,
            date=race_date,
            location=location,
            distance_km=distance_km,
            elevation_gain_m=0,
            organizer='Tímataka',
            currency='ISK',
            source_url=source_url,
        )
        
        return race

    def validate_html_content(self, html_content: str) -> bool:
        """
        Validate if HTML content appears to be from a Timataka page.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            True if content appears valid for scraping
        """
        try:
            # Basic validation - check for Timataka indicators
            html_lower = html_content.lower()
            
            timataka_indicators = [
                'timataka.net',
                'tímataka',
                'ibox-content',
                'stats-label'
            ]
            
            return any(indicator in html_lower for indicator in timataka_indicators)
            
        except Exception as e:
            logger.warning(f"Error validating HTML content: {str(e)}")
            return False
    
    def get_supported_race_types(self) -> List[str]:
        """Get list of supported race types for scraping."""
        return list(self.scraper.race_type_mapping.values())

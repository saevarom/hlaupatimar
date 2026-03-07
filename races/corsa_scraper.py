import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from django.utils import timezone
import logging
import json

logger = logging.getLogger(__name__)


class CorsaScrapingError(Exception):
    """Custom exception for Corsa scraping errors"""
    pass


class CorsaScraper:
    """
    Scraper for Corsa.is race pages.
    
    Extracts race information from HTML content including:
    - Main race name and date
    - Multiple race distances/categories
    - Race results with times and participant info
    """
    
    def __init__(self):
        self.base_url = "https://www.corsa.is"
        self.results_url = "https://www.corsa.is/results"
        self.race_type_mapping = {
            'marathon': 'marathon',
            'half marathon': 'half_marathon',
            'fun run': 'other',
            'skemmtiskokk': 'other',  # Icelandic for fun run
            'ultra': 'ultra',
        }

    def _fetch_html_with_cache(self, url: str, cache_obj=None, force_refresh: bool = False) -> str:
        """
        Fetch HTML content with caching support.
        
        Args:
            url: URL to fetch
            cache_obj: Model instance with cached_html and html_fetched_at fields (optional)
            force_refresh: If True, always fetch from web and update cache
            
        Returns:
            HTML content as string
        """
        try:
            # If we have a cache object and cached HTML, use it unless force_refresh is True
            if cache_obj and cache_obj.cached_html and not force_refresh:
                logger.info(f"Using cached HTML for URL: {url}")
                return cache_obj.cached_html
            
            # For URL without cache object, we could implement file-based caching
            # but for now, just log that no cache object is available
            if not cache_obj:
                logger.info(f"No cache object available for URL: {url}, fetching from web")
            
            # Fetch from web
            logger.info(f"Fetching HTML from web for URL: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            html_content = response.text
            
            # Update cache if cache object is provided
            if cache_obj:
                cache_obj.cached_html = html_content
                cache_obj.html_fetched_at = timezone.now()
                cache_obj.save(update_fields=['cached_html', 'html_fetched_at'])
                logger.info(f"Cached HTML for URL: {url}")
            
            return html_content
            
        except requests.exceptions.RequestException as e:
            # Track server errors if we have a race cache object
            if cache_obj and hasattr(cache_obj, 'has_server_error'):
                from races.models import Race
                if isinstance(cache_obj, Race):
                    # Extract error code if available
                    error_code = None
                    if hasattr(e, 'response') and e.response is not None:
                        error_code = e.response.status_code
                    
                    # Mark race as having server errors for 500-level errors
                    if error_code and error_code >= 500:
                        cache_obj.has_server_error = True
                        cache_obj.last_error_code = error_code
                        cache_obj.last_error_message = str(e)
                        cache_obj.error_count += 1
                        cache_obj.last_error_at = timezone.now()
                        cache_obj.save(update_fields=[
                            'has_server_error', 'last_error_code', 'last_error_message', 
                            'error_count', 'last_error_at'
                        ])
                        logger.warning(f"Marked race {cache_obj.id} as having server error {error_code}")
            
            # If web fetch fails but we have cached content, use it as fallback
            if cache_obj and cache_obj.cached_html:
                logger.warning(f"Failed to fetch {url}, using cached content: {str(e)}")
                return cache_obj.cached_html
            else:
                logger.error(f"Failed to fetch {url} and no cache available: {str(e)}")
                raise CorsaScrapingError(f"Failed to fetch {url}: {str(e)}")

    def discover_events_from_results_page(self, force_refresh: bool = False) -> List[Dict]:
        """
        Discover events by scraping the main corsa.is results page.
        
        Args:
            force_refresh: If True, bypass cache and fetch from web
        
        Returns:
            List of dictionaries containing event information:
            - name: Event name
            - date: Event date (extracted from name or estimated)
            - races: List of race categories with URLs
            
        Raises:
            CorsaScrapingError: If scraping fails or data is invalid
        """
        try:
            # Fetch the main corsa.is results page
            html_content = self._fetch_html_with_cache(self.results_url, cache_obj=None, force_refresh=force_refresh)
            
            soup = BeautifulSoup(html_content, 'lxml')
            events = []
            
            # Match CSS module classes by stable fragments instead of full hashed names.
            event_containers = soup.select('div[class*="CategoryList"][class*="list__container"]')
            
            for container in event_containers:
                event_data = self._extract_event_from_container(container)
                if event_data:
                    events.append(event_data)
            
            logger.info(f"Discovered {len(events)} events from corsa.is results page")
            return events
            
        except Exception as e:
            logger.error(f"Error discovering events from corsa.is results page: {str(e)}")
            raise CorsaScrapingError(f"Failed to discover events: {str(e)}")

    def _extract_event_from_container(self, container) -> Optional[Dict]:
        """
        Extract event information from a CategoryList container.
        
        Args:
            container: BeautifulSoup element containing event info
            
        Returns:
            Dictionary with event information or None if extraction fails
        """
        try:
            # Get event name from title (selector resilient to class hash changes).
            title_elem = container.select_one('div[class*="CategoryList"][class*="list__title"]')
            if not title_elem:
                return None
            
            event_name = title_elem.get_text().strip()
            
            # Extract year from event name (e.g., "Reykjavik Marathon 2025" -> 2025)
            year_match = re.search(r'\b(20\d{2})\b', event_name)
            year = int(year_match.group(1)) if year_match else datetime.now().year
            
            # Try to extract date information from event name
            event_date = self._estimate_event_date(event_name, year)
            
            # Get all race categories for this event.
            races = []
            race_links = container.select('div[class*="CategoryList"][class*="item"] a[href]')
            seen_urls = set()

            for race_link in race_links:
                href = (race_link.get('href') or '').strip()
                if not href:
                    continue

                race_url = urljoin(self.base_url, href)
                if race_url in seen_urls:
                    continue
                seen_urls.add(race_url)

                race_name = race_link.get_text().strip()
                race_type = self._classify_race_type(race_name)
                distance_km = self._extract_distance_from_name(race_name)

                races.append({
                    'name': race_name,
                    'url': race_url,
                    'race_type': race_type,
                    'distance_km': distance_km
                })
            
            if not races:
                return None
            
            return {
                'name': event_name,
                'date': event_date,
                'races': races,
                'source': 'corsa.is'
            }
            
        except Exception as e:
            logger.warning(f"Failed to extract event from container: {str(e)}")
            return None

    def _estimate_event_date(self, event_name: str, year: int) -> datetime:
        """
        Estimate event date based on event name and year.
        
        This is a fallback since corsa.is doesn't show specific dates on the results page.
        We'll try to make educated guesses based on known events.
        """
        name_lower = event_name.lower()
        
        # Known events with typical dates
        if 'reykjavik marathon' in name_lower or 'reykjavikur marathon' in name_lower:
            # Typically held in August
            return datetime(year, 8, 22).date()
        elif 'laugavegur' in name_lower:
            # Typically held in July
            return datetime(year, 7, 15).date()
        elif 'midnight sun' in name_lower:
            # Typically held in June (around summer solstice)
            return datetime(year, 6, 21).date()
        elif 'happiness' in name_lower or 'hamingju' in name_lower:
            # Could be various times - use mid-year as default
            return datetime(year, 6, 15).date()
        else:
            # Default to mid-year for unknown events
            return datetime(year, 6, 15).date()

    def _classify_race_type(self, race_name: str) -> str:
        """
        Classify race type based on the race name.
        
        Args:
            race_name: Name of the race category
            
        Returns:
            Race type string
        """
        name_lower = race_name.lower()
        
        distance_km = self._extract_distance_from_name(race_name)
        if distance_km is not None:
            if distance_km > 43.5:
                return 'ultra'
            if 41.0 <= distance_km <= 43.5:
                return 'marathon'
            if 20.0 <= distance_km <= 22.5:
                return 'half_marathon'
            if 9.0 <= distance_km <= 11.0:
                return '10k'
            if 4.0 <= distance_km <= 6.0:
                return '5k'

        if 'fun run' in name_lower or 'skemmtiskokk' in name_lower:
            return 'other'
        
        # Fallback to keyword matching
        for keyword, race_type in self.race_type_mapping.items():
            if keyword in name_lower:
                return race_type
        
        return 'other'

    def _extract_distance_from_name(self, race_name: str) -> Optional[float]:
        """
        Extract distance from race name.
        
        Args:
            race_name: Name of the race category
            
        Returns:
            Distance in kilometers or None if not found
        """
        name_lower = race_name.lower()
        
        # Special cases first
        if 'half marathon' in name_lower or 'half-marathon' in name_lower:
            return 21.1
        elif 'marathon' in name_lower and 'half' not in name_lower:
            return 42.2
        elif '55k' in name_lower or '55 k' in name_lower:
            return 55.0
        elif '21.1' in name_lower or '21,1' in name_lower:
            return 21.1
        elif '42.2' in name_lower or '42,2' in name_lower:
            return 42.2
        
        # Look for common distance patterns
        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*(?:km|k)\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name_lower)
            if match:
                distance_str = match.group(1).replace(',', '.')
                return float(distance_str)
        
        # Default distances for special cases
        if 'fun run' in name_lower:
            return 3.0  # Assume 3km for fun runs
        elif 'ultra' in name_lower:
            return 50.0  # Default ultra distance
        elif 'team' in name_lower or 'competition' in name_lower:
            return 55.0  # For team competitions, use the event's main distance
        
        return None

    def scrape_race_results_from_url(self, race_url: str, race_obj=None, force_refresh: bool = False) -> List[Dict]:
        """
        Scrape race results from a specific corsa.is race results URL.
        
        Args:
            race_url: URL to the specific race results page
            race_obj: Race model instance for caching (optional)
            force_refresh: If True, always fetch from web and update cache
            
        Returns:
            List of result dictionaries
        """
        try:
            # Fetch HTML with caching
            html_content = self._fetch_html_with_cache(race_url, race_obj, force_refresh)
            
            # Parse results from HTML
            return self._extract_results_from_html(html_content, race_url)
            
        except Exception as e:
            logger.error(f"Error scraping race results from {race_url}: {str(e)}")
            raise CorsaScrapingError(f"Failed to scrape race results: {str(e)}")

    def _extract_results_from_html(self, html_content: str, source_url: str) -> List[Dict]:
        """
        Extract race results from corsa.is HTML content.
        
        Since corsa.is is a React app, the results might be dynamically loaded.
        We'll try to extract what we can from the initial HTML.
        """
        try:
            results = self._extract_results_from_participants_payload(html_content)
            if results:
                logger.info(f"Extracted {len(results)} results from participants payload in {source_url}")
                return results

            soup = BeautifulSoup(html_content, 'lxml')
            results = []
            
            # Look for result entries in the HTML
            # The structure might be in JavaScript/JSON data or as rendered HTML elements
            
            # Try to find JSON data in script tags (common in Next.js apps)
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and 'results' in script.string.lower():
                    # Try to extract JSON data
                    results_data = self._extract_results_from_script(script.string)
                    if results_data:
                        results.extend(results_data)
                        break
            
            # If no results found in scripts, try to parse from rendered HTML
            if not results:
                results = self._extract_results_from_rendered_html(soup)
            
            logger.info(f"Extracted {len(results)} results from {source_url}")
            return results
            
        except Exception as e:
            logger.error(f"Error extracting results from HTML: {str(e)}")
            return []

    def _extract_results_from_participants_payload(self, html_content: str) -> List[Dict]:
        """
        Fast-path extractor for pages that embed a participants JSON array.
        This avoids expensive regex scans on large Next.js payloads.
        """
        # Next.js chunks often contain escaped JSON fragments; normalize once.
        normalized = re.sub(r'\\+"', '"', html_content)

        marker_pos = normalized.find('"participants":[')
        if marker_pos < 0:
            return []

        start = normalized.find('[', marker_pos)
        if start < 0:
            return []

        depth = 0
        in_string = False
        escaped = False
        end = -1

        for idx in range(start, len(normalized)):
            ch = normalized[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = idx
                    break

        if end < 0:
            return []

        payload = normalized[start:end + 1]

        try:
            participants = json.loads(payload)
        except json.JSONDecodeError:
            return []

        if not isinstance(participants, list):
            return []

        results = []
        for participant in participants:
            if not isinstance(participant, dict):
                continue

            gun_time_ms = participant.get('gunTime')
            chip_time_ms = participant.get('chipTime')

            try:
                gun_time_seconds = (float(gun_time_ms) / 1000.0) if gun_time_ms is not None else None
            except (TypeError, ValueError):
                gun_time_seconds = None

            try:
                chip_time_seconds = (float(chip_time_ms) / 1000.0) if chip_time_ms is not None else None
            except (TypeError, ValueError):
                chip_time_seconds = None

            rank_raw = participant.get('rankOverall')
            try:
                rank_overall = int(rank_raw)
            except (TypeError, ValueError):
                rank_overall = 0

            result = {
                'bib_number': str(participant.get('bib', '') or ''),
                'name': str(participant.get('name', '') or ''),
                'gender': str(participant.get('gender', '') or '').lower(),
                'gun_time_seconds': gun_time_seconds,
                'net_time_seconds': chip_time_seconds,
                'rank_overall': rank_overall,
                'participant_id': str(participant.get('id', '') or ''),
                'status': participant.get('status'),
                'progress': participant.get('progress'),
            }

            if result['name']:
                results.append(result)

        return results

    def _extract_results_from_script(self, script_content: str) -> List[Dict]:
        """
        Try to extract results data from JavaScript/JSON in script tags.
        
        Corsa.is uses Next.js streaming format where data is in self.__next_f.push() calls.
        The participants array contains the race results.
        """
        results = []
        try:
            # Look for Next.js streaming data format: self.__next_f.push([1,"..."])
            if 'self.__next_f.push([1,' in script_content:
                # Extract the data from Next.js streaming format
                start = script_content.find('self.__next_f.push([1,') + len('self.__next_f.push([1,')
                end = script_content.rfind('])')
                
                if end > start:
                    data_part = script_content[start:end]
                    
                    # Remove the quotes around the JSON string and unescape
                    if data_part.startswith('"') and data_part.endswith('"'):
                        json_string = data_part[1:-1]
                        
                        # Look for the participants array pattern in the unescaped JSON
                        # The JSON is double-escaped, so we need to handle the escaped quotes
                        participants_pattern = r'\\\\\"participants\\\\\":\s*\[([^\]]+)\]'
                        match = re.search(participants_pattern, json_string)
                        
                        if match:
                            participants_data = match.group(1)
                            
                            # Extract individual participant objects
                            # Each participant object contains: id, bib, name, gender, gunTime, chipTime, etc.
                            # The JSON is double-escaped: {\"id\":\"162813\",\"bib\":\"2042\",...}
                            participant_pattern = r'\{\\\"id\\\":\\\"([^"]+)\\\",\\\"bib\\\":\\\"([^"]+)\\\",.*?\\\"name\\\":\\\"([^"]+)\\\",.*?\\\"gender\\\":\\\"([^"]+)\\\",.*?\\\"gunTime\\\":(\d+),\\\"chipTime\\\":(\d+),.*?\\\"rankOverall\\\":(\d+)'
                            
                            for participant_match in re.finditer(participant_pattern, participants_data):
                                try:
                                    # Extract participant data
                                    participant_id = participant_match.group(1)
                                    bib_number = participant_match.group(2) 
                                    name = participant_match.group(3)
                                    gender = participant_match.group(4)
                                    gun_time_ms = int(participant_match.group(5))
                                    chip_time_ms = int(participant_match.group(6))
                                    rank = int(participant_match.group(7))
                                    
                                    # Convert milliseconds to seconds for our format
                                    gun_time_seconds = gun_time_ms / 1000.0
                                    chip_time_seconds = chip_time_ms / 1000.0
                                    
                                    result = {
                                        'bib_number': bib_number,
                                        'name': name,
                                        'gender': gender.lower(),
                                        'gun_time_seconds': gun_time_seconds,
                                        'net_time_seconds': chip_time_seconds, 
                                        'rank_overall': rank,
                                        'participant_id': participant_id
                                    }
                                    
                                    results.append(result)
                                    
                                except (ValueError, IndexError) as e:
                                    logger.debug(f"Error parsing participant: {str(e)}")
                                    continue
                            
                            logger.info(f"Extracted {len(results)} participants from Next.js streaming data")
                        else:
                            # Try a broader search for participants data
                            logger.debug("Participants array not found with standard pattern, trying broader search")
                            self._extract_participants_broader_search(json_string, results)
            
            # Fallback to older patterns for other data formats            
            if not results:
                json_patterns = [
                    r'window\.__NEXT_DATA__\s*=\s*({.+?});',
                    r'"props"\s*:\s*({.+?"results".+?})',
                    r'"results"\s*:\s*(\[.+?\])',
                ]
                
                for pattern in json_patterns:
                    match = re.search(pattern, script_content, re.DOTALL)
                    if match:
                        try:
                            json_data = json.loads(match.group(1))
                            # Process the JSON data to extract results
                            parsed_results = self._process_json_results(json_data)
                            results.extend(parsed_results)
                        except json.JSONDecodeError:
                            continue
                        
        except Exception as e:
            logger.debug(f"Failed to extract results from script: {str(e)}")
            
        return results

    def _extract_results_from_rendered_html(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract results from rendered HTML elements.
        
        Based on the sample HTML, look for result entries with runner info.
        """
        results = []
        
        try:
            # Look for result patterns based on the sample HTML
            # The format seems to be: "Rank X [Image] Name Bib: XXX Gun time XX:XX:XX Behind +XX:XX"
            
            # Try different approaches to find result data
            text_content = soup.get_text()
            
            # Pattern to match result lines
            result_pattern = r'Rank\s+(\d+).*?([A-Za-zÀ-ÿ\s]+)\s+Bib:\s+(\d+)\s+Gun\s+time\s+([\d:]+)\s+Behind\s+([\d:+-]+)'
            
            matches = re.finditer(result_pattern, text_content, re.MULTILINE | re.IGNORECASE)
            
            for match in matches:
                try:
                    rank = int(match.group(1))
                    name = match.group(2).strip()
                    bib_number = match.group(3)
                    gun_time = match.group(4)
                    behind_time = match.group(5)
                    
                    # Convert time to seconds for consistency
                    finish_time_seconds = self._time_to_seconds(gun_time)
                    
                    result = {
                        'rank': rank,
                        'name': name,
                        'bib_number': bib_number,
                        'finish_time': gun_time,
                        'finish_time_seconds': finish_time_seconds,
                        'behind_time': behind_time,
                        'status': 'Finished',
                        'source': 'corsa.is'
                    }
                    
                    results.append(result)
                    
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse result match: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting results from rendered HTML: {str(e)}")
            
        return results

    def _extract_participants_broader_search(self, json_string: str, results: List[Dict]) -> None:
        """
        Broader search for participants data when the standard pattern doesn't work.
        
        This method looks for individual participant objects even if they're not 
        in a clearly defined participants array.
        """
        try:
            # Look for individual participant objects with racing data
            # The JSON is double-escaped in Next.js streaming format
            # Pattern: {\"id\":\"162813\",\"bib\":\"2042\",\"name\":\"Michael R Nasuta\",...}
            broader_pattern = r'\{\\\"id\\\":\\\"([^"]+)\\\",.*?\\\"bib\\\":\\\"([^"]+)\\\",.*?\\\"name\\\":\\\"([^"]+)\\\",.*?\\\"gender\\\":\\\"([^"]+)\\\",.*?\\\"gunTime\\\":(\d+),.*?\\\"chipTime\\\":(\d+),.*?\\\"rankOverall\\\":(\d+)'
            
            for match in re.finditer(broader_pattern, json_string):
                try:
                    participant_id = match.group(1)
                    bib_number = match.group(2)
                    name = match.group(3)
                    gender = match.group(4)
                    gun_time_ms = int(match.group(5))
                    chip_time_ms = int(match.group(6))
                    rank = int(match.group(7))
                    
                    # Convert milliseconds to seconds
                    gun_time_seconds = gun_time_ms / 1000.0
                    chip_time_seconds = chip_time_ms / 1000.0
                    
                    result = {
                        'bib_number': bib_number,
                        'name': name,
                        'gender': gender.lower(),
                        'gun_time_seconds': gun_time_seconds,
                        'net_time_seconds': chip_time_seconds,
                        'rank_overall': rank,
                        'participant_id': participant_id
                    }
                    
                    results.append(result)
                    
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing participant in broader search: {str(e)}")
                    continue
                    
            if results:
                logger.info(f"Broader search found {len(results)} participants")
                
        except Exception as e:
            logger.debug(f"Error in broader participant search: {str(e)}")

    def _process_json_results(self, json_data: Dict) -> List[Dict]:
        """
        Process JSON data to extract result information.
        
        This will need to be adapted based on the actual JSON structure from corsa.is.
        """
        results = []
        
        try:
            # Navigate through the JSON structure to find results
            # This is speculative - we'd need to see the actual JSON structure
            
            if isinstance(json_data, dict):
                # Look for results in various possible locations
                possible_paths = [
                    ['props', 'pageProps', 'results'],
                    ['props', 'results'],
                    ['results'],
                    ['data', 'results'],
                ]
                
                for path in possible_paths:
                    current = json_data
                    try:
                        for key in path:
                            current = current[key]
                        
                        if isinstance(current, list):
                            for item in current:
                                result = self._parse_json_result_item(item)
                                if result:
                                    results.append(result)
                            break
                            
                    except (KeyError, TypeError):
                        continue
                        
        except Exception as e:
            logger.debug(f"Error processing JSON results: {str(e)}")
            
        return results

    def _parse_json_result_item(self, item: Dict) -> Optional[Dict]:
        """
        Parse a single result item from JSON data.
        """
        try:
            # Extract common fields that might be in the JSON
            result = {
                'name': item.get('name', '').strip(),
                'bib_number': str(item.get('bib', item.get('bibNumber', ''))),
                'finish_time': item.get('finishTime', item.get('gunTime', '')),
                'rank': item.get('rank', item.get('position', 0)),
                'status': item.get('status', 'Finished'),
                'club': item.get('club', item.get('team', '')),
                'gender': item.get('gender', ''),
                'age': item.get('age', ''),
                'source': 'corsa.is'
            }
            
            # Only return if we have at least a name
            if result['name']:
                return result
                
        except Exception as e:
            logger.debug(f"Failed to parse JSON result item: {str(e)}")
            
        return None

    def _time_to_seconds(self, time_str: str) -> Optional[int]:
        """
        Convert time string (HH:MM:SS or MM:SS) to seconds.
        """
        try:
            parts = time_str.split(':')
            if len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            pass
        return None

import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class TimatakaScrapingError(Exception):
    """Custom exception for Timataka scraping errors"""
    pass


class TimatakaScraper:
    """
    Scraper for Timataka.net race pages.
    
    Extracts race information from HTML content including:
    - Main race name and date
    - Multiple race distances/categories
    - Start times for each race
    - Race results with splits and times
    """
    
    def __init__(self):
        self.base_url = "https://timataka.net"
        self.race_type_mapping = {
            'marathon': 'marathon',
            'hálf marathon': 'half_marathon',
            'half marathon': 'half_marathon',
            '10k': '10k',
            '5k': '5k',
            'km': 'other',  # fallback for various km distances
            'tindur': 'trail',  # Icelandic mountain running
            'tindar': 'trail',
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
            
            # For homepage URL without cache object, we could implement file-based caching
            # but for now, just log that no cache object is available
            if not cache_obj:
                logger.info(f"No cache object available for URL: {url}, fetching from web")
            
            # Fetch from web
            logger.info(f"Fetching HTML from web for URL: {url}")
            response = requests.get(url, timeout=30)
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
                raise TimatakaScrapingError(f"Failed to fetch {url}: {str(e)}")
    def scrape_race_data(self, html_content: str, source_url: str = "") -> List[Dict]:
        """
        Scrape race data from Timataka.net HTML content.
        
        Args:
            html_content: Raw HTML content from a Timataka page
            source_url: Original URL for reference
            
        Returns:
            List of race dictionaries with extracted data
            
        Raises:
            TimatakaScrapingError: If scraping fails or data is invalid
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract main race information
            main_race_name = self._extract_main_race_name(soup)
            base_location = self._extract_location_from_name(main_race_name)
            
            # Extract individual race categories/distances
            race_categories = self._extract_race_categories(soup, main_race_name, base_location, source_url)
            
            if not race_categories:
                raise TimatakaScrapingError("No race categories found in the HTML")
            
            return race_categories
            
        except Exception as e:
            logger.error(f"Error scraping race data: {str(e)}")
            raise TimatakaScrapingError(f"Failed to scrape race data: {str(e)}")
    
    def discover_races_from_homepage(self, force_refresh: bool = False) -> List[Dict]:
        """
        Discover races by scraping the main timataka.net homepage.
        
        Args:
            force_refresh: If True, bypass cache and fetch from web
        
        Returns:
            List of dictionaries containing race information:
            - name: Race name (in Icelandic)
            - date: Race date as datetime object
            - url: Link to the race page
            
        Raises:
            TimatakaScrapingError: If scraping fails or data is invalid
        """
        try:
            # Fetch the main timataka.net page with caching
            # Since this is the homepage, we'll use a simple approach
            html_content = self._fetch_html_with_cache(self.base_url, cache_obj=None, force_refresh=force_refresh)
            
            soup = BeautifulSoup(html_content, 'lxml')
            races = []
            
            # Find the left-area div which contains race links
            left_area = soup.find('div', id='left-area')
            if not left_area:
                logger.warning("Could not find 'left-area' div on timataka.net homepage")
                return races
            
            # Find all elements within the left-area div, tracking h3 headers for month/year context
            current_month_year = None
            
            for element in left_area.find_all(['h3', 'li']):
                if element.name == 'h3':
                    # Extract month/year from h3 header
                    current_month_year = self._parse_month_year_header(element.get_text().strip())
                    logger.debug(f"Found date context: {current_month_year}")
                
                elif element.name == 'li':
                    # Look for race links within this li element
                    link = element.find('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        
                        # Skip empty hrefs or pure anchors
                        if not href or href.startswith('#'):
                            continue
                        
                        # Only process timataka.net race links
                        if 'timataka.net' not in href:
                            continue
                        
                        # Extract race information from the li element and its link
                        race_info = self._extract_race_info_from_li(element, link, current_month_year)
                        if race_info:
                            races.append(race_info)
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_races = []
            for race in races:
                if race['url'] not in seen_urls:
                    seen_urls.add(race['url'])
                    unique_races.append(race)
            
            logger.info(f"Discovered {len(unique_races)} races from timataka.net homepage")
            return unique_races
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching timataka.net homepage: {str(e)}")
            raise TimatakaScrapingError(f"Failed to fetch homepage: {str(e)}")
        except Exception as e:
            logger.error(f"Error discovering races: {str(e)}")
            raise TimatakaScrapingError(f"Failed to discover races: {str(e)}")
    
    def scrape_races_from_event_url(self, event_url: str, event_obj=None, force_refresh: bool = False) -> List[Dict]:
        """
        Scrape individual races from an event page URL.
        
        Args:
            event_url: URL to the event page on timataka.net
            event_obj: Optional Event model instance for HTML caching
            force_refresh: If True, bypass cache and fetch from web
            
        Returns:
            List of dictionaries containing race information:
            - name: Race name
            - race_type: Type of race (marathon, 10k, etc.)
            - date: Race date
            - location: Race location
            - distance_km: Distance in kilometers
            - etc.
            
        Raises:
            TimatakaScrapingError: If scraping fails or data is invalid
        """
        try:
            # Check if this URL is already a direct results URL with race parameters
            # (This distinguishes between normalized event pages and actual results URLs)
            if '/urslit/' in event_url and 'race=' in event_url:
                # This is a direct results URL that needs to be treated as a single race
                return self._handle_direct_results_url(event_url)
            
            # Fetch the event page with caching
            html_content = self._fetch_html_with_cache(event_url, event_obj, force_refresh)

            # Use a specialized method for extracting races from event pages
            races = self.scrape_race_data_from_event_page(html_content, event_url)

            logger.info(f"Scraped {len(races)} races from event URL: {event_url}")
            return races

        except TimatakaScrapingError:
            # Re-raise our custom errors
            raise
        except Exception as e:
            logger.error(f"Error scraping races from event: {str(e)}")
            raise TimatakaScrapingError(f"Failed to scrape races from event: {str(e)}")

    def scrape_race_data_from_event_page(self, html_content: str, source_url: str) -> List[Dict]:
        """
        Scrape race data from a Timataka event page (not results page).
        
        Event pages typically contain general information about the event and may
        link to different race categories or distances.
        
        Args:
            html_content: Raw HTML content from a Timataka event page
            source_url: Original URL for reference
            
        Returns:
            List of race dictionaries with extracted data
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract main event information
            main_race_name = self._extract_main_race_name(soup)
            if not main_race_name:
                # Fallback: try to get title from page
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text().strip()
                    # Remove "TÍMATAKA: " prefix if present
                    main_race_name = title_text.replace('TÍMATAKA: ', '').strip()
                else:
                    main_race_name = "Unknown Event"
            
            location = self._extract_location_from_name(main_race_name)
            
            # For event pages, we often just have one main race/event
            # Try to extract more detailed information
            
            # Build results URL for single race events
            # Since event URLs are now normalized to results URLs at save time,
            # we can use the source_url directly
            results_url = source_url
            
            race_info = {
                'name': main_race_name,
                'race_type': self._determine_race_type_from_name(main_race_name),
                'date': self._extract_race_date_from_page(soup),
                'location': location,
                'distance_km': self._extract_distance_from_name(main_race_name),
                'elevation_gain_m': 0,  # Default, rarely available on event pages
                'organizer': 'Tímataka',
                'currency': 'ISK',
                'description': self._extract_race_description(soup),
                'source_url': source_url,
                'results_url': results_url
            }
            
            # Try to find multiple race categories if they exist on the event page
            # Look for different patterns that might indicate multiple races
            race_categories = self._extract_race_categories_from_event_page(soup, main_race_name, location, source_url)
            
            if race_categories:
                return race_categories
            else:
                # Return single race based on main event info
                return [race_info]
                
        except Exception as e:
            logger.error(f"Error scraping race data from event page: {str(e)}")
            raise TimatakaScrapingError(f"Failed to scrape race data from event page: {str(e)}")
    
    def _extract_race_categories_from_event_page(self, soup: BeautifulSoup, main_race_name: str, 
                                               location: str, source_url: str) -> List[Dict]:
        """Extract race categories from an event page (different from results page)"""
        race_categories = []
        
        # First check for the alternative format with result links and race IDs
        detailed_races = self._extract_races_from_result_links(soup, main_race_name, location, source_url)
        if detailed_races:
            return detailed_races
        
        # Fall back to the original pattern matching approach
        # Pattern 1: Look for distance information in the page content
        content_text = soup.get_text().lower()
        
        # Extract explicit km mentions first, including comma decimals.
        explicit_distances = []
        distance_matches = re.findall(r'(?<![\d,.])(\d+(?:[.,]\d+)?)\s?km\b', content_text, re.IGNORECASE)
        for distance_match in distance_matches:
            try:
                distance_value = float(distance_match.replace(',', '.'))
            except ValueError:
                continue

            if distance_value <= 0 or distance_value > 200:
                continue

            rounded_distance = round(distance_value, 3)
            if rounded_distance not in explicit_distances:
                explicit_distances.append(rounded_distance)

        # If we found explicit distances, create separate races for each.
        if explicit_distances:
            for distance in explicit_distances:
                race_type = self._determine_race_type_from_distance(distance)
                distance_label = f"{distance:g} km"
                
                # Since event URLs are now normalized to results URLs at save time,
                # we can use the source_url directly
                results_url = source_url
                
                race_info = {
                    'name': f"{main_race_name} - {distance_label}",
                    'race_type': race_type,
                    'date': self._extract_race_date_from_page(soup),
                    'location': location,
                    'distance_km': distance,
                    'elevation_gain_m': 0,
                    'organizer': 'Tímataka',
                    'currency': 'ISK',
                    'description': self._extract_race_description(soup),
                    'source_url': source_url,
                    'results_url': results_url
                }
                race_categories.append(race_info)
        
        # Fall back to coarse keyword detection only when no explicit distances are present.
        if not race_categories:
            distance_patterns = [
                (r'\bmaraþon\b|\bmarathon\b', 'marathon', 42.2),
                (r'\bhálf(?:[- ]?maraþon)?\b|\bhalf(?:[- ]?marathon)?\b', 'half_marathon', 21.1),
                (r'(?<![\d,.])10\s?km\b', '10k', 10.0),
                (r'(?<![\d,.])5\s?km\b', '5k', 5.0),
            ]
            
            found_distances = []
            for pattern, race_type, distance in distance_patterns:
                if re.search(pattern, content_text):
                    found_distances.append((race_type, distance))
            
            # If we found specific distances, create separate races for each
            for race_type, distance in found_distances:
                # Since event URLs are now normalized to results URLs at save time,
                # we can use the source_url directly
                results_url = source_url
                
                race_info = {
                    'name': f"{main_race_name} - {race_type.replace('_', ' ').title()}",
                    'race_type': race_type,
                    'date': self._extract_race_date_from_page(soup),
                    'location': location,
                    'distance_km': distance,
                    'elevation_gain_m': 0,
                    'organizer': 'Tímataka',
                    'currency': 'ISK',
                    'description': self._extract_race_description(soup),
                    'source_url': source_url,
                    'results_url': results_url
                }
                race_categories.append(race_info)
        
        return race_categories
    
    def _extract_races_from_result_links(self, soup: BeautifulSoup, main_race_name: str, 
                                       location: str, source_url: str) -> List[Dict]:
        """
        Extract races from pages that have result links with race IDs.
        This handles the alternative format like tindahlaup2019.
        """
        race_categories = []
        
        # Look for result links with race IDs
        links = soup.find_all('a', href=True)
        # Look for links that contain race= parameter (they might be relative URLs like ?race=1)
        race_links = [link for link in links if 'race=' in link.get('href', '')]
        
        if not race_links:
            return []
        
        # Group links by race ID and extract race information
        race_data = {}
        for link in race_links:
            href = link.get('href', '')
            link_text = link.get_text().strip()
            link_distance = self._extract_distance_from_name(link_text)
            context_heading = link.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            context_name = " ".join(context_heading.get_text().split()) if context_heading else ""
            context_distance = self._extract_distance_from_name(context_name) if context_name else 0.0
            
            # Extract race ID from URL
            race_match = re.search(r'race=(\d+)', href)
            if race_match:
                race_id = race_match.group(1)
                
                if race_id not in race_data:
                    race_data[race_id] = {
                        'href': href,
                        'distance_km': link_distance if link_distance > 0 else 0.0,
                        'context_name': context_name,
                    }
                    if race_data[race_id]['distance_km'] <= 0 and context_distance > 0:
                        race_data[race_id]['distance_km'] = context_distance
                elif link_distance > 0 and race_data[race_id]['distance_km'] <= 0:
                    race_data[race_id]['distance_km'] = link_distance
                elif context_distance > 0 and race_data[race_id]['distance_km'] <= 0:
                    race_data[race_id]['distance_km'] = context_distance

                if not race_data[race_id].get('context_name') and context_name:
                    race_data[race_id]['context_name'] = context_name

                # Prioritize "overall" category links, or ensure we have cat=overall
                if 'cat=overall' in href:
                    # Perfect - this is the overall results link
                    race_data[race_id]['href'] = href
                elif 'cat=' not in href and 'cat=overall' not in race_data[race_id]['href']:
                    # No category specified - add overall category
                    race_data[race_id]['href'] = self._ensure_overall_category(href)
                else:
                    # Has a category but not overall - keep current value
                    pass
        
        # Build race entries per race ID using local context from links.
        base_date = self._extract_race_date_from_page(soup)
        if race_data:
            for race_entry in race_data.values():
                href = self._ensure_overall_category(race_entry['href'])
                base_url = source_url.rstrip('/')
                results_url = f"{base_url}/{href}"

                distance_km = race_entry.get('distance_km') or 0.0
                context_name = (race_entry.get('context_name') or "").strip()
                normalized_main = " ".join(main_race_name.split()).strip()
                normalized_context = " ".join(context_name.split()).strip()
                normalized_main_lower = normalized_main.lower()
                normalized_context_lower = normalized_context.lower()

                race_name = normalized_main
                if (
                    normalized_context
                    and normalized_context_lower != normalized_main_lower
                    and normalized_context_lower not in normalized_main_lower
                    and normalized_main_lower not in normalized_context_lower
                ):
                    race_name = f"{normalized_main} - {normalized_context}"

                type_hint_name = normalized_context or normalized_main
                race_type = (
                    self._determine_race_type_from_distance(distance_km)
                    if distance_km > 0
                    else self._determine_race_type_from_name(type_hint_name)
                )

                race_info = {
                    'name': race_name,
                    'race_type': race_type,
                    'date': base_date,
                    'location': location,
                    'distance_km': distance_km,
                    'elevation_gain_m': 0,
                    'organizer': 'Tímataka',
                    'currency': 'ISK',
                    'description': f"Race context: {normalized_context or normalized_main}",
                    'source_url': source_url,
                    'results_url': results_url
                }
                race_categories.append(race_info)
        
        return race_categories
    
    def _determine_race_type_from_distance(self, distance_km: float) -> str:
        """Determine race type based on distance in kilometers"""
        if distance_km > 43.5:
            return 'ultra'
        if 41.0 <= distance_km <= 43.5:
            return 'marathon'
        elif 20.0 <= distance_km <= 22.5:
            return 'half_marathon'
        elif 9.0 <= distance_km <= 11.0:
            return '10k'
        elif 4.0 <= distance_km <= 6.0:
            return '5k'
        else:
            return 'other'

    def _ensure_overall_category(self, href: str) -> str:
        """Ensure that a race results href includes cat=overall parameter"""
        if 'cat=overall' in href:
            # Already has overall category
            return href
        elif 'cat=' in href:
            # Has a different category - replace it with overall
            import re
            return re.sub(r'cat=[^&]*', 'cat=overall', href)
        else:
            # No category specified - add overall category
            if '?' in href:
                return f"{href}&cat=overall"
            else:
                return f"{href}?cat=overall"
    
    def _extract_race_date_from_page(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract race date from event page content"""
        # Look for date patterns in the page content
        content_text = soup.get_text()
        
        # Common Icelandic date patterns
        date_patterns = [
            r'(\d{1,2})\.\s*(janúar|febrúar|mars|apríl|maí|júní|júlí|ágúst|september|október|nóvember|desember)\s*(\d{4})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
        ]
        
        icelandic_months = {
            'janúar': 1, 'febrúar': 2, 'mars': 3, 'apríl': 4, 'maí': 5, 'júní': 6,
            'júlí': 7, 'ágúst': 8, 'september': 9, 'október': 10, 'nóvember': 11, 'desember': 12
        }
        
        for pattern in date_patterns:
            match = re.search(pattern, content_text, re.IGNORECASE)
            if match:
                try:
                    if 'janúar' in pattern:  # Icelandic format
                        day, month_name, year = match.groups()
                        month = icelandic_months.get(month_name.lower())
                        if month:
                            return datetime(int(year), month, int(day))
                    else:  # Numeric formats
                        groups = match.groups()
                        if len(groups) == 3:
                            if '-' in pattern:  # YYYY-MM-DD
                                year, month, day = groups
                            else:  # DD/MM/YYYY
                                day, month, year = groups
                            return datetime(int(year), int(month), int(day))
                except ValueError:
                    continue
        
        return None
    
    def _extract_race_description(self, soup: BeautifulSoup) -> str:
        """Extract race description from page content"""
        # Look for meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc.get('content').strip()
        
        # Look for main content area
        content_areas = soup.find_all(['div', 'section'], class_=['content', 'main', 'description'])
        for area in content_areas:
            text = area.get_text().strip()
            if len(text) > 50:  # Meaningful content
                return text[:500]  # Limit length
        
        return ""
    
    def _determine_race_type_from_name(self, name: str) -> str:
        """Determine race type from race name"""
        name_lower = name.lower()
        
        type_mappings = {
            'hálf': 'half_marathon',
            'half': 'half_marathon',
            'marathon': 'marathon',
            'maraþon': 'marathon',
            'ultra': 'ultra',
            '10k': '10k',
            '5k': '5k',
            'hlaup': 'other',  # Generic "run" in Icelandic
            'þríþraut': 'other',  # Triathlon
            'criterium': 'other',
            'hjól': 'other',  # Cycling
            'trail': 'trail',
        }
        
        for keyword, race_type in type_mappings.items():
            if keyword in name_lower:
                return race_type
        
        return 'other'
    
    def _extract_distance_from_name(self, name: str) -> float:
        """Extract distance from race name"""
        name_lower = name.lower()
        
        # Look for explicit distance mentions
        distance_patterns = [
            # Support compact forms like "26K" as well as "26 km"
            (r'(\d+(?:[.,]\d+)?)\s?(?:km|k)\b', lambda m: float(m.group(1).replace(',', '.'))),
            (r'\bh[áa]lf(?:[-\s]?maraþon)?\b|\bhalf(?:[-\s]?marathon)?\b', 21.1),
            (r'\bmarathon\b|\bmaraþon\b', 42.2),
            (r'\b10\s?k\b', 10.0),
            (r'\b5\s?k\b', 5.0),
        ]
        
        for pattern, distance in distance_patterns:
            match = re.search(pattern, name_lower)
            if match:
                if callable(distance):
                    return distance(match)
                else:
                    return distance

        # Handle labels like "Austur Ultra 53" where km suffix is omitted.
        # Exclude year-like values to avoid false positives (e.g. "Ultra 2025").
        if 'ultra' in name_lower:
            numeric_matches = re.findall(r'\b(\d{1,3}(?:[.,]\d+)?)\b', name_lower)
            for token in numeric_matches:
                try:
                    value = float(token.replace(',', '.'))
                except ValueError:
                    continue
                if 1.0 <= value <= 200.0:
                    return value
        
        return 0.0  # Default if no distance found

    def _parse_month_year_header(self, header_text: str) -> Optional[Dict]:
        """Parse month and year from h3 header text like 'Sep 2025' or 'Ágú 2024'"""
        if not header_text:
            return None
            
        # Icelandic month abbreviations to numbers
        icelandic_months = {
            # Icelandic months
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maí': 5, 'jún': 6,
            'júl': 7, 'ágú': 8, 'sep': 9, 'okt': 10, 'nóv': 11, 'des': 12,
            # English abbreviations (common on timataka.net)
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'aug': 8, 'jul': 7, 'jun': 6, 'dec': 12, 'nov': 11, 'oct': 10
        }
        
        # Try to extract month and year pattern like "Sep 2025" or "Ágú 2024"
        parts = header_text.lower().split()
        if len(parts) >= 2:
            month_str = parts[0]
            year_str = parts[1]
            
            # Find matching month
            month = None
            for month_key, month_num in icelandic_months.items():
                if month_str.startswith(month_key):
                    month = month_num
                    break
            
            # Parse year
            try:
                year = int(year_str)
                if month and 2000 <= year <= 2030:  # Reasonable year range
                    return {'month': month, 'year': year}
            except ValueError:
                pass
        
        return None
    
    def _extract_race_info_from_li(self, li_element, link, date_context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract race information from a li element containing a race link and its date"""
        try:
            href = link.get('href')
            
            # Convert relative URL to absolute
            if href.startswith('/'):
                race_url = self.base_url + href
            else:
                race_url = href
            
            # Get the link text as race name
            race_name = link.get_text().strip()
            
            # Skip if name is too short
            if len(race_name) < 3:
                return None
                
            # Skip some obvious non-race links
            skip_names = [
                'here', 'click', 'more', 'info', 'contact', 'about',
                'myndir', 'pictures', 'results only', 'úrslit'
            ]
            if race_name.lower() in skip_names:
                return None
            
            # Get the full text of the li element which should contain the date
            li_text = li_element.get_text().strip()
            
            # Try to extract date from the li element text first
            race_date = self._parse_icelandic_date_from_li(li_text, date_context)
            
            # If no date found from li, fall back to previous methods
            if not race_date:
                race_date = self._extract_date_with_context(race_name, race_url, date_context)
            
            if not race_date:
                race_date = self._extract_date_from_name(race_name)
            
            if not race_date:
                race_date = self._extract_date_from_url(race_url)
            
            return {
                'name': race_name,
                'date': race_date,
                'url': race_url,
            }
            
        except Exception as e:
            logger.warning(f"Error extracting race info from li: {str(e)}")
            return None
    
    def _parse_icelandic_date_from_li(self, li_text: str, date_context: Optional[Dict] = None) -> Optional[datetime]:
        """Parse Icelandic date from li element text like 'Race Name (3. september)'"""
        if not li_text or not date_context:
            return None
        
        # Look for date pattern in parentheses like "(3. september)" or "(31. ágúst)"
        date_pattern = r'\((\d{1,2})\.\s*([a-záðéíóúýþæø]+)\)'
        match = re.search(date_pattern, li_text, re.IGNORECASE)
        
        if match:
            day_str = match.group(1)
            month_str = match.group(2).lower()
            
            # Icelandic month names
            icelandic_months = {
                'janúar': 1, 'jan': 1,
                'febrúar': 2, 'feb': 2,
                'mars': 3, 'mar': 3,
                'apríl': 4, 'apr': 4,
                'maí': 5, 'may': 5,
                'júní': 6, 'jun': 6,
                'júlí': 7, 'jul': 7,
                'ágúst': 8, 'aug': 8, 'ágú': 8,
                'september': 9, 'sep': 9,
                'október': 10, 'okt': 10, 'oct': 10,
                'nóvember': 11, 'nóv': 11, 'nov': 11,
                'desember': 12, 'des': 12, 'dec': 12
            }
            
            try:
                day = int(day_str)
                
                # Find matching month
                month = None
                for month_key, month_num in icelandic_months.items():
                    if month_str.startswith(month_key) or month_key.startswith(month_str):
                        month = month_num
                        break
                
                if month and 1 <= day <= 31:
                    # Use year from date_context
                    year = date_context.get('year', datetime.now().year)
                    try:
                        return datetime(year, month, day)
                    except ValueError:
                        # Invalid date (e.g., Feb 30), fall back to context
                        pass
                        
            except ValueError:
                pass
        
        return None
    
    def _extract_race_info_from_link(self, link, soup: BeautifulSoup, date_context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract race information from a race link and its context"""
        try:
            href = link.get('href')
            
            # Convert relative URL to absolute
            if href.startswith('/'):
                race_url = self.base_url + href
            else:
                race_url = href
            
            # Get the link text as potential race name
            race_name = link.get_text().strip()
            
            # Skip if name is too short
            if len(race_name) < 3:
                return None
                
            # Skip some obvious non-race links (but be more permissive)
            skip_names = [
                'here', 'click', 'more', 'info', 'contact', 'about',
                'myndir', 'pictures', 'results only', 'úrslit'
            ]
            if race_name.lower() in skip_names:
                return None
            
            # Try to extract date using the date context from h3 headers
            race_date = self._extract_date_with_context(race_name, race_url, date_context)
            
            # If no date found with context, fall back to old methods
            if not race_date:
                race_date = self._extract_date_from_context(link, soup)
                
            if not race_date:
                race_date = self._extract_date_from_name(race_name)
            
            if not race_date:
                race_date = self._extract_date_from_url(race_url)
            
            return {
                'name': race_name,
                'date': race_date,
                'url': race_url,
            }
            
        except Exception as e:
            logger.warning(f"Error extracting race info from link: {str(e)}")
            return None
    
    def _extract_date_with_context(self, race_name: str, race_url: str, date_context: Optional[Dict]) -> Optional[datetime]:
        """Extract race date using month/year context from h3 headers"""
        if not date_context:
            return None
            
        # Look for day information in race name or URL
        day = self._extract_day_from_text(race_name) or self._extract_day_from_text(race_url)
        
        if day:
            try:
                return datetime(date_context['year'], date_context['month'], day)
            except ValueError:
                # Invalid date (e.g., Feb 30), fall back to mid-month
                pass
        
        # If no specific day found, use mid-month as default
        try:
            return datetime(date_context['year'], date_context['month'], 15)
        except ValueError:
            return None
    
    def _extract_day_from_text(self, text: str) -> Optional[int]:
        """Extract day number from text"""
        if not text:
            return None
            
        # Look for day patterns like "13-03" (13th day), "2024-03-15", "15.", etc.
        day_patterns = [
            r'\b(\d{1,2})\.',  # "15."
            r'-(\d{1,2})-',    # "-15-"
            r'(\d{1,2})-\d{1,2}-\d{4}',  # "15-03-2024"
            r'\d{4}-\d{1,2}-(\d{1,2})',  # "2024-03-15"
            r'(\d{1,2}) ',     # "15 " (day followed by space)
        ]
        
        for pattern in day_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    day = int(match.group(1))
                    if 1 <= day <= 31:
                        return day
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        """Extract date from URL (e.g., from /racename2025/)"""
        # Look for year in URL
        year_match = re.search(r'(\d{4})', url)
        if year_match:
            year = int(year_match.group(1))
            if 2020 <= year <= 2030:  # Reasonable range
                # Default to mid-year if we only have year
                return datetime(year, 6, 15)
        return None
    
    def _extract_date_from_context(self, link, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract date from the context around a race link"""
        # Look for date patterns in the parent elements
        parent = link.parent
        attempts = 0
        
        while parent and attempts < 3:
            text = parent.get_text()
            date = self._parse_icelandic_date(text)
            if date:
                return date
            parent = parent.parent
            attempts += 1
        
        # Look for date in nearby siblings
        if link.parent:
            for sibling in link.parent.find_all_next(limit=5):
                text = sibling.get_text()
                date = self._parse_icelandic_date(text)
                if date:
                    return date
        
        return None
    
    def _extract_date_from_name(self, race_name: str) -> Optional[datetime]:
        """Try to extract date from race name"""
        return self._parse_icelandic_date(race_name)
    
    def _parse_icelandic_date(self, text: str) -> Optional[datetime]:
        """Parse Icelandic date from text"""
        if not text:
            return None
            
        # Icelandic month names
        icelandic_months = {
            'janúar': 1, 'febrúar': 2, 'mars': 3, 'apríl': 4,
            'maí': 5, 'júní': 6, 'júlí': 7, 'ágúst': 8,
            'september': 9, 'október': 10, 'nóvember': 11, 'desember': 12
        }
        
        # Try various Icelandic date patterns
        patterns = [
            r'(\d{1,2})\.\s*(\w+)\s*(\d{4})',  # "15. maí 2025"
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',    # "15 maí 2025"
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # "15.05.2025"
            r'(\d{4})-(\d{1,2})-(\d{1,2})',    # "2025-05-15"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) == 3:
                        if match.group(2).isdigit():
                            # Numeric date format
                            day = int(match.group(1))
                            month = int(match.group(2))
                            year = int(match.group(3))
                            return datetime(year, month, day)
                        else:
                            # Month name format
                            day = int(match.group(1))
                            month_name = match.group(2).lower()
                            year = int(match.group(3))
                            
                            month = icelandic_months.get(month_name)
                            if month:
                                return datetime(year, month, day)
                except (ValueError, KeyError):
                    continue
        
        return None
    
    def _extract_main_race_name(self, soup: BeautifulSoup) -> str:
        """Extract the main race name from the page title or header"""
        # Try title tag first
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text().strip()
            # Remove "TÍMATAKA: " prefix if present
            if 'TÍMATAKA:' in title_text:
                return title_text.split('TÍMATAKA:')[-1].strip()
            return title_text
        
        # Try h2 header
        h2_tag = soup.find('h2')
        if h2_tag:
            return h2_tag.get_text().strip()
        
        # Fallback to h1
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text().strip()
        
        return "Unknown Race"
    
    def _extract_location_from_name(self, race_name: str) -> str:
        """Extract location from race name (Icelandic place names)"""
        # Common Icelandic location patterns
        icelandic_locations = [
            'Reykjavík', 'Reykjavik', 'Mosfellsbær', 'Mosfellsbaer', 
            'Kópavogur', 'Kopavogur', 'Hafnarfjörður', 'Hafnarfjordur',
            'Garðabær', 'Gardabaer', 'Akureyri', 'Selfoss', 'Keflavík',
            'Vestmannaeyjar', 'Ísafjörður', 'Egilsstaðir'
        ]
        
        race_name_lower = race_name.lower()
        for location in icelandic_locations:
            if location.lower() in race_name_lower:
                return location
        
        # Extract from name patterns like "Tindahlaup Mosfellsbæjar"
        if 'mosfellsbæjar' in race_name_lower or 'mosfellsbaer' in race_name_lower:
            return 'Mosfellsbær'
        
        return "Iceland"  # Default fallback
    
    def _extract_race_categories(self, soup: BeautifulSoup, main_race_name: str, 
                                base_location: str, source_url: str) -> List[Dict]:
        """Extract individual race categories/distances from the page"""
        race_categories = []
        
        # Find all race category containers (typically in col-md-3 divs)
        category_containers = soup.find_all('div', class_='col-md-3')
        
        for container in category_containers:
            # Skip if this doesn't contain race information
            h4_tag = container.find('h4')
            if not h4_tag:
                continue
            
            race_info = self._parse_race_category_container(
                container, main_race_name, base_location, source_url
            )
            
            if race_info:
                race_categories.append(race_info)
        
        return race_categories
    
    def _parse_race_category_container(self, container, main_race_name: str, 
                                     base_location: str, source_url: str) -> Optional[Dict]:
        """Parse a single race category container"""
        try:
            # Extract race name and distance from h4 tag
            h4_tag = container.find('h4')
            if not h4_tag:
                return None
            
            race_text = h4_tag.get_text().strip()
            
            # Extract distance information
            distance_km, race_description = self._parse_race_distance(race_text)
            
            # Extract date and time
            date_info = self._extract_date_time(container)
            
            # Determine race type based on distance and description
            race_type = self._determine_race_type(race_description, distance_km)
            
            # Extract overall results URL
            results_url = self._extract_results_url(container)
            
            # Build the race name
            race_name = f"{main_race_name} - {race_description}"
            
            race_data = {
                'name': race_name,
                'description': f"{race_description} as part of {main_race_name}",
                'race_type': race_type,
                'date': date_info['date'],
                'location': base_location,
                'distance_km': distance_km,
                'elevation_gain_m': 0,  # Not available in this format
                'max_participants': None,
                'registration_url': '',
                'official_website': '',
                'organizer': 'Tímataka',
                'entry_fee': None,
                'currency': 'ISK',
                'source_url': source_url,
                'results_url': results_url,
                'start_time': date_info.get('time', ''),
            }
            
            return race_data
            
        except Exception as e:
            logger.warning(f"Error parsing race category container: {str(e)}")
            return None
    
    def _parse_race_distance(self, race_text: str) -> tuple[float, str]:
        """
        Parse distance from race text like '7 tindar (37 km)' or '3 tindar (19 km)'
        
        Returns:
            tuple: (distance_in_km, description)
        """
        # Pattern to match distance in parentheses
        km_pattern = r'\((\d+(?:[.,]\d+)?)\s*km\s*\)'
        km_match = re.search(km_pattern, race_text, re.IGNORECASE)
        
        if km_match:
            distance_km = float(km_match.group(1).replace(',', '.'))
            # Remove the km part to get description
            description = re.sub(km_pattern, '', race_text, flags=re.IGNORECASE).strip()
            return distance_km, description

        # Also support non-parenthesized patterns like "4,2 km"
        inline_km_pattern = r'\b(\d+(?:[.,]\d+)?)\s*km\b'
        inline_km_match = re.search(inline_km_pattern, race_text, re.IGNORECASE)
        if inline_km_match:
            distance_km = float(inline_km_match.group(1).replace(',', '.'))
            description = re.sub(
                inline_km_pattern,
                '',
                race_text,
                count=1,
                flags=re.IGNORECASE,
            ).strip(' -,:')
            return distance_km, description or race_text
        
        # If no km found, try to infer from common patterns
        if 'marathon' in race_text.lower():
            if 'hálf' in race_text.lower() or 'half' in race_text.lower():
                return 21.0975, race_text
            else:
                return 42.195, race_text
        
        # For "tindar" (mountain peaks), make reasonable estimates
        if 'tindar' in race_text.lower() or 'tindur' in race_text.lower():
            # Extract number of peaks
            peak_match = re.search(r'(\d+)\s*tind', race_text.lower())
            if peak_match:
                peaks = int(peak_match.group(1))
                # Rough estimate: each peak adds ~5km
                estimated_distance = peaks * 5.0
                return estimated_distance, race_text
        
        # Fallback: try to find any number that might be distance
        numbers = [
            float(match.replace(',', '.'))
            for match in re.findall(r'(\d+(?:[.,]\d+)?)', race_text)
        ]
        plausible_numbers = [number for number in numbers if number <= 200]
        if plausible_numbers:
            return max(plausible_numbers), race_text
        
        return 10.0, race_text  # Default fallback
    
    def _extract_date_time(self, container) -> Dict[str, str]:
        """Extract date and time information from container"""
        # Look for date/time in stats-label class
        stats_label = container.find('small', class_='stats-label')
        if not stats_label:
            return {'date': '2025-01-01', 'time': '09:00'}
        
        date_text = stats_label.get_text().strip()
        
        try:
            # Parse date format like "30.08.2025 09:00"
            if re.match(r'\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}', date_text):
                date_part, time_part = date_text.split(' ', 1)
                day, month, year = date_part.split('.')
                
                # Convert to ISO format
                date_iso = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                return {'date': date_iso, 'time': time_part}
            
            # Try to parse with dateutil as fallback
            parsed_date = parse_date(date_text, dayfirst=True)
            return {
                'date': parsed_date.strftime('%Y-%m-%d'),
                'time': parsed_date.strftime('%H:%M')
            }
            
        except Exception as e:
            logger.warning(f"Could not parse date '{date_text}': {str(e)}")
            return {'date': '2025-01-01', 'time': '09:00'}
    
    def _determine_race_type(self, description: str, distance_km: float) -> str:
        """Determine race type based on description and distance"""
        description_lower = description.lower()
        
        # Check description first
        for pattern, race_type in self.race_type_mapping.items():
            if pattern in description_lower:
                return race_type
        
        # Determine by distance
        if distance_km > 43.5:
            return 'ultra'
        if 41.0 <= distance_km <= 43.5:
            return 'marathon'
        elif 20.0 <= distance_km <= 22.5:
            return 'half_marathon'
        elif 9.0 <= distance_km <= 11.0:
            return '10k'
        elif 4.0 <= distance_km <= 6.0:
            return '5k'
        else:
            return 'other'

    def _extract_results_url(self, container) -> str:
        """Extract the overall results URL from a race category container"""
        # Look for links with 'cat=overall' parameter
        overall_links = container.find_all('a', href=True)
        
        for link in overall_links:
            href = link.get('href', '')
            if 'cat=overall' in href:
                return href
        
        # If no overall link found, return empty string
        return ''

    def scrape_race_results_from_url(self, results_url: str, race_id: int, race_obj=None, force_refresh: bool = False) -> Dict:
        """
        Scrape race results from a Timataka.net results URL with caching support.
        
        Args:
            results_url: URL to the race results page
            race_id: ID of the race in the database
            race_obj: Optional Race model instance for HTML caching
            force_refresh: If True, bypass cache and fetch from web
            
        Returns:
            Dictionary containing race results data
        """
        try:
            # Fetch HTML with caching
            html_content = self._fetch_html_with_cache(results_url, race_obj, force_refresh)
            
            # Process the HTML content
            race_date = race_obj.date if race_obj else None
            return self.scrape_race_results(html_content, race_id, race_date=race_date)
            
        except Exception as e:
            logger.error(f"Error scraping race results from URL {results_url}: {str(e)}")
            raise TimatakaScrapingError(f"Failed to scrape race results: {str(e)}")

    def scrape_race_results(self, html_content: str, race_id: int, race_date: Optional[datetime] = None) -> Dict:
        """
        Scrape race results from a Timataka.net results page.
        
        Args:
            html_content: Raw HTML content from a Timataka results page
            race_id: ID of the race in the database
            
        Returns:
            Dictionary with results data and metadata
            
        Raises:
            TimatakaScrapingError: If scraping fails or data is invalid
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract race name from the page
            race_name = self._extract_race_name_from_results(soup)
            
            # Find the results table
            results_table = self._find_results_table(soup)
            if not results_table:
                raise TimatakaScrapingError("No results table found in the HTML")
            
            # Extract column headers to understand the table structure
            headers = self._extract_table_headers(results_table)
            
            # Extract all result rows
            results = self._extract_result_rows(results_table, headers, race_date=race_date)
            
            return {
                'race_id': race_id,
                'race_name': race_name,
                'results_count': len(results),
                'headers': headers,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error scraping race results: {str(e)}")
            raise TimatakaScrapingError(f"Failed to scrape race results: {str(e)}")
    
    def _extract_race_name_from_results(self, soup: BeautifulSoup) -> str:
        """Extract race name from results page"""
        # Try h2 inside ibox-title first
        h2_tag = soup.find('div', class_='ibox-title')
        if h2_tag:
            h2 = h2_tag.find('h2')
            if h2:
                return h2.get_text().strip()
        
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text().strip()
            if 'TÍMATAKA:' in title_text:
                return title_text.split('TÍMATAKA:')[-1].strip()
            return title_text
        
        return "Unknown Race"
    
    def _find_results_table(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Find the main results table in the page"""
        # Look for table with class 'table table-striped' (common format)
        table = soup.find('table', class_='table table-striped')
        if table:
            return table
        
        # Look for table with class 'table table-condensed table-hover' (alternative format)
        table = soup.find('table', class_='table table-condensed table-hover')
        if table:
            return table
        
        # Look for any table with 'table' class as fallback
        table = soup.find('table', class_='table')
        if table:
            return table
        
        # Last resort: any table
        table = soup.find('table')
        return table
    
    def _extract_table_headers(self, table: BeautifulSoup) -> List[str]:
        """Extract and normalize table headers"""
        headers = []
        thead = table.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                for th in header_row.find_all('th'):
                    header_text = th.get_text().strip().lower()
                    # Map common headers to standardized names
                    if header_text in ['rank', 'place', '#']:
                        headers.append('rank')
                    elif header_text in ['bib', 'number']:
                        headers.append('bib')
                    elif header_text in ['name', 'participant']:
                        headers.append('name')
                    elif header_text in ['year', 'birth year', 'age']:
                        headers.append('year')
                    elif header_text in ['club', 'team']:
                        headers.append('club')
                    elif header_text in ['split', 'splits']:
                        headers.append('split')
                    elif header_text in ['time', 'finish time', 'final']:
                        headers.append('time')
                    elif header_text in ['behind', 'time behind']:
                        headers.append('behind')
                    elif header_text in ['chiptime', 'chip time']:
                        headers.append('chiptime')
                    elif header_text in ['pace']:
                        headers.append('pace')
                    else:
                        headers.append(header_text if header_text else 'unknown')
        return headers
    
    def _extract_result_rows(self, table: BeautifulSoup, headers: List[str], race_date: Optional[datetime] = None) -> List[Dict]:
        """Extract all result rows from the table"""
        results = []
        tbody = table.find('tbody')
        if not tbody:
            return results
        
        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < len(headers):
                continue  # Skip incomplete rows
            
            result_data = {}
            
            for i, header in enumerate(headers):
                if i < len(cells):
                    cell_text = cells[i].get_text().strip()
                    
                    if header == 'rank':
                        result_data['rank'] = self._parse_rank(cell_text)
                    elif header == 'bib':
                        result_data['bib'] = cell_text
                    elif header == 'name':
                        result_data['name'] = cell_text
                    elif header == 'year':
                        result_data['year'] = self._parse_year_or_age(cell_text, race_date=race_date)
                    elif header == 'club':
                        result_data['club'] = cell_text
                    elif header == 'pace':
                        result_data['pace'] = cell_text
                    elif header == 'split':
                        result_data['splits'] = self._parse_splits(cells[i])
                    elif header == 'time':
                        result_data['finish_time'] = self._parse_time(cell_text)
                    elif header == 'behind':
                        result_data['time_behind'] = self._parse_time_behind(cell_text)
                    elif header == 'chiptime':
                        result_data['chip_time'] = self._parse_time(cell_text)
                    else:
                        result_data[header] = cell_text
            
            if result_data.get('name') and result_data.get('finish_time'):
                results.append(result_data)
        
        return results
    
    def _parse_rank(self, text: str) -> Optional[int]:
        """Parse rank/place number"""
        if not text or text == '':
            return None
        try:
            return int(text.strip())
        except ValueError:
            return None
    
    def _parse_year_or_age(self, text: str, race_date: Optional[datetime] = None) -> Optional[int]:
        """Parse birth year or age, converting age to birth year if needed"""
        if not text or text == '':
            return None
        try:
            value = int(text.strip())
            if 1900 <= value <= 2020:
                # This looks like a birth year
                return value
            elif 10 <= value <= 100:
                # This looks like an age, convert to birth year
                reference_year = race_date.year if race_date else datetime.now().year
                return reference_year - value
        except ValueError:
            pass
        return None
    
    def _parse_year(self, text: str) -> Optional[int]:
        """Parse birth year"""
        if not text or text == '':
            return None
        try:
            year = int(text.strip())
            if 1900 <= year <= 2020:
                return year
        except ValueError:
            pass
        return None
    
    def _parse_time(self, text: str) -> Optional[timedelta]:
        """Parse time string to timedelta"""
        if not text or text.strip() == '':
            return None
        
        # Clean the text
        time_str = text.strip()
        
        # Handle format like "03:11:35" (hours:minutes:seconds)
        time_pattern = r'(\d{1,2}):(\d{2}):(\d{2})'
        match = re.search(time_pattern, time_str)
        
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            return timedelta(hours=hours, minutes=minutes, seconds=seconds)
        
        return None
    
    def _parse_time_behind(self, text: str) -> Optional[timedelta]:
        """Parse time behind (like '+45:47' or '+01:02:51')"""
        if not text or text.strip() == '' or text.strip() == '+':
            return None
        
        # Remove the '+' sign and parse
        time_str = text.strip().lstrip('+')
        
        # Handle format like "45:47" (minutes:seconds) or "01:02:51" (hours:minutes:seconds)
        if time_str.count(':') == 1:
            # Format: MM:SS
            parts = time_str.split(':')
            if len(parts) == 2:
                try:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    return timedelta(minutes=minutes, seconds=seconds)
                except ValueError:
                    pass
        elif time_str.count(':') == 2:
            # Format: HH:MM:SS
            return self._parse_time(time_str)
        
        return None
    
    def _parse_splits(self, cell_element) -> List[Dict[str, str]]:
        """Parse split times from HTML cell element into structured data"""
        splits = []
        
        # Get the HTML content of the cell
        cell_html = str(cell_element)
        
        if not cell_html or cell_html.strip() == '':
            return splits
        
        # Split by <br> tags to get individual split lines
        split_lines = []
        
        # Handle different br tag formats
        split_patterns = [r'<br\s*/?>', r'<br>', r'</br>']
        split_text = cell_html
        
        for pattern in split_patterns:
            split_text = re.sub(pattern, '\n', split_text, flags=re.IGNORECASE)
        
        # Remove HTML tags and get lines
        clean_text = BeautifulSoup(split_text, 'html.parser').get_text()
        lines = clean_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Parse format like "00:58:05 (Hafravatn)"
            pattern = r'(\d{1,2}:\d{2}:\d{2})\s*\(([^)]+)\)'
            match = re.search(pattern, line)
            
            if match:
                time_str = match.group(1)
                location = match.group(2).strip()
                
                time_delta = self._parse_time(time_str)
                if time_delta:
                    splits.append({
                        'time': time_delta,
                        'location': location
                    })
        
        return splits

    def _handle_direct_results_url(self, results_url: str, race_obj=None, force_refresh: bool = False) -> List[Dict]:
        """
        Handle URLs that are already results URLs (contain /urslit/ and race parameters).
        These should be treated as single races with enhanced URLs.
        
        Args:
            results_url: URL that's already a results URL like /urslit/?race=1
            race_obj: Optional Race model instance for HTML caching
            force_refresh: If True, bypass cache and fetch from web
            
        Returns:
            List with a single race dictionary
        """
        try:
            # Ensure the URL has cat=overall parameter
            enhanced_url = self._ensure_overall_category(results_url)
            
            # Extract race information from the URL and page content
            html_content = self._fetch_html_with_cache(results_url, race_obj, force_refresh)
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract race name from page title or content
            race_name = self._extract_main_race_name(soup)
            if not race_name:
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text().strip()
                    race_name = title_text.replace('TÍMATAKA: ', '').strip()
                else:
                    race_name = "Unknown Race"
            
            # Extract other information
            location = self._extract_location_from_name(race_name)
            race_date = self._extract_race_date_from_page(soup)
            distance = self._extract_distance_from_name(race_name)
            race_type = self._determine_race_type_from_distance(distance) if distance > 0 else self._determine_race_type_from_name(race_name)
            
            race_info = {
                'name': race_name,
                'race_type': race_type,
                'date': race_date,
                'location': location,
                'distance_km': distance,
                'elevation_gain_m': 0,
                'organizer': 'Tímataka',
                'currency': 'ISK',
                'description': f"Race with results at: {results_url}",
                'source_url': results_url,
                'results_url': enhanced_url  # Use the enhanced URL with cat=overall
            }
            
            return [race_info]
            
        except Exception as e:
            logger.error(f"Error handling direct results URL {results_url}: {str(e)}")
            # Fallback: create a basic race entry
            return [{
                'name': "Unknown Race",
                'race_type': 'other',
                'date': None,
                'location': 'Iceland',
                'distance_km': 0.0,
                'elevation_gain_m': 0,
                'organizer': 'Tímataka',
                'currency': 'ISK',
                'description': f"Race with results at: {results_url}",
                'source_url': results_url,
                'results_url': self._ensure_overall_category(results_url)
            }]

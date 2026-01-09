import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from races.scraper import TimatakaScraper, TimatakaScrapingError
from races.services import ScrapingService
from races.models import Race
import json


class Command(BaseCommand):
    help = 'Scrape race data or results from a Timataka.net HTML file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', 
            type=str, 
            help='Path to HTML file to scrape (relative to project root)',
            default='sample_data/tindahlaup-2025.html'
        )
        parser.add_argument(
            '--save', 
            action='store_true',
            help='Save scraped data to database'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output scraped data to JSON file',
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['races', 'results'],
            default='races',
            help='Type of content to scrape: races or results'
        )
        parser.add_argument(
            '--race-id',
            type=int,
            help='Race ID for results scraping (required when type=results)'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing data'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        scrape_type = options['type']
        
        # Make path absolute if relative
        if not os.path.isabs(file_path):
            file_path = os.path.join(settings.BASE_DIR, file_path)
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise CommandError(f'HTML file "{file_path}" does not exist.')
        
        # Read HTML content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        except Exception as e:
            raise CommandError(f'Error reading file: {str(e)}')
        
        # Initialize service
        service = ScrapingService()
        
        if scrape_type == 'races':
            self._handle_races_scraping(service, html_content, file_path, options)
        elif scrape_type == 'results':
            self._handle_results_scraping(service, html_content, options)
    
    def _handle_races_scraping(self, service: ScrapingService, html_content: str, 
                              file_path: str, options: dict):
        """Handle scraping of race data"""
        try:
            self.stdout.write(f'Scraping race data from: {file_path}')
            source_url = f"file://{file_path}"
            
            if options['save']:
                # Scrape and save to database
                result = service.scrape_and_save_races(
                    html_content, 
                    source_url, 
                    overwrite=options['overwrite']
                )
                
                self.stdout.write(self.style.SUCCESS(
                    f'Scraping completed: {result["scraped"]} scraped, '
                    f'{result["saved"]} saved, {result["skipped"]} skipped, '
                    f'{result["updated"]} updated, {result["errors"]} errors'
                ))
            else:
                # Just scrape without saving
                races_data = service.scrape_races_only(html_content, source_url)
                self.stdout.write(self.style.SUCCESS(f'Successfully scraped {len(races_data)} race(s)'))
                
                # Display scraped data
                for i, race_data in enumerate(races_data, 1):
                    self.stdout.write(f'\n--- Race {i} ---')
                    self.stdout.write(f'Name: {race_data["name"]}')
                    self.stdout.write(f'Date: {race_data["date"]}')
                    self.stdout.write(f'Distance: {race_data["distance_km"]} km')
                    self.stdout.write(f'Type: {race_data["race_type"]}')
                    self.stdout.write(f'Location: {race_data["location"]}')
                    if race_data.get('start_time'):
                        self.stdout.write(f'Start Time: {race_data["start_time"]}')
                
                # Output to JSON file if requested
                if options['output']:
                    self._save_to_json(races_data, options['output'])
        
        except TimatakaScrapingError as e:
            raise CommandError(f'Scraping failed: {str(e)}')
        except Exception as e:
            raise CommandError(f'Unexpected error: {str(e)}')
    
    def _handle_results_scraping(self, service: ScrapingService, html_content: str, options: dict):
        """Handle scraping of race results"""
        race_id = options.get('race_id')
        if not race_id:
            raise CommandError('--race-id is required when scraping results')
        
        try:
            # Check if race exists
            try:
                race = Race.objects.get(id=race_id)
                self.stdout.write(f'Scraping results for race: {race.name}')
            except Race.DoesNotExist:
                raise CommandError(f'Race with ID {race_id} not found')
            
            if options['save']:
                # Scrape and save to database
                result = service.scrape_and_save_race_results(
                    html_content, 
                    race_id, 
                    overwrite=options['overwrite']
                )
                
                self.stdout.write(self.style.SUCCESS(
                    f'Results scraping completed: {result["scraped"]} scraped, '
                    f'{result["saved"]} saved, {result["skipped"]} skipped, '
                    f'{result["errors"]} errors'
                ))
            else:
                # Just scrape without saving
                scraper = TimatakaScraper()
                results_data = scraper.scrape_race_results(html_content, race_id)
                
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully scraped {results_data["results_count"]} result(s)'
                ))
                
                # Display sample results
                self.stdout.write(f'\nRace: {results_data["race_name"]}')
                self.stdout.write(f'Headers: {", ".join(results_data["headers"])}')
                
                # Show first 5 results
                for i, result in enumerate(results_data["results"][:5], 1):
                    self.stdout.write(f'\n--- Result {i} ---')
                    self.stdout.write(f'Name: {result.get("name")}')
                    self.stdout.write(f'Rank: {result.get("rank")}')
                    self.stdout.write(f'Time: {result.get("finish_time")}')
                    self.stdout.write(f'Club: {result.get("club")}')
                    if result.get("year"):
                        self.stdout.write(f'Year: {result.get("year")}')
                    if result.get("splits"):
                        self.stdout.write(f'Splits: {len(result.get("splits"))} checkpoints')
                
                if len(results_data["results"]) > 5:
                    self.stdout.write(f'\n... and {len(results_data["results"]) - 5} more results')
                
                # Output to JSON file if requested
                if options['output']:
                    self._save_to_json(results_data, options['output'])
        
        except TimatakaScrapingError as e:
            raise CommandError(f'Results scraping failed: {str(e)}')
        except Exception as e:
            raise CommandError(f'Unexpected error: {str(e)}')
    
    def _save_to_json(self, data, filename: str):
        """Save data to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self.stdout.write(self.style.SUCCESS(f'Data saved to: {filename}'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error saving to JSON: {str(e)}'))

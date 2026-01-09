# Timataka Scraper Documentation

## Overview

The Timataka scraper is designed to extract race information from Timataka.net HTML pages. It can parse race events with multiple distances and categories, extracting detailed information about each race.

## Features

- **HTML Content Processing**: Accepts raw HTML content from Timataka.net pages
- **Multiple Race Detection**: Automatically detects multiple race distances/categories on a single page
- **Data Extraction**: Extracts comprehensive race information including:
  - Race names and descriptions
  - Dates and start times
  - Distances (automatically parsed from various formats)
  - Race types (marathon, half marathon, trail runs, etc.)
  - Locations (with Icelandic place name recognition)
- **Database Integration**: Option to save scraped races directly to database
- **API Integration**: RESTful endpoints for scraping operations

## Supported Race Types

The scraper can automatically detect and classify these race types:

- `marathon` - Full marathon races (42.195km)
- `half_marathon` - Half marathon races (~21km)
- `10k` - 10 kilometer races
- `5k` - 5 kilometer races
- `trail` - Trail/mountain runs (including Icelandic "tindar" races)
- `other` - Other distances

## Usage

### Command Line Interface

```bash
# Basic scraping (display only)
python manage.py timataka_scrape_file --file sample_data/tindahlaup-2025.html

# Save to database
python manage.py timataka_scrape_file --file sample_data/tindahlaup-2025.html --save

# Export to JSON
python manage.py timataka_scrape_file --file sample_data/tindahlaup-2025.html --output races.json
```

### API Endpoints

#### POST /api/races/scrape
Scrape race data from HTML content.

**Request Body:**
```json
{
  "html_content": "<html>...</html>",
  "source_url": "https://timataka.net/example",
  "save_to_db": true,
  "overwrite_existing": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scraped 4 races, saved 4, skipped 0, errors 0",
  "scraped": 4,
  "saved": 4,
  "skipped": 0,
  "errors": 0,
  "races": [...]
}
```

#### GET /api/races/scrape/supported-types
Get list of supported race types.

### Python Code

```python
from races.scraper import TimatakaScraper
from races.services import ScrapingService

# Direct scraper usage
scraper = TimatakaScraper()
races = scraper.scrape_race_data(html_content, source_url)

# Service usage with database integration
service = ScrapingService()
result = service.scrape_and_save_races(html_content, source_url)
```

## Data Fields Extracted

For each race, the scraper extracts:

- **name**: Complete race name with distance category
- **description**: Descriptive text about the race
- **race_type**: Classified race type (see supported types above)
- **date**: Race date in ISO format (YYYY-MM-DD)
- **location**: Race location (Icelandic place names recognized)
- **distance_km**: Distance in kilometers (float)
- **organizer**: Set to "Tímataka" for scraped races
- **source_url**: Original URL for reference
- **start_time**: Race start time (not saved to database)

## HTML Structure Requirements

The scraper expects Timataka.net HTML with these elements:

- **Title/Header**: `<title>` or `<h2>` containing race name
- **Race Categories**: `<div class="col-md-3">` containers with race information
- **Distance Info**: `<h4>` tags with distance patterns like "7 tindar (37 km)"
- **Date/Time**: `<small class="stats-label">` with date format "DD.MM.YYYY HH:MM"

## Example Output

From the sample Tindahlaup file, the scraper extracts:

```json
[
  {
    "name": "Tindahlaup Mosfellsbæjar 2025 - 7 tindar",
    "description": "7 tindar as part of Tindahlaup Mosfellsbæjar 2025",
    "race_type": "trail",
    "date": "2025-08-30",
    "location": "Mosfellsbær",
    "distance_km": 37.0,
    "organizer": "Tímataka"
  }
]
```

## Error Handling

The scraper includes comprehensive error handling:

- **TimatakaScrapingError**: Specific errors for scraping issues
- **Validation**: HTML content validation before processing
- **Graceful Fallbacks**: Default values when data cannot be parsed
- **Detailed Logging**: Error and warning messages for debugging

## Future Enhancements

Planned improvements include:

- **Live URL Fetching**: Direct scraping from URLs
- **Result Data Scraping**: Extract race results and participant data
- **Scheduling**: Automated periodic scraping
- **Multiple Site Support**: Support for other Icelandic race timing sites
- **Enhanced Location Detection**: More comprehensive Icelandic place names

#!/usr/bin/env python3
"""
Test script to verify that the scraper correctly extracts results URLs
"""

import os
import sys
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hlaupatimar.settings')

import django
django.setup()

from races.scraper import TimatakaScraper

def test_results_url_extraction():
    """Test that the scraper correctly extracts results URLs from the sample HTML"""
    
    # Read the sample HTML file
    sample_file_path = project_dir / 'sample_data' / 'tindahlaup-2025.html'
    
    if not sample_file_path.exists():
        print(f"Error: Sample file not found at {sample_file_path}")
        return False
    
    with open(sample_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Initialize scraper
    scraper = TimatakaScraper()
    
    try:
        # Scrape the race data
        source_url = "https://timataka.net/tindahlaup2025/"
        races_data = scraper.scrape_race_data(html_content, source_url)
        
        print(f"Successfully scraped {len(races_data)} races")
        print("\nRace data with results URLs:")
        print("=" * 60)
        
        for i, race in enumerate(races_data, 1):
            print(f"\nRace {i}:")
            print(f"  Name: {race['name']}")
            print(f"  Distance: {race['distance_km']} km")
            print(f"  Results URL: {race.get('results_url', 'NOT FOUND')}")
            
            # Verify the results URL contains the expected pattern
            results_url = race.get('results_url', '')
            if results_url and 'cat=overall' in results_url:
                print(f"  ✅ Results URL looks correct")
            elif results_url:
                print(f"  ⚠️  Results URL found but doesn't contain 'cat=overall'")
            else:
                print(f"  ❌ No results URL found")
        
        # Summary
        races_with_results = sum(1 for race in races_data if race.get('results_url'))
        print(f"\n" + "=" * 60)
        print(f"Summary: {races_with_results}/{len(races_data)} races have results URLs")
        
        return races_with_results > 0
        
    except Exception as e:
        print(f"Error scraping data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing results URL extraction from Timataka scraper...")
    success = test_results_url_extraction()
    
    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed!")
        sys.exit(1)

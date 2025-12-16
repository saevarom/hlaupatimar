#!/usr/bin/env python3
"""
Test script to verify that races with results URLs can be saved to the database
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

from races.services import ScrapingService
from races.models import Race

def test_save_races_with_results_url():
    """Test that races with results URLs can be saved to the database"""
    
    # Read the sample HTML file
    sample_file_path = project_dir / 'sample_data' / 'tindahlaup-2025.html'
    
    if not sample_file_path.exists():
        print(f"Error: Sample file not found at {sample_file_path}")
        return False
    
    with open(sample_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Initialize scraping service
    service = ScrapingService()
    
    try:
        print("Saving races to database...")
        source_url = "https://timataka.net/tindahlaup2025/"
        
        # Save races to database
        result = service.scrape_and_save_races(html_content, source_url, overwrite=True)
        
        print(f"Scraping result: {result}")
        
        # Verify races were saved with results URLs
        saved_races = Race.objects.filter(source_url=source_url)
        print(f"\nFound {saved_races.count()} races in database:")
        
        for race in saved_races:
            print(f"\nRace: {race.name}")
            print(f"  Date: {race.date}")
            print(f"  Distance: {race.distance_km} km")
            print(f"  Source URL: {race.source_url}")
            print(f"  Results URL: {race.results_url}")
            
            if race.results_url and 'cat=overall' in race.results_url:
                print(f"  ✅ Results URL saved correctly")
            elif race.results_url:
                print(f"  ⚠️  Results URL saved but doesn't contain 'cat=overall'")
            else:
                print(f"  ❌ No results URL saved")
        
        # Summary
        races_with_results = saved_races.filter(results_url__isnull=False).exclude(results_url='').count()
        print(f"\n" + "=" * 60)
        print(f"Summary: {races_with_results}/{saved_races.count()} races have results URLs in database")
        
        return races_with_results > 0
        
    except Exception as e:
        print(f"Error saving races: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing saving races with results URLs to database...")
    success = test_save_races_with_results_url()
    
    if success:
        print("\n✅ Database test completed successfully!")
    else:
        print("\n❌ Database test failed!")
        sys.exit(1)

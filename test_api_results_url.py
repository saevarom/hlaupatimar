#!/usr/bin/env python3
"""
Test script to verify that the API returns the results_url field
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

import json
from django.test import Client
from races.models import Race

def test_api_results_url():
    """Test that the API returns the results_url field"""
    
    # Create a Django test client
    client = Client()
    
    try:
        # Check if we have any races in the database
        races = Race.objects.all()
        
        if not races.exists():
            print("No races found in database. Please run the scraper first.")
            return False
        
        print(f"Found {races.count()} races in database")
        
        # Test the races list API endpoint
        response = client.get('/api/races/')
        
        if response.status_code != 200:
            print(f"API request failed with status code: {response.status_code}")
            print(f"Response content: {response.content}")
            return False
        
        # Parse the JSON response
        data = response.json()
        
        print(f"\nAPI returned {len(data)} races")
        
        # Check each race for results_url field
        for i, race in enumerate(data, 1):
            print(f"\nRace {i}:")
            print(f"  ID: {race.get('id')}")
            print(f"  Name: {race.get('name')}")
            print(f"  Results URL: {race.get('results_url', 'NOT FOUND')}")
            
            if 'results_url' in race:
                if race['results_url'] and 'cat=overall' in race['results_url']:
                    print(f"  ✅ Results URL field present and correct")
                elif race['results_url']:
                    print(f"  ⚠️  Results URL field present but may be incorrect")
                else:
                    print(f"  ⚠️  Results URL field present but empty")
            else:
                print(f"  ❌ Results URL field missing from API response")
        
        # Summary
        races_with_results_field = sum(1 for race in data if 'results_url' in race)
        races_with_results_data = sum(1 for race in data if race.get('results_url'))
        
        print(f"\n" + "=" * 60)
        print(f"Summary:")
        print(f"  - {races_with_results_field}/{len(data)} races have results_url field in API")
        print(f"  - {races_with_results_data}/{len(data)} races have non-empty results_url")
        
        return races_with_results_field == len(data)
        
    except Exception as e:
        print(f"Error testing API: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing API returns results_url field...")
    success = test_api_results_url()
    
    if success:
        print("\n✅ API test completed successfully!")
    else:
        print("\n❌ API test failed!")
        sys.exit(1)

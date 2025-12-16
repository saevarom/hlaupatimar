#!/usr/bin/env python3
"""
Test script for the Timataka scraping API
"""
import json
import requests
import sys
from pathlib import Path

def test_scraping_api():
    """Test the scraping API with the sample HTML file"""
    
    # Read the sample HTML file
    html_file = Path("sample_data/tindahlaup-2025.html")
    if not html_file.exists():
        print(f"Error: {html_file} not found")
        return False
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Prepare the API request
    api_url = "http://localhost:8002/api/races/scrape"
    payload = {
        "html_content": html_content,
        "source_url": "https://timataka.net/tindahlaup2025/",
        "save_to_db": True,
        "overwrite_existing": False
    }
    
    print("Testing scraping API...")
    print(f"API URL: {api_url}")
    print(f"HTML content length: {len(html_content)} characters")
    print(f"Save to DB: {payload['save_to_db']}")
    print("-" * 50)
    
    try:
        # Make the API request
        response = requests.post(api_url, json=payload, timeout=30)
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Scraping successful!")
            print(f"Message: {result.get('message', 'N/A')}")
            print(f"Scraped: {result.get('scraped', 0)} races")
            print(f"Saved: {result.get('saved', 0)} races")
            print(f"Skipped: {result.get('skipped', 0)} races")
            print(f"Errors: {result.get('errors', 0)} races")
            
            if result.get('races'):
                print("\nScraped races:")
                for i, race in enumerate(result['races'], 1):
                    print(f"  {i}. {race.get('name', 'N/A')}")
                    print(f"     Type: {race.get('race_type', 'N/A')}")
                    print(f"     Date: {race.get('date', 'N/A')}")
                    print(f"     Distance: {race.get('distance_km', 'N/A')} km")
                    print(f"     Location: {race.get('location', 'N/A')}")
                    print()
            
            return True
        else:
            print(f"❌ API error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Error response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error: Is the API server running on localhost:8002?")
        return False
    except requests.exceptions.Timeout:
        print("❌ Request timeout: API took too long to respond")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_races_list_api():
    """Test the races list API to see if scraped data is available"""
    
    api_url = "http://localhost:8002/api/races/"
    
    print("\nTesting races list API...")
    print(f"API URL: {api_url}")
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            races = response.json()
            print(f"✅ Found {len(races)} races in database")
            
            if races:
                print("\nRaces in database:")
                for i, race in enumerate(races, 1):
                    print(f"  {i}. {race.get('name', 'N/A')} ({race.get('date', 'N/A')})")
            
            return True
        else:
            print(f"❌ API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error accessing races API: {e}")
        return False

if __name__ == "__main__":
    print("hlaupatimar API Test Suite")
    print("=" * 50)
    
    # Test scraping API
    scraping_success = test_scraping_api()
    
    # Test races list API
    list_success = test_races_list_api()
    
    print("\n" + "=" * 50)
    if scraping_success and list_success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)

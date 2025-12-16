#!/usr/bin/env python3
"""
Demo script showing the Runner API functionality.
This script demonstrates the new API endpoints for searching and viewing runner details.
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hlaupatimar.settings')
django.setup()

from races.api import search_runners, get_runner_detail
from django.http import HttpRequest
import json


def demo_runner_search():
    """Demonstrate the runner search API"""
    print("="*60)
    print("RUNNER SEARCH API DEMO")
    print("="*60)
    
    request = HttpRequest()
    
    # Test 1: Search for runners named Pétur
    print("\n1. Search for runners named 'Pétur' (limit 5):")
    try:
        results = search_runners(request, q='Pétur', limit=5)
        print(f"   Found {len(results)} runners:")
        for runner in results:
            print(f"   - ID {runner.id}: {runner.name} ({runner.birth_year}) - {runner.total_races} races")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: Search for runners by gender
    print("\n2. Search for female runners named 'Anna' (limit 3):")
    try:
        results = search_runners(request, q='Anna', gender='F', limit=3)
        print(f"   Found {len(results)} runners:")
        for runner in results:
            print(f"   - ID {runner.id}: {runner.name} ({runner.birth_year}) - {runner.total_races} races")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Search by birth year
    print("\n3. Search for runners born in 1980 (limit 5):")
    try:
        results = search_runners(request, birth_year=1980, limit=5)
        print(f"   Found {len(results)} runners:")
        for runner in results:
            print(f"   - ID {runner.id}: {runner.name} ({runner.birth_year}) - {runner.total_races} races")
    except Exception as e:
        print(f"   Error: {e}")


def demo_runner_detail():
    """Demonstrate the runner detail API"""
    print("\n" + "="*60)
    print("RUNNER DETAIL API DEMO")
    print("="*60)
    
    request = HttpRequest()
    
    # Get a sample runner first
    search_results = search_runners(request, q='Pétur', limit=1)
    if not search_results:
        print("No runners found for demo")
        return
    
    runner_id = search_results[0].id
    
    print(f"\nFetching detailed information for runner ID {runner_id}:")
    
    try:
        result = get_runner_detail(request, runner_id)
        
        print(f"\n📊 RUNNER PROFILE")
        print(f"   Name: {result.name}")
        print(f"   ID: {result.id}")
        print(f"   Birth Year: {result.birth_year}")
        print(f"   Gender: {result.gender}")
        print(f"   Nationality: {result.nationality}")
        print(f"   Total Races: {result.total_races}")
        
        print(f"\n🏃 RACE HISTORY ({len(result.race_history)} races):")
        
        for i, race in enumerate(result.race_history[:3], 1):  # Show first 3 races
            print(f"\n   {i}. {race.race_date} - {race.race_name}")
            print(f"      Event: {race.event_name}")
            print(f"      Distance: {race.distance_km}km")
            print(f"      Location: {race.location}")
            print(f"      Finish Time: {race.finish_time}")
            print(f"      Status: {race.status}")
            
            if race.bib_number:
                print(f"      Bib: {race.bib_number}")
            if race.club:
                print(f"      Club: {race.club}")
            
            if race.splits:
                print(f"      Splits ({len(race.splits)}):")
                for split in race.splits:
                    distance_str = f" ({split.distance_km}km)" if split.distance_km else ""
                    print(f"        - {split.name}{distance_str}: {split.time}")
        
        if len(result.race_history) > 3:
            print(f"\n   ... and {len(result.race_history) - 3} more races")
            
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()


def demo_api_json_output():
    """Demonstrate JSON serialization of API responses"""
    print("\n" + "="*60)
    print("JSON API OUTPUT DEMO")
    print("="*60)
    
    request = HttpRequest()
    
    # Get search results and convert to JSON-serializable format
    print("\nSearch results as JSON:")
    search_results = search_runners(request, q='Pétur', limit=2)
    
    # Convert to dict for JSON serialization
    search_json = []
    for runner in search_results:
        search_json.append({
            'id': runner.id,
            'name': runner.name,
            'birth_year': runner.birth_year,
            'gender': runner.gender,
            'nationality': runner.nationality,
            'total_races': runner.total_races
        })
    
    print(json.dumps(search_json, indent=2, default=str))
    
    if search_results:
        print(f"\nRunner detail as JSON (ID {search_results[0].id}):")
        detail = get_runner_detail(request, search_results[0].id)
        
        # Convert to dict for JSON serialization
        detail_json = {
            'id': detail.id,
            'name': detail.name,
            'birth_year': detail.birth_year,
            'gender': detail.gender,
            'nationality': detail.nationality,
            'total_races': detail.total_races,
            'race_history': [
                {
                    'event_name': race.event_name,
                    'race_name': race.race_name,
                    'race_date': race.race_date,
                    'distance_km': race.distance_km,
                    'location': race.location,
                    'finish_time': race.finish_time,
                    'status': race.status,
                    'bib_number': race.bib_number,
                    'club': race.club,
                    'splits': [
                        {
                            'name': split.name,
                            'distance_km': split.distance_km,
                            'time': split.time
                        }
                        for split in race.splits
                    ]
                }
                for race in detail.race_history[:1]  # Just first race for brevity
            ]
        }
        
        print(json.dumps(detail_json, indent=2, default=str))


def show_api_endpoints():
    """Show available API endpoints"""
    print("\n" + "="*60)
    print("AVAILABLE API ENDPOINTS")
    print("="*60)
    
    print("\n🔍 SEARCH RUNNERS:")
    print("   GET /api/races/runners")
    print("   Parameters:")
    print("     - q: Search term for runner name (optional)")
    print("     - birth_year: Filter by birth year (optional)")
    print("     - gender: Filter by gender M/F (optional)")
    print("     - limit: Max results (default: 20, max: 100)")
    print("     - offset: Pagination offset (default: 0)")
    print("\n   Example: GET /api/races/runners?q=Pétur&limit=5")
    
    print("\n👤 RUNNER DETAIL:")
    print("   GET /api/races/runners/{runner_id}")
    print("   Returns complete runner information including race history")
    print("\n   Example: GET /api/races/runners/52199")
    
    print("\n📚 API DOCUMENTATION:")
    print("   Available at: http://localhost:8000/api/docs")


if __name__ == "__main__":
    show_api_endpoints()
    demo_runner_search()
    demo_runner_detail() 
    demo_api_json_output()
    
    print("\n" + "="*60)
    print("✅ API DEMO COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("\nTo test the HTTP endpoints:")
    print("1. Visit http://localhost:8000/api/docs for interactive API docs")
    print("2. Use curl: curl 'http://localhost:8000/api/races/runners?q=Pétur&limit=3'")
    print("3. Use curl: curl 'http://localhost:8000/api/races/runners/52199'")

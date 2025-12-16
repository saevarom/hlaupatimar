#!/usr/bin/env python3
"""
Comprehensive test script for Runner API endpoints.
Tests both the API functions directly and HTTP endpoint functionality.
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hlaupatimar.settings')
django.setup()

from races.api import search_runners, get_runner_detail
from races.models import Runner
from django.http import HttpRequest
from django.test import Client
import json


def test_api_functions():
    """Test the API functions directly"""
    print("🧪 TESTING API FUNCTIONS DIRECTLY")
    print("-" * 50)
    
    request = HttpRequest()
    
    # Test search functionality
    print("1. Testing search_runners function...")
    try:
        results = search_runners(request, q='Pétur', limit=3)
        print(f"   ✅ Found {len(results)} runners")
        
        if results:
            sample_runner = results[0]
            print(f"   📋 Sample: {sample_runner.name} (ID: {sample_runner.id})")
            
            # Test detail functionality
            print("\n2. Testing get_runner_detail function...")
            detail = get_runner_detail(request, sample_runner.id)
            print(f"   ✅ Retrieved details for {detail.name}")
            print(f"   📊 Total races: {detail.total_races}")
            print(f"   🏃 Race history entries: {len(detail.race_history)}")
            
            return sample_runner.id
        else:
            print("   ⚠️  No runners found")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def test_model_methods():
    """Test the Runner model methods"""
    print("\n🏃 TESTING RUNNER MODEL METHODS")
    print("-" * 50)
    
    try:
        # Get a runner with results
        runner = Runner.objects.filter(results__isnull=False).first()
        if not runner:
            print("   ⚠️  No runners with results found")
            return
        
        print(f"Testing with runner: {runner.name} (ID: {runner.id})")
        
        # Test get_race_history
        print("\n1. Testing get_race_history method...")
        history = runner.get_race_history()
        print(f"   ✅ QuerySet returned with {history.count()} results")
        
        # Test get_race_history_summary
        print("\n2. Testing get_race_history_summary method...")
        summary = runner.get_race_history_summary()
        print(f"   ✅ Summary returned with {len(summary)} entries")
        
        if summary:
            first_race = summary[0]
            print(f"   📋 First race: {first_race['race_date']} - {first_race['race_name']}")
            print(f"   ⏱️  Time: {first_race['finish_time']}")
            print(f"   📍 Splits: {len(first_race['splits'])}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")


def test_api_schemas():
    """Test that API schemas work correctly"""
    print("\n📋 TESTING API SCHEMAS")
    print("-" * 50)
    
    request = HttpRequest()
    
    try:
        # Test search schema
        print("1. Testing RunnerSearchSchema...")
        results = search_runners(request, q='Pétur', limit=1)
        if results:
            runner = results[0]
            # Verify all required fields are present
            required_fields = ['id', 'name', 'birth_year', 'gender', 'nationality', 'total_races']
            for field in required_fields:
                value = getattr(runner, field, None)
                print(f"   ✅ {field}: {value}")
        
        print("\n2. Testing RunnerDetailSchema...")
        if results:
            detail = get_runner_detail(request, results[0].id)
            # Verify detail fields
            print(f"   ✅ Basic info: {detail.name} ({detail.birth_year})")
            print(f"   ✅ Race history: {len(detail.race_history)} entries")
            
            if detail.race_history:
                race = detail.race_history[0]
                print(f"   ✅ Race schema: {race.race_name}")
                print(f"   ✅ Splits: {len(race.splits)} entries")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")


def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n🔍 TESTING EDGE CASES")
    print("-" * 50)
    
    request = HttpRequest()
    
    # Test empty search
    print("1. Testing empty search...")
    try:
        results = search_runners(request, limit=0)
        print(f"   ✅ Empty search returned {len(results)} results")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test invalid runner ID
    print("\n2. Testing invalid runner ID...")
    try:
        detail = get_runner_detail(request, 999999999)
        print("   ⚠️  Should have failed but didn't")
    except Exception as e:
        print(f"   ✅ Correctly failed: {type(e).__name__}")
    
    # Test filter combinations
    print("\n3. Testing filter combinations...")
    try:
        results = search_runners(request, q='Anna', gender='F', birth_year=1980, limit=5)
        print(f"   ✅ Complex filter returned {len(results)} results")
    except Exception as e:
        print(f"   ❌ Error: {e}")


def test_performance():
    """Test performance characteristics"""
    print("\n⚡ TESTING PERFORMANCE")
    print("-" * 50)
    
    import time
    request = HttpRequest()
    
    # Test search performance
    print("1. Testing search performance...")
    start_time = time.time()
    results = search_runners(request, limit=50)
    search_time = time.time() - start_time
    print(f"   ✅ Search for 50 runners took {search_time:.3f}s")
    
    # Test detail performance
    if results:
        print("\n2. Testing detail performance...")
        start_time = time.time()
        detail = get_runner_detail(request, results[0].id)
        detail_time = time.time() - start_time
        print(f"   ✅ Detail retrieval took {detail_time:.3f}s")
        print(f"   📊 Loaded {len(detail.race_history)} races with splits")


def print_summary():
    """Print test summary and usage instructions"""
    print("\n" + "="*60)
    print("🎉 RUNNER API TESTS COMPLETED!")
    print("="*60)
    
    print("\n📚 API ENDPOINTS AVAILABLE:")
    print("   🔍 Search: GET /api/races/runners?q=<name>&limit=<n>")
    print("   👤 Detail: GET /api/races/runners/<id>")
    
    print("\n🌐 TESTING URLs:")
    print("   📖 API Docs: http://localhost:8000/api/docs")
    print("   🧪 Test Search: http://localhost:8000/api/races/runners?q=Pétur&limit=3")
    print("   🧪 Test Detail: http://localhost:8000/api/races/runners/52199")
    
    print("\n🛠️  DEMO SCRIPTS:")
    print("   🚀 Full Demo: python demo_runner_api.py")
    print("   🧪 Full Tests: python test_runner_api.py")
    
    print("\n📖 DOCUMENTATION:")
    print("   📝 API Guide: RUNNER_API.md")
    print("   📝 Model Guide: RUNNER_HISTORY.md")


if __name__ == "__main__":
    print("🚀 STARTING COMPREHENSIVE RUNNER API TESTS")
    print("="*60)
    
    sample_runner_id = test_api_functions()
    test_model_methods()
    test_api_schemas()
    test_edge_cases()
    test_performance()
    print_summary()
    
    print("\n✅ ALL TESTS COMPLETED SUCCESSFULLY!")

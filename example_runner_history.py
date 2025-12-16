#!/usr/bin/env python3
"""
Example script showing how to use the Runner model's race history methods.

This demonstrates how to get all race results for a runner over time,
including races, results, and split times.
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hlaupatimar.settings')
django.setup()

from races.models import Runner


def show_runner_history(runner_name, max_results=None):
    """
    Display race history for a runner.
    
    Args:
        runner_name: Name of the runner to look up
        max_results: Maximum number of results to show (None for all)
    """
    try:
        # Find runners with this name
        runners = Runner.objects.filter(name__icontains=runner_name).filter(results__isnull=False).distinct()
        
        if not runners.exists():
            print(f"No runners found with name containing '{runner_name}' who have race results.")
            return
        
        if runners.count() > 1:
            print(f"Found {runners.count()} runners with name containing '{runner_name}':")
            for i, runner in enumerate(runners, 1):
                print(f"  {i}. {runner} - {runner.results.count()} results")
            
            choice = input("\nEnter the number of the runner you want to see: ")
            try:
                runner = list(runners)[int(choice) - 1]
            except (ValueError, IndexError):
                print("Invalid selection.")
                return
        else:
            runner = runners.first()
        
        print(f"\n{'='*60}")
        print(f"RACE HISTORY FOR {runner.name}")
        if runner.birth_year:
            print(f"Born: {runner.birth_year}")
        if runner.gender:
            print(f"Gender: {runner.get_gender_display()}")
        print(f"Total races: {runner.results.count()}")
        print(f"{'='*60}\n")
        
        # Get race history
        history = runner.get_race_history()
        if max_results:
            history = history[:max_results]
        
        for i, result in enumerate(history, 1):
            race = result.race
            event = race.event
            
            print(f"{i}. {race.date} - {race.name}")
            if event:
                print(f"   Event: {event.name}")
            print(f"   Distance: {race.distance_km}km")
            print(f"   Location: {race.location}")
            print(f"   Finish Time: {result.finish_time}")
            print(f"   Status: {result.get_status_display()}")
            if result.bib_number:
                print(f"   Bib: {result.bib_number}")
            if result.club:
                print(f"   Club: {result.club}")
            
            # Show splits if available
            splits = result.splits.all()
            if splits:
                print(f"   Splits ({splits.count()}):")
                for split in splits:
                    distance_str = f" ({split.distance_km}km)" if split.distance_km else ""
                    print(f"     - {split.split_name}{distance_str}: {split.split_time}")
            
            print()
        
    except Exception as e:
        print(f"Error: {e}")


def show_runner_summary_json(runner_name):
    """
    Show runner history as structured data (JSON-like format).
    
    Args:
        runner_name: Name of the runner to look up
    """
    try:
        runner = Runner.objects.filter(name__icontains=runner_name).filter(results__isnull=False).first()
        
        if not runner:
            print(f"No runner found with name containing '{runner_name}' who has race results.")
            return
        
        print(f"Getting race history summary for: {runner}")
        summary = runner.get_race_history_summary()
        
        import json
        print(json.dumps(summary, indent=2, default=str))
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python example_runner_history.py <runner_name> [max_results]")
        print("  python example_runner_history.py --json <runner_name>")
        print("\nExamples:")
        print("  python example_runner_history.py 'Pétur Sturla'")
        print("  python example_runner_history.py 'Brynjar' 5")
        print("  python example_runner_history.py --json 'Pétur Sturla'")
        sys.exit(1)
    
    if sys.argv[1] == "--json":
        if len(sys.argv) < 3:
            print("Error: Please provide a runner name for JSON output")
            sys.exit(1)
        show_runner_summary_json(sys.argv[2])
    else:
        runner_name = sys.argv[1]
        max_results = int(sys.argv[2]) if len(sys.argv) > 2 else None
        show_runner_history(runner_name, max_results)

# Runner Race History

This document describes the new methods added to the `Runner` model for retrieving race history and results over time.

## New Methods

### `get_race_history()`

Returns all race results for a runner as a Django QuerySet, ordered by race date (oldest first).

**Returns**: QuerySet of Result objects with prefetched race, event, and splits data

**Example**:
```python
from races.models import Runner

runner = Runner.objects.get(id=12345)
history = runner.get_race_history()

for result in history:
    print(f"{result.race.date} - {result.race.name}: {result.finish_time}")
    for split in result.splits.all():
        print(f"  - {split.split_name}: {split.split_time}")
```

### `get_race_history_summary()`

Returns a summary of all race results as a list of dictionaries, suitable for JSON serialization or API responses.

**Returns**: List of dictionaries containing complete race and result information

**Example**:
```python
from races.models import Runner

runner = Runner.objects.get(id=12345)
summary = runner.get_race_history_summary()

# Each item in the summary contains:
for race in summary:
    print(f"Event: {race['event_name']}")
    print(f"Race: {race['race_name']}")
    print(f"Date: {race['race_date']}")
    print(f"Distance: {race['distance_km']}km")
    print(f"Time: {race['finish_time']}")
    print(f"Splits: {len(race['splits'])}")
```

**Dictionary Structure**:
```python
{
    'event_name': str,        # Name of the event
    'race_name': str,         # Name of the specific race
    'race_date': date,        # Date of the race
    'distance_km': float,     # Race distance in kilometers
    'location': str,          # Race location
    'finish_time': timedelta, # Runner's finish time
    'status': str,            # Result status (Finished, DNF, etc.)
    'bib_number': str,        # Runner's bib number
    'club': str,              # Runner's club/team
    'splits': [               # List of split times
        {
            'name': str,           # Split point name
            'distance_km': float,  # Split distance (may be null)
            'time': timedelta      # Cumulative time to split
        }
    ]
}
```

## Usage Examples

### In Django Views

```python
from django.http import JsonResponse
from races.models import Runner

def runner_history_api(request, runner_id):
    """API endpoint for runner race history"""
    try:
        runner = Runner.objects.get(id=runner_id)
        summary = runner.get_race_history_summary()
        return JsonResponse({
            'runner': str(runner),
            'total_races': len(summary),
            'races': summary
        })
    except Runner.DoesNotExist:
        return JsonResponse({'error': 'Runner not found'}, status=404)
```

### In Templates

```python
# views.py
def runner_detail(request, runner_id):
    runner = get_object_or_404(Runner, id=runner_id)
    race_history = runner.get_race_history()
    
    return render(request, 'runner_detail.html', {
        'runner': runner,
        'race_history': race_history
    })
```

```html
<!-- runner_detail.html -->
<h1>{{ runner.name }}</h1>
<h2>Race History ({{ race_history.count }} races)</h2>

{% for result in race_history %}
<div class="race-result">
    <h3>{{ result.race.date }} - {{ result.race.name }}</h3>
    <p>Time: {{ result.finish_time }}</p>
    <p>Status: {{ result.get_status_display }}</p>
    
    {% if result.splits.all %}
    <h4>Splits:</h4>
    <ul>
        {% for split in result.splits.all %}
        <li>{{ split.split_name }}: {{ split.split_time }}</li>
        {% endfor %}
    </ul>
    {% endif %}
</div>
{% endfor %}
```

## Management Commands

### `runner_race_history`

A Django management command for viewing runner history from the command line.

**Usage**:
```bash
# Search by name
python manage.py runner_race_history "Runner Name"
python manage.py runner_race_history "Runner Name" --limit 5

# Search by ID
python manage.py runner_race_history --runner-id 12345
python manage.py runner_race_history --runner-id 12345 --limit 3

# JSON output
python manage.py runner_race_history --runner-id 12345 --json
```

**Options**:
- `runner_name`: Name to search for (partial matches allowed)
- `--runner-id`: Specify runner by ID instead of name
- `--limit`: Maximum number of results to show
- `--json`: Output results as JSON

## Example Scripts

### `example_runner_history.py`

A standalone Python script that demonstrates the usage:

```bash
# Interactive search
python example_runner_history.py "Runner Name"

# Limit results
python example_runner_history.py "Runner Name" 5

# JSON output
python example_runner_history.py --json "Runner Name"
```

## Performance Notes

Both methods use optimized queries with:
- `select_related('race__event')` - Reduces database queries for race and event data
- `prefetch_related('splits')` - Efficiently loads all split data
- Proper ordering by race date and name

The QuerySet returned by `get_race_history()` is lazy and can be further filtered or limited as needed.

## Database Considerations

The methods work with the existing database schema and relationships:
- `Runner` → `Result` (one-to-many via `results` related name)
- `Result` → `Race` (foreign key)
- `Result` → `Split` (one-to-many via `splits` related name)  
- `Race` → `Event` (foreign key, may be null)

Results are ordered by:
1. Race date (ascending)
2. Race name (for same-day races)

This ensures a chronological view of the runner's race history.

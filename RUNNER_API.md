# Runner API Documentation

This document describes the Runner API endpoints for searching and retrieving detailed runner information.

## Base URL

All endpoints are available under the base URL: `http://localhost:8002/api/races/`

## Authentication

Currently, no authentication is required for these endpoints.

## Endpoints

### 1. Search Runners

**Endpoint:** `GET /api/races/runners/search`

Search for runners with optional filters and pagination.

#### Parameters

| Parameter | Type | Required | Description | Default | Max |
|-----------|------|----------|-------------|---------|-----|
| `q` | string | No | Search term for runner name (partial matches) | - | - |
| `birth_year` | integer | No | Filter by birth year | - | - |
| `gender` | string | No | Filter by gender (`M` or `F`) | - | - |
| `limit` | integer | No | Maximum number of results | 20 | 100 |
| `offset` | integer | No | Number of results to skip (pagination) | 0 | - |

#### Response Schema

```json
[
  {
    "id": 52199,
    "name": "Pétur Sturla Bjarnason",
    "birth_year": 1980,
    "gender": "M",
    "nationality": "ISL",
    "total_races": 6
  }
]
```

#### Examples

```bash
# Search for runners named 'Pétur'
GET /api/races/runners/search?q=Pétur&limit=5

# Search for female runners named 'Anna'
GET /api/races/runners/search?q=Anna&gender=F&limit=3

# Search for runners born in 1980
GET /api/races/runners/search?birth_year=1980&limit=10

# Pagination example
GET /api/races/runners/search?q=Anna&limit=10&offset=10
```

### 2. Runner Detail

**Endpoint:** `GET /api/races/runners/{runner_id}`

Get detailed information about a specific runner including complete race history.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `runner_id` | integer | Yes | Unique identifier of the runner |

#### Response Schema

```json
{
  "id": 52199,
  "name": "Pétur Sturla Bjarnason",
  "birth_year": 1980,
  "gender": "M",
  "nationality": "ISL",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "total_races": 6,
  "race_history": [
    {
      "event_name": "109. Víðavangshlaup ÍR",
      "race_name": "109. Víðavangshlaup ÍR - Víðavangshlaup ÍR - 5 km",
      "race_date": "2024-04-25",
      "distance_km": 5.0,
      "location": "Iceland",
      "finish_time": "0:16:30",
      "status": "Finished",
      "bib_number": "2742",
      "club": "Ungmennafélagið Afturelding",
      "splits": [
        {
          "name": "~3.5 KM",
          "distance_km": null,
          "time": "0:10:49"
        }
      ]
    }
  ]
}
```

#### Race History Fields

Each race in the `race_history` array contains:

| Field | Type | Description |
|-------|------|-------------|
| `event_name` | string | Name of the racing event |
| `race_name` | string | Specific race name within the event |
| `race_date` | date | Date of the race (YYYY-MM-DD) |
| `distance_km` | float | Race distance in kilometers |
| `location` | string | Race location |
| `finish_time` | string | Runner's finish time (HH:MM:SS) |
| `status` | string | Result status (Finished, DNF, DNS, DQ) |
| `bib_number` | string | Runner's bib number (optional) |
| `club` | string | Runner's club/team (optional) |
| `splits` | array | Array of split times |

#### Split Fields

Each split in the `splits` array contains:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Split point name |
| `distance_km` | float | Distance to split point in km (optional) |
| `time` | string | Cumulative time to split (HH:MM:SS) |

#### Example

```bash
# Get detailed information for runner ID 52199
GET /api/races/runners/52199
```

## Usage Examples

### Using curl

```bash
# Search for runners
curl "http://localhost:8002/api/races/runners/search?q=Pétur&limit=3"

# Get runner details
curl "http://localhost:8002/api/races/runners/52199"
```

### Using Python requests

```python
import requests

# Search for runners
response = requests.get(
    "http://localhost:8002/api/races/runners/search",
    params={"q": "Pétur", "limit": 5}
)
runners = response.json()

# Get runner details
runner_id = runners[0]["id"]
response = requests.get(f"http://localhost:8002/api/races/runners/{runner_id}")
runner_detail = response.json()

print(f"Runner: {runner_detail['name']}")
print(f"Total races: {runner_detail['total_races']}")
```

### Using JavaScript fetch

```javascript
// Search for runners
fetch('/api/races/runners/search?q=Pétur&limit=5')
  .then(response => response.json())
  .then(runners => {
    console.log('Found runners:', runners);
    
    // Get details for first runner
    if (runners.length > 0) {
      return fetch(`/api/races/runners/${runners[0].id}`);
    }
  })
  .then(response => response.json())
  .then(runner => {
    console.log('Runner details:', runner);
    console.log('Race history:', runner.race_history);
  });
```

## Error Handling

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Runner not found |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Performance Notes

- The search endpoint is optimized for name-based searches
- Runner detail endpoint uses optimized database queries with prefetching
- Race history is ordered chronologically (oldest first)
- Large result sets are paginated to improve performance

## Rate Limiting

Currently, no rate limiting is implemented, but this may be added in future versions.

## Interactive API Documentation

For interactive API testing and more detailed schema information, visit:
**http://localhost:8002/api/docs**

This provides a Swagger/OpenAPI interface where you can test endpoints directly from your browser.

## Demo Script

Run the demo script to see the API in action:

```bash
docker compose exec web python demo_runner_api.py
```

This demonstrates all API functionality with real data from the database.

## Integration with Frontend

These endpoints are designed to be consumed by frontend applications. Common use cases:

1. **Runner Search Autocomplete**: Use the search endpoint with partial names
2. **Runner Profile Pages**: Use the detail endpoint to show complete runner information
3. **Race History Displays**: The race_history array provides chronological race data
4. **Performance Analytics**: Split times and race results for trend analysis

## Future Enhancements

Planned improvements include:

- Pagination metadata (total count, page numbers)
- Additional filter options (nationality, club)
- Performance statistics (average times, PRs)
- Race result rankings and comparisons
- Export formats (CSV, PDF)

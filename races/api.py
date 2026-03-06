from ninja import Router, File
from ninja.files import UploadedFile
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.http import JsonResponse
from typing import List, Optional
from datetime import date

from .models import Race, Result, Split, Runner
from .schemas import (
    RaceSchema, RaceCreateSchema, RaceListFilterSchema,
    ResultSchema, ResultCreateSchema,
    SplitSchema, SplitCreateSchema,
    ScrapingResultSchema, HTMLContentSchema,
    RunnerSchema, RunnerSearchSchema, RunnerDetailSchema
)
from .services import ScrapingService, TimatakaScrapingError

router = Router()


@router.post("/scrape", response=ScrapingResultSchema)
def scrape_html_content(request, payload: HTMLContentSchema):
    """
    Scrape race data from Timataka.net HTML content.
    
    This endpoint accepts HTML content and extracts race information from it.
    Optionally saves the races to the database.
    """
    try:
        scraping_service = ScrapingService()
        
        # Validate HTML content
        if not payload.html_content or len(payload.html_content.strip()) < 100:
            return ScrapingResultSchema(
                success=False,
                message="HTML content is too short or empty"
            )
        
        if payload.save_to_db:
            # Scrape and save to database
            result = scraping_service.scrape_and_save_races(
                payload.html_content,
                payload.source_url,
                overwrite=payload.overwrite_existing
            )
            
            # Get the recently scraped races for response
            if result['saved'] > 0 or result['updated'] > 0:
                recent_races = Race.objects.filter(
                    source_url=payload.source_url
                ).order_by('-updated_at')[:result['scraped']]
                races_data = [RaceSchema.from_orm(race) for race in recent_races]
            else:
                races_data = None
            
            return ScrapingResultSchema(
                success=True,
                message=f"Scraped {result['scraped']} races, saved {result['saved']}, updated {result['updated']}, skipped {result['skipped']}, errors {result['errors']}",
                scraped=result['scraped'],
                saved=result['saved'],
                updated=result['updated'],
                skipped=result['skipped'],
                errors=result['errors'],
                races=races_data
            )
        else:
            # Just scrape without saving
            races_data = scraping_service.scrape_races_only(
                payload.html_content,
                payload.source_url
            )
            
            # Convert to schema format
            races_schemas = []
            for race_data in races_data:
                # Remove fields not in schema
                race_data_clean = {k: v for k, v in race_data.items() if k != 'start_time'}
                # Add required fields for schema
                race_data_clean.update({
                    'id': 0,  # Placeholder for non-saved races
                    'created_at': '2025-01-01T00:00:00Z',
                    'updated_at': '2025-01-01T00:00:00Z'
                })
                races_schemas.append(race_data_clean)
            
            return ScrapingResultSchema(
                success=True,
                message=f"Successfully scraped {len(races_data)} races (not saved to database)",
                scraped=len(races_data),
                races=races_schemas
            )
            
    except TimatakaScrapingError as e:
        return ScrapingResultSchema(
            success=False,
            message=f"Scraping error: {str(e)}"
        )
    except Exception as e:
        return ScrapingResultSchema(
            success=False,
            message=f"Unexpected error: {str(e)}"
        )


@router.get("/scrape/supported-types")
def get_supported_race_types(request):
    """Get list of supported race types for scraping"""
    scraping_service = ScrapingService()
    return {
        "supported_types": scraping_service.get_supported_race_types(),
        "description": "Race types that can be automatically detected during scraping"
    }


@router.get("/search", response=List[RaceSchema])
def search_races(request, q: str, limit: int = 20):
    """Search races by name, description, or location"""
    queryset = Race.objects.filter(
        Q(name__icontains=q) |
        Q(description__icontains=q) |
        Q(location__icontains=q) |
        Q(organizer__icontains=q)
    )[:limit]
    return queryset


@router.get("/", response=List[RaceSchema])
def list_races(
    request,
    race_type: Optional[str] = None,
    location: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    distance_min: Optional[float] = None,
    distance_max: Optional[float] = None,
    limit: int = 20,
    offset: int = 0
):
    """List all races with optional filtering"""
    queryset = Race.objects.all()
    
    if race_type:
        queryset = queryset.filter(race_type=race_type)
    if location:
        queryset = queryset.filter(location__icontains=location)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    if distance_min:
        queryset = queryset.filter(distance_km__gte=distance_min)
    if distance_max:
        queryset = queryset.filter(distance_km__lte=distance_max)
    
    return queryset[offset:offset + limit]


@router.post("/", response=RaceSchema)
def create_race(request, payload: RaceCreateSchema):
    """Create a new race"""
    race = Race.objects.create(**payload.dict())
    return race


@router.get("/{race_id}", response=RaceSchema)
def get_race(request, race_id: int):
    """Get a specific race by ID"""
    return get_object_or_404(Race, id=race_id)


@router.put("/{race_id}", response=RaceSchema)
def update_race(request, race_id: int, payload: RaceCreateSchema):
    """Update a specific race"""
    race = get_object_or_404(Race, id=race_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(race, attr, value)
    race.save()
    return race


@router.delete("/{race_id}")
def delete_race(request, race_id: int):
    """Delete a specific race"""
    race = get_object_or_404(Race, id=race_id)
    race.delete()
    return {"success": True}


@router.get("/{race_id}/results", response=List[ResultSchema])
def list_race_results(
    request, 
    race_id: int,
    gender: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List all results for a specific race"""
    race = get_object_or_404(Race, id=race_id)
    queryset = race.results.all()
    
    if gender:
        queryset = queryset.filter(gender=gender)
    if status:
        queryset = queryset.filter(status=status)
    
    return queryset[offset:offset + limit]


@router.post("/{race_id}/results", response=ResultSchema)
def create_race_result(request, race_id: int, payload: ResultCreateSchema):
    """Create a new result for a race"""
    race = get_object_or_404(Race, id=race_id)
    payload_dict = payload.dict()
    payload_dict['race_id'] = race.id
    result = Result.objects.create(**payload_dict)
    return result


@router.get("/results/{result_id}", response=ResultSchema)
def get_result(request, result_id: int):
    """Get a specific result by ID"""
    return get_object_or_404(Result, id=result_id)


@router.get("/results/{result_id}/splits", response=List[SplitSchema])
def list_result_splits(request, result_id: int):
    """List all splits for a specific result"""
    result = get_object_or_404(Result, id=result_id)
    return result.splits.all()


@router.post("/results/{result_id}/splits", response=SplitSchema)
def create_split(request, result_id: int, payload: SplitCreateSchema):
    """Create a new split for a result"""
    result = get_object_or_404(Result, id=result_id)
    payload_dict = payload.dict()
    payload_dict['result_id'] = result.id
    split = Split.objects.create(**payload_dict)
    return split


# Runner API endpoints

@router.get("/runners/search", response=List[RunnerSearchSchema])
def search_runners(
    request,
    q: Optional[str] = None,
    birth_year: Optional[int] = None,
    gender: Optional[str] = None,
    stable_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """
    Search for runners with optional filters.
    
    Parameters:
    - q: Search term for runner name (partial matches)
    - birth_year: Filter by birth year
    - gender: Filter by gender (M/F)
    - limit: Maximum number of results (default: 20, max: 100)
    - offset: Number of results to skip (for pagination)
    """
    # Limit the maximum number of results
    limit = min(limit, 100)
    
    queryset = Runner.objects.annotate(
        total_races=Count('results')
    ).filter(results__isnull=False).distinct()
    
    # Apply filters
    if stable_id:
        queryset = queryset.filter(stable_id=stable_id)
    else:
        if q:
            queryset = queryset.filter(name__icontains=q)
        
        if birth_year:
            queryset = queryset.filter(birth_year=birth_year)
        
        if gender and gender.upper() in ['M', 'F']:
            queryset = queryset.filter(gender=gender.upper())
    
    # Order by name for consistent results
    queryset = queryset.order_by('name', 'birth_year')
    
    # Apply pagination
    runners = queryset[offset:offset + limit]
    
    # Convert to schema format
    result = []
    for runner in runners:
        result.append(RunnerSearchSchema(
            id=runner.id,
            stable_id=runner.stable_id,
            name=runner.name,
            birth_year=runner.birth_year,
            gender=runner.gender,
            nationality=runner.nationality,
            total_races=runner.total_races
        ))
    
    return result


@router.get("/runners/{runner_id}", response=RunnerDetailSchema)
def get_runner_detail(request, runner_id: str):
    """
    Get detailed information about a specific runner including complete race history.
    
    Returns:
    - Runner basic information
    - Complete race history with results and splits
    - Ordered chronologically by race date
    """
    if runner_id.startswith("rnr_"):
        runner = get_object_or_404(Runner, stable_id=runner_id)
    else:
        runner = get_object_or_404(Runner, id=int(runner_id))
    
    # Get race history summary using the model method
    race_history_data = runner.get_race_history_summary()
    
    # Convert to schema format
    race_history = [
        {
            'event_name': race['event_name'],
            'race_name': race['race_name'],
            'race_date': race['race_date'],
            'distance_km': race['distance_km'],
            'location': race['location'],
            'finish_time': race['finish_time'],
            'status': race['status'],
            'bib_number': race['bib_number'],
            'club': race['club'],
            'splits': [
                {
                    'name': split['name'],
                    'distance_km': split['distance_km'],
                    'time': split['time']
                }
                for split in race['splits']
            ]
        }
        for race in race_history_data
    ]
    
    return RunnerDetailSchema(
        id=runner.id,
        stable_id=runner.stable_id,
        name=runner.name,
        birth_year=runner.birth_year,
        gender=runner.gender,
        nationality=runner.nationality,
        created_at=runner.created_at,
        updated_at=runner.updated_at,
        total_races=len(race_history),
        race_history=race_history
    )

from ninja import Router, File
from ninja.files import UploadedFile
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Case, When, IntegerField
from django.http import Http404
from django.http import JsonResponse
from typing import Dict, List, Optional
from datetime import date
from django.utils import timezone

from .models import Race, Result, Split, Runner, RunnerAlias
from .schemas import (
    RaceSchema, RaceCreateSchema, RaceListFilterSchema,
    ResultSchema, ResultCreateSchema,
    SplitSchema, SplitCreateSchema,
    ScrapingResultSchema, HTMLContentSchema,
    RunnerSchema, RunnerSearchSchema, RunnerDetailSchema, RaceResultRowSchema, EventSummarySchema
)
from .services import ScrapingService, TimatakaScrapingError

router = Router()


def _resolve_runner_for_read(runner_identifier: str) -> Runner:
    """
    Resolve runner id/stable_id to canonical runner using runner alias mappings.
    """
    is_stable = runner_identifier.startswith("rnr_")

    alias_queryset = RunnerAlias.objects.filter(is_active=True).select_related("canonical_runner")
    alias = None
    if is_stable:
        alias = alias_queryset.filter(alias_stable_id=runner_identifier).first()
    else:
        try:
            alias_runner_id = int(runner_identifier)
        except (TypeError, ValueError):
            alias_runner_id = None
        alias = (
            alias_queryset.filter(alias_runner_id=alias_runner_id).first()
            if alias_runner_id is not None
            else None
        )
    if alias and alias.canonical_runner_id:
        return alias.canonical_runner

    runner = None
    if is_stable:
        runner = Runner.objects.filter(stable_id=runner_identifier).first()
    else:
        try:
            numeric_id = int(runner_identifier)
        except (TypeError, ValueError):
            numeric_id = None
        if numeric_id is not None:
            runner = Runner.objects.filter(id=numeric_id).first()

    if runner:
        source_alias = alias_queryset.filter(
            Q(source_runner=runner)
            | Q(alias_runner_id=runner.id)
            | Q(alias_stable_id=runner.stable_id or ""),
        ).first()
        return source_alias.canonical_runner if source_alias else runner

    raise Http404("Runner not found")


def _get_profile_race_counts(runners: List[Runner]) -> Dict[int, int]:
    """
    Return accurate distinct race counts for canonical runners, including all active aliases.
    """
    if not runners:
        return {}

    canonical_ids = [runner.id for runner in runners]
    profile_runner_ids_by_canonical = {runner_id: {runner_id} for runner_id in canonical_ids}

    alias_rows = list(
        RunnerAlias.objects.filter(
            is_active=True,
            canonical_runner_id__in=canonical_ids,
        ).values(
            "canonical_runner_id",
            "source_runner_id",
            "alias_runner_id",
            "alias_stable_id",
        )
    )

    stable_to_canonical_ids: Dict[str, set[int]] = {}
    for alias in alias_rows:
        canonical_id = alias["canonical_runner_id"]
        source_runner_id = alias.get("source_runner_id")
        alias_runner_id = alias.get("alias_runner_id")
        alias_stable_id = alias.get("alias_stable_id")

        if source_runner_id:
            profile_runner_ids_by_canonical[canonical_id].add(source_runner_id)
        if alias_runner_id:
            profile_runner_ids_by_canonical[canonical_id].add(alias_runner_id)
        if alias_stable_id:
            stable_to_canonical_ids.setdefault(alias_stable_id, set()).add(canonical_id)

    if stable_to_canonical_ids:
        for runner_id, stable_id in Runner.objects.filter(
            stable_id__in=list(stable_to_canonical_ids.keys())
        ).values_list("id", "stable_id"):
            for canonical_id in stable_to_canonical_ids.get(stable_id, ()):
                profile_runner_ids_by_canonical[canonical_id].add(runner_id)

    canonical_ids_by_runner_id: Dict[int, set[int]] = {}
    all_profile_runner_ids = set()
    for canonical_id, runner_ids in profile_runner_ids_by_canonical.items():
        all_profile_runner_ids.update(runner_ids)
        for runner_id in runner_ids:
            canonical_ids_by_runner_id.setdefault(runner_id, set()).add(canonical_id)

    race_ids_by_canonical = {runner_id: set() for runner_id in canonical_ids}
    for runner_id, race_id in Result.objects.filter(
        runner_id__in=all_profile_runner_ids
    ).values_list("runner_id", "race_id").distinct():
        for canonical_id in canonical_ids_by_runner_id.get(runner_id, ()):
            race_ids_by_canonical[canonical_id].add(race_id)

    return {
        canonical_id: len(race_ids)
        for canonical_id, race_ids in race_ids_by_canonical.items()
    }


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
    queryset = (
        Race.objects.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q) |
            Q(organizer__icontains=q)
        )
        .order_by("-date", "-id")[:limit]
    )
    return queryset


@router.get("/events/latest", response=List[EventSummarySchema])
def list_latest_events(request, limit: int = 12):
    """List latest processed events (newest by event date)."""
    from .models import Event

    safe_limit = max(1, min(limit, 50))
    placeholder_date = date(2099, 12, 31)
    today = timezone.localdate()

    events = (
        Event.objects.filter(races__isnull=False)
        .exclude(date=placeholder_date)
        .annotate(race_count=Count("races", distinct=True))
        .annotate(result_count=Count("races__results", distinct=True))
        .order_by("-date", "-id")
        .distinct()[:safe_limit]
    )

    response = []
    for event in events:
        has_results = getattr(event, "result_count", 0) > 0
        preview_race_id = None
        if has_results:
            preview_race_id = (
                Race.objects.filter(event_id=event.id, results__isnull=False)
                .order_by("-date", "-id")
                .values_list("id", flat=True)
                .first()
            )
        response.append(
            {
                "id": event.id,
                "name": event.name,
                "date": event.date,
                "source": event.source,
                "race_count": getattr(event, "race_count", 0),
                "result_count": getattr(event, "result_count", 0),
                "has_results": has_results,
                "is_upcoming": event.date > today,
                "preview_race_id": preview_race_id,
            }
        )

    return response


@router.get("/", response=List[RaceSchema])
def list_races(
    request,
    race_type: Optional[str] = None,
    location: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    distance_min: Optional[float] = None,
    distance_max: Optional[float] = None,
    latest_first: bool = False,
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

    if latest_first:
        queryset = queryset.order_by("-date", "-id")
    
    return queryset[offset:offset + limit]


@router.get("/{race_id}/event-races", response=List[RaceSchema])
def list_event_races(request, race_id: int, limit: int = 20):
    """List other races that belong to the same event as the selected race."""
    race = get_object_or_404(Race, id=race_id)
    if not race.event_id:
        return []

    safe_limit = max(1, min(limit, 50))
    return (
        Race.objects.filter(event_id=race.event_id)
        .exclude(id=race.id)
        .order_by("date", "distance_km", "name")[:safe_limit]
    )


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
    
    alias_stable_subquery = RunnerAlias.objects.filter(is_active=True).values_list("alias_stable_id", flat=True)
    alias_runner_id_subquery = RunnerAlias.objects.filter(
        is_active=True,
        alias_runner_id__isnull=False,
    ).values_list("alias_runner_id", flat=True)
    queryset = Runner.objects.exclude(
        Q(source_aliases__is_active=True)
        | Q(stable_id__in=alias_stable_subquery)
        | Q(id__in=alias_runner_id_subquery)
    ).filter(
        Q(results__isnull=False) | Q(canonical_aliases__is_active=True)
    ).distinct()
    
    # Apply filters
    if stable_id:
        try:
            canonical_runner = _resolve_runner_for_read(stable_id)
        except Http404:
            return []
        queryset = queryset.filter(id=canonical_runner.id)
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
    
    race_counts_by_runner_id = _get_profile_race_counts(list(runners))

    # Convert to schema format
    result = []
    for runner in runners:
        total_races = race_counts_by_runner_id.get(runner.id, 0)
        if total_races <= 0:
            continue
        result.append(RunnerSearchSchema(
            id=runner.id,
            stable_id=runner.stable_id,
            name=runner.name,
            birth_year=runner.birth_year,
            gender=runner.gender,
            nationality=runner.nationality,
            total_races=total_races
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
    runner = _resolve_runner_for_read(runner_id)
    
    # Get race history summary using the model method
    race_history_data = runner.get_race_history_summary()
    
    # Convert to schema format
    race_history = [
        {
            'race_id': race['race_id'],
            'event_name': race['event_name'],
            'race_name': race['race_name'],
            'race_date': race['race_date'],
            'distance_km': race['distance_km'],
            'surface_type': race.get('surface_type', 'unknown'),
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


@router.get("/{race_id}/results-table", response=List[RaceResultRowSchema])
def list_race_results_table(
    request,
    race_id: int,
    gender: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 500,
    offset: int = 0
):
    """
    List race results in a frontend-friendly format with runner metadata.
    """
    race = get_object_or_404(Race, id=race_id)
    status_priority = Case(
        When(status='finished', then=0),
        default=1,
        output_field=IntegerField(),
    )
    queryset = race.results.select_related('runner').order_by(status_priority, 'finish_time', 'id')

    if gender and gender.upper() in ['M', 'F']:
        queryset = queryset.filter(runner__gender=gender.upper())
    if status:
        queryset = queryset.filter(status=status)

    page_results = list(queryset[offset:offset + limit])
    runner_ids = [result.runner_id for result in page_results if result.runner_id]
    alias_map = {
        alias.source_runner_id: alias.canonical_runner
        for alias in RunnerAlias.objects.filter(
            source_runner_id__in=runner_ids,
            is_active=True,
        ).select_related("canonical_runner")
    }

    rows = []
    for position, result in enumerate(page_results, start=offset + 1):
        runner = result.runner
        canonical_runner = alias_map.get(runner.id) if runner else None
        display_runner = canonical_runner or runner
        rows.append(
            RaceResultRowSchema(
                id=result.id,
                race_id=race.id,
                position=position,
                runner_id=display_runner.id if display_runner else None,
                runner_stable_id=display_runner.stable_id if display_runner else None,
                runner_name=display_runner.name if display_runner else (result.participant_name or 'Óþekktur'),
                gender=display_runner.gender if display_runner else None,
                birth_year=display_runner.birth_year if display_runner else None,
                bib_number=result.bib_number,
                club=result.club or None,
                finish_time=result.finish_time,
                chip_time=result.chip_time,
                time_behind=result.time_behind,
                status=result.status,
            )
        )

    return rows

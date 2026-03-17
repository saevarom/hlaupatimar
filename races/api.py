from ninja import Router, File
from ninja.files import UploadedFile
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Case, When, IntegerField, OuterRef, Subquery, DurationField
from django.http import Http404
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional
from datetime import date, timedelta
from django.utils import timezone
from collections import defaultdict

from .models import Event, Race, RaceCorrectionSuggestion, Result, Split, Runner, RunnerAlias
from .schemas import (
    RaceSchema, RaceCreateSchema, RaceListFilterSchema,
    ResultSchema, ResultCreateSchema,
    SplitSchema, SplitCreateSchema,
    ScrapingResultSchema, HTMLContentSchema,
    RunnerSchema, RunnerSearchSchema, RunnerDetailSchema, RaceResultRowSchema, EventSummarySchema,
    RaceStatsSchema, RaceTimeStatsSchema, RaceTimeBucketSchema, RaceGenderStatsSchema,
    RaceAgeBandStatsSchema, RaceClubStatsSchema, RaceComparisonSchema, RaceComparisonMetricSchema,
    PaginatedRaceListSchema, RaceCorrectionSuggestionCreateSchema, RaceCorrectionSuggestionSchema
)
from .services import ScrapingService, TimatakaScrapingError

router = Router()


def _public_races():
    return Race.public.all()


def _public_events():
    return Event.public.all()


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
        runner_id__in=all_profile_runner_ids,
        race__discipline='running',
    ).values_list("runner_id", "race_id").distinct():
        for canonical_id in canonical_ids_by_runner_id.get(runner_id, ()):
            race_ids_by_canonical[canonical_id].add(race_id)

    return {
        canonical_id: len(race_ids)
        for canonical_id, race_ids in race_ids_by_canonical.items()
    }


def _with_winning_time(queryset):
    winner_subquery = (
        Result.objects.filter(
            race_id=OuterRef("pk"),
            status="finished",
            finish_time__isnull=False,
        )
        .order_by("finish_time", "id")
        .values("finish_time")[:1]
    )
    return queryset.annotate(
        winning_time=Subquery(
            winner_subquery,
            output_field=DurationField(),
        )
    )


def _get_winning_time_by_race_ids(race_ids: List[int]) -> Dict[int, timedelta]:
    if not race_ids:
        return {}

    race_id_set = {int(race_id) for race_id in race_ids if race_id is not None}
    if not race_id_set:
        return {}

    winner_map: Dict[int, timedelta] = {}
    rows = (
        Result.objects.filter(
            race_id__in=race_id_set,
            status="finished",
            finish_time__isnull=False,
        )
        .order_by("race_id", "finish_time", "id")
        .values_list("race_id", "finish_time")
    )
    for race_id, finish_time in rows:
        if race_id not in winner_map:
            winner_map[race_id] = finish_time
    return winner_map


def _percentile_seconds(sorted_seconds: List[float], percentile: float) -> Optional[float]:
    if not sorted_seconds:
        return None
    if len(sorted_seconds) == 1:
        return sorted_seconds[0]

    position = (len(sorted_seconds) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(sorted_seconds) - 1)
    weight = position - lower
    return (
        sorted_seconds[lower] * (1 - weight)
        + sorted_seconds[upper] * weight
    )


def _timedelta_from_seconds(seconds: Optional[float]) -> Optional[timedelta]:
    if seconds is None:
        return None
    return timedelta(seconds=int(round(seconds)))


def _sub_x_thresholds_for_race(race: Race) -> List[int]:
    distance_km = float(race.distance_km or 0)
    race_type = (race.race_type or "").strip().lower()

    if race_type == "5k" or 4.0 <= distance_km <= 6.0:
        return [20, 25, 30, 35]
    if race_type == "10k" or 9.0 <= distance_km <= 11.0:
        return [40, 45, 50, 60]
    if race_type == "half_marathon" or 20.0 <= distance_km <= 22.5:
        return [90, 100, 110, 120, 150]
    if race_type == "marathon" or 41.0 <= distance_km <= 43.5:
        return [180, 210, 240, 270, 300]
    return [240, 360, 480, 720]


def _format_minutes(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60}klst"
    return f"{minutes}m"


def _bucket_label(lower_minutes: Optional[int], upper_minutes: Optional[int]) -> str:
    if lower_minutes is None and upper_minutes is not None:
        return f"Undir {_format_minutes(upper_minutes)}"
    if lower_minutes is not None and upper_minutes is not None:
        return f"{_format_minutes(lower_minutes)}-{_format_minutes(upper_minutes)}"
    if lower_minutes is not None:
        return f"{_format_minutes(lower_minutes)}+"
    return "Annað"


def _age_band_label(age: int) -> str:
    if age < 20:
        return "Undir 20"
    if age < 30:
        return "20-29"
    if age < 40:
        return "30-39"
    if age < 50:
        return "40-49"
    if age < 60:
        return "50-59"
    return "60+"


def _race_comparison_gender_label(gender: Optional[str]) -> Optional[str]:
    normalized_gender = (gender or "").strip().upper()
    if normalized_gender == "F":
        return "Konur"
    if normalized_gender == "M":
        return "Karlar"
    return None


def _race_comparison_surface_label(surface_type: str) -> str:
    return {
        "road": "vegahlaup",
        "trail": "utanvegahlaup",
        "mixed": "blandað yfirborð",
        "unknown": "óþekkt yfirborð",
    }.get((surface_type or "").strip().lower(), "hlaup")


def _race_comparison_type_label(race: Race) -> str:
    race_type = (race.race_type or "").strip().lower()
    labels = {
        "5k": "5 km",
        "10k": "10 km",
        "half_marathon": "hálft maraþon",
        "marathon": "maraþon",
        "ultra": "ultra",
        "trail": "utanvegahlaup",
    }
    if race_type in labels:
        return labels[race_type]
    distance_km = float(race.distance_km or 0.0)
    if distance_km > 0:
        return f"{distance_km:g} km"
    return "hlaup"


def _race_comparison_label(race: Race) -> str:
    return f"{_race_comparison_type_label(race)}, {_race_comparison_surface_label(race.surface_type)}"


def _race_comparison_cohort_key(race: Race) -> Optional[str]:
    if not _is_running_race_candidate(race):
        return None

    discipline = (race.discipline or "").strip().lower()
    race_type = (race.race_type or "").strip().lower()
    surface_type = (race.surface_type or "").strip().lower()
    distance_km = float(race.distance_km or 0.0)

    if surface_type not in {"road", "mixed"}:
        return None

    if race_type == "5k" and 4.75 <= distance_km <= 5.25:
        return f"discipline:{discipline}:type:{race_type}:surface:{surface_type}"
    if race_type == "10k" and 9.5 <= distance_km <= 10.5:
        return f"discipline:{discipline}:type:{race_type}:surface:{surface_type}"
    if race_type == "half_marathon" and 20.5 <= distance_km <= 21.7:
        return f"discipline:{discipline}:type:{race_type}:surface:{surface_type}"
    if race_type == "marathon" and 42.0 <= distance_km <= 42.6:
        return f"discipline:{discipline}:type:{race_type}:surface:{surface_type}"
    return None


def _build_race_comparison_metric(
    current_seconds: Optional[float],
    peer_metric_seconds: List[float],
) -> RaceComparisonMetricSchema:
    sorted_peer_seconds = sorted(peer_metric_seconds)
    peer_median_seconds = _percentile_seconds(sorted_peer_seconds, 0.50)

    faster_count = sum(value < (current_seconds or 0) for value in sorted_peer_seconds)
    slower_count = sum(value > (current_seconds or 0) for value in sorted_peer_seconds)
    comparison_count = len(sorted_peer_seconds)

    faster_than_percentage = (
        round((slower_count / comparison_count) * 100, 1)
        if comparison_count
        else None
    )
    delta_from_peer_median_percentage = (
        round(((current_seconds - peer_median_seconds) / peer_median_seconds) * 100, 1)
        if current_seconds is not None and peer_median_seconds not in {None, 0}
        else None
    )

    return RaceComparisonMetricSchema(
        current=_timedelta_from_seconds(current_seconds),
        peer_median=_timedelta_from_seconds(peer_median_seconds),
        rank=faster_count + 1 if current_seconds is not None else None,
        faster_than_percentage=faster_than_percentage,
        delta_from_peer_median_percentage=delta_from_peer_median_percentage,
    )


def _is_plausible_race_performance(
    race: Race,
    winner_seconds: float,
    median_seconds: float,
) -> bool:
    distance_km = float(race.distance_km or 0.0)
    if distance_km <= 0:
        return False

    minimum_median_seconds = distance_km * 120.0
    minimum_winner_seconds = distance_km * 90.0
    return median_seconds >= minimum_median_seconds and winner_seconds >= minimum_winner_seconds


def _is_running_race_candidate(race: Race) -> bool:
    return (race.discipline or "").strip().lower() == "running"


def _build_race_speed_data(
    races: List[Race],
    gender: Optional[str] = None,
) -> Dict[int, Dict[str, object]]:
    minimum_finishers = 5
    minimum_cohort_races = 5
    today = timezone.localdate()

    requested_races = [
        race
        for race in races
        if race.date and race.date <= today and _is_running_race_candidate(race)
    ]
    if not requested_races:
        return {}

    requested_cohorts = {
        int(race.id): _race_comparison_cohort_key(race)
        for race in requested_races
    }
    requested_keys = {key for key in requested_cohorts.values() if key}
    if not requested_keys:
        return {}

    peer_races = list(
        _public_races().filter(date__lte=today).only(
            "id",
            "discipline",
            "race_type",
            "surface_type",
            "distance_km",
            "date",
        )
    )

    peer_cohort_by_race_id: Dict[int, str] = {}
    peer_race_ids: List[int] = []
    for peer_race in peer_races:
        cohort_key = _race_comparison_cohort_key(peer_race)
        if cohort_key and cohort_key in requested_keys and _is_running_race_candidate(peer_race):
            peer_cohort_by_race_id[int(peer_race.id)] = cohort_key
            peer_race_ids.append(int(peer_race.id))

    if not peer_race_ids:
        return {}

    results_queryset = Result.objects.filter(
        race_id__in=peer_race_ids,
        status="finished",
        finish_time__isnull=False,
    )
    normalized_gender = (gender or "").strip().upper()
    if normalized_gender in {"F", "M"}:
        results_queryset = results_queryset.filter(runner__gender=normalized_gender)

    seconds_by_race_id: Dict[int, List[float]] = defaultdict(list)
    for race_id, finish_time in results_queryset.values_list("race_id", "finish_time").order_by("race_id", "finish_time"):
        seconds_by_race_id[int(race_id)].append(float(finish_time.total_seconds()))

    cohort_rows: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    race_stats: Dict[int, Dict[str, object]] = {}
    peer_race_by_id = {int(race.id): race for race in peer_races}

    for peer_race_id in peer_race_ids:
        sorted_seconds = seconds_by_race_id.get(peer_race_id, [])
        if len(sorted_seconds) < minimum_finishers:
            continue

        median_seconds = _percentile_seconds(sorted_seconds, 0.50)
        if median_seconds is None:
            continue
        if not _is_plausible_race_performance(
            peer_race_by_id[peer_race_id],
            winner_seconds=sorted_seconds[0],
            median_seconds=median_seconds,
        ):
            continue

        row = {
            "race_id": peer_race_id,
            "winner_seconds": sorted_seconds[0],
            "median_seconds": median_seconds,
            "finishers": len(sorted_seconds),
            "cohort_key": peer_cohort_by_race_id[peer_race_id],
        }
        race_stats[peer_race_id] = row
        cohort_rows[peer_cohort_by_race_id[peer_race_id]].append(row)

    speed_data: Dict[int, Dict[str, object]] = {}
    for race in requested_races:
        cohort_key = requested_cohorts.get(int(race.id))
        current_row = race_stats.get(int(race.id))
        if not cohort_key or not current_row:
            continue

        cohort = cohort_rows.get(cohort_key, [])
        if len(cohort) < minimum_cohort_races:
            continue

        peer_rows = [row for row in cohort if int(row["race_id"]) != int(race.id)]
        if not peer_rows:
            continue

        peer_winner_seconds = [float(row["winner_seconds"]) for row in peer_rows]
        peer_median_seconds = [float(row["median_seconds"]) for row in peer_rows]
        if not peer_winner_seconds or not peer_median_seconds:
            continue

        winner_metric = _build_race_comparison_metric(
            float(current_row["winner_seconds"]),
            peer_winner_seconds,
        )
        median_metric = _build_race_comparison_metric(
            float(current_row["median_seconds"]),
            peer_median_seconds,
        )
        peer_median_baseline = _percentile_seconds(sorted(peer_median_seconds), 0.50)
        speed_index = (
            round((float(current_row["median_seconds"]) / peer_median_baseline) * 100, 1)
            if peer_median_baseline not in {None, 0}
            else None
        )

        speed_data[int(race.id)] = {
            "cohort_label": _race_comparison_label(race),
            "cohort_race_count": len(cohort),
            "finishers_in_race": int(current_row["finishers"]),
            "winner_metric": winner_metric,
            "median_metric": median_metric,
            "median_seconds": float(current_row["median_seconds"]),
            "speed_index": speed_index,
            "speed_delta_percentage": median_metric.delta_from_peer_median_percentage,
            "speed_rank_percentage": median_metric.faster_than_percentage,
        }

    return speed_data


def _attach_race_speed_fields(race_items: List[Race]) -> List[Race]:
    speed_data_by_race_id = _build_race_speed_data(race_items)
    for race in race_items:
        race.median_finish_time = None
        race.finisher_count = None
        race.speed_index = None
        race.speed_delta_percentage = None
        race.speed_rank_percentage = None
        race.speed_cohort_size = None

        speed_data = speed_data_by_race_id.get(int(race.id))
        if not speed_data:
            continue

        race.median_finish_time = _timedelta_from_seconds(speed_data["median_seconds"])
        race.finisher_count = int(speed_data["finishers_in_race"])
        race.speed_index = speed_data["speed_index"]
        race.speed_delta_percentage = speed_data["speed_delta_percentage"]
        race.speed_rank_percentage = speed_data["speed_rank_percentage"]
        race.speed_cohort_size = int(speed_data["cohort_race_count"])

    return race_items


def _winning_time_seconds(value: Optional[timedelta]) -> Optional[float]:
    if value is None:
        return None
    return float(value.total_seconds())


def _sort_race_items(race_items: List[Race], order_by: str) -> List[Race]:
    if order_by == "date_asc":
        race_items.sort(key=lambda race: (race.date, race.id))
    elif order_by == "speed_fastest":
        race_items.sort(
            key=lambda race: (
                race.speed_index is None,
                race.speed_index if race.speed_index is not None else float("inf"),
                race.date,
                race.id,
            )
        )
    elif order_by == "speed_slowest":
        race_items.sort(
            key=lambda race: (
                race.speed_index is None,
                -(race.speed_index if race.speed_index is not None else 0.0),
                race.date,
                race.id,
            )
        )
    elif order_by == "winning_fastest":
        race_items.sort(
            key=lambda race: (
                race.winning_time is None,
                _winning_time_seconds(race.winning_time)
                if race.winning_time is not None
                else float("inf"),
                race.date,
                race.id,
            )
        )
    elif order_by == "winning_slowest":
        race_items.sort(
            key=lambda race: (
                race.winning_time is None,
                -(_winning_time_seconds(race.winning_time) or 0.0),
                race.date,
                race.id,
            )
        )
    else:
        race_items.sort(key=lambda race: (race.date, race.id), reverse=True)

    return race_items


def _build_race_comparison(
    race: Race,
    finished_seconds: List[float],
    gender: Optional[str] = None,
) -> Optional[RaceComparisonSchema]:
    if not finished_seconds:
        return None

    speed_data = _build_race_speed_data([race], gender=gender).get(int(race.id))
    if not speed_data:
        return None

    return RaceComparisonSchema(
        cohort_label=str(speed_data["cohort_label"]),
        cohort_race_count=int(speed_data["cohort_race_count"]),
        finishers_in_race=int(speed_data["finishers_in_race"]),
        gender_label=_race_comparison_gender_label(gender),
        winner=speed_data["winner_metric"],
        median=speed_data["median_metric"],
    )


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
def search_races(
    request,
    q: Optional[str] = None,
    race_type: Optional[str] = None,
    surface_type: Optional[str] = None,
    require_speed_index: bool = False,
    order_by: str = "date_desc",
    limit: int = 20,
):
    """Search races by name, description, or location"""
    safe_limit = max(1, min(limit, 100))
    queryset = _public_races()

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q) |
            Q(organizer__icontains=q)
        )
    if race_type:
        queryset = queryset.filter(race_type=race_type)
    if surface_type:
        queryset = queryset.filter(surface_type=surface_type)

    race_items = list(
        _with_winning_time(queryset)
    )
    _attach_race_speed_fields(race_items)

    if require_speed_index:
        race_items = [
            race for race in race_items
            if race.speed_index is not None
        ]

    _sort_race_items(race_items, order_by)
    return race_items[:safe_limit]


@router.get("/events/latest", response=List[EventSummarySchema])
def list_latest_events(request, limit: int = 12):
    """List latest processed events (newest by event date)."""
    safe_limit = max(1, min(limit, 50))
    placeholder_date = date(2099, 12, 31)
    today = timezone.localdate()

    events = (
        _public_events()
        .filter(races__discipline='running')
        .exclude(date=placeholder_date)
        .annotate(race_count=Count("races", filter=Q(races__discipline='running'), distinct=True))
        .annotate(
            result_count=Count(
                "races__results",
                filter=Q(races__discipline='running'),
                distinct=True,
            )
        )
        .order_by("-date", "-id")
        .distinct()[:safe_limit]
    )

    response = []
    preview_race_ids: List[int] = []
    preview_race_id_by_event: Dict[int, int] = {}
    for event in events:
        has_results = getattr(event, "result_count", 0) > 0
        preview_race_id = None
        if has_results:
            preview_race_id = (
                _public_races().filter(event_id=event.id, results__isnull=False)
                .order_by("-date", "-id")
                .values_list("id", flat=True)
                .first()
            )
        if preview_race_id:
            preview_race_id_by_event[event.id] = preview_race_id
            preview_race_ids.append(preview_race_id)

    winning_time_by_race_id = _get_winning_time_by_race_ids(preview_race_ids)

    for event in events:
        preview_race_id = preview_race_id_by_event.get(event.id)
        response.append(
            {
                "id": event.id,
                "name": event.name,
                "date": event.date,
                "discipline": event.discipline,
                "winning_time": winning_time_by_race_id.get(preview_race_id) if preview_race_id else None,
                "source": event.source,
                "race_count": getattr(event, "race_count", 0),
                "result_count": getattr(event, "result_count", 0),
                "has_results": getattr(event, "result_count", 0) > 0,
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
    queryset = _public_races()
    
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


@router.get("/browse", response=PaginatedRaceListSchema)
def browse_races(
    request,
    q: Optional[str] = None,
    year: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    race_type: Optional[str] = None,
    surface_type: Optional[str] = None,
    require_speed_index: bool = False,
    order_by: str = "date_desc",
    limit: int = 50,
    offset: int = 0,
):
    """Browse races chronologically with pagination and lightweight filtering."""
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)

    queryset = _public_races()

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(location__icontains=q)
            | Q(organizer__icontains=q)
        )
    if year:
        queryset = queryset.filter(date__year=year)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    if race_type:
        queryset = queryset.filter(race_type=race_type)
    if surface_type:
        queryset = queryset.filter(surface_type=surface_type)

    race_items = list(_with_winning_time(queryset))
    _attach_race_speed_fields(race_items)
    if require_speed_index:
        race_items = [
            race for race in race_items
            if race.speed_index is not None
        ]

    _sort_race_items(race_items, order_by)
    total = len(race_items)

    items = race_items[safe_offset:safe_offset + safe_limit]

    return PaginatedRaceListSchema(
        items=items,
        total=total,
        limit=safe_limit,
        offset=safe_offset,
        has_next=(safe_offset + safe_limit) < total,
        has_previous=safe_offset > 0,
    )


@router.get("/{race_id}/event-races", response=List[RaceSchema])
def list_event_races(request, race_id: int, limit: int = 20):
    """List other races that belong to the same event as the selected race."""
    race = get_object_or_404(_public_races(), id=race_id)
    if not race.event_id:
        return []

    safe_limit = max(1, min(limit, 50))
    return (
        _public_races().filter(event_id=race.event_id)
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
    return get_object_or_404(_public_races(), id=race_id)


@router.post("/{race_id}/correction-suggestions", response=RaceCorrectionSuggestionSchema)
def create_race_correction_suggestion(
    request,
    race_id: int,
    payload: RaceCorrectionSuggestionCreateSchema,
):
    race = get_object_or_404(_public_races(), id=race_id)
    suggestion = RaceCorrectionSuggestion(
        race=race,
        current_surface_type=race.surface_type,
        current_distance_km=race.distance_km,
        current_discipline=race.discipline,
        current_race_type=race.race_type,
        suggested_surface_type=(payload.suggested_surface_type or "").strip(),
        suggested_distance_km=payload.suggested_distance_km,
        suggested_discipline=(payload.suggested_discipline or "").strip(),
        suggested_race_type=(payload.suggested_race_type or "").strip(),
        comment=(payload.comment or "").strip(),
        submitter_name=(payload.submitter_name or "").strip(),
        submitter_email=(payload.submitter_email or "").strip(),
    )
    try:
        suggestion.save()
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, "messages", None) else "Invalid correction suggestion."
        return JsonResponse({"detail": message}, status=400)
    return suggestion


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
    race = get_object_or_404(_public_races(), id=race_id)
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
        Q(results__race__discipline='running') | Q(canonical_aliases__is_active=True)
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
    
    race_history_results = list(
        runner.get_race_history()
        .filter(race__discipline='running')
    )
    race_history = []
    for result in race_history_results:
        race_history.append(
            {
                'race_id': result.race.id,
                'event_name': result.race.event.name if result.race.event else 'Unknown Event',
                'race_name': result.race.name,
                'race_date': result.race.date,
                'distance_km': result.race.distance_km,
                'discipline': result.race.discipline,
                'surface_type': result.race.surface_type,
                'location': result.race.location,
                'finish_time': result.finish_time,
                'status': result.status,
                'bib_number': result.bib_number,
                'club': result.club,
                'splits': [
                    {
                        'name': split.split_name,
                        'distance_km': split.distance_km,
                        'time': split.split_time,
                    }
                    for split in result.splits.all()
                ],
            }
        )
    
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


@router.get("/{race_id}/stats", response=RaceStatsSchema)
def get_race_stats(request, race_id: int, gender: Optional[str] = None):
    """Get aggregate MVP statistics for a race."""
    race = get_object_or_404(_public_races(), id=race_id)
    queryset = race.results.select_related("runner").all()
    if gender and gender.upper() in {"F", "M"}:
        queryset = queryset.filter(runner__gender=gender.upper())
    results = list(queryset)

    total_results = len(results)
    status_counts = {"finished": 0, "dnf": 0, "dns": 0, "dq": 0}

    finished_results = []
    for result in results:
        status = (result.status or "finished").strip().lower()
        if status not in status_counts:
            status = "finished"
        status_counts[status] += 1
        if status == "finished" and result.finish_time is not None:
            finished_results.append(result)

    finished_seconds = sorted(
        float(result.finish_time.total_seconds())
        for result in finished_results
        if result.finish_time is not None
    )

    winner_seconds = finished_seconds[0] if finished_seconds else None
    average_seconds = (
        (sum(finished_seconds) / len(finished_seconds))
        if finished_seconds
        else None
    )
    time_stats = RaceTimeStatsSchema(
        winner=_timedelta_from_seconds(winner_seconds),
        average=_timedelta_from_seconds(average_seconds),
        p10=_timedelta_from_seconds(_percentile_seconds(finished_seconds, 0.10)),
        p25=_timedelta_from_seconds(_percentile_seconds(finished_seconds, 0.25)),
        p50=_timedelta_from_seconds(_percentile_seconds(finished_seconds, 0.50)),
        p75=_timedelta_from_seconds(_percentile_seconds(finished_seconds, 0.75)),
        p90=_timedelta_from_seconds(_percentile_seconds(finished_seconds, 0.90)),
    )

    thresholds = _sub_x_thresholds_for_race(race)
    bucket_counts = [0 for _ in range(len(thresholds) + 1)]
    for seconds in finished_seconds:
        minutes = seconds / 60.0
        bucket_index = len(thresholds)
        for idx, threshold in enumerate(thresholds):
            if minutes < threshold:
                bucket_index = idx
                break
        bucket_counts[bucket_index] += 1

    sub_x_buckets = []
    for idx, count in enumerate(bucket_counts):
        lower = None if idx == 0 else thresholds[idx - 1]
        upper = thresholds[idx] if idx < len(thresholds) else None
        sub_x_buckets.append(
            RaceTimeBucketSchema(
                label=_bucket_label(lower, upper),
                count=count,
                percentage=round((count / len(finished_seconds) * 100), 1) if finished_seconds else 0.0,
            )
        )

    gender_stats = {
        "F": {"label": "Konur", "total": 0, "finished": 0, "dnf": 0, "dns": 0, "dq": 0},
        "M": {"label": "Karlar", "total": 0, "finished": 0, "dnf": 0, "dns": 0, "dq": 0},
        "U": {"label": "Óþekkt", "total": 0, "finished": 0, "dnf": 0, "dns": 0, "dq": 0},
    }

    age_stats: Dict[str, Dict[str, object]] = {}
    club_stats: Dict[str, Dict[str, object]] = {}

    for result in results:
        status = (result.status or "finished").strip().lower()
        if status not in status_counts:
            status = "finished"

        runner_gender = (result.runner.gender if result.runner else "") or ""
        gender_code = runner_gender if runner_gender in {"F", "M"} else "U"
        gender_row = gender_stats[gender_code]
        gender_row["total"] += 1
        gender_row[status] += 1

        age_value = None
        if result.runner and result.runner.birth_year and race.date:
            age_value = race.date.year - int(result.runner.birth_year)
        elif result.age:
            age_value = int(result.age)
        if age_value is not None and 5 <= age_value <= 120:
            band = _age_band_label(age_value)
            band_row = age_stats.setdefault(
                band,
                {"label": band, "total": 0, "finished": 0, "finished_seconds": []},
            )
            band_row["total"] += 1
            if status == "finished" and result.finish_time is not None:
                band_row["finished"] += 1
                band_row["finished_seconds"].append(float(result.finish_time.total_seconds()))

        if status == "finished" and result.finish_time is not None:
            club_name = (result.club or "").strip()
            if club_name and club_name not in {"-", "--"}:
                club_key = club_name.casefold()
                club_row = club_stats.setdefault(
                    club_key,
                    {"club": club_name, "finishers": 0, "total_seconds": 0.0, "finished_seconds": []},
                )
                club_row["finishers"] += 1
                finish_seconds = float(result.finish_time.total_seconds())
                club_row["total_seconds"] += finish_seconds
                club_row["finished_seconds"].append(finish_seconds)

    gender_breakdown = [
        RaceGenderStatsSchema(
            code=code,
            label=data["label"],
            total=int(data["total"]),
            finished=int(data["finished"]),
            dnf=int(data["dnf"]),
            dns=int(data["dns"]),
            dq=int(data["dq"]),
        )
        for code, data in [("F", gender_stats["F"]), ("M", gender_stats["M"]), ("U", gender_stats["U"])]
    ]

    age_order = ["Undir 20", "20-29", "30-39", "40-49", "50-59", "60+"]
    age_breakdown = []
    for label in age_order:
        data = age_stats.get(label)
        if not data:
            continue
        finished_seconds_for_band = sorted(data["finished_seconds"])
        median_seconds = _percentile_seconds(finished_seconds_for_band, 0.50)
        average_seconds = (
            (sum(finished_seconds_for_band) / len(finished_seconds_for_band))
            if finished_seconds_for_band
            else None
        )
        age_breakdown.append(
            RaceAgeBandStatsSchema(
                label=label,
                total=int(data["total"]),
                finished=int(data["finished"]),
                median_time=_timedelta_from_seconds(median_seconds),
                average_time=_timedelta_from_seconds(average_seconds),
            )
        )

    club_leaderboard_rows = []
    for club in club_stats.values():
        finished_seconds_for_club = sorted(club["finished_seconds"])
        median_seconds = _percentile_seconds(finished_seconds_for_club, 0.50)
        avg_seconds = (
            float(club["total_seconds"]) / int(club["finishers"])
            if club["finishers"]
            else None
        )
        club_leaderboard_rows.append(
            RaceClubStatsSchema(
                club=str(club["club"]),
                finishers=int(club["finishers"]),
                median_time=_timedelta_from_seconds(median_seconds),
                average_time=_timedelta_from_seconds(avg_seconds),
            )
        )

    club_leaderboard_rows.sort(
        key=lambda row: (
            -row.finishers,
            row.average_time.total_seconds() if row.average_time else float("inf"),
            row.club.casefold(),
        )
    )

    comparison = _build_race_comparison(
        race=race,
        finished_seconds=finished_seconds,
        gender=gender,
    )

    return RaceStatsSchema(
        race_id=race.id,
        total_results=total_results,
        finished=status_counts["finished"],
        dnf=status_counts["dnf"],
        dns=status_counts["dns"],
        dq=status_counts["dq"],
        finish_rate=round((status_counts["finished"] / total_results) * 100, 1) if total_results else 0.0,
        time_stats=time_stats,
        sub_x_buckets=sub_x_buckets,
        gender_breakdown=gender_breakdown,
        age_breakdown=age_breakdown,
        club_leaderboard=club_leaderboard_rows[:10],
        comparison=comparison,
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
    race = get_object_or_404(_public_races(), id=race_id)
    status_priority = Case(
        When(status='finished', then=0),
        default=1,
        output_field=IntegerField(),
    )
    queryset = (
        race.results
        .select_related('runner')
        .prefetch_related('splits')
        .order_by(status_priority, 'finish_time', 'id')
    )

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
                splits=[
                    {
                        "name": split.split_name,
                        "distance_km": split.distance_km,
                        "time": split.split_time,
                    }
                    for split in result.splits.all()
                ],
                status=result.status,
            )
        )

    return rows

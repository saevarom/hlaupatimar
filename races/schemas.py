from ninja import Schema
from datetime import date, datetime, timedelta
from typing import Optional, List
from decimal import Decimal


class RunnerSchema(Schema):
    id: int
    stable_id: Optional[str] = None
    name: str
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    nationality: str = "ISL"
    created_at: datetime
    updated_at: datetime


class RunnerSearchSchema(Schema):
    id: int
    stable_id: Optional[str] = None
    name: str
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    nationality: str = "ISL"
    total_races: int


class SplitDetailSchema(Schema):
    name: str
    distance_km: Optional[float] = None
    time: timedelta


class RaceHistorySchema(Schema):
    race_id: int
    event_name: str
    race_name: str
    race_date: date
    distance_km: float
    discipline: str = "unknown"
    surface_type: str = "unknown"
    location: str
    finish_time: timedelta
    status: str
    bib_number: Optional[str] = None
    club: Optional[str] = None
    splits: List[SplitDetailSchema]


class RunnerDetailSchema(Schema):
    id: int
    stable_id: Optional[str] = None
    name: str
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    nationality: str = "ISL"
    created_at: datetime
    updated_at: datetime
    total_races: int
    race_history: List[RaceHistorySchema]


class RaceResultRowSchema(Schema):
    id: int
    race_id: int
    position: int
    runner_id: Optional[int] = None
    runner_stable_id: Optional[str] = None
    runner_name: str
    gender: Optional[str] = None
    birth_year: Optional[int] = None
    bib_number: Optional[str] = None
    club: Optional[str] = None
    finish_time: timedelta
    chip_time: Optional[timedelta] = None
    time_behind: Optional[timedelta] = None
    splits: List[SplitDetailSchema] = []
    status: str


class RaceTimeStatsSchema(Schema):
    winner: Optional[timedelta] = None
    average: Optional[timedelta] = None
    p10: Optional[timedelta] = None
    p25: Optional[timedelta] = None
    p50: Optional[timedelta] = None
    p75: Optional[timedelta] = None
    p90: Optional[timedelta] = None


class RaceTimeBucketSchema(Schema):
    label: str
    count: int
    percentage: float


class RaceGenderStatsSchema(Schema):
    code: str
    label: str
    total: int
    finished: int
    dnf: int
    dns: int
    dq: int


class RaceAgeBandStatsSchema(Schema):
    label: str
    total: int
    finished: int
    median_time: Optional[timedelta] = None
    average_time: Optional[timedelta] = None


class RaceClubStatsSchema(Schema):
    club: str
    finishers: int
    median_time: Optional[timedelta] = None
    average_time: Optional[timedelta] = None


class RaceComparisonMetricSchema(Schema):
    current: Optional[timedelta] = None
    peer_median: Optional[timedelta] = None
    rank: Optional[int] = None
    faster_than_percentage: Optional[float] = None
    delta_from_peer_median_percentage: Optional[float] = None


class RaceComparisonSchema(Schema):
    cohort_label: str
    cohort_race_count: int
    finishers_in_race: int
    gender_label: Optional[str] = None
    winner: RaceComparisonMetricSchema
    median: RaceComparisonMetricSchema


class RaceStatsSchema(Schema):
    race_id: int
    total_results: int
    finished: int
    dnf: int
    dns: int
    dq: int
    finish_rate: float
    time_stats: RaceTimeStatsSchema
    sub_x_buckets: List[RaceTimeBucketSchema]
    gender_breakdown: List[RaceGenderStatsSchema]
    age_breakdown: List[RaceAgeBandStatsSchema]
    club_leaderboard: List[RaceClubStatsSchema]
    comparison: Optional[RaceComparisonSchema] = None


class EventSummarySchema(Schema):
    id: int
    name: str
    date: date
    discipline: str = "unknown"
    winning_time: Optional[timedelta] = None
    source: str
    race_count: int
    result_count: int
    has_results: bool
    is_upcoming: bool
    preview_race_id: Optional[int] = None


class RaceSchema(Schema):
    id: int
    name: str
    description: Optional[str] = None
    race_type: str
    date: date
    discipline: str = "unknown"
    winning_time: Optional[timedelta] = None
    median_finish_time: Optional[timedelta] = None
    finisher_count: Optional[int] = None
    speed_index: Optional[float] = None
    speed_delta_percentage: Optional[float] = None
    speed_rank_percentage: Optional[float] = None
    speed_cohort_size: Optional[int] = None
    location: str
    distance_km: float
    surface_type: str = "unknown"
    elevation_gain_m: int = 0
    max_participants: Optional[int] = None
    registration_url: Optional[str] = None
    official_website: Optional[str] = None
    organizer: Optional[str] = None
    entry_fee: Optional[Decimal] = None
    currency: str = "ISK"
    created_at: datetime
    updated_at: datetime
    source_url: Optional[str] = None
    results_url: Optional[str] = None


class PaginatedRaceListSchema(Schema):
    items: List[RaceSchema]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_previous: bool


class RaceCreateSchema(Schema):
    name: str
    description: Optional[str] = None
    race_type: str
    date: date
    location: str
    distance_km: float
    surface_type: Optional[str] = None
    elevation_gain_m: int = 0
    max_participants: Optional[int] = None
    registration_url: Optional[str] = None
    official_website: Optional[str] = None
    organizer: Optional[str] = None
    entry_fee: Optional[Decimal] = None
    currency: str = "ISK"
    source_url: Optional[str] = None
    results_url: Optional[str] = None


class RaceCorrectionSuggestionCreateSchema(Schema):
    suggested_surface_type: Optional[str] = None
    suggested_distance_km: Optional[float] = None
    suggested_discipline: Optional[str] = None
    suggested_race_type: Optional[str] = None
    comment: Optional[str] = None
    submitter_name: Optional[str] = None
    submitter_email: Optional[str] = None


class RaceCorrectionSuggestionSchema(Schema):
    id: int
    race_id: int
    status: str
    comment: str = ""
    submitter_name: str = ""
    submitter_email: str = ""
    suggested_surface_type: str = ""
    suggested_distance_km: Optional[float] = None
    suggested_discipline: str = ""
    suggested_race_type: str = ""
    created_at: datetime


class ResultSchema(Schema):
    id: int
    race_id: int
    bib_number: Optional[str] = None
    participant_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    nationality: str = "ISL"
    club: Optional[str] = None
    finish_time: timedelta
    gun_time: Optional[timedelta] = None
    overall_place: int
    gender_place: Optional[int] = None
    age_group_place: Optional[int] = None
    status: str = "finished"
    created_at: datetime
    updated_at: datetime


class ResultCreateSchema(Schema):
    bib_number: Optional[str] = None
    participant_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    nationality: str = "ISL"
    club: Optional[str] = None
    finish_time: timedelta
    gun_time: Optional[timedelta] = None
    overall_place: int
    gender_place: Optional[int] = None
    age_group_place: Optional[int] = None
    status: str = "finished"


class SplitSchema(Schema):
    id: int
    result_id: int
    distance_km: float
    split_time: timedelta
    cumulative_time: timedelta


class SplitCreateSchema(Schema):
    distance_km: float
    split_time: timedelta
    cumulative_time: timedelta


class RaceListFilterSchema(Schema):
    race_type: Optional[str] = None
    location: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    distance_min: Optional[float] = None
    distance_max: Optional[float] = None


class PaginationSchema(Schema):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[dict]


class ScrapingResultSchema(Schema):
    """Schema for scraping operation results"""
    success: bool
    message: str
    scraped: int = 0
    saved: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    races: Optional[List[RaceSchema]] = None


class HTMLContentSchema(Schema):
    """Schema for HTML content input"""
    html_content: str
    source_url: Optional[str] = ""
    save_to_db: bool = False
    overwrite_existing: bool = False

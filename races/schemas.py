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
    event_name: str
    race_name: str
    race_date: date
    distance_km: float
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


class RaceSchema(Schema):
    id: int
    name: str
    description: Optional[str] = None
    race_type: str
    date: date
    location: str
    distance_km: float
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


class RaceCreateSchema(Schema):
    name: str
    description: Optional[str] = None
    race_type: str
    date: date
    location: str
    distance_km: float
    elevation_gain_m: int = 0
    max_participants: Optional[int] = None
    registration_url: Optional[str] = None
    official_website: Optional[str] = None
    organizer: Optional[str] = None
    entry_fee: Optional[Decimal] = None
    currency: str = "ISK"
    source_url: Optional[str] = None
    results_url: Optional[str] = None


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

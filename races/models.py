import base64
import hashlib
import re
import unicodedata

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


# Source website choices - used by both Event and Race models
SOURCE_CHOICES = [
    ('timataka.net', 'Timataka.net'),
    ('corsa.is', 'Corsa.is'),
]

RACE_SURFACE_TYPES = [
    ('road', 'Road'),
    ('trail', 'Trail'),
    ('mixed', 'Mixed'),
    ('unknown', 'Unknown'),
]


class Runner(models.Model):
    """Model representing a unique runner/participant"""
    
    name = models.CharField(max_length=200)
    stable_id = models.CharField(max_length=16, unique=True, editable=False, null=True, blank=True)
    birth_year = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2020)])
    gender = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')], blank=True)
    nationality = models.CharField(max_length=3, default='ISL', help_text="ISO 3166-1 alpha-3 country code")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['name', 'birth_year']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['birth_year']),
            models.Index(fields=['name', 'birth_year']),
        ]

    @staticmethod
    def build_stable_id(name: str, birth_year: int | None, gender: str | None) -> str:
        """Generate a deterministic ID from name, birth year, and gender."""
        normalized_name = re.sub(r'\s+', ' ', (name or '').strip()).casefold()
        normalized_gender = (gender or '').strip().upper()
        birth_year_value = str(birth_year) if birth_year else ''
        raw = f"{normalized_name}|{birth_year_value}|{normalized_gender}"
        digest = hashlib.sha256(raw.encode('utf-8')).digest()
        token = base64.b32encode(digest).decode('ascii').rstrip('=')
        return f"rnr_{token[:12].lower()}"

    def save(self, *args, **kwargs):
        if self.birth_year:
            computed_id = self.build_stable_id(self.name, self.birth_year, self.gender)
            if self.stable_id != computed_id:
                conflict = Runner.objects.filter(stable_id=computed_id).exclude(pk=self.pk).exists()
                if conflict:
                    self.stable_id = None
                else:
                    self.stable_id = computed_id
        else:
            self.stable_id = None
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.birth_year:
            return f"{self.name} ({self.birth_year})"
        return self.name

    def get_canonical_runner(self):
        alias_query = RunnerAlias.objects.filter(is_active=True)
        conditions = models.Q(source_runner=self) | models.Q(alias_runner_id=self.id)
        if self.stable_id:
            conditions |= models.Q(alias_stable_id=self.stable_id)
        alias = alias_query.filter(conditions).select_related('canonical_runner').first()
        return alias.canonical_runner if alias else self

    def get_profile_runner_ids(self):
        canonical = self.get_canonical_runner()
        runner_ids = {canonical.id}
        alias_rows = list(
            RunnerAlias.objects.filter(
                canonical_runner=canonical,
                is_active=True,
            ).values('source_runner_id', 'alias_runner_id', 'alias_stable_id')
        )

        alias_stable_ids = []
        for alias in alias_rows:
            source_runner_id = alias.get('source_runner_id')
            alias_runner_id = alias.get('alias_runner_id')
            alias_stable_id = alias.get('alias_stable_id')
            if source_runner_id:
                runner_ids.add(source_runner_id)
            if alias_runner_id:
                runner_ids.add(alias_runner_id)
            if alias_stable_id:
                alias_stable_ids.append(alias_stable_id)

        if alias_stable_ids:
            linked_ids = Runner.objects.filter(stable_id__in=alias_stable_ids).values_list('id', flat=True)
            runner_ids.update(linked_ids)

        return list(runner_ids)
    
    def get_race_history(self):
        """
        Returns all race results for this runner, ordered by race date.
        
        Returns:
            QuerySet of Result objects with prefetched race, event, and splits data,
            ordered by race date (oldest first), then by race name for same-day races.
        """
        return Result.objects.filter(
            runner_id__in=self.get_profile_runner_ids()
        ).select_related(
            'race__event',
            'runner',
        ).prefetch_related(
            'splits'
        ).order_by('race__date', 'race__name')
    
    def get_race_history_summary(self):
        """
        Returns a summary of all race results for this runner.
        
        Returns:
            List of dictionaries containing race and result information.
            Each dictionary contains:
            - event_name: Name of the event
            - race_name: Name of the specific race
            - race_date: Date of the race
            - distance_km: Race distance in kilometers
            - location: Race location
            - finish_time: Runner's finish time
            - status: Result status (Finished, DNF, etc.)
            - bib_number: Runner's bib number
            - club: Runner's club/team
            - splits: List of split times with name, distance, and time
        """
        results = self.get_race_history()
        summary = []
        
        for result in results:
            race_data = {
                'race_id': result.race.id,
                'event_name': result.race.event.name if result.race.event else 'Unknown Event',
                'race_name': result.race.name,
                'race_date': result.race.date,
                'distance_km': result.race.distance_km,
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
                        'time': split.split_time
                    }
                    for split in result.splits.all()
                ]
            }
            summary.append(race_data)
        
        return summary


class RunnerAlias(models.Model):
    """
    Alias mapping to resolve old/duplicate runner identifiers to a canonical runner profile.
    """

    alias_stable_id = models.CharField(max_length=16, unique=True, db_index=True)
    alias_runner_id = models.IntegerField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Legacy runner numeric ID, if applicable.",
    )
    source_runner = models.ForeignKey(
        Runner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_aliases',
        help_text="Linked duplicate profile (can be null after merge/delete).",
    )
    canonical_runner = models.ForeignKey(
        Runner,
        on_delete=models.CASCADE,
        related_name='canonical_aliases',
        help_text="Default profile this alias should resolve to.",
    )
    reason = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['alias_stable_id']
        indexes = [
            models.Index(fields=['canonical_runner', 'is_active']),
            models.Index(fields=['source_runner', 'is_active']),
        ]

    def __str__(self):
        return (
            f"{self.alias_stable_id} -> "
            f"{self.canonical_runner.stable_id or self.canonical_runner_id}"
        )


def _normalize_surface_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', (value or '').casefold())
    return ''.join(char for char in normalized if not unicodedata.combining(char))


class RaceSurfaceKeyword(models.Model):
    """
    Dictionary rule for race surface classification.

    Example:
    - snippet: "tindahlaupid"
    - surface_type: "trail"
    """

    snippet = models.CharField(
        max_length=120,
        help_text="Word or text snippet to match against race name/description/location.",
    )
    normalized_snippet = models.CharField(max_length=120, unique=True, editable=False, db_index=True)
    surface_type = models.CharField(max_length=20, choices=RACE_SURFACE_TYPES, db_index=True)
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Lower value means higher priority when multiple rules match.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'normalized_snippet']
        indexes = [
            models.Index(fields=['is_active', 'priority']),
            models.Index(fields=['surface_type']),
        ]

    @classmethod
    def get_active_rules(cls) -> list[tuple[str, str]]:
        return list(
            cls.objects.filter(is_active=True)
            .order_by('priority', 'id')
            .values_list('normalized_snippet', 'surface_type')
        )

    def save(self, *args, **kwargs):
        self.normalized_snippet = _normalize_surface_text(self.snippet).strip()
        if not self.normalized_snippet:
            raise ValidationError("snippet must contain at least one alphanumeric character")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.snippet} -> {self.surface_type}"


class RaceDistanceKeyword(models.Model):
    """
    Dictionary rule for race distance classification by name/description/location.

    Example:
    - snippet: "Powerade"
    - distance_km: 10.0
    """

    snippet = models.CharField(
        max_length=120,
        help_text="Word or text snippet to match against race name/description/location.",
    )
    normalized_snippet = models.CharField(max_length=120, unique=True, editable=False, db_index=True)
    distance_km = models.FloatField(validators=[MinValueValidator(0.1)])
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Lower value means higher priority when multiple rules match.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'normalized_snippet']
        indexes = [
            models.Index(fields=['is_active', 'priority']),
            models.Index(fields=['distance_km']),
        ]

    @classmethod
    def get_active_rules(cls) -> list[tuple[str, float]]:
        return list(
            cls.objects.filter(is_active=True)
            .order_by('priority', 'id')
            .values_list('normalized_snippet', 'distance_km')
        )

    def save(self, *args, **kwargs):
        self.normalized_snippet = _normalize_surface_text(self.snippet).strip()
        if not self.normalized_snippet:
            raise ValidationError("snippet must contain at least one alphanumeric character")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.snippet} -> {self.distance_km:g} km"


class Event(models.Model):
    """Model representing a racing event (found on timataka.net homepage)"""
    
    name = models.CharField(max_length=200, help_text="Event name as found on timataka.net homepage")
    date = models.DateField(help_text="Event date parsed from homepage")
    url = models.URLField(unique=True, help_text="URL to the event page on timataka.net")
    
    # Processing status
    STATUS_CHOICES = [
        ('discovered', 'Discovered'),
        ('processed', 'Processed'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='discovered')
    last_processed = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    
    # HTML caching
    cached_html = models.TextField(blank=True, help_text="Cached HTML content from the event page")
    html_fetched_at = models.DateTimeField(null=True, blank=True, help_text="When the HTML was last fetched")
    
    # Source tracking
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='timataka.net', help_text="Source website")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['url']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.date}"


class Race(models.Model):
    """Model representing a running race/competition"""
    
    RACE_TYPES = [
        ('marathon', 'Marathon'),
        ('half_marathon', 'Half Marathon'),
        ('10k', '10K'),
        ('5k', '5K'),
        ('trail', 'Trail Run'),
        ('ultra', 'Ultra Marathon'),
        ('other', 'Other'),
    ]

    # Link to the event this race belongs to
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='races', null=True, blank=True)
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    race_type = models.CharField(max_length=20, choices=RACE_TYPES)
    date = models.DateField()
    location = models.CharField(max_length=100)
    distance_km = models.FloatField(validators=[MinValueValidator(0.1)])
    elevation_gain_m = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    surface_type = models.CharField(max_length=20, choices=RACE_SURFACE_TYPES, default='unknown', help_text="Road/trail classification", db_index=True)
    max_participants = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    registration_url = models.URLField(blank=True)
    official_website = models.URLField(blank=True)
    organizer = models.CharField(max_length=200, blank=True)
    entry_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='ISK')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='timataka.net', help_text="Source website")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    source_url = models.URLField(blank=True, help_text="URL where this race data was scraped from")
    results_url = models.URLField(blank=True, help_text="URL to the overall race results")
    
    # HTML caching
    cached_html = models.TextField(blank=True, help_text="Cached HTML content from the results page")
    html_fetched_at = models.DateTimeField(null=True, blank=True, help_text="When the HTML was last fetched")
    
    # Error tracking
    has_server_error = models.BooleanField(default=False, help_text="True if the race results page returns server errors (500, 404, etc.)")
    last_error_code = models.IntegerField(null=True, blank=True, help_text="Last HTTP error code encountered")
    last_error_message = models.TextField(blank=True, help_text="Last error message encountered")
    error_count = models.IntegerField(default=0, help_text="Number of consecutive errors encountered")
    last_error_at = models.DateTimeField(null=True, blank=True, help_text="When the last error occurred")
    
    class Meta:
        ordering = ['date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['race_type']),
            models.Index(fields=['location']),
        ]

    @staticmethod
    def infer_distance_from_rules(
        name: str = '',
        description: str = '',
        location: str = '',
        distance_rules: list[tuple[str, float]] | None = None,
    ) -> float | None:
        text = _normalize_surface_text(f"{name} {description} {location}")

        if distance_rules is None:
            try:
                distance_rules = RaceDistanceKeyword.get_active_rules()
            except Exception:
                distance_rules = []

        for snippet, distance_km in distance_rules:
            if snippet and snippet in text:
                return float(distance_km)
        return None

    @staticmethod
    def infer_race_type_from_distance(distance_km: float, current_race_type: str = 'other') -> str:
        distance = float(distance_km or 0.0)
        current = (current_race_type or 'other').strip().lower()
        if distance > 43.5:
            return 'ultra'
        if 41.0 <= distance <= 43.5:
            return 'marathon'
        if 20.0 <= distance <= 22.5:
            return 'half_marathon'
        if 9.0 <= distance <= 11.0:
            return '10k'
        if 4.0 <= distance <= 6.0:
            return '5k'
        return current or 'other'

    @staticmethod
    def infer_surface_type_from_rules(
        name: str = '',
        description: str = '',
        location: str = '',
        surface_rules: list[tuple[str, str]] | None = None,
    ) -> str | None:
        text = _normalize_surface_text(f"{name} {description} {location}")

        if surface_rules is None:
            try:
                surface_rules = RaceSurfaceKeyword.get_active_rules()
            except Exception:
                surface_rules = []

        for snippet, surface_type in surface_rules:
            if snippet and snippet in text:
                return surface_type
        return None

    @staticmethod
    def infer_surface_type(
        race_type: str,
        name: str = '',
        description: str = '',
        location: str = '',
        elevation_gain_m: int = 0,
        distance_km: float = 0.0,
        surface_rules: list[tuple[str, str]] | None = None,
    ) -> str:
        race_type_value = (race_type or '').strip().lower()
        text = _normalize_surface_text(f"{name} {description} {location}")

        matched_surface = Race.infer_surface_type_from_rules(
            name=name,
            description=description,
            location=location,
            surface_rules=surface_rules,
        )
        if matched_surface:
            return matched_surface

        trail_keywords = [
            'trail',
            'fjall',
            'fell',
            'stiga',
            'stigur',
            'utanvega',
            'heidi',
            'backyard',
            'mountain',
            'ultra',
            'fjallahjola',
            'torfaera',
        ]
        road_keywords = [
            'gotu',
            'road',
            'street',
            'city',
            'malbik',
            'hringur',
            'mara',
        ]

        if any(keyword in text for keyword in trail_keywords):
            return 'trail'
        if any(keyword in text for keyword in road_keywords):
            return 'road'

        if race_type_value == 'trail':
            return 'trail'
        if race_type_value in {'5k', '10k', 'half_marathon', 'marathon'}:
            return 'road'

        distance = float(distance_km or 0.0)
        elevation = float(elevation_gain_m or 0.0)
        gain_per_km = (elevation / distance) if distance > 0 else 0.0

        if gain_per_km >= 35:
            return 'trail'
        if gain_per_km >= 15:
            return 'mixed'
        if distance > 0:
            return 'road'

        return 'road'

    def save(self, *args, **kwargs):
        inferred_distance = self.infer_distance_from_rules(
            name=self.name,
            description=self.description,
            location=self.location,
        )
        if inferred_distance and abs(float(self.distance_km or 0.0) - inferred_distance) > 1e-6:
            self.distance_km = inferred_distance
            self.race_type = self.infer_race_type_from_distance(
                inferred_distance,
                current_race_type=self.race_type,
            )

        if not self.surface_type or self.surface_type == 'unknown':
            self.surface_type = self.infer_surface_type(
                race_type=self.race_type,
                name=self.name,
                description=self.description,
                location=self.location,
                elevation_gain_m=self.elevation_gain_m,
                distance_km=self.distance_km,
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.date}"


class Result(models.Model):
    """Model representing a race result for a participant"""
    
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='results')
    runner = models.ForeignKey(Runner, on_delete=models.CASCADE, related_name='results', null=True, blank=True)
    bib_number = models.CharField(max_length=20, blank=True)
    club = models.CharField(max_length=200, blank=True, help_text="Running club or team")
    
    # Legacy fields for migration
    participant_name = models.CharField(max_length=200, blank=True)
    age = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(5), MaxValueValidator(120)])
    nationality = models.CharField(max_length=3, default='ISL', help_text="ISO 3166-1 alpha-3 country code")
    
    # Time results
    finish_time = models.DurationField(help_text="Total race time")
    gun_time = models.DurationField(null=True, blank=True, help_text="Time from gun start")
    chip_time = models.DurationField(null=True, blank=True, help_text="Chip/net time")
    time_behind = models.DurationField(null=True, blank=True, help_text="Time behind winner")
    
    # Status
    STATUS_CHOICES = [
        ('finished', 'Finished'),
        ('dnf', 'Did Not Finish'),
        ('dns', 'Did Not Start'),
        ('dq', 'Disqualified'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='finished')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['finish_time']
        indexes = [
            models.Index(fields=['race', 'finish_time']),
            models.Index(fields=['participant_name']),
            models.Index(fields=['finish_time']),
        ]
    
    def __str__(self):
        if self.runner:
            return f"{self.runner.name} - {self.race.name} ({self.finish_time})"
        return f"{self.participant_name} - {self.race.name} ({self.finish_time})"


class Split(models.Model):
    """Model representing split times during a race"""
    
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name='splits')
    split_name = models.CharField(max_length=100, help_text="Name of the split point (e.g., 'Hafravatn')")
    distance_km = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    split_time = models.DurationField(help_text="Cumulative time from start to this split")
    
    class Meta:
        ordering = ['split_time']
        unique_together = ['result', 'split_name']
    
    def __str__(self):
        return f"{self.result.runner.name} - {self.split_name}: {self.split_time}"

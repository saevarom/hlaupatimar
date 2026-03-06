import base64
import hashlib
import re

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


# Source website choices - used by both Event and Race models
SOURCE_CHOICES = [
    ('timataka.net', 'Timataka.net'),
    ('corsa.is', 'Corsa.is'),
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
    
    def get_race_history(self):
        """
        Returns all race results for this runner, ordered by race date.
        
        Returns:
            QuerySet of Result objects with prefetched race, event, and splits data,
            ordered by race date (oldest first), then by race name for same-day races.
        """
        return self.results.select_related(
            'race__event'
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
                'event_name': result.race.event.name if result.race.event else 'Unknown Event',
                'race_name': result.race.name,
                'race_date': result.race.date,
                'distance_km': result.race.distance_km,
                'location': result.race.location,
                'finish_time': result.finish_time,
                'status': result.get_status_display(),
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

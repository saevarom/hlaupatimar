from django.contrib import admin
from .models import (
    Event,
    Race,
    RaceDistanceKeyword,
    RaceSurfaceKeyword,
    Result,
    Runner,
    RunnerAlias,
    Split,
)


@admin.register(Runner)
class RunnerAdmin(admin.ModelAdmin):
    list_display = ['name', 'birth_year', 'gender', 'nationality']
    list_filter = ['gender', 'nationality', 'birth_year']
    search_fields = ['name']
    ordering = ['name']


@admin.register(RunnerAlias)
class RunnerAliasAdmin(admin.ModelAdmin):
    list_display = [
        'alias_stable_id',
        'alias_runner_id',
        'source_runner',
        'canonical_runner',
        'is_active',
        'updated_at',
    ]
    list_filter = ['is_active']
    search_fields = ['alias_stable_id', 'source_runner__name', 'canonical_runner__name']
    ordering = ['alias_stable_id']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'source', 'status', 'cache_status', 'last_processed', 'created_at']
    list_filter = ['source', 'status', 'date', 'last_processed']
    search_fields = ['name', 'url']
    date_hierarchy = 'date'
    ordering = ['-date']
    readonly_fields = ['created_at', 'updated_at', 'html_fetched_at']
    list_per_page = 50
    
    def cache_status(self, obj):
        """Show cache status"""
        if obj.cached_html:
            return f"Cached ({len(obj.cached_html)} chars)"
        return "Not cached"
    cache_status.short_description = "HTML Cache"


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ['name', 'event', 'date', 'source', 'race_type', 'location', 'distance_km', 'cache_status']
    list_filter = ['source', 'race_type', 'date', 'location', 'event__status', 'event__source']
    search_fields = ['name', 'location', 'organizer', 'event__name']
    date_hierarchy = 'date'
    ordering = ['-date']
    readonly_fields = ['created_at', 'updated_at', 'html_fetched_at']
    
    # Optimize for large datasets
    list_per_page = 50  # Limit items per page
    actions = ['delete_selected']  # Explicitly define actions
    list_select_related = ['event']  # Optimize database queries
    
    def cache_status(self, obj):
        """Show cache status"""
        if obj.cached_html:
            return f"Cached ({len(obj.cached_html)} chars)"
        return "Not cached"
    cache_status.short_description = "HTML Cache"
    
    def get_deleted_objects(self, objs, request):
        """
        Override to limit the number of related objects shown during deletion confirmation.
        This helps prevent the DATA_UPLOAD_MAX_NUMBER_FIELDS error.
        """
        try:
            # Get the standard deletion info
            deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
            
            # If we have too many related objects, truncate the display
            max_display_objects = 100
            if len(deleted_objects) > max_display_objects:
                # Keep first 100 objects and add a summary
                truncated_objects = deleted_objects[:max_display_objects]
                remaining_count = len(deleted_objects) - max_display_objects
                truncated_objects.append(f"... and {remaining_count} more related objects")
                deleted_objects = truncated_objects
            
            return deleted_objects, model_count, perms_needed, protected
        except Exception:
            # Fallback to basic deletion info if there's an error
            return [], {}, set(), []



@admin.register(RaceSurfaceKeyword)
class RaceSurfaceKeywordAdmin(admin.ModelAdmin):
    list_display = ['snippet', 'surface_type', 'priority', 'is_active', 'updated_at']
    list_filter = ['surface_type', 'is_active']
    search_fields = ['snippet', 'notes']
    ordering = ['priority', 'snippet']
    readonly_fields = ['normalized_snippet', 'created_at', 'updated_at']


@admin.register(RaceDistanceKeyword)
class RaceDistanceKeywordAdmin(admin.ModelAdmin):
    list_display = ['snippet', 'distance_km', 'priority', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['snippet', 'notes']
    ordering = ['priority', 'snippet']
    readonly_fields = ['normalized_snippet', 'created_at', 'updated_at']


class RelatedFieldDropdownFilter(admin.SimpleListFilter):
    title = 'Race'  # Filter title displayed in the sidebar
    parameter_name = 'race_id'  # URL parameter name
    template = 'admin/dropdown_filter.html'

    def lookups(self, request, model_admin):
        # Return a list of tuples: (value, human-readable name)
        # These will be the options in the dropdown
        return [(obj.id, str(obj)) for obj in Race.objects.all().order_by('-date')]

    def queryset(self, request, queryset):
        # Filter the queryset based on the selected value
        if self.value():
            return queryset.filter(race__id=self.value())
        return queryset

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['get_participant_name', 'get_gender', 'race', 'finish_time', 'status']
    list_filter = ['status', 'race__source', RelatedFieldDropdownFilter, 'race__date', 'race__race_type', 'runner__gender']
    search_fields = ['runner__name', 'participant_name', 'club']
    ordering = ['race', 'finish_time']
    date_hierarchy = 'race__date'
    list_per_page = 100  # Limit items per page for performance
    list_select_related = ['race', 'runner']  # Optimize database queries
    
    def get_participant_name(self, obj):
        return obj.runner.name if obj.runner else obj.participant_name
    get_participant_name.short_description = 'Participant Name'
    
    def get_gender(self, obj):
        return obj.runner.gender if obj.runner else ''
    get_gender.short_description = 'Gender'
    
    def get_queryset(self, request):
        """Optimize queryset for admin list view"""
        return super().get_queryset(request).select_related('race', 'runner')


@admin.register(Split)
class SplitAdmin(admin.ModelAdmin):
    list_display = ['get_participant_name', 'get_race_name', 'split_name', 'split_time']
    list_filter = ['split_name', 'result__race__date']
    search_fields = ['result__runner__name', 'result__participant_name', 'split_name']
    ordering = ['result', 'split_time']
    list_per_page = 100
    list_select_related = ['result__race', 'result__runner']
    
    def get_participant_name(self, obj):
        return obj.result.runner.name if obj.result.runner else obj.result.participant_name
    get_participant_name.short_description = 'Participant'
    
    def get_race_name(self, obj):
        return obj.result.race.name
    get_race_name.short_description = 'Race'
    
    def get_queryset(self, request):
        """Optimize queryset for admin list view"""
        return super().get_queryset(request).select_related('result__race', 'result__runner')

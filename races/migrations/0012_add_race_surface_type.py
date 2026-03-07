import unicodedata

from django.db import migrations, models


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', (value or '').casefold())
    return ''.join(char for char in normalized if not unicodedata.combining(char))


def _infer_surface_type(race_type, name, description, location, elevation_gain_m, distance_km):
    race_type_value = (race_type or '').strip().lower()
    text = _normalize_text(f"{name or ''} {description or ''} {location or ''}")

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


def populate_surface_types(apps, schema_editor):
    Race = apps.get_model('races', 'Race')
    for race in Race.objects.all().only(
        'id',
        'race_type',
        'name',
        'description',
        'location',
        'elevation_gain_m',
        'distance_km',
    ):
        surface_type = _infer_surface_type(
            race_type=race.race_type,
            name=race.name,
            description=race.description,
            location=race.location,
            elevation_gain_m=race.elevation_gain_m,
            distance_km=race.distance_km,
        )
        Race.objects.filter(id=race.id).update(surface_type=surface_type)


class Migration(migrations.Migration):

    dependencies = [
        ('races', '0011_alter_event_date_alter_event_name_alter_event_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='race',
            name='surface_type',
            field=models.CharField(
                choices=[('road', 'Road'), ('trail', 'Trail'), ('mixed', 'Mixed'), ('unknown', 'Unknown')],
                db_index=True,
                default='unknown',
                help_text='Road/trail classification',
                max_length=20,
            ),
        ),
        migrations.RunPython(populate_surface_types, migrations.RunPython.noop),
    ]

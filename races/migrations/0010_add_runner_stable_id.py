import base64
import hashlib
import re

from django.db import migrations, models


def _build_stable_id(name: str, birth_year: int | None, gender: str | None) -> str:
    normalized_name = re.sub(r'\s+', ' ', (name or '').strip()).casefold()
    normalized_gender = (gender or '').strip().upper()
    birth_year_value = str(birth_year) if birth_year else ''
    raw = f"{normalized_name}|{birth_year_value}|{normalized_gender}"
    digest = hashlib.sha256(raw.encode('utf-8')).digest()
    token = base64.b32encode(digest).decode('ascii').rstrip('=')
    return f"rnr_{token[:12].lower()}"


def populate_stable_ids(apps, schema_editor):
    Runner = apps.get_model('races', 'Runner')
    for runner in Runner.objects.all().only('id', 'name', 'birth_year', 'gender'):
        if runner.birth_year:
            stable_id = _build_stable_id(runner.name, runner.birth_year, runner.gender)
            exists = Runner.objects.filter(stable_id=stable_id).exclude(id=runner.id).exists()
            if not exists:
                Runner.objects.filter(id=runner.id).update(stable_id=stable_id)


class Migration(migrations.Migration):

    dependencies = [
        ('races', '0009_add_source_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='runner',
            name='stable_id',
            field=models.CharField(blank=True, max_length=16, null=True, unique=True, editable=False),
        ),
        migrations.RunPython(populate_stable_ids, migrations.RunPython.noop),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('races', '0012_add_race_surface_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='RaceSurfaceKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('snippet', models.CharField(help_text='Word or text snippet to match against race name/description/location.', max_length=120)),
                ('normalized_snippet', models.CharField(db_index=True, editable=False, max_length=120, unique=True)),
                ('surface_type', models.CharField(choices=[('road', 'Road'), ('trail', 'Trail'), ('mixed', 'Mixed'), ('unknown', 'Unknown')], db_index=True, max_length=20)),
                ('priority', models.PositiveIntegerField(default=100, help_text='Lower value means higher priority when multiple rules match.')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['priority', 'normalized_snippet'],
                'indexes': [
                    models.Index(fields=['is_active', 'priority'], name='races_races_is_acti_0da536_idx'),
                    models.Index(fields=['surface_type'], name='races_races_surface_f0d3b3_idx'),
                ],
            },
        ),
    ]

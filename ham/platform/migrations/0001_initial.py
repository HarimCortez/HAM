from django.db import migrations, models

import ham.platform.ids


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ChurchProfile",
            fields=[
                (
                    "id",
                    ham.platform.ids.UUID7Field(
                        default=ham.platform.ids.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("ham_phone", models.CharField(blank=True, default="", max_length=32)),
                ("ham_email", models.EmailField(blank=True, default="", max_length=254)),
                (
                    "time_zone",
                    models.CharField(default="America/New_York", max_length=64),
                ),
                ("website_url", models.URLField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by_id", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "platform_church_profile",
                "verbose_name": "Church profile",
            },
        ),
    ]

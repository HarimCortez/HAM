from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models

import ham.platform.ids


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("seq", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "id",
                    models.UUIDField(default=ham.platform.ids.uuid7, editable=False, unique=True),
                ),
                ("occurred_at", models.DateTimeField()),
                (
                    "actor_type",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("system", "System"),
                            ("requester", "Requester"),
                        ],
                        max_length=16,
                    ),
                ),
                ("actor_user_id", models.UUIDField(blank=True, null=True)),
                ("acting_as_user_id", models.UUIDField(blank=True, null=True)),
                ("impersonation_id", models.UUIDField(blank=True, null=True)),
                (
                    "actor_roles",
                    ArrayField(
                        models.CharField(max_length=32), blank=True, default=list, size=None
                    ),
                ),
                ("action", models.CharField(max_length=100)),
                ("target_type", models.CharField(max_length=64)),
                ("target_id", models.CharField(max_length=64)),
                ("project_id", models.UUIDField(blank=True, null=True)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("reason", models.TextField(blank=True, default="")),
                ("context", models.JSONField(blank=True, default=dict)),
                ("rules_version", models.CharField(max_length=32)),
            ],
            options={
                "db_table": "audit_event",
                "ordering": ("-seq",),
            },
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["occurred_at"], name="audit_occurred_at_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["actor_user_id", "occurred_at"], name="audit_actor_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["project_id", "occurred_at"], name="audit_project_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ),
    ]

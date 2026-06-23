# Generated manually for BUD-1141 formula IDE state API.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0027_general_query_optimization_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormulaIdeDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("formula_id", models.CharField(default="draft-default", max_length=64, verbose_name="Идентификатор формулы")),
                ("code", models.TextField(blank=True, verbose_name="Код формулы")),
                ("constructor_blocks", models.JSONField(blank=True, default=list, verbose_name="Блоки конструктора")),
                ("is_saved", models.BooleanField(default=True, verbose_name="Черновик сохранён")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="formula_ide_drafts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Черновик IDE формул",
                "verbose_name_plural": "Черновики IDE формул",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="formulaidedraft",
            constraint=models.UniqueConstraint(
                fields=("user", "formula_id"),
                name="uniq_formula_ide_user_key",
            ),
        ),
        migrations.AddIndex(
            model_name="formulaidedraft",
            index=models.Index(fields=["user"], name="idx_formula_ide_user"),
        ),
        migrations.AddIndex(
            model_name="formulaidedraft",
            index=models.Index(fields=["user", "updated_at"], name="idx_formula_ide_user_upd"),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_user_contact_verification"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhoneVerificationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phone", models.CharField(max_length=32, verbose_name="Телефон")),
                ("code_hash", models.CharField(max_length=128, verbose_name="Hash кода")),
                (
                    "attempts_count",
                    models.PositiveSmallIntegerField(
                        default=0,
                        verbose_name="Количество попыток",
                    ),
                ),
                ("expires_at", models.DateTimeField(verbose_name="Действителен до")),
                (
                    "sent_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="Дата отправки",
                    ),
                ),
                (
                    "confirmed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Дата подтверждения",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Дата создания",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="phone_verification_codes",
                        to="users.user",
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Код подтверждения телефона",
                "verbose_name_plural": "Коды подтверждения телефона",
                "ordering": ["-sent_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=~models.Q(phone=""),
                fields=("phone",),
                name="uniq_user_non_empty_phone",
            ),
        ),
        migrations.AddIndex(
            model_name="phoneverificationcode",
            index=models.Index(
                fields=["user", "phone", "confirmed_at"],
                name="idx_phone_verif_user_phone",
            ),
        ),
        migrations.AddIndex(
            model_name="phoneverificationcode",
            index=models.Index(
                fields=["expires_at"],
                name="idx_phone_verif_expires",
            ),
        ),
        migrations.AddIndex(
            model_name="phoneverificationcode",
            index=models.Index(
                fields=["sent_at"],
                name="idx_phone_verif_sent",
            ),
        ),
    ]

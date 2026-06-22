from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_user_app_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=True, verbose_name="Email подтверждён"),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата подтверждения email"),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата последней отправки подтверждения email"),
        ),
        migrations.AddField(
            model_name="user",
            name="phone_verified",
            field=models.BooleanField(default=False, verbose_name="Телефон подтверждён"),
        ),
        migrations.AddField(
            model_name="user",
            name="phone_verified_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата подтверждения телефона"),
        ),
    ]
